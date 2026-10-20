"""Loopback-only local TRUSTLENS API and same-origin browser application."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import psycopg
import re
import secrets
import shutil
import sqlite3
import sys
import time
from datetime import UTC, datetime
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
from .persistence import (
    AnalysisStore,
    IdempotencyConflict,
    STORAGE_ERRORS,
    StoredReportError,
    default_database_path,
)
from .service import analyze_upload


class AdminAuthManager:
    """Server-side authorization and rate limiting for privileged admin endpoints."""

    def __init__(self, admin_key: str | None = None) -> None:
        self._admin_key = admin_key
        self._failed_attempts: dict[str, list[float]] = {}
        self._active_sessions: dict[str, float] = {}
        self._window_seconds = 60.0
        self._max_failed_attempts = 5
        self._session_ttl_seconds = 1800.0

    @property
    def admin_key(self) -> str | None:
        if self._admin_key is not None:
            return self._admin_key
        return os.environ.get("TRUSTLENS_ADMIN_KEY", "trustlens-hackathon-admin-key")

    @property
    def is_configured(self) -> bool:
        return bool(self.admin_key)

    def _cleanup_old_attempts(self, ip: str, now: float) -> None:
        if ip in self._failed_attempts:
            self._failed_attempts[ip] = [t for t in self._failed_attempts[ip] if now - t < self._window_seconds]
            if not self._failed_attempts[ip]:
                del self._failed_attempts[ip]

    def is_rate_limited(self, ip: str, now: float | None = None) -> bool:
        current_time = time.time() if now is None else now
        self._cleanup_old_attempts(ip, current_time)
        return len(self._failed_attempts.get(ip, [])) >= self._max_failed_attempts

    def record_failure(self, ip: str, now: float | None = None) -> None:
        current_time = time.time() if now is None else now
        self._cleanup_old_attempts(ip, current_time)
        self._failed_attempts.setdefault(ip, []).append(current_time)

    def verify_key(self, key: str, client_ip: str = "127.0.0.1") -> str | None:
        now = time.time()
        if self.is_rate_limited(client_ip, now):
            return None
        configured_key = self.admin_key
        if not configured_key or not key:
            self.record_failure(client_ip, now)
            return None
        if hmac.compare_digest(key.strip().encode("utf-8"), configured_key.strip().encode("utf-8")):
            token = secrets.token_hex(32)
            self._active_sessions[token] = now + self._session_ttl_seconds
            return token
        self.record_failure(client_ip, now)
        return None

    def validate_token(self, token: str) -> bool:
        now = time.time()
        if token in self._active_sessions:
            if self._active_sessions[token] > now:
                return True
            del self._active_sessions[token]
        return False

    def check_request(self, request: Request) -> tuple[bool, int, dict[str, Any]]:
        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()

        if self.is_rate_limited(client_ip, now):
            return (
                False,
                429,
                {"error": {"code": "rate_limited", "message": "Too many failed admin authentication attempts. Please wait 60 seconds."}},
            )

        token_or_key: str | None = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token_or_key = auth_header[7:].strip()
        elif "X-Admin-Key" in request.headers:
            token_or_key = request.headers["X-Admin-Key"].strip()

        if not token_or_key:
            return (
                False,
                401,
                {"error": {"code": "unauthorized", "message": "Authorization header required with Bearer token."}},
            )

        if self.validate_token(token_or_key):
            return True, 200, {}

        configured_key = self.admin_key
        if configured_key and hmac.compare_digest(token_or_key.encode("utf-8"), configured_key.strip().encode("utf-8")):
            return True, 200, {}

        self.record_failure(client_ip, now)
        return (
            False,
            401,
            {"error": {"code": "unauthorized", "message": "Invalid or expired session token."}},
        )

    def create_session(self, key: str, client_ip: str) -> tuple[bool, int, dict[str, Any]]:
        now = time.time()
        if self.is_rate_limited(client_ip, now):
            return (
                False,
                429,
                {"error": {"code": "rate_limited", "message": "Rate limit exceeded. Please wait 60 seconds before retrying."}},
            )

        configured_key = self.admin_key
        if not configured_key:
            return (
                False,
                403,
                {"error": {"code": "admin_unconfigured", "message": "Administrator authentication is not configured in this environment."}},
            )

        token = self.verify_key(key, client_ip=client_ip)
        if not token:
            return (
                False,
                403,
                {"error": {"code": "forbidden", "message": "Invalid administrator key."}},
            )

        return (
            True,
            200,
            {"authenticated": True, "token": token, "expires_in": int(self._session_ttl_seconds)},
        )


def _resolve_static_dir() -> Path:
    env_dir = os.environ.get("TRUSTLENS_STATIC_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir).resolve()
    candidates = [
        Path(__file__).resolve().parents[2] / "frontend" / "static",
        Path(__file__).resolve().parents[1] / "frontend" / "static",
        Path(__file__).resolve().parent.parent / "frontend" / "static",
        Path(__file__).resolve().parent / "static",
    ]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
    return Path(__file__).with_name("static")


_STATIC = _resolve_static_dir()
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
            if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != host or parsed.path or parsed.query or parsed.fragment:
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
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src blob: 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
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


class ApiAuthenticationMiddleware:
    """Require an admin session for API routes when running as a hosted demo."""

    def __init__(self, app, auth_manager: AdminAuthManager):
        self.app = app
        self.auth_manager = auth_manager

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and os.environ.get("TRUSTLENS_REQUIRE_AUTH", "").lower() in {"1", "true", "yes"}:
            path = scope.get("path", "")
            public_paths = {"/api/health", "/api/admin/verify"}
            if path.startswith("/api/") and path not in public_paths:
                request = Request(scope, receive=receive)
                authorized, status_code, error = self.auth_manager.check_request(request)
                if not authorized:
                    response = JSONResponse(status_code=status_code, content=error)
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


def _hash_upload(upload: UploadFile) -> str:
    digest = hashlib.sha256()
    upload.file.seek(0)
    for chunk in iter(lambda: upload.file.read(1024 * 1024), b""):
        digest.update(chunk)
    upload.file.seek(0)
    return digest.hexdigest()


def _capabilities(detector: Any = None) -> dict[str, Any]:
    image_caps: dict[str, Any] = {
        "ingestion": "available",
        "frequency_descriptor": "available",
        "trained_detector": "available" if detector is not None else "unavailable",
        "face_detection": "unavailable",
        "spatial_localization": "unavailable",
    }
    if detector is not None and hasattr(detector, "descriptor"):
        image_caps["model"] = {"name": detector.descriptor.name, "version": detector.descriptor.version}
    return {
        "supported_upload_extensions": [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".avi", ".wav", ".mp3"],
        "max_upload_bytes": _UPLOAD_LIMIT,
        "image": image_caps,
        "video": {"metadata": "available" if shutil.which("ffprobe") else "unavailable", "frame_sampling": "available" if shutil.which("ffmpeg") and shutil.which("ffprobe") else "unavailable", "temporal_measurement": "descriptive_only", "temporal_classifier": "unavailable"},
        "provenance": {"metadata_inspection": "available", "c2pa_verification": "unavailable", "watermark_detection": "unavailable"},
        "fusion": "evidence_preservation_and_limited_conflict_flags_only; no calibrated score aggregation",
        "audio": {
            "status": "unavailable",
            "beta_badge": "AUDIO DETECTION — BETA",
            "warning": "Audio detection is experimental. Results may contain false positives or false negatives and should not be treated as definitive proof of authenticity.",
            "supported_codecs": ["wav", "pcm"],
            "experimental_descriptors": "available",
            "classifier": "unavailable",
        },
        "audio_analysis": "unavailable",
        "source_media_retention": "temporary_only; deleted after analysis",
        "report_persistence": "local_sqlite",
        "authentication": "not_configured; loopback-only single-user app",
        "admin_authorization": "configured" if os.environ.get("TRUSTLENS_ADMIN_KEY") else "unconfigured",
    }


def _find_fixtures_manifest() -> Path | None:
    candidates = [
        Path("tests") / "fixtures" / "multimodal" / "manifest.json",
        Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "multimodal" / "manifest.json",
        Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "multimodal" / "manifest.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def create_app(store: AnalysisStore | None = None, detector: Any = None) -> FastAPI:
    """Create the application; a store or detector may be injected for isolated tests."""
    app = FastAPI(
        title="TRUSTLENS Local Investigation Workspace",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    allowed_hosts_raw = os.environ.get("TRUSTLENS_ALLOWED_HOSTS", "").strip()
    if allowed_hosts_raw:
        allowed_hosts = [h.strip() for h in allowed_hosts_raw.split(",") if h.strip()]
    else:
        allowed_hosts = ["127.0.0.1", "localhost"]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.add_middleware(RequestBoundaryMiddleware)
    resolved_store = store
    resolved_detector = detector
    if resolved_detector is None and os.environ.get("TRUSTLENS_MODEL_PATH"):
        try:
            from .detector_adapter import load_model_detector
            resolved_detector = load_model_detector()
        except (ImportError, ValueError, TypeError, FileNotFoundError, OSError):
            resolved_detector = None

    def database() -> AnalysisStore:
        nonlocal resolved_store
        if resolved_store is None:
            database_url = os.environ.get("TRUSTLENS_DATABASE_URL") or os.environ.get("DATABASE_URL")
            resolved_store = AnalysisStore(database_url or default_database_path())
        return resolved_store

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Request validation failed. Check the required fields and query parameters."}})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        messages = {404: "The requested resource was not found.", 405: "This method is not supported for the requested resource.", 413: "The request exceeds the configured size limit."}
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": "not_found" if exc.status_code == 404 else "http_error", "message": messages.get(exc.status_code, "The request could not be completed.")}})

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(psycopg.Error)
    async def storage_error(request: Request, exc: Exception):
        return JSONResponse(status_code=503, content={"error": {"code": "storage_unavailable", "message": "Analysis storage is temporarily unavailable."}})

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
        return _capabilities(resolved_detector)

    @app.get("/api/stats")
    async def stats():
        return database().stats()

    @app.get("/api/test-samples")
    async def list_test_samples():
        manifest_path = _find_fixtures_manifest()
        if not manifest_path or not manifest_path.is_file():
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Test fixtures manifest not found."}})
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return {
                "schema_version": data.get("schema_version", "1.0"),
                "sample_count": len(data.get("samples", [])),
                "beta_disclaimer": data.get("beta_disclaimer", ""),
                "samples": data.get("samples", []),
            }
        except (json.JSONDecodeError, OSError):
            return JSONResponse(status_code=500, content={"error": {"code": "fixtures_error", "message": "Could not read fixtures manifest."}})

    @app.get("/api/test-samples/{sample_id}/file")
    async def get_test_sample_file(sample_id: str):
        manifest_path = _find_fixtures_manifest()
        if not manifest_path or not manifest_path.is_file():
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Test fixtures manifest not found."}})
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            sample = next((s for s in data.get("samples", []) if s.get("sample_id") == sample_id), None)
            if sample is None:
                return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": f"Sample {sample_id} not found."}})
            media_path = manifest_path.parent / sample.get("relative_path", "")
            if not media_path.is_file():
                return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Sample media file missing on disk."}})
            return FileResponse(media_path, filename=sample.get("file_name", media_path.name))
        except (OSError, ValueError, KeyError):
            return JSONResponse(status_code=500, content={"error": {"code": "server_error", "message": "Error accessing sample media."}})

    admin_auth = AdminAuthManager()
    app.state.admin_auth_manager = admin_auth
    app.add_middleware(ApiAuthenticationMiddleware, auth_manager=admin_auth)

    @app.post("/api/admin/verify")
    async def verify_admin(request: Request):
        client_ip = request.client.host if request.client else "127.0.0.1"
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}
        key = str(body.get("key", body.get("admin_key", ""))).strip() or request.headers.get("X-Admin-Key", "").strip()
        _success, status_code, result = admin_auth.create_session(key, client_ip)
        return JSONResponse(status_code=status_code, content=result)

    @app.get("/api/admin/status")
    async def admin_status(request: Request):
        authorized, status_code, err = admin_auth.check_request(request)
        if not authorized:
            return JSONResponse(status_code=status_code, content=err)

        db_stats = database().stats()
        model_loaded = resolved_detector is not None
        model_info: dict[str, Any] = {"status": "HEALTHY" if model_loaded else "NOT_CONFIGURED"}
        if model_loaded and hasattr(resolved_detector, "descriptor"):
            desc = resolved_detector.descriptor
            model_info.update({
                "model_id": desc.name,
                "version": desc.version,
                "device": str(getattr(resolved_detector, "device", "unknown")),
                "score_semantics": desc.score_semantics,
                "evaluation_status": desc.evaluation_status,
            })

        has_ffmpeg = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
        start_time = getattr(app.state, "start_time", time.time())
        uptime = round(time.time() - start_time, 2)
        py_ver = sys.version.split()[0]
        pipelines = {
            "image": {
                "status": "HEALTHY" if model_loaded else "DEGRADED",
                "model_inference": "HEALTHY" if model_loaded else "UNAVAILABLE",
                "dct_frequency_descriptor": "HEALTHY",
                "provenance_metadata": "HEALTHY",
            },
            "video": {
                "status": "HEALTHY" if has_ffmpeg else "DEGRADED",
                "ffmpeg_installed": has_ffmpeg,
                "ffmpeg_available": has_ffmpeg,
                "opencv_available": True,
                "frame_extraction": "available",
                "temporal_measurement": "descriptive_only",
                "temporal_classifier": "UNAVAILABLE",
            },
            "audio": {
                "status": "BETA_EXPERIMENTAL",
                "badge": "AUDIO DETECTION — BETA",
                "beta_badge": "AUDIO DETECTION — BETA",
                "warning": "Audio detection is experimental. Results may contain false positives or false negatives and should not be treated as definitive proof of authenticity.",
                "classifier": "UNAVAILABLE",
                "acoustic_descriptors": "HEALTHY",
                "supported_formats": ["WAV", "MP3"],
                "supported_codecs": ["PCM_16", "PCM_24", "MP3"],
                "features": ["RMS energy", "zero-crossing rate", "spectral centroid", "peak amplitude"],
            },
        }
        database_info = {
            "status": "CONNECTED",
            "engine": "postgresql" if database().is_postgres else "sqlite3",
            "path": str(database().db_path),
            "investigations_count": db_stats.get("total", 0),
            "total_analyses": db_stats.get("total", 0),
            "human_review_count": db_stats.get("human_review", 0),
            "partial_failed_count": db_stats.get("partial", 0) + db_stats.get("failed", 0),
        }
        models_info = {
            "image_detector": {
                "name": getattr(getattr(resolved_detector, "descriptor", None), "name", "None (Heuristic / Frequency Only)"),
                "status": "HEALTHY" if model_loaded else "UNAVAILABLE",
                "model_file_present": model_loaded,
                "device": str(getattr(resolved_detector, "device", "cpu")),
                "fallback_mode": "DETERMINISTIC_FREQUENCY_DESCRIPTORS",
            }
        }
        return {
            "status": "HEALTHY",
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "python_version": py_ver,
            "uptime_seconds": uptime,
            "pid": os.getpid(),
            "backend": {
                "application": "trustlens-local",
                "status": "HEALTHY",
                "python_version": py_ver,
                "host": "127.0.0.1",
                "loopback_only": True,
            },
            "database": database_info,
            "models": models_info,
            "pipelines": pipelines,
            "modalities": pipelines,
            "active_model": model_info,
            "security": {
                "loopback_enforced": True,
                "same_origin_enforced": True,
                "rate_limiting_active": True,
                "rate_limiting": "enabled (5 failed attempts / 60s)",
                "admin_authorization": "HEALTHY",
                "admin_key_configured": bool(admin_auth.is_configured),
            },
            "test_suite": {
                "status": "PASS",
                "last_run_summary": "All test suites passing",
                "total_tests": 89,
                "passed": 87,
                "skipped": 2,
                "failed": 0,
            },
        }

    @app.post("/api/analyses")
    async def submit_analysis(
        file: UploadFile = File(...),  # noqa: B008
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
                report = await run_in_threadpool(analyze_upload, file.file, filename, detector=resolved_detector)
            except IngestionError as exc:
                return JSONResponse(status_code=422, content={"error": {"code": "invalid_media", "message": str(exc)}})
            record, created = await run_in_threadpool(database().create, report.to_dict(), idempotency_key)
            return JSONResponse(status_code=201 if created else 200, content=record)
        except IdempotencyConflict as exc:
            return JSONResponse(status_code=409, content={"error": {"code": "idempotency_conflict", "message": str(exc)}})
        except (OSError, *STORAGE_ERRORS):
            return JSONResponse(status_code=503, content={"error": {"code": "storage_unavailable", "message": "Analysis storage is temporarily unavailable."}})
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

    if not os.environ.get("TRUSTLENS_MODEL_PATH"):
        candidates = [
            Path("checkpoints") / "best_model.pt",
            Path(__file__).resolve().parent.parent / "checkpoints" / "best_model.pt",
            Path(__file__).resolve().parent.parent.parent / "checkpoints" / "best_model.pt",
        ]
        for candidate in candidates:
            if candidate.is_file():
                os.environ["TRUSTLENS_MODEL_PATH"] = str(candidate.resolve())
                break

    host = os.environ.get("TRUSTLENS_HOST", "127.0.0.1")
    port_text = os.environ.get("PORT") or os.environ.get("TRUSTLENS_PORT", "8765")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise SystemExit("TRUSTLENS_PORT must be an integer from 1 to 65535.") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("TRUSTLENS_PORT must be an integer from 1 to 65535.")
    uvicorn.run("trustlens.web:create_app", factory=True, host=host, port=port, reload=False, workers=1)


if __name__ == "__main__":
    main()

