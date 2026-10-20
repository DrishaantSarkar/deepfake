"""Start, stop, and restart TRUSTLENS with isolated storage to verify recovery."""

from __future__ import annotations

import hashlib
import os
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


ROOT = Path(__file__).resolve().parents[1]


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def start_server(env: dict[str, str], base_url: str) -> subprocess.Popen:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [sys.executable, "-m", "trustlens.web"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"TRUSTLENS exited during startup with status {process.returncode}.")
        try:
            response = httpx.get(f"{base_url}/api/health", timeout=0.5)
            if response.status_code == 200 and response.json().get("status") == "available":
                return process
        except httpx.HTTPError:
            pass
        time.sleep(0.15)
    process.terminate()
    process.wait(timeout=5)
    raise RuntimeError("TRUSTLENS did not become healthy within 15 seconds.")


def stop_server(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
        process.wait(timeout=10)


def main() -> None:
    temp_root = ROOT / ".trustlens-test-tmp"
    temp_root.mkdir(exist_ok=True)
    run_id = uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="restart-smoke-", dir=temp_root) as directory:
        run_dir = Path(directory)
        media_dir = run_dir / "media"
        media_dir.mkdir()
        port = free_loopback_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["TRUSTLENS_DB_PATH"] = str(run_dir / "reports.sqlite3")
        env["TRUSTLENS_TEMP_DIR"] = str(media_dir)
        env["TRUSTLENS_PORT"] = str(port)
        process: subprocess.Popen | None = None
        analysis_id = ""
        original_bytes = b""
        try:
            process = start_server(env, base_url)
            original = np.zeros((48, 64, 3), dtype=np.uint8)
            original[6:42, 10:54] = (70, 140, 220)
            ok, encoded = cv2.imencode(".png", original)
            assert ok
            original_bytes = encoded.tobytes()
            response = httpx.post(
                f"{base_url}/api/analyses",
                files={"file": (f"restart-{run_id}.png", original_bytes, "image/png")},
                headers={"Idempotency-Key": f"restart-{run_id}"},
                timeout=30,
            )
            assert response.status_code == 201, response.text
            record = response.json()
            analysis_id = record["analysis_id"]
            expected_hash = hashlib.sha256(original_bytes).hexdigest()
            assert record["report"]["source"]["sha256"] == expected_hash
            assert not list(media_dir.iterdir()), "Temporary media remained after the first process returned."

            stop_server(process)
            process = None
            process = start_server(env, base_url)
            with httpx.Client(base_url=base_url, timeout=10) as client:
                health = client.get("/api/health")
                detail = client.get(f"/api/analyses/{analysis_id}")
                assert health.status_code == 200, health.text
                assert detail.status_code == 200, detail.text
                restored = detail.json()
                assert restored["report"]["source"]["sha256"] == expected_hash
                assert restored["report"]["proposed_outcome"] == "INSUFFICIENT_EVIDENCE_REVIEW"
                assert client.delete(f"/api/analyses/{analysis_id}").status_code == 204
                assert client.get("/api/stats").json()["total"] == 0
            print("process_restart_persistence=PASS")
            print("source_hash_and_report_integrity=PASS")
            print("temporary_media_cleanup=PASS")
        finally:
            stop_server(process)


if __name__ == "__main__":
    main()
