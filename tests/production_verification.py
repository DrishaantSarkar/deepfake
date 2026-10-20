"""Comprehensive live verification of TRUSTLENS in production configuration."""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import cv2
import httpx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_verification():
    print("=" * 70)
    print("TRUSTLENS PRODUCTION RUNTIME VERIFICATION")
    print("=" * 70)

    temp_dir = tempfile.mkdtemp(prefix="trustlens-prod-verify-")
    temp_path = Path(temp_dir)
    db_path = temp_path / "prod-analyses.sqlite3"
    media_staging_dir = temp_path / "staging"
    media_staging_dir.mkdir()

    port = get_free_port()
    base_url = f"http://127.0.0.1:{port}"
    admin_secret = "test-prod-admin-secret-" + uuid.uuid4().hex

    env = os.environ.copy()
    env["TRUSTLENS_HOST"] = "127.0.0.1"
    env["TRUSTLENS_PORT"] = str(port)
    env["TRUSTLENS_ALLOWED_HOSTS"] = f"127.0.0.1,localhost"
    env["TRUSTLENS_DB_PATH"] = str(db_path)
    env["TRUSTLENS_TEMP_DIR"] = str(media_staging_dir)
    env["TRUSTLENS_MODEL_PATH"] = str(ROOT / "checkpoints" / "best_model.pt")
    env["TRUSTLENS_ADMIN_KEY"] = admin_secret
    env["TRUSTLENS_ENV"] = "production"

    server_process = subprocess.Popen(
        [sys.executable, "-m", "trustlens.web"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    checklist: dict[str, str] = {}

    try:
        # Wait for startup
        print(f"[1/15] Starting TRUSTLENS on {base_url}...")
        deadline = time.time() + 15
        server_ready = False
        while time.time() < deadline:
            if server_process.poll() is not None:
                _, err = server_process.communicate()
                raise RuntimeError(f"Server exited prematurely: {err.decode('utf-8', errors='replace')}")
            try:
                r = httpx.get(f"{base_url}/api/health", timeout=1.0)
                if r.status_code == 200:
                    server_ready = True
                    break
            except httpx.HTTPError:
                time.sleep(0.2)

        if not server_ready:
            raise TimeoutError("Server did not become ready within 15 seconds")
        print("  -> Server ready!")
        checklist["server_startup"] = "PASS"

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            # 2. Health check
            print("[2/15] Verifying /api/health...")
            r_health = client.get("/api/health")
            assert r_health.status_code == 200
            assert r_health.json().get("status") == "available"
            print("  -> /api/health returned 200 available")
            checklist["api_health"] = "PASS"

            # 3. Capabilities check
            print("[3/15] Verifying /api/capabilities and model availability...")
            r_caps = client.get("/api/capabilities")
            assert r_caps.status_code == 200
            caps = r_caps.json()
            assert caps["image"]["trained_detector"] == "available"
            assert caps["image"]["model"]["name"] == "resnet18-frame-baseline"
            print(f"  -> Model '{caps['image']['model']['name']}' loaded and available")
            checklist["model_capabilities"] = "PASS"

            # 4. Web UI and Security Headers
            print("[4/15] Verifying UI home and security headers...")
            r_ui = client.get("/")
            assert r_ui.status_code == 200
            assert "content-security-policy" in r_ui.headers
            assert "x-content-type-options" in r_ui.headers
            assert "x-frame-options" in r_ui.headers
            assert b"TRUSTLENS" in r_ui.content
            print("  -> Web UI returned 200 with strict CSP and security headers")
            checklist["ui_and_security_headers"] = "PASS"

            # 5. Static Assets
            print("[5/15] Verifying static bundle assets...")
            r_css = client.get("/static/app.css")
            r_js = client.get("/static/app.js")
            assert r_css.status_code == 200 and len(r_css.content) > 1000
            assert r_js.status_code == 200 and len(r_js.content) > 1000
            print("  -> Static assets (app.css, app.js) served successfully")
            checklist["static_assets"] = "PASS"

            # 6. Admin Authentication & Session
            print("[6/15] Verifying admin authentication...")
            r_admin_unauth = client.get("/api/admin/status")
            assert r_admin_unauth.status_code == 401
            r_admin_verify = client.post("/api/admin/verify", json={"key": admin_secret})
            assert r_admin_verify.status_code == 200
            admin_token = r_admin_verify.json()["token"]
            r_admin_status = client.get("/api/admin/status", headers={"Authorization": f"Bearer {admin_token}"})
            assert r_admin_status.status_code == 200
            status_body = r_admin_status.json()
            assert status_body["status"] == "HEALTHY"
            assert admin_secret not in str(status_body)
            print("  -> Admin authenticated with session token; telemetry HEALTHY; zero secret leakage")
            checklist["admin_auth_and_telemetry"] = "PASS"

            # 7. Image Analysis with ResNet-18 Inference
            print("[7/15] Verifying real image analysis pipeline...")
            img = np.zeros((224, 224, 3), dtype=np.uint8)
            img[30:190, 40:180] = (120, 180, 240)
            _, encoded_png = cv2.imencode(".png", img)
            img_bytes = encoded_png.tobytes()
            idempotency_key = "verify-img-" + uuid.uuid4().hex[:8]

            r_img = client.post(
                "/api/analyses",
                files={"file": ("sample_test.png", img_bytes, "image/png")},
                headers={"Idempotency-Key": idempotency_key},
            )
            assert r_img.status_code == 201, r_img.text
            img_data = r_img.json()
            analysis_id = img_data["analysis_id"]
            report = img_data["report"]
            detector_res = report["analysis"]["result"]["detector"]
            assert detector_res["status"] == "SUCCESS"
            assert "synthetic" in detector_res["raw_scores"]
            assert "real" in detector_res["raw_scores"]
            print(f"  -> Image analyzed: ID={analysis_id}, Detector={detector_res['status']}, "
                  f"Scores: real={detector_res['raw_scores']['real']:.4f}, synthetic={detector_res['raw_scores']['synthetic']:.4f}")
            checklist["image_analysis_pipeline"] = "PASS"

            # 8. Idempotency Check
            print("[8/15] Verifying idempotency handling...")
            r_replay = client.post(
                "/api/analyses",
                files={"file": ("sample_test.png", img_bytes, "image/png")},
                headers={"Idempotency-Key": idempotency_key},
            )
            assert r_replay.status_code == 200
            assert r_replay.json()["analysis_id"] == analysis_id
            print("  -> Idempotent replay returned 200 with identical analysis ID")
            checklist["idempotency_replay"] = "PASS"

            # 9. Real Video Analysis (using FFmpeg test fixture)
            print("[9/15] Verifying real video analysis pipeline...")
            video_fixture = temp_path / "test_fixture.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                "-i", "testsrc=size=64x48:rate=4:duration=1", "-an", "-c:v", "mpeg4",
                "-pix_fmt", "yuv420p", str(video_fixture),
            ], check=True, capture_output=True, text=True)

            with video_fixture.open("rb") as vf:
                r_vid = client.post(
                    "/api/analyses",
                    files={"file": ("test_fixture.mp4", vf, "video/mp4")},
                )
            assert r_vid.status_code == 201, r_vid.text
            vid_data = r_vid.json()
            vid_id = vid_data["analysis_id"]
            vid_report = vid_data["report"]
            assert vid_report["analysis"]["kind"] == "video"
            assert len(vid_report["analysis"]["result"]["frames"]) > 0
            print(f"  -> Video analyzed: ID={vid_id}, Sampled {len(vid_report['analysis']['result']['frames'])} frames")
            checklist["video_analysis_pipeline"] = "PASS"

            # 10. Evidence endpoint
            print("[10/15] Verifying /api/analyses/{id}/evidence...")
            r_ev = client.get(f"/api/analyses/{analysis_id}/evidence")
            assert r_ev.status_code == 200
            assert "evidence" in r_ev.json()
            print("  -> Evidence endpoint returned 200")
            checklist["evidence_endpoint"] = "PASS"

            # 11. Report Download
            print("[11/15] Verifying /api/analyses/{id}/report download...")
            r_rep = client.get(f"/api/analyses/{analysis_id}/report")
            assert r_rep.status_code == 200
            assert "attachment" in r_rep.headers.get("content-disposition", "")
            print("  -> Report JSON download returned 200 with attachment disposition")
            checklist["report_download"] = "PASS"

            # 12. History and Search
            print("[12/15] Verifying investigation history and query filters...")
            r_list = client.get("/api/analyses", params={"limit": 10, "media_type": "image"})
            assert r_list.status_code == 200
            items = r_list.json()["items"]
            assert any(item["analysis_id"] == analysis_id for item in items)
            print(f"  -> History query listed {len(items)} image records")
            checklist["history_and_search"] = "PASS"

            # 13. Record Deletion
            print("[13/15] Verifying record deletion...")
            r_del = client.delete(f"/api/analyses/{analysis_id}")
            assert r_del.status_code == 204
            r_get_deleted = client.get(f"/api/analyses/{analysis_id}")
            assert r_get_deleted.status_code == 404
            print(f"  -> Record {analysis_id} deleted successfully (returned 204, then 404)")
            checklist["record_deletion"] = "PASS"

            # 14. Negative Tests (Security & Validation)
            print("[14/15] Verifying negative security and validation controls...")
            # Cross-origin write rejection
            r_csrf = client.post("/api/analyses", headers={"Origin": "https://evil-attacker.com"})
            assert r_csrf.status_code == 403
            # Invalid media rejection
            r_bad_media = client.post("/api/analyses", files={"file": ("test.png", b"not an image", "image/png")})
            assert r_bad_media.status_code == 422
            # Missing record
            r_notfound = client.get("/api/analyses/non-existent-id")
            assert r_notfound.status_code == 404
            print("  -> Cross-origin (403), corrupt media (422), not-found (404) properly enforced")
            checklist["negative_security_tests"] = "PASS"

            # 15. Ephemeral Media Cleanup
            print("[15/15] Verifying temporary media staging directory cleanup...")
            residual_files = list(media_staging_dir.iterdir())
            assert len(residual_files) == 0, f"Found residual files in {media_staging_dir}: {residual_files}"
            print("  -> Zero residual files in temporary staging directory (cleanup verified)")
            checklist["ephemeral_media_cleanup"] = "PASS"

    finally:
        print("\nShutting down test server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + "=" * 70)
    print("ALL 15/15 PRODUCTION VERIFICATION CHECKS PASSED!")
    print("=" * 70)
    for check, res in checklist.items():
        print(f"  [x] {check}: {res}")
    return checklist


if __name__ == "__main__":
    run_verification()
