import io
import json
import copy
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from trustlens.ingestion import IngestionError, MediaType, ProcessingStatus
from trustlens.service import REPORT_SCHEMA_VERSION, analyze_upload, validate_analysis_report


class AnalysisServiceTests(unittest.TestCase):
    def test_image_upload_returns_versioned_serializable_fused_report(self):
        stream = io.BytesIO()
        Image.new("RGB", (24, 20), (20, 60, 120)).save(stream, format="PNG")
        original = stream.getvalue()
        upload = io.BytesIO(original)
        temporary_root = Path(".trustlens-tmp")
        temporary_root.mkdir(exist_ok=True)
        before = {path.name for path in temporary_root.iterdir()}
        report = analyze_upload(upload, "photo.png")
        after = {path.name for path in temporary_root.iterdir()}
        body = report.to_dict()
        serialized = json.dumps(body)
        self.assertEqual(report.schema_version, REPORT_SCHEMA_VERSION)
        self.assertEqual(report.processing_status, ProcessingStatus.PARTIAL)
        self.assertEqual(body["source"]["media_type"], MediaType.IMAGE.value)
        self.assertEqual(body["source"]["sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(body["analysis"]["kind"], "image")
        self.assertEqual(body["analysis"]["result"]["provenance"]["content_credentials"]["status"], "UNAVAILABLE")
        self.assertEqual(body["analysis"]["result"]["provenance"]["watermark"]["status"], "UNAVAILABLE")
        self.assertEqual(body["analysis"]["result"]["provenance"]["metadata"]["status"], "DETECTED")
        evidence_sources = {entry["evidence_source"] for entry in body["fusion"]["evidence"]}
        self.assertTrue({"metadata_inspection", "content_credentials", "watermark"}.issubset(evidence_sources))
        self.assertIsNotNone(body["fusion"])
        self.assertTrue(body["human_review_required"])
        self.assertEqual(body["proposed_outcome"], "INSUFFICIENT_EVIDENCE_REVIEW")
        validate_analysis_report(body)
        self.assertFalse(upload.closed)
        self.assertEqual(after, before)
        self.assertNotIn(".trustlens-tmp", serialized)
        self.assertNotIn(str(Path.cwd()), serialized)

    def test_report_validator_rejects_inconsistent_hash_and_schema(self):
        stream = io.BytesIO()
        Image.new("RGB", (8, 8), (1, 2, 3)).save(stream, format="PNG")
        body = analyze_upload(io.BytesIO(stream.getvalue()), "photo.png").to_dict()
        bad_hash = copy.deepcopy(body)
        bad_hash["source"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_analysis_report(bad_hash)
        bad_schema = copy.deepcopy(body)
        bad_schema["schema_version"] = "future"
        with self.assertRaises(ValueError):
            validate_analysis_report(bad_schema)
        bad_filename = copy.deepcopy(body)
        bad_filename["source"]["filename"] = "../../private.png"
        with self.assertRaises(ValueError):
            validate_analysis_report(bad_filename)

    def test_report_has_reproducibility_metadata_and_valid_evidence_graph(self):
        stream = io.BytesIO()
        Image.new("RGB", (8, 8), (1, 2, 3)).save(stream, format="PNG")
        body = analyze_upload(io.BytesIO(stream.getvalue()), "photo.png").to_dict()
        self.assertEqual(body["schema_version"], "1.1")
        self.assertTrue(body["generated_at"].endswith("Z"))
        self.assertEqual(body["producer"]["version"], "LOCAL_UNVERSIONED")
        graph = body["evidence_graph"]
        self.assertEqual(graph["schema_version"], "1.0")
        self.assertEqual({node["type"] for node in graph["nodes"]}, {"source", "report", "assessment"})
        validate_analysis_report(body)
        broken = copy.deepcopy(body)
        broken["evidence_graph"]["edges"][0]["to"] = "source:missing"
        with self.assertRaises(ValueError):
            validate_analysis_report(broken)

    def test_report_validator_keeps_legacy_v1_reports_readable(self):
        stream = io.BytesIO()
        Image.new("RGB", (8, 8), (1, 2, 3)).save(stream, format="PNG")
        body = analyze_upload(io.BytesIO(stream.getvalue()), "photo.png").to_dict()
        for field in ("generated_at", "producer", "evidence_graph"):
            body.pop(field)
        body["schema_version"] = "1.0"
        validate_analysis_report(body)

    def test_invalid_upload_raises_ingestion_error(self):
        with self.assertRaises(IngestionError):
            analyze_upload(io.BytesIO(b"not media"), "unknown.bin")

    def test_unexpected_analysis_error_returns_safe_failed_report_and_cleans_upload(self):
        stream = io.BytesIO()
        Image.new("RGB", (8, 8), (1, 2, 3)).save(stream, format="PNG")
        root = Path(".trustlens-tmp")
        root.mkdir(exist_ok=True)
        before = {path.name for path in root.iterdir()}
        with patch("trustlens.service.analyze_image", side_effect=RuntimeError("private local path")):
            report = analyze_upload(io.BytesIO(stream.getvalue()), "failure.png")
        after = {path.name for path in root.iterdir()}
        body = report.to_dict()
        self.assertEqual(report.processing_status, ProcessingStatus.FAILED)
        self.assertEqual(body["analysis"]["status"], "FAILED")
        self.assertEqual(body["analysis"]["failure_stage"], "analysis")
        self.assertIsNone(body["analysis"]["result"])
        self.assertIsNone(body["fusion"])
        self.assertNotIn("private local path", json.dumps(body))
        self.assertEqual(before, after)
        validate_analysis_report(body)

    def test_audio_upload_is_explicitly_unavailable_and_not_fused(self):
        audio_header = b"RIFF" + (4).to_bytes(4, "little") + b"WAVE"
        report = analyze_upload(io.BytesIO(audio_header), "future.wav")
        body = report.to_dict()
        self.assertEqual(report.processing_status, ProcessingStatus.UNAVAILABLE)
        self.assertEqual(body["analysis"]["kind"], "audio")
        self.assertIsNone(body["fusion"])
        self.assertEqual(body["proposed_outcome"], "INSUFFICIENT_EVIDENCE_REVIEW")
        self.assertTrue(body["human_review_required"])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "real FFmpeg/ffprobe not installed")
class RealVideoServiceTests(unittest.TestCase):
    def test_video_upload_runs_through_report_and_fusion(self):
        temp_root = Path(".trustlens-tmp")
        temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="service-e2e-", dir=temp_root) as directory:
            clip_path = Path(directory) / "clip.mp4"
            subprocess.run(
                [shutil.which("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "testsrc=size=64x48:rate=4:duration=1",
                 "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(clip_path)],
                check=True, capture_output=True, text=True, timeout=30,
            )
            with clip_path.open("rb") as upload:
                report = analyze_upload(upload, "clip.mp4")
            body = report.to_dict()
            self.assertEqual(body["source"]["media_type"], "video")
            self.assertEqual(body["analysis"]["kind"], "video")
            self.assertIsNotNone(body["fusion"])
            self.assertTrue(body["analysis"]["result"]["frames"])
            video_evidence = {entry["evidence_source"] for entry in body["fusion"]["evidence"]}
            self.assertIn("temporal_analysis", video_evidence)
            self.assertEqual(body["analysis"]["result"]["sampling"]["requested_interval_seconds"], 5.0)
            self.assertEqual(body["analysis"]["result"]["sampling"]["interval_seconds"], 1.0)
            self.assertTrue(any("temporary" in note for note in body["limitations"]))
            self.assertTrue(body["human_review_required"])


if __name__ == "__main__":
    unittest.main()
