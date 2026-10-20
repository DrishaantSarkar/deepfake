import unittest

from trustlens.provenance import assess_provenance


class ProvenanceAssessmentTests(unittest.TestCase):
    def test_reports_named_metadata_but_does_not_claim_signature_verification(self):
        result = assess_provenance("image", {
            "format": "JPEG", "width": 10, "height": 8,
            "metadata_status": "DETECTED", "exif_status": "DETECTED",
            "exif_named": {"DateTimeOriginal": "2024:03:04 05:06:07", "Make": "Camera maker"},
            "exif": {"36867": "2024:03:04 05:06:07", "271": "Camera maker"},
        })
        metadata = result["metadata"]
        self.assertEqual(metadata["status"], "DETECTED")
        self.assertEqual(metadata["observed_fields"]["exif_named"]["Make"], "Camera maker")
        self.assertEqual(metadata["exif_status"], "DETECTED")
        self.assertEqual(result["content_credentials"]["status"], "UNAVAILABLE")
        self.assertEqual(result["watermark"]["status"], "UNAVAILABLE")

    def test_distinguishes_missing_from_failed_video_metadata_probe(self):
        missing = assess_provenance("video", {})
        failed = assess_provenance("video", {}, parser_warnings=["ffprobe timed out; metadata was not verified."])
        unavailable = assess_provenance("video", {}, parser_warnings=["ffprobe is unavailable."])
        self.assertEqual(missing["metadata"]["status"], "MISSING")
        self.assertEqual(failed["metadata"]["status"], "ERROR")
        self.assertEqual(unavailable["metadata"]["status"], "UNAVAILABLE")
        self.assertTrue(failed["metadata"]["parser_warnings"])

    def test_rejects_unknown_media_type_and_non_object_metadata(self):
        with self.assertRaises(ValueError):
            assess_provenance("document", {})
        with self.assertRaises(ValueError):
            assess_provenance("image", None)


if __name__ == "__main__":
    unittest.main()
