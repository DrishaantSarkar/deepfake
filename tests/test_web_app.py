"""End-to-end tests for the local HTTP application and SQLite history."""

import json
import tempfile
import unittest
import os
from unittest.mock import patch
from pathlib import Path
import sqlite3

import cv2
import numpy as np
from fastapi.testclient import TestClient

from trustlens.persistence import AnalysisStore
from trustlens.web import RequestBoundaryMiddleware, create_app, main


def image_bytes() -> bytes:
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    image[8:36, 15:50] = (30, 120, 210)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Could not create API test image")
    return encoded.tobytes()


class WebApplicationTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path.cwd() / ".trustlens-test-tmp"
        temp_root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temp_root)
        self.db_path = Path(self.directory.name) / "history.sqlite3"
        self.store = AnalysisStore(self.db_path)
        self.client = TestClient(create_app(self.store), base_url="http://127.0.0.1")

    def tearDown(self):
        self.client.close()
        self.directory.cleanup()

    def upload(self, contents=None, filename="evidence.png", key="request-1"):
        return self.client.post(
            "/api/analyses",
            files={"file": (filename, contents if contents is not None else image_bytes(), "image/png")},
            headers={"Idempotency-Key": key},
        )

    def test_local_app_serves_ui_capabilities_and_health(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"TRUSTLENS", page.content)
        self.assertIn("content-security-policy", page.headers)
        self.assertEqual(self.client.get("/static/app.css").status_code, 200)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.assertEqual(self.client.get("/api/health").json()["status"], "available")
        capabilities = self.client.get("/api/capabilities").json()
        self.assertEqual(capabilities["authentication"], "not_configured; loopback-only single-user app")
        self.assertEqual(capabilities["image"]["trained_detector"], "unavailable")
        self.assertEqual(capabilities["video"]["temporal_classifier"], "unavailable")
        self.assertEqual(self.client.get("/api/openapi.json").status_code, 200)
        self.assertEqual(self.client.get("/api/health", headers={"Host": "attacker.example"}).status_code, 400)
        self.assertEqual(self.client.get("/api/health", headers={"Host": "testserver"}).status_code, 400)

    def test_upload_persists_report_only_and_history_endpoints_work(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.text)
        record = response.json()
        analysis_id = record["analysis_id"]
        self.assertEqual(record["media"]["filename"], "evidence.png")
        self.assertTrue(record["human_review_required"])
        self.assertEqual(self.client.get("/api/stats").json()["total"], 1)
        listed = self.client.get("/api/analyses", params={"q": "evidence", "media_type": "image"}).json()
        self.assertEqual([item["analysis_id"] for item in listed["items"]], [analysis_id])
        detail = self.client.get(f"/api/analyses/{analysis_id}").json()
        self.assertEqual(detail["report"]["source"]["sha256"], record["media"]["sha256"])
        self.assertEqual(self.client.get(f"/api/analyses/{analysis_id}/evidence").status_code, 200)
        self.assertEqual(self.client.get(f"/api/analyses/{analysis_id}/report").status_code, 200)
        restarted = TestClient(create_app(AnalysisStore(self.db_path)), base_url="http://127.0.0.1")
        self.assertEqual(restarted.get(f"/api/analyses/{analysis_id}").json()["analysis_id"], analysis_id)
        restarted.close()
        persisted = self.db_path.read_bytes()
        self.assertNotIn(image_bytes(), persisted)
        self.assertEqual(self.client.delete(f"/api/analyses/{analysis_id}").status_code, 204)
        self.assertEqual(self.client.get("/api/stats").json()["total"], 0)

    def test_idempotency_replays_same_source_and_rejects_different_source(self):
        first = self.upload(key="stable-key")
        replay = self.upload(key="stable-key")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.json()["analysis_id"], replay.json()["analysis_id"])
        other = self.upload(contents=image_bytes() + b"different", key="stable-key")
        self.assertEqual(other.status_code, 409)
        self.assertEqual(self.client.get("/api/stats").json()["total"], 1)

    def test_invalid_media_and_cross_origin_writes_are_rejected(self):
        invalid = self.upload(b"not an image", "broken.png")
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(self.client.get("/api/stats").json()["total"], 0)
        cross_origin = self.client.post("/api/analyses", headers={"Origin": "https://attacker.example"})
        self.assertEqual(cross_origin.status_code, 403)
        malformed_origin = self.client.post("/api/analyses", headers={"Origin": "http://["})
        self.assertEqual(malformed_origin.status_code, 403)

    def test_unknown_records_filters_and_storage_failures_return_errors_without_leaking_details(self):
        self.assertEqual(self.client.get("/api/analyses/missing-id").status_code, 404)
        self.assertEqual(self.client.get("/api/analyses/missing-id/report").status_code, 404)
        self.assertEqual(self.client.delete("/api/analyses/missing-id").status_code, 404)
        self.assertEqual(self.client.get("/api/analyses", params={"status": "BOGUS"}).status_code, 422)
        self.assertEqual(self.client.get("/api/analyses", params={"media_type": "nope"}).status_code, 422)
        original_create = self.store.create

        def failed_write(report, idempotency_key=None):
            raise sqlite3.OperationalError("private database path must not leak")

        self.store.create = failed_write
        response = self.upload(key="write-failure")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private database path", response.text)
        self.assertEqual(self.client.get("/api/stats").json()["total"], 0)
        self.store.create = original_create

    def test_upload_filename_path_is_sanitized_in_saved_report(self):
        response = self.upload(filename="..\\..\\escape.png")
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["media"]["filename"], "escape.png")

    def test_request_body_limit_and_corrupt_database_fail_safely(self):
        limited_app = create_app(AnalysisStore(Path(self.directory.name) / "limited.sqlite3"))
        limited_app.add_middleware(RequestBoundaryMiddleware, max_body_bytes=16)
        with TestClient(limited_app, base_url="http://127.0.0.1") as limited_client:
            too_large = limited_client.post("/api/analyses", content=b"x" * 17, headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(too_large.status_code, 413)

        corrupt_db = Path(self.directory.name) / "corrupt.sqlite3"
        corrupt_db.write_bytes(b"not a sqlite database")
        with patch.dict(os.environ, {"TRUSTLENS_DB_PATH": str(corrupt_db)}):
            with TestClient(create_app(), base_url="http://127.0.0.1") as corrupt_client:
                response = corrupt_client.get("/api/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "local_storage_unavailable")
        self.assertNotIn("not a sqlite database", response.text)

    def test_malformed_persisted_report_returns_sanitized_storage_error(self):
        response = self.upload(key="corrupt-report")
        self.assertEqual(response.status_code, 201, response.text)
        analysis_id = response.json()["analysis_id"]
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("UPDATE analyses SET report_json = ? WHERE analysis_id = ?", ("{", analysis_id))
            connection.commit()
        finally:
            connection.close()

        detail = self.client.get(f"/api/analyses/{analysis_id}")
        listing = self.client.get("/api/analyses")
        for result in (detail, listing):
            with self.subTest(status=result.status_code, body=result.text[:60]):
                self.assertEqual(result.status_code, 503)
                self.assertEqual(result.json()["error"]["code"], "stored_report_unavailable")
                self.assertNotIn("JSONDecodeError", result.text)
                self.assertNotIn(str(self.db_path), result.text)

    def test_report_row_mismatch_returns_sanitized_storage_error(self):
        response = self.upload(key="mismatched-report")
        self.assertEqual(response.status_code, 201, response.text)
        record = response.json()
        report = record["report"]
        report["source"]["sha256"] = "0" * 64
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                "UPDATE analyses SET report_json = ? WHERE analysis_id = ?",
                (json.dumps(report), record["analysis_id"]),
            )
            connection.commit()
        finally:
            connection.close()

        result = self.client.get(f"/api/analyses/{record['analysis_id']}")
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json()["error"]["code"], "stored_report_unavailable")
        self.assertNotIn("0" * 64, result.text)

    def test_non_finite_persisted_metadata_returns_sanitized_storage_error(self):
        response = self.upload(key="non-finite-report")
        self.assertEqual(response.status_code, 201, response.text)
        record = response.json()
        report = record["report"]
        report["source"]["metadata"]["invalid_numeric_value"] = float("nan")
        connection = sqlite3.connect(self.db_path)
        try:
            # The default encoder emits the non-standard token "NaN", which
            # json.loads accepts unless the stored payload is revalidated.
            connection.execute(
                "UPDATE analyses SET report_json = ? WHERE analysis_id = ?",
                (json.dumps(report), record["analysis_id"]),
            )
            connection.commit()
        finally:
            connection.close()

        result = self.client.get(f"/api/analyses/{record['analysis_id']}")
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json()["error"]["code"], "stored_report_unavailable")
        self.assertNotIn("NaN", result.text)

    def test_server_port_is_configurable_but_host_stays_loopback(self):
        with patch.dict(os.environ, {"TRUSTLENS_PORT": "9123"}), patch("uvicorn.run") as run:
            main()
        self.assertEqual(run.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(run.call_args.kwargs["port"], 9123)
        with patch.dict(os.environ, {"TRUSTLENS_PORT": "65536"}):
            with self.assertRaises(SystemExit):
                main()


if __name__ == "__main__":
    unittest.main()
