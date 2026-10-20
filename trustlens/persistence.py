"""Small SQLite persistence layer for local analysis reports and history."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class IdempotencyConflict(ValueError):
    """An idempotency key was reused for a different source file."""


class StoredReportError(ValueError):
    """A persisted report is malformed or structurally invalid."""


def default_database_path() -> Path:
    configured = os.environ.get("TRUSTLENS_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "TRUSTLENS" / "analyses.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class AnalysisStore:
    """Thread-safe-by-connection SQLite store for report metadata, not media."""

    def __init__(self, database_path: str | Path):
        self.path = Path(database_path).expanduser().resolve()
        self.db_path = self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _session(self):
        """Commit/rollback a short transaction and always release the handle."""
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._session() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    analysis_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    processing_status TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    human_review_required INTEGER NOT NULL CHECK (human_review_required IN (0, 1)),
                    report_json TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS analyses_created_idx ON analyses(created_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS analyses_status_idx ON analyses(processing_status)")
            connection.execute("CREATE INDEX IF NOT EXISTS analyses_media_idx ON analyses(media_type)")
        if os.name != "nt":
            try:
                self.path.parent.chmod(0o700)
                self.path.chmod(0o600)
            except OSError:
                pass

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, Any]:
        try:
            report = json.loads(row["report_json"])
            if not isinstance(report, dict):
                raise ValueError("report JSON root is not an object")
            # Python's JSON decoder accepts NaN and infinities by default, but
            # those values are not valid JSON and cannot be emitted safely by
            # the API's strict JSON response serializer.
            json.dumps(report, ensure_ascii=False, allow_nan=False)
            source = report.get("source")
            if not isinstance(source, dict):
                raise ValueError("report source is not an object")
            size_bytes = source.get("size_bytes")
            metadata = source.get("metadata", {})
            if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
                raise ValueError("report source size is invalid")
            if not isinstance(metadata, dict):
                raise ValueError("report source metadata is invalid")
            stored_review_flag = row["human_review_required"]
            if stored_review_flag not in (0, 1):
                raise ValueError("stored review flag is invalid")
            human_review_required = bool(stored_review_flag)
            if (
                report.get("report_id") != row["analysis_id"]
                or report.get("processing_status") != row["processing_status"]
                or report.get("human_review_required") is not human_review_required
                or source.get("sha256") != row["source_sha256"]
                or source.get("media_type") != row["media_type"]
                or source.get("filename") != row["filename"]
            ):
                raise ValueError("report does not match its history row")
            return {
                "analysis_id": row["analysis_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "processing_status": row["processing_status"],
                "media": {
                    "filename": row["filename"],
                    "media_type": row["media_type"],
                    "sha256": row["source_sha256"],
                    "size_bytes": size_bytes,
                    "metadata": metadata,
                },
                "human_review_required": human_review_required,
                "report": report,
            }
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            raise StoredReportError("A saved analysis report is malformed or structurally invalid.") from exc

    def find_idempotent(self, key: str, source_sha256: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute("SELECT * FROM analyses WHERE idempotency_key = ?", (key,)).fetchone()
        if row is None:
            return None
        if row["source_sha256"] != source_sha256:
            raise IdempotencyConflict("Idempotency-Key was already used for a different upload.")
        return self._serialize(row)

    def create(self, report: dict[str, Any], idempotency_key: str | None = None) -> tuple[dict[str, Any], bool]:
        source = report["source"]
        now = _now()
        with self._session() as connection:
            try:
                connection.execute("""
                    INSERT INTO analyses (
                        analysis_id, created_at, updated_at, processing_status,
                        media_type, filename, source_sha256, human_review_required,
                        report_json, idempotency_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    report["report_id"], now, now, report["processing_status"],
                    source["media_type"], source["filename"], source["sha256"],
                    int(report["human_review_required"]),
                    json.dumps(report, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
                    idempotency_key,
                ))
            except sqlite3.IntegrityError:
                if idempotency_key:
                    row = connection.execute("SELECT * FROM analyses WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
                    if row is not None:
                        if row["source_sha256"] != source["sha256"]:
                            raise IdempotencyConflict("Idempotency-Key was already used for a different upload.")
                        return self._serialize(row), False
                raise
            row = connection.execute("SELECT * FROM analyses WHERE analysis_id = ?", (report["report_id"],)).fetchone()
        return self._serialize(row), True

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute("SELECT * FROM analyses WHERE analysis_id = ?", (analysis_id,)).fetchone()
        return self._serialize(row) if row else None

    def list(self, *, limit: int = 20, offset: int = 0,
             status: str | None = None, media_type: str | None = None,
             query: str | None = None) -> dict[str, Any]:
        clauses: list[str] = []
        values: list[Any] = []
        if status:
            clauses.append("processing_status = ?")
            values.append(status)
        if media_type:
            clauses.append("media_type = ?")
            values.append(media_type)
        if query:
            clauses.append("(filename LIKE ? OR source_sha256 LIKE ?)")
            pattern = f"%{query}%"
            values.extend((pattern, pattern))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._session() as connection:
            total = connection.execute("SELECT COUNT(*) FROM analyses" + where, values).fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM analyses" + where + " ORDER BY created_at DESC, analysis_id DESC LIMIT ? OFFSET ?",
                (*values, limit, offset),
            ).fetchall()
        return {"items": [self._serialize(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def stats(self) -> dict[str, int]:
        with self._session() as connection:
            counts = {row["processing_status"]: row["count"] for row in connection.execute(
                "SELECT processing_status, COUNT(*) AS count FROM analyses GROUP BY processing_status"
            )}
            review = connection.execute("SELECT COUNT(*) FROM analyses WHERE human_review_required = 1").fetchone()[0]
            total = connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
        return {"total": total, "completed": counts.get("SUCCESS", 0),
                "partial": counts.get("PARTIAL", 0), "failed": counts.get("FAILED", 0),
                "unavailable": counts.get("UNAVAILABLE", 0), "human_review": review}

    def delete(self, analysis_id: str) -> bool:
        with self._session() as connection:
            cursor = connection.execute("DELETE FROM analyses WHERE analysis_id = ?", (analysis_id,))
        return cursor.rowcount > 0
