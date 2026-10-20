"""Comprehensive tests for multimodal processing across Image, Video, and Audio (BETA)."""

import json
from pathlib import Path
import unittest
from typing import Any
from unittest.mock import MagicMock

from trustlens.audio_analysis import (
    AUDIO_BETA_LABEL,
    AUDIO_BETA_WARNING,
    analyze_audio_file,
)
from trustlens.ingestion import MediaType, ingest_upload
from trustlens.service import analyze_upload, validate_analysis_report


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "multimodal"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


class TestMultimodalPipeline(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        samples = data.get("samples", data)
        self.fixtures = {}
        for e in samples:
            sid = e.get("sample_id", "")
            self.fixtures[sid] = e
            self.fixtures[sid.lower()] = e
            self.fixtures[sid.upper()] = e
            fn = e.get("file_name", "")
            if fn:
                self.fixtures[fn] = e
                self.fixtures[fn.lower()] = e
            digits = "".join(c for c in sid if c.isdigit())
            if digits:
                num = int(digits)
                gt = "real" if e["ground_truth"] == "real" else "ai"
                mod = "img" if e["modality"] == "image" else ("vid" if e["modality"] == "video" else "aud")
                for fmt in (f"{mod}_{gt}_{num}", f"{mod}_{gt}_{num:02d}", f"{mod}_{gt}_{num:03d}"):
                    self.fixtures[fmt] = e
                    self.fixtures[fmt.lower()] = e
                    self.fixtures[fmt.upper()] = e

    def get_fixture_entry(self, key: str) -> dict[str, Any]:
        if key in self.fixtures:
            return self.fixtures[key]
        if key.lower() in self.fixtures:
            return self.fixtures[key.lower()]
        if key.upper() in self.fixtures:
            return self.fixtures[key.upper()]
        for k, v in self.fixtures.items():
            if key.lower() in k.lower() or key.lower() in v.get("file_name", "").lower():
                return v
        raise KeyError(f"Fixture {key} not found among: {list(self.fixtures.keys())[:10]}")

    def get_fixture_path(self, key: str) -> Path:
        entry = self.get_fixture_entry(key)
        return FIXTURES_DIR / entry["relative_path"]

    def get_fixture_hash(self, key: str) -> str:
        entry = self.get_fixture_entry(key)
        return str(entry.get("sha256") or entry.get("file_hash") or "")

    # ---------------------------------------------------------
    # A. IMAGE FIXTURES & PIPELINE
    # ---------------------------------------------------------
    def test_real_image_fixture_ingestion_and_analysis(self):
        img_path = self.get_fixture_path("IMG_REAL_001")
        with open(img_path, "rb") as f:
            content = f.read()

        ingested = ingest_upload(content, filename="IMG_REAL_001.jpg")
        self.assertEqual(ingested.detected_type, MediaType.IMAGE)
        self.assertEqual(ingested.source_sha256, self.get_fixture_hash("IMG_REAL_001"))

        # Run analysis through service
        report = analyze_upload(ingested, detector=None)
        validate_analysis_report(report)

        # Integrity check: model is unavailable -> report abstains honestly
        self.assertIn(report["processing_status"], ["SUCCESS", "PARTIAL"])
        self.assertEqual(report["proposed_outcome"], "INSUFFICIENT_EVIDENCE_REVIEW")
        self.assertTrue(report["human_review_required"])
        # Deterministic frequency evidence is present
        result = report["analysis"]["result"]
        freq_channel = next((c for c in result["evidence"] if c["source"] == "frequency_descriptor"), None)
        self.assertIsNotNone(freq_channel)
        self.assertIn("energy_fraction_by_band", freq_channel["measured_signal"])

    def test_synthetic_image_fixture_ingestion_and_analysis(self):
        img_path = self.get_fixture_path("IMG_AI_001")
        with open(img_path, "rb") as f:
            content = f.read()

        ingested = ingest_upload(content, filename=img_path.name)
        self.assertEqual(ingested.detected_type, MediaType.IMAGE)
        self.assertEqual(ingested.source_sha256, self.get_fixture_hash("IMG_AI_001"))

        report = analyze_upload(ingested, detector=None)
        validate_analysis_report(report)
        self.assertIn(report["processing_status"], ["SUCCESS", "PARTIAL"])
        self.assertEqual(report["proposed_outcome"], "INSUFFICIENT_EVIDENCE_REVIEW")

    # ---------------------------------------------------------
    # B. VIDEO FIXTURES & PIPELINE
    # ---------------------------------------------------------
    def test_real_video_fixture_ingestion(self):
        vid_path = self.get_fixture_path("VID_REAL_001")
        with open(vid_path, "rb") as f:
            content = f.read()

        ingested = ingest_upload(content, filename=vid_path.name)
        self.assertEqual(ingested.detected_type, MediaType.VIDEO)
        self.assertEqual(ingested.source_sha256, self.get_fixture_hash("VID_REAL_001"))

        report = analyze_upload(ingested, detector=None)
        validate_analysis_report(report)
        self.assertIn(report["processing_status"], ["SUCCESS", "PARTIAL"])
        result = report["analysis"]["result"]
        self.assertIn("frames", result)

    def test_synthetic_video_fixture_ingestion(self):
        vid_path = self.get_fixture_path("VID_AI_001")
        with open(vid_path, "rb") as f:
            content = f.read()

        ingested = ingest_upload(content, filename=vid_path.name)
        self.assertEqual(ingested.detected_type, MediaType.VIDEO)
        self.assertEqual(ingested.source_sha256, self.get_fixture_hash("VID_AI_001"))

        report = analyze_upload(ingested, detector=None)
        validate_analysis_report(report)
        self.assertIn(report["processing_status"], ["SUCCESS", "PARTIAL"])

    # ---------------------------------------------------------
    # C. AUDIO (BETA) FIXTURES & PIPELINE
    # ---------------------------------------------------------
    def test_audio_beta_markings_and_disclaimers(self):
        self.assertEqual(AUDIO_BETA_LABEL, "AUDIO DETECTION — BETA")
        self.assertIn("experimental", AUDIO_BETA_WARNING.lower())
        self.assertIn("not be treated as definitive proof", AUDIO_BETA_WARNING.lower())

    def test_real_audio_fixture_analysis(self):
        aud_path = self.get_fixture_path("AUD_REAL_001")
        features = analyze_audio_file(aud_path)

        self.assertIn("signal_descriptors", features)
        self.assertIn("technical_metadata", features)
        self.assertEqual(features["beta_label"], AUDIO_BETA_LABEL)
        self.assertEqual(features["beta_warning"], AUDIO_BETA_WARNING)

        sd = features["signal_descriptors"]
        self.assertEqual(sd["sample_rate_hz"], 16000)
        self.assertEqual(sd["channels"], 1)
        self.assertGreater(sd["duration_seconds"], 0.5)
        self.assertGreater(sd["rms_energy"], 0)
        self.assertGreaterEqual(sd["zero_crossing_rate"], 0)

    def test_synthetic_audio_fixture_analysis(self):
        aud_path = self.get_fixture_path("AUD_AI_001")
        features = analyze_audio_file(aud_path)

        self.assertIn("signal_descriptors", features)
        sd = features["signal_descriptors"]
        self.assertEqual(sd["sample_rate_hz"], 16000)
        self.assertGreater(sd["rms_energy"], 0)

    def test_audio_upload_through_service(self):
        aud_path = self.get_fixture_path("AUD_REAL_001")
        with open(aud_path, "rb") as f:
            content = f.read()

        ingested = ingest_upload(content, filename="AUD_REAL_001.wav")
        self.assertEqual(ingested.detected_type, MediaType.AUDIO)

        report = analyze_upload(ingested, detector=None)
        validate_analysis_report(report)

        # Audio reports maintain schema 1.1 invariant: analysis.result must be None
        self.assertIsNone(report["analysis"]["result"])
        self.assertEqual(report["processing_status"], "UNAVAILABLE")

        # Must include beta notices and limitations
        limitations_text = " ".join(report.get("limitations", []))
        self.assertIn("AUDIO DETECTION — BETA", limitations_text)
        self.assertIn("experimental", limitations_text)

    # ---------------------------------------------------------
    # D. MODEL FAILURE INJECTION & CONTROLLED FALLBACK
    # ---------------------------------------------------------
    def test_image_model_exception_triggers_truthful_fallback(self):
        # Create a mock detector that throws a runtime error
        from trustlens.image_analysis import DetectorDescriptor
        desc = DetectorDescriptor(
            name="mock_failing_detector",
            version="1.0.0",
            supported_inputs=("RGB Pillow image",),
            preprocessing="none",
            output_labels=("real", "synthetic"),
            score_semantics="raw logits",
            resource_requirements="cpu",
            limitations=("mock",),
            evaluation_status="EVALUATED",
            calibration_status="CALIBRATED",
            label_space="synthetic_vs_natural",
        )
        failing_detector = MagicMock()
        failing_detector.descriptor = desc
        failing_detector.is_available.return_value = True
        failing_detector.predict.side_effect = RuntimeError("GPU out of memory or model corrupted")

        img_path = self.get_fixture_path("IMG_REAL_001")
        with open(img_path, "rb") as f:
            content = f.read()

        ingested = ingest_upload(content, filename="IMG_REAL_001.jpg")

        # analyze_upload should NOT crash; it must safely fall back
        report = analyze_upload(ingested, detector=failing_detector)
        validate_analysis_report(report)

        # Honest reporting: status is PARTIAL or SUCCESS, proposed outcome abstains
        self.assertIn(report["processing_status"], ["PARTIAL", "SUCCESS"])
        self.assertEqual(report["proposed_outcome"], "INSUFFICIENT_EVIDENCE_REVIEW")

        # Result contains fallback frequency evidence
        result = report["analysis"]["result"]
        freq_channel = next((c for c in result["evidence"] if c["source"] == "frequency_descriptor"), None)
        self.assertIsNotNone(freq_channel)
        self.assertIn("energy_fraction_by_band", freq_channel["measured_signal"])

        # Limitations explain the inconclusive state
        limitations = report.get("limitations", []) + result.get("limitations", [])
        lim_text = " ".join(limitations)
        self.assertTrue("INCONCLUSIVE" in lim_text or "unavailable" in lim_text.lower())


if __name__ == "__main__":
    unittest.main()
