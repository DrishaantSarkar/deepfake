import io
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from trustlens.evidence_fusion import fuse_reports
from trustlens.image_analysis import analyze_image
from trustlens.ingestion import ingest_media
from trustlens.video_analysis import VideoSamplingConfig, analyze_video


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def image_report(source_id="img-1", digest=HASH_A, label="synthetic", *, label_space=None, correlation_group=None, score=2.7):
    detector = {
        "status": "SUCCESS",
        "model": {"name": "fixture", "version": "1", "output_labels": ["synthetic", "real"]},
        "label_space": label_space,
        "correlation_group": correlation_group,
    }
    return {
        "source_id": source_id, "source_sha256": digest, "media_type": "image", "processing_status": "PARTIAL",
        "detector": detector,
        "evidence": [{
            "source": "whole_image_detector", "method": "fixture", "method_version": "1",
            "status": "SUCCESS", "measured_signal": {"predicted_label": label, "raw_scores": {label: score}},
            "output_semantics": "raw score", "limitations": [], "error": None,
        }],
    }


class EvidenceFusionTests(unittest.TestCase):
    def test_empty_fusion_abstains_without_score_aggregation(self):
        result = fuse_reports()
        self.assertEqual(result.proposed_outcome, "INSUFFICIENT_EVIDENCE_REVIEW")
        self.assertEqual(result.aggregation_method, "none")
        self.assertFalse(result.calibrated)
        self.assertTrue(result.human_review_required)

    def test_preserves_raw_evidence_and_does_not_average_scores(self):
        result = fuse_reports(image_report())
        item = result.evidence[0]
        self.assertEqual(item.measured_signal["raw_scores"]["synthetic"], 2.7)
        self.assertEqual(result.processing_status, "PARTIAL")
        self.assertEqual(result.conflicts, [])
        self.assertEqual(json.loads(json.dumps(result.to_dict()))["evidence"][0]["status"], "SUCCESS")

    def test_missing_label_space_does_not_create_conflict(self):
        result = fuse_reports(image_report(label="synthetic"), image_report("img-2", HASH_B, "real"))
        self.assertEqual(result.conflicts, [])

    def test_distinct_label_spaces_do_not_create_conflict(self):
        result = fuse_reports(
            image_report("subject", HASH_A, "synthetic", label_space="space-a", correlation_group="model-a"),
            image_report("subject", HASH_B, "real", label_space="space-b", correlation_group="model-b"),
        )
        self.assertEqual(result.conflicts, [])

    def test_explicit_comparable_independent_labels_flag_conflict(self):
        result = fuse_reports(
            image_report("subject", HASH_A, "synthetic", label_space="authenticity-v1", correlation_group="model-a"),
            image_report("subject", HASH_B, "real", label_space="authenticity-v1", correlation_group="model-b"),
        )
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(set(result.conflicts[0]["labels"]), {"synthetic", "real"})
        self.assertEqual(result.proposed_outcome, "INSUFFICIENT_EVIDENCE_REVIEW")

    def test_repeated_correlation_group_does_not_flag_conflict(self):
        result = fuse_reports(
            image_report("subject", HASH_A, "synthetic", label_space="authenticity-v1", correlation_group="shared"),
            image_report("subject", HASH_B, "real", label_space="authenticity-v1", correlation_group="shared"),
        )
        self.assertEqual(result.conflicts, [])

    def test_incompatible_label_vocabularies_do_not_flag_conflict(self):
        second = image_report("subject", HASH_B, "real", label_space="authenticity-v1", correlation_group="model-b")
        second["detector"]["model"]["output_labels"] = ["real", "unknown"]
        result = fuse_reports(
            image_report("subject", HASH_A, "synthetic", label_space="authenticity-v1", correlation_group="model-a"),
            second,
        )
        self.assertEqual(result.conflicts, [])

    def test_successful_detector_requires_model_identity_and_labels(self):
        report = image_report(label_space="auth-v1", correlation_group="model-a")
        report["detector"]["model"].pop("version")
        with self.assertRaises(ValueError):
            fuse_reports(report)

    def test_failed_detector_is_preserved_as_failed_not_prediction(self):
        report = image_report()
        report["detector"]["status"] = "FAILED"
        channel = report["evidence"][0]
        channel["status"] = "FAILED"
        channel["measured_signal"] = {"predicted_label": None, "raw_scores": None}
        channel["error"] = "inference failed"
        report["errors"] = ["detector execution failed"]
        result = fuse_reports(report)
        self.assertEqual(result.evidence[0].status, "FAILED")
        self.assertEqual(result.evidence[0].error, "inference failed")
        self.assertEqual(result.conflicts, [])
        self.assertEqual(result.processing_status, "PARTIAL")
        self.assertEqual(result.source_reports[0]["errors"], ["detector execution failed"])

    def test_video_frame_evidence_retains_parent_timestamp_and_frame_hash(self):
        frame_report = image_report("video:sample:0", HASH_C)
        video = {
            "source_id": "video", "source_sha256": HASH_A, "media_type": "video", "processing_status": "PARTIAL",
            "frames": [{"sha256": HASH_C, "timestamp_seconds": 4.5, "image_assessment": frame_report}],
        }
        result = fuse_reports(video)
        self.assertEqual(len(result.evidence), 1)
        item = result.evidence[0]
        self.assertEqual(item.parent_video_id, "video")
        self.assertEqual(item.parent_video_sha256, HASH_A)
        self.assertEqual(item.frame_sha256, HASH_C)
        self.assertEqual(item.timestamp_seconds, 4.5)

    def test_rejects_frame_hash_that_differs_from_assessment_hash(self):
        video = {
            "source_id": "video", "source_sha256": HASH_A, "media_type": "video", "processing_status": "PARTIAL",
            "frames": [{"sha256": HASH_C, "timestamp_seconds": 4.5,
                        "image_assessment": image_report("video:sample:0", HASH_B)}],
        }
        with self.assertRaises(ValueError):
            fuse_reports(video)

    def test_rejects_boolean_as_timestamp(self):
        video = {
            "source_id": "video", "source_sha256": HASH_A, "media_type": "video",
            "frames": [{"sha256": HASH_C, "timestamp_seconds": True,
                        "image_assessment": image_report("video:sample:0", HASH_C)}],
        }
        with self.assertRaises(ValueError):
            fuse_reports(video)

    def test_rejects_invalid_hash_and_non_finite_signal(self):
        bad_hash = image_report(digest="bad")
        with self.assertRaises(ValueError):
            fuse_reports(bad_hash)
        bad_signal = image_report()
        bad_signal["evidence"][0]["measured_signal"]["score"] = float("nan")
        with self.assertRaises(ValueError):
            fuse_reports(bad_signal)

    def test_rejects_duplicate_source_evidence_identities(self):
        report = image_report()
        with self.assertRaises(ValueError):
            fuse_reports(report, report)

    def test_real_image_ingestion_analysis_and_fusion_path(self):
        stream = io.BytesIO()
        Image.new("RGB", (24, 20), (30, 80, 160)).save(stream, format="PNG")
        original = stream.getvalue()
        media = ingest_media(io.BytesIO(original), "fixture.png")
        try:
            self.assertEqual(media.source_sha256, hashlib.sha256(original).hexdigest())
            report = analyze_image(media).to_dict()
            result = fuse_reports(report)
            self.assertEqual(result.source_reports[0]["source_sha256"], media.source_sha256)
            self.assertEqual(result.source_reports[0]["processing_status"], "PARTIAL")
            self.assertTrue(result.human_review_required)
            self.assertEqual(result.proposed_outcome, "INSUFFICIENT_EVIDENCE_REVIEW")
        finally:
            media.cleanup()

    def test_mixed_image_and_video_reports_preserve_both_sources(self):
        video = {
            "source_id": "video", "source_sha256": HASH_C, "media_type": "video",
            "processing_status": "PARTIAL", "errors": ["sparse sampling"], "limitations": [],
            "frames": [{"sha256": HASH_B, "timestamp_seconds": 1.25,
                        "image_assessment": image_report("video:sample:0", HASH_B)}],
        }
        result = fuse_reports(image_report(), video)
        self.assertEqual(len(result.source_reports), 2)
        self.assertEqual({source["media_type"] for source in result.source_reports}, {"image", "video"})
        self.assertTrue(any(source["errors"] == ["sparse sampling"] for source in result.source_reports))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "real FFmpeg/ffprobe not installed")
