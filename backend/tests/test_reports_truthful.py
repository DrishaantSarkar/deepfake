"""Tests for reporting integrity, truthful fallbacks, and non-fabricated assessments."""

from pathlib import Path
import unittest
from unittest.mock import MagicMock

from trustlens.ingestion import ingest_upload
from trustlens.service import analyze_upload, validate_analysis_report


class TestReportsTruthful(unittest.TestCase):
    def test_report_schema_contract_distinctions(self):
        """Verify report clearly separates evidence, predictions, status, and limitations."""
        img_path = Path(__file__).parent / "fixtures" / "multimodal" / "media" / "img_real_nature.jpg"
        media = ingest_upload(img_path.read_bytes(), filename="img_real_nature.jpg")

        report = analyze_upload(media, detector=None)
        validate_analysis_report(report)

        # 1. Processing status is distinct from assessment
        self.assertIn("processing_status", report)
        self.assertIn(report["processing_status"], ["SUCCESS", "PARTIAL", "FAILED", "UNAVAILABLE"])

        # 2. Analysis decision/assessment
        self.assertIn("analysis", report)
        self.assertIn("status", report["analysis"])

        # 3. Model availability is explicitly disclosed
        result = report["analysis"]["result"]
        # 3. Model availability is explicitly disclosed
        result = report["analysis"]["result"]
        self.assertIn(result["detector"]["status"], ["UNAVAILABLE", "FAILED"])

        # 4. Limitations and uncertainty are explicitly enumerated
        self.assertIn("limitations", report)
        self.assertIsInstance(report["limitations"], list)
        self.assertGreater(len(report["limitations"]), 0)

        # 5. Supporting observed evidence (frequency bands)
        freq_channel = next((c for c in result["evidence"] if c["source"] == "frequency_descriptor"), None)
        self.assertIsNotNone(freq_channel)
        self.assertIn("energy_fraction_by_band", freq_channel["measured_signal"])

    def test_no_fabricated_confidence_or_verdict_when_model_fails(self):
        """When the ML model fails, the report MUST NOT invent a probability or hardcode real/AI."""
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
        failing_detector.predict.side_effect = ValueError("Corrupted tensor or missing weights")

        img_path = Path(__file__).parent / "fixtures" / "multimodal" / "media" / "img_real_nature.jpg"
        media = ingest_upload(img_path.read_bytes(), filename="img_real_nature.jpg")

        report = analyze_upload(media, detector=failing_detector)
        validate_analysis_report(report)

        # Status must indicate fallback/limitation
        self.assertIn(report["processing_status"], ["PARTIAL", "SUCCESS"])
        result = report["analysis"]["result"]

        # Confidence/verdict must not be fabricated
        self.assertEqual(result.get("proposed_outcome"), "INSUFFICIENT_EVIDENCE_REVIEW")
        self.assertTrue(result.get("human_review_required", True))

        # Limitations explain the inconclusive state
        limitations = report.get("limitations", []) + result.get("limitations", [])
        lim_text = " ".join(limitations)
        self.assertTrue("INCONCLUSIVE" in lim_text or "unavailable" in lim_text.lower())

    def test_fixture_labels_are_not_used_in_production_inference(self):
        """Ensure analyze_upload never checks manifest ground truth to fabricate answers."""
        img_path = Path(__file__).parent / "fixtures" / "multimodal" / "media" / "img_ai_diffusion_pattern.png"
        media = ingest_upload(img_path.read_bytes(), filename="img_ai_diffusion_pattern.png")

        # Without a detector, it must NOT return 'synthetic' or 'likely_ai' just because the fixture is synthetic
        report = analyze_upload(media, detector=None)
        validate_analysis_report(report)

        # It must abstain honestly
        self.assertEqual(report["proposed_outcome"], "INSUFFICIENT_EVIDENCE_REVIEW")
        self.assertTrue(report["human_review_required"])


if __name__ == "__main__":
    from pathlib import Path
    unittest.main()

