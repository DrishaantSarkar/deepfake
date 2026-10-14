"""Bounded media intake and image normalization for TRUSTLENS.

The original upload is retained byte-for-byte in an isolated temporary directory.
Call ``IngestedMedia.cleanup()`` when downstream processing no longer needs it.
Video probing is optional and uses ffprobe when installed; it never decodes frames.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import uuid
import unicodedata
import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Any

from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class ProcessingStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class MediaLimits:
    max_file_bytes: int = 100 * 1024 * 1024
    max_image_pixels: int = 40_000_000
    max_image_side: int = 4096
    max_video_seconds: float = 20 * 60
    max_video_fps: float = 60.0
    max_video_side: int = 4096
    probe_timeout_seconds: float = 8.0
    read_chunk_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        for name in ("max_file_bytes", "max_image_pixels", "max_image_side", "max_video_side", "read_chunk_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("max_video_seconds", "max_video_fps", "probe_timeout_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")


@dataclass
class IngestedMedia:
    schema_version: str
    source_id: str
    source_name: str
    source_sha256: str
    detected_type: MediaType
    original_size_bytes: int
    original_format: str
    metadata: dict[str, Any] = field(default_factory=dict)
    preprocessing: dict[str, Any] = field(default_factory=dict)
    status: ProcessingStatus = ProcessingStatus.SUCCESS
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    source_path: str = ""
    normalized_image_path: str | None = None
    _temporary_directory: tempfile.TemporaryDirectory[str] | None = field(default=None, repr=False)

    def cleanup(self) -> None:
        """Remove the isolated source and derived artifacts."""
        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()
            self._temporary_directory = None
        self.source_path = ""
        self.normalized_image_path = None


class IngestionError(ValueError):
    """Raised when an upload fails validation before a media record is produced."""


_EXTENSIONS: dict[MediaType, set[str]] = {
    MediaType.IMAGE: {".jpg", ".jpeg", ".png", ".webp"},
    MediaType.VIDEO: {".mp4", ".mov", ".avi"},
    MediaType.AUDIO: {".wav", ".mp3"},
}
_IMAGE_EXTENSION_FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


def _detect_type(header: bytes) -> tuple[MediaType, str] | None:
    if header.startswith(b"\xff\xd8\xff"):
        return MediaType.IMAGE, "JPEG"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return MediaType.IMAGE, "PNG"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return MediaType.IMAGE, "WEBP"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return MediaType.VIDEO, "ISO-BMFF"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return MediaType.VIDEO, "AVI"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return MediaType.AUDIO, "WAV"
    if header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0):
        return MediaType.AUDIO, "MP3"
    return None


def _ratio(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    try:
        numerator, denominator = value.split("/", 1)
        ratio = float(numerator) / float(denominator)
        return ratio if math.isfinite(ratio) and ratio > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def _safe_container_tags(value: Any, label: str) -> tuple[dict[str, str], str, str | None]:
    """Bound ffprobe tags and distinguish missing, malformed, and partial data."""
    if value is None:
        return {}, "MISSING", None
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        return {}, "ERROR", f"{label} metadata tags were malformed."
    keys = sorted(value)
    tags: dict[str, str] = {}
    partial = len(keys) > 64
    for key in keys[:64]:
        raw = value[key]
        if not isinstance(raw, (str, int, float, bool)):
            partial = True
            continue
        text = str(raw)
        if len(text) > 2048:
            text = text[:2048]
            partial = True
        tags[key] = text
    if partial:
        return tags, "PARTIAL", f"{label} tags were bounded to 64 fields and 2048 characters per value; some metadata may be omitted."
    return tags, "DETECTED", None


def _probe_video(path: Path, limits: MediaLimits) -> tuple[dict[str, Any], list[str]]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}, ["ffprobe is unavailable; video stream metadata and decode status were not verified."]
    try:
        completed = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
            "format=duration,format_name:format_tags:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,duration,nb_frames:stream_tags",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=limits.probe_timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired:
        return {}, ["ffprobe timed out; video stream metadata was not verified."]
    if completed.returncode != 0:
        return {}, ["ffprobe could not parse the video container or streams."]
    try:
        data = json.loads(completed.stdout)
        if not isinstance(data, dict):
            raise ValueError("ffprobe JSON root must be an object")
        streams = data.get("streams", [])
        format_data = data.get("format", {})
        if (
            not isinstance(streams, list)
            or any(not isinstance(stream, dict) for stream in streams)
            or not isinstance(format_data, dict)
        ):
            raise ValueError("ffprobe streams and format have invalid shapes")
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        if video is None:
            return {}, ["No video stream was found."]
        duration_raw = video.get("duration")
        if duration_raw is None:
            duration_raw = format_data.get("duration")
        duration = float(duration_raw) if duration_raw is not None else None
        if duration is not None and (not math.isfinite(duration) or duration <= 0):
            duration = None
        width, height = int(video["width"]), int(video["height"])
        if width <= 0 or height <= 0:
            raise ValueError("ffprobe dimensions must be positive")
        avg_fps = _ratio(video.get("avg_frame_rate"))
        nominal_fps = _ratio(video.get("r_frame_rate"))
        frame_count_raw = video.get("nb_frames")
        frame_count = int(frame_count_raw) if frame_count_raw and str(frame_count_raw).isdigit() else None
        container_tags, container_tags_status, container_tags_warning = _safe_container_tags(
            data.get("format", {}).get("tags"), "Container",
        )
        stream_tags, stream_tags_status, stream_tags_warning = _safe_container_tags(video.get("tags"), "Video stream")
        metadata = {
            "duration_seconds": duration,
            "frame_rate": avg_fps,
            "average_frame_rate": avg_fps,
            "nominal_frame_rate": nominal_fps,
            "frame_count": frame_count,
            "width": width,
            "height": height,
            "codec": video.get("codec_name"),
            "container": format_data.get("format_name"),
            "streams": [{"type": s.get("codec_type"), "codec": s.get("codec_name")} for s in streams],
            "audio_stream_present": any(s.get("codec_type") == "audio" for s in streams),
            "container_tags": container_tags,
            "container_tags_status": container_tags_status,
            "video_stream_tags": stream_tags,
            "video_stream_tags_status": stream_tags_status,
        }
        violations = []
        violations.extend(item for item in (container_tags_warning, stream_tags_warning) if item)
        if duration is None:
            violations.append("Video duration is unavailable.")
        elif duration > limits.max_video_seconds:
            violations.append(f"Video duration exceeds the {limits.max_video_seconds:g}s limit.")
        if max(width, height) > limits.max_video_side:
            violations.append(f"Video dimension exceeds the {limits.max_video_side}px side limit.")
        if any(rate is not None and rate > limits.max_video_fps for rate in (avg_fps, nominal_fps)):
            violations.append(f"Video frame rate exceeds the {limits.max_video_fps:g} fps limit.")
        return metadata, violations
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return {}, ["ffprobe returned incomplete or invalid stream metadata."]


def ingest_media(
    source: BinaryIO,
    filename: str,
    *,
    limits: MediaLimits | None = None,
) -> IngestedMedia:
    """Validate and stage one upload, hashing its original bytes as they are read.

    Caller owns ``source``. Returned temporary files remain available until
    ``cleanup`` is called. Unsupported or invalid media raises ``IngestionError``.
    """
    limits = limits or MediaLimits()
    if not hasattr(source, "read"):
        raise TypeError("source must be a binary file-like object")
    safe_name = Path(filename.replace("\\", "/")).name or "upload"
    # Multipart filenames are untrusted display data. Remove control characters
    # before they enter the report contract, logs, HTML, or SQLite metadata.
    safe_name = "".join(char for char in safe_name if unicodedata.category(char) != "Cc").strip() or "upload"
    suffix = Path(safe_name).suffix
    if len(safe_name) > 255:
        stem = safe_name[:-len(suffix)] if suffix else safe_name
        safe_name = stem[:255 - len(suffix)] + suffix if len(suffix) <= 32 else safe_name[:255]
    extension = Path(safe_name).suffix.lower()
    # Keep uploads outside the project tree by default: workspaces may be
    # cloud-synced. Operators/tests may explicitly select a private temp root.
    configured_temp = os.environ.get("TRUSTLENS_TEMP_DIR")
    temporary_root = Path(configured_temp).expanduser() if configured_temp else Path(tempfile.gettempdir()) / "TRUSTLENS"
    temporary_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = tempfile.TemporaryDirectory(prefix="trustlens-", dir=temporary_root)
    source_path = Path(directory.name) / "source.media"
    digest = hashlib.sha256()
    total = 0
    header = b""
    try:
        with source_path.open("xb") as destination:
            while True:
                chunk = source.read(limits.read_chunk_bytes)
                if not chunk:
                    break
                if not isinstance(chunk, (bytes, bytearray)):
                    raise IngestionError("Upload stream must return bytes.")
                total += len(chunk)
                if total > limits.max_file_bytes:
                    raise IngestionError(f"File exceeds the {limits.max_file_bytes} byte limit.")
                if len(header) < 32:
                    header += bytes(chunk[: 32 - len(header)])
                digest.update(chunk)
                destination.write(chunk)
        if total == 0:
            raise IngestionError("Empty files are not supported.")
        detected = _detect_type(header)
        if detected is None:
            raise IngestionError("Could not identify a supported media type from file contents.")
        media_type, original_format = detected
        if extension not in _EXTENSIONS[media_type]:
            raise IngestionError(f"Detected {media_type.value} content does not match a supported filename extension.")

        result = IngestedMedia(
            schema_version="1.0",
            source_id=str(uuid.uuid4()),
            source_name=safe_name,
            source_sha256=digest.hexdigest(),
            detected_type=media_type,
            original_size_bytes=total,
            original_format=original_format,
            source_path=str(source_path),
            _temporary_directory=directory,
        )
        if media_type == MediaType.IMAGE:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(source_path) as image:
                        width, height = image.size
                        if width <= 0 or height <= 0 or width * height > limits.max_image_pixels:
                            raise IngestionError(f"Image dimensions exceed the {limits.max_image_pixels} pixel limit.")
                        image.verify()
                    with Image.open(source_path) as image:
                        expected_format = _IMAGE_EXTENSION_FORMATS.get(extension)
                        if image.format != expected_format:
                            raise IngestionError("Image content format does not match its filename extension.")
                        image.load()
                        exif_error = None
                        try:
                            exif = image.getexif()
                            exif_status = "DETECTED" if exif else "MISSING"
                        except (ValueError, TypeError, OSError):
                            exif = {}
                            exif_status = "ERROR"
                            exif_error = "Image EXIF metadata could not be parsed; pixel decoding succeeded."
                        orientation = exif.get(274)
                        oriented = ImageOps.exif_transpose(image)
                        alpha_present = "A" in oriented.getbands() or "transparency" in oriented.info
                        if oriented.mode in {"I;16", "I;16B", "I;16L", "I"}:
                            try:
                                import numpy as np
                            except ImportError as exc:
                                raise IngestionError("NumPy is required to normalize high-bit-depth grayscale images.") from exc
                            values = np.asarray(oriented)
                            low, high = int(values.min()), int(values.max())
                            if low < 0 or high > 65535:
                                raise IngestionError("32-bit integer image values outside the supported unsigned 16-bit range are not supported.")
                            grayscale = Image.fromarray(np.rint(values.astype(np.float64) / 257.0).astype(np.uint8), mode="L")
                            oriented = grayscale.convert("RGB")
                            alpha_present = False
                            high_bit_depth = "unsigned 16-bit grayscale scaled to 8-bit with value/257"
                        else:
                            if alpha_present:
                                oriented = oriented.convert("RGBA")
                            else:
                                oriented = oriented.convert("RGB")
                            high_bit_depth = "not detected"
                        transformed_size = oriented.size
                        oriented.thumbnail((limits.max_image_side, limits.max_image_side), Image.Resampling.LANCZOS)
                        normalized_path = Path(directory.name) / "normalized.png"
                        oriented.save(normalized_path, format="PNG", optimize=False)
                        result.normalized_image_path = str(normalized_path)
                        exif_by_name = {
                            ExifTags.TAGS.get(int(key), str(key)): str(value)
                            for key, value in exif.items() if key != 37500
                        }
                        named_exif = {
                            name: exif_by_name[name]
                            for name in ("DateTime", "DateTimeOriginal", "DateTimeDigitized", "Make", "Model", "Software")
                            if name in exif_by_name
                        }
                        result.metadata = {
                            "format": image.format,
                            "width": width,
                            "height": height,
                            "mode": image.mode,
                            "exif_orientation": orientation,
                            "exif": {str(k): str(v) for k, v in exif.items() if k != 37500},
                            "exif_named": named_exif,
                            "exif_status": exif_status,
                            "metadata_status": "PARTIAL" if exif_error else "DETECTED",
                            "metadata_warnings": [exif_error] if exif_error else [],
                        }
                        result.preprocessing = {
                            "orientation_applied": orientation not in (None, 1),
                            "color_mode": oriented.mode,
                            "alpha_present": alpha_present,
                            "alpha_handling": "preserved in normalized RGBA artifact; analysis RGB composites on white" if alpha_present else "no alpha channel",
                            "high_bit_depth_handling": high_bit_depth,
                            "pre_resize_width": transformed_size[0],
                            "pre_resize_height": transformed_size[1],
                            "width": oriented.width,
                            "height": oriented.height,
                            "resized": transformed_size != oriented.size,
                            "format": "PNG",
                        }
            except IngestionError:
                directory.cleanup()
                raise
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                directory.cleanup()
                raise IngestionError("Image is corrupted, truncated, or unsafe to decode.") from exc
        elif media_type == MediaType.VIDEO:
            result.metadata, result.warnings = _probe_video(source_path, limits)
            result.preprocessing = {"status": ProcessingStatus.NOT_APPLICABLE.value, "frame_extraction": "deferred"}
            if result.warnings:
                result.status = ProcessingStatus.PARTIAL
            if result.metadata and any("exceeds" in warning for warning in result.warnings):
                directory.cleanup()
                raise IngestionError("Video exceeds configured duration, frame-rate, or dimension limits.")
        else:
            result.metadata = {"format": original_format, "analysis": "deferred"}
            result.preprocessing = {"status": ProcessingStatus.NOT_APPLICABLE.value, "audio_analysis": "deferred"}
            result.status = ProcessingStatus.PARTIAL
            result.warnings.append("Audio analysis is deferred; this phase validates format and records file integrity only.")
        return result
    except Exception:
        if directory is not None:
            directory.cleanup()
        raise
