"""Loopback-only local TRUSTLENS API and same-origin browser application."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .ingestion import IngestionError, MediaLimits, ProcessingStatus
from .persistence import AnalysisStore, IdempotencyConflict, StoredReportError, default_database_path
from .service import analyze_upload


_STATIC = Path(__file__).with_name("static")
_UPLOAD_LIMIT = MediaLimits().max_file_bytes
_BODY_LIMIT = _UPLOAD_LIMIT + 256 * 1024
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_STATUS_FILTERS = {status.value for status in ProcessingStatus}


class BodyTooLarge(Exception):
    pass


class RequestBoundaryMiddleware:
    """Enforce upload body bounds, same-origin writes, and browser security headers."""

    def __init__(self, app, *, max_body_bytes: int = _BODY_LIMIT):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        method = scope.get("method", "GET").upper()
        if method in {"POST", "PUT", "PATCH", "DELETE"} and b"origin" in headers:
            origin = headers[b"origin"].decode("latin-1")
            host = headers.get(b"host", b"").decode("latin-1").lower()
            try:
                parsed = urlsplit(origin)
            except ValueError:
                await self._json(send, 403, {"error": {"code": "cross_origin_request", "message": "Cross-origin state changes are not allowed."}})
                return
            if parsed.scheme != "http" or parsed.netloc.lower() != host or parsed.path or parsed.query or parsed.fragment:
                await self._json(send, 403, {"error": {"code": "cross_origin_request", "message": "Cross-origin state changes are not allowed."}})
                return
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._too_large(send)
                    return
            except ValueError:
                await self._json(send, 400, {"error": {"code": "invalid_content_length", "message": "Request content length is invalid."}})
                return

        received = 0
        response_started = False

        async def counted_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise BodyTooLarge
            return message

        async def secured_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                response_headers = list(message.get("headers", []))
                response_headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-frame-options", b"DENY"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src blob:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
                    (b"cache-control", b"no-store"),
                ])
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, counted_receive, secured_send)
        except BodyTooLarge:
            if not response_started:
                await self._too_large(send)

    async def _too_large(self, send):
        await self._json(send, 413, {"error": {"code": "request_too_large", "message": f"Request exceeds the {_UPLOAD_LIMIT // (1024 * 1024)} MiB upload limit."}})

    @staticmethod
    async def _json(send, status: int, value: dict[str, Any]):
        body = json.dumps(value).encode("utf-8")
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def _hash_upload(upload: UploadFile) -> str:
    digest = hashlib.sha256()
    upload.file.seek(0)
    for chunk in iter(lambda: upload.file.read(1024 * 1024), b""):
        digest.update(chunk)
    upload.file.seek(0)
    return digest.hexdigest()


def _capabilities() -> dict[str, Any]:
    return {
        "supported_upload_extensions": [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".avi", ".wav", ".mp3"],
        "max_upload_bytes": _UPLOAD_LIMIT,
        "image": {"ingestion": "available", "frequency_descriptor": "available", "trained_detector": "unavailable", "face_detection": "unavailable", "spatial_localization": "unavailable"},
        "video": {"metadata": "available" if shutil.which("ffprobe") else "unavailable", "frame_sampling": "available" if shutil.which("ffmpeg") and shutil.which("ffprobe") else "unavailable", "temporal_measurement": "descriptive_only", "temporal_classifier": "unavailable"},
        "provenance": {"metadata_inspection": "available", "c2pa_verification": "unavailable", "watermark_detection": "unavailable"},
        "fusion": "evidence_preservation_and_limited_conflict_flags_only; no calibrated score aggregation",
        "audio_analysis": "unavailable",
        "source_media_retention": "temporary_only; deleted after analysis",
        "report_persistence": "local_sqlite",
        "authentication": "not_configured; loopback-only single-user app",
    }


def create_app(store: AnalysisStore | None = None) -> FastAPI:
    """Create the application; a store may be injected for isolated tests."""
    app = FastAPI(
        title="TRUSTLENS Local Investigation Workspace",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.add_middleware(RequestBoundaryMiddleware)
    resolved_store = store

    def database() -> AnalysisStore:
        nonlocal resolved_store
        if resolved_store is None:
            resolved_store = AnalysisStore(default_database_path())
        return resolved_store

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Request validation failed. Check the required fields and query parameters."}})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        messages = {404: "The requested resource was not found.", 405: "This method is not supported for the requested resource.", 413: "The request exceeds the configured size limit."}
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": "not_found" if exc.status_code == 404 else "http_error", "message": messages.get(exc.status_code, "The request could not be completed.")}})

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request: Request, exc: sqlite3.Error):
        return JSONResponse(status_code=503, content={"error": {"code": "local_storage_unavailable", "message": "Local analysis storage is unavailable. Check the configured data directory."}})

    @app.exception_handler(StoredReportError)
    async def stored_report_error(request: Request, exc: StoredReportError):
        return JSONResponse(status_code=503, content={"error": {"code": "stored_report_unavailable", "message": "A saved report could not be read because its stored data is invalid."}})

    @app.get("/", include_in_schema=False)
    async def home():
        return FileResponse(_STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    @app.get("/api/health")
    async def health():
        database().stats()
        return {"status": "available", "application": "trustlens-local", "persistence": "available"}

    @app.get("/api/capabilities")
    async def capabilities():
        return _capabilities()

    @app.get("/api/stats")
    async def stats():
        return database().stats()

    @app.post("/api/analyses")
    async def submit_analysis(
        file: UploadFile = File(...),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        if idempotency_key is not None and not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            return JSONResponse(status_code=400, content={"error": {"code": "invalid_idempotency_key", "message": "Idempotency-Key must be 1–128 safe ASCII characters."}})
        try:
            source_hash = await run_in_threadpool(_hash_upload, file)
            if idempotency_key:
                previous = database().find_idempotent(idempotency_key, source_hash)
                if previous is not None:
                    return JSONResponse(status_code=200, content=previous)
            filename = file.filename or "upload"
            try:
                report = await run_in_threadpool(analyze_upload, file.file, filename)
            except IngestionError as exc:
                return JSONResponse(status_code=422, content={"error": {"code": "invalid_media", "message": str(exc)}})
            record, created = await run_in_threadpool(database().create, report.to_dict(), idempotency_key)
            return JSONResponse(status_code=201 if created else 200, content=record)
        except IdempotencyConflict as exc:
            return JSONResponse(status_code=409, content={"error": {"code": "idempotency_conflict", "message": str(exc)}})
        except (OSError, sqlite3.Error):
            return JSONResponse(status_code=503, content={"error": {"code": "local_storage_unavailable", "message": "Local analysis storage is unavailable. Check the configured data directory."}})
        finally:
            await file.close()

    @app.get("/api/analyses")
    async def list_analyses(
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        status: str | None = None,
        media_type: str | None = Query(default=None, alias="media_type"),
        q: str | None = Query(default=None, max_length=128),
    ):
        if status and status not in _STATUS_FILTERS:
            return JSONResponse(status_code=422, content={"error": {"code": "invalid_status_filter", "message": "Status filter is not recognized."}})
        if media_type and media_type not in {"image", "video", "audio"}:
            return JSONResponse(status_code=422, content={"error": {"code": "invalid_media_filter", "message": "Media type filter is not recognized."}})
        return database().list(limit=limit, offset=offset, status=status, media_type=media_type, query=q)

    @app.get("/api/analyses/{analysis_id}")
    async def get_analysis(analysis_id: str):
        record = database().get(analysis_id)
        if record is None:
            return JSONResponse(status_code=404, content={"error": {"code": "analysis_not_found", "message": "The requested analysis was not found."}})
        return record

    @app.get("/api/analyses/{analysis_id}/evidence")
    async def get_evidence(analysis_id: str):
        record = database().get(analysis_id)
        if record is None:
            return JSONResponse(status_code=404, content={"error": {"code": "analysis_not_found", "message": "The requested analysis was not found."}})
        report = record["report"]
        result = report.get("analysis", {}).get("result") or {}
        return {"analysis_id": analysis_id, "processing_status": report["processing_status"], "evidence": result.get("evidence", []), "frames": result.get("frames", []), "temporal_analysis": result.get("temporal_analysis"), "provenance": result.get("provenance"), "fusion": report.get("fusion"), "limitations": report.get("limitations", []), "uncertainty": report.get("uncertainty", {})}

    @app.get("/api/analyses/{analysis_id}/report")
    async def download_report(analysis_id: str):
        record = database().get(analysis_id)
        if record is None:
            return JSONResponse(status_code=404, content={"error": {"code": "analysis_not_found", "message": "The requested analysis was not found."}})
        return JSONResponse(content=record["report"], headers={"Content-Disposition": f'attachment; filename="trustlens-{analysis_id}.json"'})

    @app.delete("/api/analyses/{analysis_id}", status_code=204)
    async def delete_analysis(analysis_id: str):
        if not database().delete(analysis_id):
            return JSONResponse(status_code=404, content={"error": {"code": "analysis_not_found", "message": "The requested analysis was not found."}})
        return Response(status_code=204)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    port_text = os.environ.get("TRUSTLENS_PORT", "8765")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise SystemExit("TRUSTLENS_PORT must be an integer from 1 to 65535.") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("TRUSTLENS_PORT must be an integer from 1 to 65535.")
    uvicorn.run("trustlens.web:app", host="127.0.0.1", port=port, reload=False, workers=1)


if __name__ == "__main__":
    main()
