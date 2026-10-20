import io
import unittest

from PIL import Image

from trustlens.image_analysis import (
    DetectorDescriptor,
    DetectorOutput,
    analyze_image,
)
from trustlens.ingestion import IngestionError, MediaType, ProcessingStatus, ingest_media


from pathlib import Path

PHOTO_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "multimodal" / "media" / "img_real_portrait.jpg"
)


def get_test_photo_bytes() -> bytes:
    if PHOTO_FIXTURE_PATH.is_file():
        return PHOTO_FIXTURE_PATH.read_bytes()
    img = Image.new("RGB", (64, 64), (135, 160, 185))
    stream = io.BytesIO()
    img.save(stream, format="JPEG")
    return stream.getvalue()


png_bytes = get_test_photo_bytes


class TestDetector:
    descriptor = DetectorDescriptor(
        name="test-only",
        version="0",
        supported_inputs=("RGB Pillow image",),
        preprocessing="none",
        output_labels=("synthetic", "real"),
        score_semantics="test raw scores only",
        resource_requirements="none",
        limitations=("Test fixture; not a real detector.",),
        evaluation_status="NOT_EVALUATED",
        calibration_status="NOT_CALIBRATED",
    )

    def predict(self, image):
        return DetectorOutput(
            status=ProcessingStatus.SUCCESS,
            raw_scores={"synthetic": 2.7, "real": -1.1},
            predicted_label="synthetic",
        )


class ImageAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.media = ingest_media(io.BytesIO(get_test_photo_bytes()), "portrait.jpg")

    def tearDown(self):
        self.media.cleanup()

    def test_without_model_abstains_and_keeps_frequency_separate(self):
        assessment = analyze_image(self.media)
        self.assertEqual(assessment.proposed_outcome, "INSUFFICIENT_EVIDENCE_REVIEW")
        self.assertTrue(assessment.human_review_required)
        self.assertEqual(assessment.detector["status"], "UNAVAILABLE")
        by_source = {item.source: item for item in assessment.evidence}
        self.assertEqual(by_source["frequency_descriptor"].status, ProcessingStatus.SUCCESS)
        self.assertIn("energy_fraction_by_band", by_source["frequency_descriptor"].measured_signal)
        self.assertEqual(by_source["spatial_detector"].status, ProcessingStatus.UNAVAILABLE)
        self.assertEqual(assessment.localization["regions"], [])
        self.assertEqual(assessment.to_dict()["processing_status"], "PARTIAL")

    def test_detector_raw_output_is_preserved_without_probability_claim(self):
        assessment = analyze_image(self.media, TestDetector())
        self.assertEqual(assessment.detector["raw_scores"]["synthetic"], 2.7)
        self.assertEqual(assessment.detector["score_semantics"], "test raw scores only")
        self.assertEqual(assessment.detector["calibration_status"], "NOT_CALIBRATED")
        # Model output alone does not bypass evidence fusion or calibration.
        self.assertEqual(assessment.proposed_outcome, "INSUFFICIENT_EVIDENCE_REVIEW")

    def test_rejects_non_image_media(self):
        self.media.detected_type = MediaType.VIDEO
        with self.assertRaises(ValueError):
            analyze_image(self.media)

    def test_invalid_input_cannot_reach_analysis(self):
        with self.assertRaises(IngestionError):
            ingest_media(io.BytesIO(b"bad"), "bad.png")

    def test_alpha_is_preserved_in_source_artifact_and_composited_for_analysis(self):
        image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        media = ingest_media(io.BytesIO(stream.getvalue()), "transparent.png")
        try:
            with Image.open(media.normalized_image_path) as normalized:
                self.assertEqual(normalized.mode, "RGBA")
            assessment = analyze_image(media)
            self.assertTrue(assessment.preprocessing["alpha_present"])
            self.assertIn("composited onto white", assessment.preprocessing["alpha_policy"])
        finally:
            media.cleanup()


if __name__ == "__main__":
    unittest.main()
