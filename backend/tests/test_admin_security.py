"""Security, authorization, and rate-limiting tests for the admin status endpoints."""

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from trustlens.persistence import AnalysisStore
from trustlens.web import AdminAuthManager, create_app


class TestAdminSecurity(unittest.TestCase):
    def setUp(self):
        temp_root = Path.cwd() / ".trustlens-test-tmp"
        temp_root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temp_root)
        self.db_path = Path(self.directory.name) / "admin_test.sqlite3"
        self.store = AnalysisStore(self.db_path)
        self.app = create_app(self.store)
        self.client = TestClient(self.app, base_url="http://127.0.0.1")

    def tearDown(self):
        self.client.close()
        self.directory.cleanup()

    # ---------------------------------------------------------
    # A. UNIT TESTS FOR AdminAuthManager
    # ---------------------------------------------------------
    def test_auth_manager_verification_and_tokens(self):
        manager = AdminAuthManager(admin_key="correct-horse-battery-staple")

        # Wrong key returns None
        self.assertIsNone(manager.verify_key("wrong-key", client_ip="127.0.0.1"))

        # Correct key returns session token
        token = manager.verify_key("correct-horse-battery-staple", client_ip="127.0.0.1")
        self.assertIsNotNone(token)
        self.assertTrue(manager.validate_token(token))

        # Invalid or revoked token returns False
        self.assertFalse(manager.validate_token("invalid-random-token"))

    def test_auth_manager_rate_limiting(self):
        manager = AdminAuthManager(admin_key="secret-key-12345")
        ip = "192.168.1.100"

        # 5 failed attempts
        for i in range(5):
            self.assertFalse(manager.is_rate_limited(ip))
            res = manager.verify_key(f"wrong-try-{i}", client_ip=ip)
            self.assertIsNone(res)

        # 6th attempt is rate-limited
        self.assertTrue(manager.is_rate_limited(ip))
        # Even with the correct key, a rate-limited IP is blocked
        blocked_res = manager.verify_key("secret-key-12345", client_ip=ip)
        self.assertIsNone(blocked_res)

        # A different IP is not affected
        other_ip = "192.168.1.101"
        self.assertFalse(manager.is_rate_limited(other_ip))
        valid_res = manager.verify_key("secret-key-12345", client_ip=other_ip)
        self.assertIsNotNone(valid_res)

    # ---------------------------------------------------------
    # B. HTTP ENDPOINT SECURITY & STATUS TESTS
    # ---------------------------------------------------------
    def test_unauthenticated_status_access_returns_401(self):
        # Direct GET without auth header
        res = self.client.get("/api/admin/status")
        self.assertEqual(res.status_code, 401)
        self.assertIn("Authorization header required", res.json()["error"]["message"])

    def test_invalid_bearer_token_returns_401(self):
        res = self.client.get(
            "/api/admin/status",
            headers={"Authorization": "Bearer totally-fake-token-value"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("Invalid or expired session token", res.json()["error"]["message"])

    def test_verify_wrong_key_returns_403(self):
        res = self.client.post("/api/admin/verify", json={"key": "definitely-not-the-key"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Invalid administrator key", res.json()["error"]["message"])

    def test_verify_rate_limiting_triggers_429(self):
        # Trigger 5 failures
        for i in range(5):
            self.client.post("/api/admin/verify", json={"key": f"bad-key-{i}"})

        # 6th should trigger 429
        res = self.client.post("/api/admin/verify", json={"key": "bad-key-6"})
        self.assertEqual(res.status_code, 429)
        self.assertIn("Rate limit exceeded", res.json()["error"]["message"])

    def test_authenticated_admin_flow_and_telemetry(self):
        # Retrieve the key configured on the app's manager
        admin_manager = self.app.state.admin_auth_manager
        current_key = admin_manager.admin_key

        # Reset rate limiting to ensure clean state
        admin_manager._failed_attempts.clear()

        # Step 1: Verify key to obtain session token
        verify_res = self.client.post("/api/admin/verify", json={"key": current_key})
        self.assertEqual(verify_res.status_code, 200)
        token_data = verify_res.json()
        self.assertIn("token", token_data)
        token = token_data["token"]

        # Step 2: Access privileged status endpoint with Bearer token
        status_res = self.client.get(
            "/api/admin/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(status_res.status_code, 200)
        status_data = status_res.json()

        # Verify diagnostic structure
        self.assertEqual(status_data["status"], "HEALTHY")
        self.assertIn("python_version", status_data)
        self.assertIn("uptime_seconds", status_data)
        self.assertIn("database", status_data)
        self.assertEqual(status_data["database"]["status"], "CONNECTED")

        # Pipelines
        self.assertIn("pipelines", status_data)
        self.assertIn("image", status_data["pipelines"])
        self.assertIn("video", status_data["pipelines"])
        self.assertIn("audio", status_data["pipelines"])

        # Prominent Audio BETA markings in telemetry
        audio_telemetry = status_data["pipelines"]["audio"]
        self.assertIn("BETA", audio_telemetry["status"])
        self.assertEqual(audio_telemetry["badge"], "AUDIO DETECTION — BETA")
        self.assertIn("experimental", audio_telemetry["warning"].lower())

        # Security check: Admin key MUST NOT be leaked in the response payload
        self.assertNotIn(current_key, str(status_data))
        self.assertNotIn("admin_key", status_data.get("security", {}))
        self.assertTrue(status_data["security"]["admin_key_configured"])


if __name__ == "__main__":
    unittest.main()