class RealVideoFusionWorkflowTests(unittest.TestCase):
    def test_real_video_sampling_and_fusion_path(self):
        temporary_root = Path(".trustlens-tmp")
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="fusion-e2e-", dir=temporary_root) as directory:
            clip_path = Path(directory) / "fixture.mp4"
            subprocess.run(
                [shutil.which("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "testsrc=size=64x48:rate=4:duration=1",
                 "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(clip_path)],
                check=True, capture_output=True, text=True, timeout=30,
            )
            media = ingest_media(io.BytesIO(clip_path.read_bytes()), "fixture.mp4")
            try:
                video_report = analyze_video(
                    media, config=VideoSamplingConfig(interval_seconds=0.5, max_frames=3),
                ).to_dict()
                result = fuse_reports(video_report)
                self.assertTrue(video_report["frames"])
                expected_frame_evidence = sum(len(frame["image_assessment"]["evidence"]) for frame in video_report["frames"])
                self.assertEqual(len(result.evidence), expected_frame_evidence + 1)  # includes the video temporal channel
                self.assertIn("temporal_analysis", {item.evidence_source for item in result.evidence})
                frame_evidence = [item for item in result.evidence if item.evidence_source != "temporal_analysis"]
                self.assertTrue(all(item.parent_video_sha256 == media.source_sha256 for item in frame_evidence))
                self.assertTrue(all(item.frame_sha256 and item.timestamp_seconds is not None for item in frame_evidence))
                self.assertEqual(result.proposed_outcome, "INSUFFICIENT_EVIDENCE_REVIEW")
            finally:
                media.cleanup()


if __name__ == "__main__":
    unittest.main()
