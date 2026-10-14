import io
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from trustlens.ingestion import MediaType, ProcessingStatus, ingest_media
from trustlens.video_analysis import VideoSamplingConfig, analyze_video


def fake_mp4_header():
    return (20).to_bytes(4, "big") + b"ftyp" + b"isom" + b"\x00\x00\x02\x00" + b"mdat"


class VideoAnalysisTests(unittest.TestCase):
    def test_sampling_config_rejects_unbounded_or_invalid_values(self):
        with self.assertRaises(ValueError):
            VideoSamplingConfig(interval_seconds=0)
        with self.assertRaises(ValueError):
            VideoSamplingConfig(max_frames=0)
        for field, value in (
            ("interval_seconds", math.nan),
            ("max_duration_seconds", math.inf),
            ("timeout_seconds", -math.inf),
            ("interval_seconds", True),
            ("max_frames", 1.5),
            ("max_frame_side", False),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                VideoSamplingConfig(**{field: value})

    def test_without_verified_metadata_returns_unavailable(self):
        media = ingest_media(io.BytesIO(fake_mp4_header()), "clip.mp4")
        try:
            self.assertEqual(media.detected_type, MediaType.VIDEO)
            report = analyze_video(media)
            self.assertEqual(report.processing_status, ProcessingStatus.UNAVAILABLE)
            self.assertEqual(report.sampling["status"], "UNAVAILABLE")
            self.assertEqual(report.frames, [])
            self.assertTrue(report.human_review_required)
            self.assertEqual(report.proposed_outcome, "INSUFFICIENT_EVIDENCE_REVIEW")
            self.assertIn("ffprobe", report.errors[0])
        finally:
            media.cleanup()

    def test_verified_metadata_but_missing_ffmpeg_is_unavailable(self):
        media = ingest_media(io.BytesIO(fake_mp4_header()), "clip.mp4")
        try:
            media.metadata = {"duration_seconds": 5.0, "width": 16, "height": 16, "frame_rate": 30.0}
            with patch("trustlens.video_analysis.shutil.which", return_value=None):
                report = analyze_video(media)
            self.assertEqual(report.processing_status, ProcessingStatus.UNAVAILABLE)
            self.assertIn("ffmpeg", report.errors[0])
        finally:
            media.cleanup()

    def test_sample_timestamp_links_to_frame_image_assessment(self):
        media = ingest_media(io.BytesIO(fake_mp4_header()), "clip.mp4")
        try:
            media.metadata = {"duration_seconds": 5.0, "width": 16, "height": 16, "frame_rate": 30.0}

            def fake_ffmpeg(command, **kwargs):
                output_path = command[-1].replace("%06d", "000000")
                Image.new("RGB", (16, 16), (90, 120, 150)).save(output_path, format="PNG")
                return SimpleNamespace(returncode=0, stderr="[Parsed_showinfo] n:0 pts_time:0.000000", stdout="")

            with patch("trustlens.video_analysis.shutil.which", return_value="ffmpeg"), patch(
                "trustlens.video_analysis.subprocess.run", side_effect=fake_ffmpeg
            ):
                report = analyze_video(media)
            self.assertEqual(report.sampling["sampled_count"], 1)
            self.assertEqual(report.frames[0].timestamp_seconds, 0.0)
            self.assertIsNone(report.frames[0].source_frame_index)
            self.assertEqual(report.frames[0].image_assessment["source_id"], f"{media.source_id}:sample:0")
            self.assertEqual(report.frames[0].image_assessment["proposed_outcome"], "INSUFFICIENT_EVIDENCE_REVIEW")
            self.assertEqual(report.processing_status, ProcessingStatus.PARTIAL)
            self.assertEqual(report.temporal_analysis["status"], "UNAVAILABLE")
        finally:
            media.cleanup()

    def test_temporal_measurement_compares_samples_without_classifying_them(self):
        media = ingest_media(io.BytesIO(fake_mp4_header()), "clip.mp4")
        try:
            media.metadata = {"duration_seconds": 5.0, "width": 16, "height": 16, "frame_rate": 30.0}

            def fake_ffmpeg(command, **kwargs):
                Image.new("RGB", (16, 16), (0, 0, 0)).save(command[-1].replace("%06d", "000000"), format="PNG")
                Image.new("RGB", (16, 16), (255, 255, 255)).save(command[-1].replace("%06d", "000001"), format="PNG")
                return SimpleNamespace(returncode=0, stderr="pts_time:0.000000 pts_time:5.000000", stdout="")

            with patch("trustlens.video_analysis.shutil.which", return_value="ffmpeg"), patch(
                "trustlens.video_analysis.subprocess.run", side_effect=fake_ffmpeg
            ):
                report = analyze_video(media)
            temporal = report.temporal_analysis
            self.assertEqual(temporal["status"], "PARTIAL")
            self.assertEqual(len(temporal["pairs"]), 1)
            self.assertEqual(temporal["pairs"][0]["mean_absolute_luma_difference_0_to_1"], 1.0)
            self.assertIn("no manipulation inference", temporal["interpretation"])
        finally:
            media.cleanup()

    def test_ffmpeg_timeout_is_a_failed_processing_result(self):
        from subprocess import TimeoutExpired

        media = ingest_media(io.BytesIO(fake_mp4_header()), "clip.mp4")
        try:
            media.metadata = {"duration_seconds": 5.0, "width": 16, "height": 16, "frame_rate": 30.0}
            with patch("trustlens.video_analysis.shutil.which", return_value="ffmpeg"), patch(
                "trustlens.video_analysis.subprocess.run", side_effect=TimeoutExpired("ffmpeg", 1)
            ):
                report = analyze_video(media)
            self.assertEqual(report.processing_status, ProcessingStatus.FAILED)
            self.assertIn("timeout", report.errors[0].lower())
            self.assertEqual(report.frames, [])
        finally:
            media.cleanup()

    def test_ffmpeg_nonzero_exit_does_not_create_successful_analysis(self):
        media = ingest_media(io.BytesIO(fake_mp4_header()), "clip.mp4")
        try:
            media.metadata = {"duration_seconds": 5.0, "width": 16, "height": 16, "frame_rate": 30.0}
            with patch("trustlens.video_analysis.shutil.which", return_value="ffmpeg"), patch(
                "trustlens.video_analysis.subprocess.run",
                return_value=SimpleNamespace(returncode=1, stderr="decoder error", stdout=""),
            ):
                report = analyze_video(media)
            self.assertEqual(report.processing_status, ProcessingStatus.FAILED)
            self.assertEqual(report.sampling["status"], "FAILED")
            self.assertEqual(report.proposed_outcome, "INSUFFICIENT_EVIDENCE_REVIEW")
        finally:
            media.cleanup()

    def test_rejects_image_input(self):
        class ImageLike:
            detected_type = MediaType.IMAGE

        with self.assertRaises(ValueError):
            analyze_video(ImageLike())


if __name__ == "__main__":
    unittest.main()
