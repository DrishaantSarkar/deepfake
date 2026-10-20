import unittest
from unittest.mock import patch

from trustlens.diagnostics import DiagnosticState, run_media_diagnostics


class DiagnosticsTests(unittest.TestCase):
    def test_structured_report_distinguishes_missing_tools_from_successful_image_checks(self):
        with patch("trustlens.diagnostics.shutil.which", return_value=None):
            report = run_media_diagnostics(timeout_seconds=2)
        statuses = {item.component: item.status for item in report.checks}
        self.assertEqual(statuses["pillow_image_decode_normalization"], DiagnosticState.AVAILABLE)
        self.assertEqual(statuses["numpy_opencv_image_decode"], DiagnosticState.AVAILABLE)
        self.assertEqual(statuses["ffmpeg"], DiagnosticState.MISSING)
        self.assertEqual(statuses["ffprobe"], DiagnosticState.MISSING)
        self.assertEqual(statuses["video_metadata_extraction"], DiagnosticState.MISSING)
        self.assertEqual(statuses["trustlens_video_sampling"], DiagnosticState.MISSING)
        json_ready = report.to_dict()
        self.assertEqual(json_ready["schema_version"], "1.0")
        self.assertTrue(all(isinstance(item["status"], str) for item in json_ready["checks"]))


if __name__ == "__main__":
    unittest.main()
