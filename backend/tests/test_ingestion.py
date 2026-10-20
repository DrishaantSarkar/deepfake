import hashlib
import io
import math
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from trustlens.ingestion import IngestionError, MediaLimits, MediaType, ProcessingStatus, _probe_video, _ratio, ingest_media


def png_bytes(size=(8, 6)):
    image = Image.new("RGBA", size, (20, 40, 60, 255))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def jpeg_bytes():
    image = Image.new("RGB", (8, 6), (20, 40, 60))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


class IngestionTests(unittest.TestCase):
    def test_malformed_ffprobe_json_shapes_return_unavailable_metadata(self):
        malformed_outputs = (
            "[]",
            '{"streams": [null], "format": {}}',
            '{"streams": [{"codec_type": "video", "width": 16, "height": 16, "avg_frame_rate": "30/1", "duration": "5"}], "format": []}',
        )
        with patch("trustlens.ingestion.shutil.which", return_value="ffprobe"), patch(
            "trustlens.ingestion.subprocess.run",
            side_effect=[SimpleNamespace(returncode=0, stdout=output) for output in malformed_outputs],
        ):
            for output in malformed_outputs:
                with self.subTest(output=output):
                    metadata, warnings = _probe_video(Path("unused.mp4"), MediaLimits())
                    self.assertEqual(metadata, {})
                    self.assertTrue(any("incomplete or invalid" in item for item in warnings))

    def test_non_finite_video_duration_and_frame_rate_are_not_serialized(self):
        output = '{"streams": [{"codec_type": "video", "width": 16, "height": 16, "avg_frame_rate": "inf/1", "r_frame_rate": "30/1", "duration": "NaN"}], "format": {"format_name": "mov,mp4"}}'
        with patch("trustlens.ingestion.shutil.which", return_value="ffprobe"), patch(
            "trustlens.ingestion.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=output),
        ):
            metadata, warnings = _probe_video(Path("unused.mp4"), MediaLimits())
        self.assertIsNone(metadata["duration_seconds"])
        self.assertIsNone(metadata["average_frame_rate"])
        self.assertIn("Video duration is unavailable.", warnings)
        self.assertIsNone(_ratio("inf/1"))

    def test_media_limits_require_finite_reals_and_positive_integer_bounds(self):
        for field, value in (
            ("max_video_seconds", math.nan),
            ("max_video_fps", math.inf),
            ("probe_timeout_seconds", -math.inf),
            ("max_file_bytes", 1.5),
            ("max_image_pixels", True),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                MediaLimits(**{field: value})

    def test_image_hash_metadata_and_normalized_artifact(self):
        payload = png_bytes()
        record = ingest_media(io.BytesIO(payload), "sample.png")
        try:
            self.assertEqual(record.detected_type, MediaType.IMAGE)
            self.assertEqual(record.source_sha256, hashlib.sha256(payload).hexdigest())
            self.assertEqual((record.metadata["width"], record.metadata["height"]), (8, 6))
            self.assertTrue(record.preprocessing["alpha_present"])
            self.assertIn("preserved", record.preprocessing["alpha_handling"])
            self.assertTrue(record.normalized_image_path)
            with Image.open(record.normalized_image_path) as normalized:
                self.assertEqual((normalized.mode, normalized.size), ("RGBA", (8, 6)))
        finally:
            record.cleanup()

    def test_rejects_empty_and_unknown_content(self):
        for payload, filename in ((b"", "empty.png"), (b"not media", "unknown.jpg")):
            with self.subTest(filename=filename), self.assertRaises(IngestionError):
                ingest_media(io.BytesIO(payload), filename)

    def test_rejects_extension_mismatch(self):
        with self.assertRaises(IngestionError):
            ingest_media(io.BytesIO(jpeg_bytes()), "sample.png")

    def test_filename_removes_path_and_control_characters_and_preserves_extension(self):
        payload = png_bytes()
        record = ingest_media(io.BytesIO(payload), "..\\..\\evidence\\report\n.png")
        try:
            self.assertEqual(record.source_name, "report.png")
            self.assertNotIn("\n", record.source_name)
        finally:
            record.cleanup()
        long_name = "a" * 300 + ".png"
        record = ingest_media(io.BytesIO(payload), long_name)
        try:
            self.assertLessEqual(len(record.source_name), 255)
            self.assertTrue(record.source_name.endswith(".png"))
        finally:
            record.cleanup()

    def test_image_exif_exposes_named_capture_and_device_fields(self):
        image = Image.new("RGB", (8, 6), (20, 40, 60))
        exif = Image.Exif()
        exif[36867] = "2024:03:04 05:06:07"  # DateTimeOriginal
        exif[271] = "Camera maker"
        exif[272] = "Camera model"
        exif[305] = "Editing software"
        stream = io.BytesIO()
        image.save(stream, format="JPEG", exif=exif)
        record = ingest_media(io.BytesIO(stream.getvalue()), "camera.jpg")
        try:
            self.assertEqual(record.metadata["exif_status"], "DETECTED")
            self.assertEqual(record.metadata["metadata_status"], "DETECTED")
            self.assertEqual(record.metadata["exif_named"]["DateTimeOriginal"], "2024:03:04 05:06:07")
            self.assertEqual(record.metadata["exif_named"]["Make"], "Camera maker")
            self.assertEqual(record.metadata["exif_named"]["Model"], "Camera model")
            self.assertEqual(record.metadata["exif_named"]["Software"], "Editing software")
        finally:
            record.cleanup()

    def test_rejects_oversize_before_completion(self):
        with self.assertRaises(IngestionError):
            ingest_media(io.BytesIO(png_bytes()), "sample.png", limits=MediaLimits(max_file_bytes=12))

    def test_rejects_pixel_limit(self):
        with self.assertRaises(IngestionError):
            ingest_media(io.BytesIO(png_bytes((20, 20))), "sample.png", limits=MediaLimits(max_image_pixels=100))

    def test_handles_grayscale_and_uint16_images_explicitly(self):
        grayscale = Image.new("L", (3, 1))
        gray_buffer = io.BytesIO()
        grayscale.save(gray_buffer, format="PNG")
        gray_record = ingest_media(io.BytesIO(gray_buffer.getvalue()), "gray.png")
        try:
            with Image.open(gray_record.normalized_image_path) as normalized:
                self.assertEqual(normalized.mode, "RGB")
            self.assertEqual(gray_record.preprocessing["alpha_present"], False)
        finally:
            gray_record.cleanup()

        import numpy as np
        high_depth = Image.fromarray(np.array([[0, 32768, 65535]], dtype=np.uint16))
        high_buffer = io.BytesIO()
        high_depth.save(high_buffer, format="PNG")
        record = ingest_media(io.BytesIO(high_buffer.getvalue()), "16bit.png")
        try:
            with Image.open(record.normalized_image_path) as normalized:
                self.assertEqual(normalized.mode, "RGB")
                self.assertEqual(normalized.getpixel((0, 0)), (0, 0, 0))
                self.assertEqual(normalized.getpixel((2, 0)), (255, 255, 255))
            self.assertIn("value/257", record.preprocessing["high_bit_depth_handling"])
        finally:
            record.cleanup()

    def test_rejects_truncated_and_unsupported_image_content(self):
        truncated = b"\x89PNG\r\n\x1a\n" + b"truncated"
        gif = b"GIF89a" + b"\x01\x00\x01\x00" + b"\x00\x00\x00"
        for payload, filename in ((truncated, "truncated.png"), (gif, "unsupported.gif")):
            with self.subTest(filename=filename), self.assertRaises(IngestionError):
                ingest_media(io.BytesIO(payload), filename)

    def test_audio_validation_is_explicitly_deferred(self):
        payload = b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + b"\x10\x00\x00\x00\x01\x00\x01\x00" + b"\x40\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00data" + b"\x00\x00\x00\x00"
        record = ingest_media(io.BytesIO(payload), "sample.wav")
        try:
            self.assertEqual(record.detected_type, MediaType.AUDIO)
            self.assertEqual(record.source_sha256, hashlib.sha256(payload).hexdigest())
            self.assertEqual(record.status, ProcessingStatus.PARTIAL)
            self.assertIn("deferred", record.warnings[0])
        finally:
            record.cleanup()


if __name__ == "__main__":
    unittest.main()
