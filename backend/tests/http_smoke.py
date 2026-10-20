"""Real-loopback HTTP smoke workflow; requires a running TRUSTLENS server and FFmpeg."""

from __future__ import annotations

import json
import hashlib
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import cv2
import httpx
import numpy as np


BASE_URL = os.environ.get("TRUSTLENS_BASE_URL", "http://127.0.0.1:8765")


def main() -> None:
    token = uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix="trustlens-http-smoke-") as temp:
        temp_path = Path(temp)
        video_path = temp_path / f"{token}-sample.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "testsrc=size=64x48:rate=4:duration=1", "-an", "-c:v", "mpeg4",
            "-pix_fmt", "yuv420p", str(video_path),
        ], check=True, capture_output=True, text=True)

        baseline_total = 0
        created_ids: list[str] = []
        results: dict[str, object] = {}
        with httpx.Client(base_url=BASE_URL, timeout=45) as client:
            health = client.get("/api/health")
            assert health.status_code == 200 and health.json()["status"] == "available", health.text
            caps = client.get("/api/capabilities").json()
            detector_available = caps["image"]["trained_detector"] == "available"
            assert caps["video"]["temporal_classifier"] == "unavailable"
            baseline_total = client.get("/api/stats").json()["total"]
            try:
                image = np.zeros((48, 64, 3), dtype=np.uint8)
                image[8:40, 12:52] = (25, 120, 210)
                ok, encoded = cv2.imencode(".png", image)
                assert ok
                image_key = f"smoke-image-{token}"
                response = client.post(
                    "/api/analyses",
                    files={"file": (f"{token}-fixture.png", encoded.tobytes(), "image/png")},
                    headers={"Idempotency-Key": image_key},
                )
                assert response.status_code == 201, response.text
                image_record = response.json()
                created_ids.append(image_record["analysis_id"])
                report = image_record["report"]
                assert report["source"]["sha256"] == hashlib.sha256(encoded.tobytes()).hexdigest()
                assert report["proposed_outcome"] == "INSUFFICIENT_EVIDENCE_REVIEW"
                expected_detector_status = "SUCCESS" if detector_available else "UNAVAILABLE"
                assert report["analysis"]["result"]["detector"]["status"] == expected_detector_status
                replay = client.post(
                    "/api/analyses",
                    files={"file": (f"{token}-fixture.png", encoded.tobytes(), "image/png")},
                    headers={"Idempotency-Key": image_key},
                )
                assert replay.status_code == 200 and replay.json()["analysis_id"] == image_record["analysis_id"]

                with video_path.open("rb") as source:
                    video_response = client.post(
                        "/api/analyses",
                        files={"file": (video_path.name, source, "video/mp4")},
                        headers={"Idempotency-Key": f"smoke-video-{token}"},
                    )
                assert video_response.status_code == 201, video_response.text
                video_record = video_response.json()
                created_ids.append(video_record["analysis_id"])
                video_report = video_record["report"]
                assert video_report["proposed_outcome"] == "INSUFFICIENT_EVIDENCE_REVIEW"
                assert video_report["analysis"]["result"]["frames"]

                invalid = client.post("/api/analyses", files={"file": (f"{token}-bad.png", b"not media", "image/png")})
                assert invalid.status_code == 422, invalid.text
                history = client.get("/api/analyses", params={"q": token, "limit": 10}).json()
                assert history["total"] == 2

                for record in (image_record, video_record):
                    analysis_id = record["analysis_id"]
                    assert client.get(f"/api/analyses/{analysis_id}").status_code == 200
                    assert client.get(f"/api/analyses/{analysis_id}/evidence").status_code == 200
                    downloaded = client.get(f"/api/analyses/{analysis_id}/report")
                    assert downloaded.status_code == 200 and "attachment" in downloaded.headers.get("content-disposition", "")

                results = {
                    "health_and_capabilities": "PASS",
                    "image_hash_and_truthful_detector_unavailable": "PASS",
                    "idempotency_replay": "PASS",
                    "video_decode_and_sampled_frames": "PASS",
                    "invalid_media_rejected_without_record": "PASS",
                    "history_detail_evidence_and_report_download": "PASS",
                }
            finally:
                for analysis_id in created_ids:
                    client.delete(f"/api/analyses/{analysis_id}")
            assert client.get("/api/stats").json()["total"] == baseline_total
        temp_root = os.environ.get("TRUSTLENS_TEMP_DIR")
        if temp_root:
            leftovers = list(Path(temp_root).glob("trustlens-*"))
            assert not leftovers, f"Temporary media artifacts remain: {leftovers}"
        results["record_cleanup_and_temp_media_cleanup"] = "PASS"
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
