"""Bounded video frame sampling and frame-level image assessment.

FFmpeg is used only after ingestion has verified stream metadata. Sampled-frame
results remain linked to the source video and presentation timestamps. Sparse
sampling is not treated as a full examination of every frame.
"""

from __future__ import annotations

import hashlib
import math
import re
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from .image_analysis import ImageDetector, analyze_image
from .ingestion import IngestedMedia, MediaType, ProcessingStatus


VIDEO_REPORT_SCHEMA_VERSION = "1.0"
_PTS_PATTERN = re.compile(r"pts_time:([-+]?(?:\d+(?:\.\d*)?|\.\d+))")


@dataclass(frozen=True)
class VideoSamplingConfig:
    interval_seconds: float = 5.0
    max_frames: int = 12
    max_duration_seconds: float = 1200.0
    max_frame_side: int = 1024
    timeout_seconds: float = 180.0
    max_total_frame_bytes: int = 128 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in ("interval_seconds", "max_duration_seconds", "timeout_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")
        for name in ("max_frames", "max_frame_side", "max_total_frame_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass
class VideoFrameResult:
    sample_index: int
    source_frame_index: int | None
    timestamp_seconds: float | None
    artifact_reference: str
    sha256: str
    image_assessment: dict[str, Any]


@dataclass
class VideoAssessment:
    schema_version: str
    source_id: str
    source_sha256: str
    media_type: MediaType
    processing_status: ProcessingStatus
    proposed_outcome: str
    human_review_required: bool
    video_metadata: dict[str, Any]
    sampling: dict[str, Any]
    frames: list[VideoFrameResult] = field(default_factory=list)
    temporal_analysis: dict[str, Any] = field(default_factory=dict)
    localization: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["media_type"] = self.media_type.value
        result["processing_status"] = self.processing_status.value
        return result


def _report(
    media: IngestedMedia,
    *,
    status: ProcessingStatus,
    sampling_status: ProcessingStatus,
    sampling_strategy: str,
    frame_results: list[VideoFrameResult] | None = None,
    limitations: list[str] | None = None,
    errors: list[str] | None = None,
    sampled_duration: float | None = None,
) -> VideoAssessment:
    return VideoAssessment(
        schema_version=VIDEO_REPORT_SCHEMA_VERSION,
        source_id=media.source_id,
        source_sha256=media.source_sha256,
        media_type=MediaType.VIDEO,
        processing_status=status,
        proposed_outcome="INSUFFICIENT_EVIDENCE_REVIEW",
        human_review_required=True,
        video_metadata=dict(media.metadata),
        sampling={
            "status": sampling_status.value,
            "strategy": sampling_strategy,
            "interval_seconds": None,
            "requested_max_frames": None,
            "sampled_duration_seconds": sampled_duration,
            "sampled_count": len(frame_results or []),
            "extracted_frame_count": 0,
            "frame_processing_failures": 0,
            "sampling_gaps_expected": True,
            "source_frame_indices_available": False,
        },
        frames=frame_results or [],
        temporal_analysis={
            "status": ProcessingStatus.UNAVAILABLE.value,
            "method": None,
            "reason": "No validated temporal analysis method is configured.",
        },
        localization={
            "status": ProcessingStatus.UNAVAILABLE.value,
            "suspicious_frames": [],
            "suspicious_time_ranges": [],
            "reason": "No model-supported suspicious frame localization is available.",
        },
        limitations=limitations or [],
        errors=errors or [],
    )


def _verify_source(media: IngestedMedia) -> bool:
    path = Path(media.source_path)
    if not path.is_file():
        return False
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == media.source_sha256


def _temporal_measurement(frame_paths: list[Path], timestamps: list[float]) -> dict[str, Any]:
    """Measure adjacent sampled-frame luminance changes without classifying them.

    Samples are resized to a fixed 64x64 grayscale grid. The normalized mean
    absolute pixel difference is descriptive and can reflect scene cuts,
    motion, exposure, compression, or other ordinary changes. It is not a
    manipulation score and has no decision threshold.
    """
    if len(frame_paths) < 2:
        return {
            "status": ProcessingStatus.UNAVAILABLE.value,
            "method": "adjacent-sampled-frame-luma-difference-v1",
            "reason": "At least two successfully extracted frames are required.",
            "pairs": [],
            "limitations": ["Sparse frame samples do not support continuous temporal conclusions."],
        }
    import numpy as np

    samples: list[tuple[int, float, Any]] = []
    for index, path in enumerate(frame_paths):
        try:
            with Image.open(path) as opened:
                gray = opened.convert("L").resize((64, 64), Image.Resampling.BILINEAR)
                values = np.asarray(gray, dtype=np.float32) / 255.0
            timestamp = timestamps[index] if index < len(timestamps) else None
            if timestamp is not None and math.isfinite(timestamp) and timestamp >= 0:
                samples.append((index, timestamp, values))
        except (OSError, ValueError):
            continue
    pairs = []
    for previous, current in zip(samples, samples[1:]):
        difference = float(np.mean(np.abs(current[2] - previous[2])))
        pairs.append({
            "from_sample_index": previous[0],
            "to_sample_index": current[0],
            "from_timestamp_seconds": previous[1],
            "to_timestamp_seconds": current[1],
            "mean_absolute_luma_difference_0_to_1": difference,
        })
    return {
        "status": ProcessingStatus.PARTIAL.value if pairs else ProcessingStatus.UNAVAILABLE.value,
        "method": "adjacent-sampled-frame-luma-difference-v1",
        "semantics": "Mean absolute grayscale pixel difference after resizing each sampled frame to 64x64; descriptive only.",
        "pairs": pairs,
        "interpretation": "Differences may reflect scene changes, motion, exposure, compression, or ordinary edits; no manipulation inference is made.",
        "limitations": [
            "Only successfully extracted sparse samples are compared; intervening frames are not examined.",
            "This measurement is not evaluated as a deepfake signal and has no validated threshold.",
            "The resized grayscale difference does not estimate optical flow or track faces/objects.",
        ],
    }


def analyze_video(
    media: IngestedMedia,
    *,
    detector: ImageDetector | None = None,
    config: VideoSamplingConfig | None = None,
) -> VideoAssessment:
    """Sample verified video at bounded intervals and assess each extracted frame.

    The result preserves actual sampled-frame presentation timestamps from
    FFmpeg's ``showinfo`` output. Original decoded frame indices are unavailable
    with this sampling strategy and are left null rather than estimated.
    """
    config = config or VideoSamplingConfig()
    if media.detected_type != MediaType.VIDEO:
        raise ValueError("Video analysis requires ingested video media.")
    if not _verify_source(media):
        return _report(
            media,
            status=ProcessingStatus.FAILED,
            sampling_status=ProcessingStatus.FAILED,
            sampling_strategy="not_started",
            errors=["Staged video is missing or its bytes no longer match the ingestion SHA-256."],
        )

    required_metadata = ("duration_seconds", "width", "height", "frame_rate")
    if any(media.metadata.get(key) is None for key in required_metadata):
        return _report(
            media,
            status=ProcessingStatus.UNAVAILABLE,
            sampling_status=ProcessingStatus.UNAVAILABLE,
            sampling_strategy="not_started",
            limitations=["Verified duration, dimensions, and frame rate are required before sampling."],
            errors=["Video stream metadata is unavailable; re-ingest with ffprobe installed."],
        )
    if max(int(media.metadata["width"]), int(media.metadata["height"])) > config.max_frame_side * 4:
        return _report(
            media,
            status=ProcessingStatus.FAILED,
            sampling_status=ProcessingStatus.FAILED,
            sampling_strategy="not_started",
            errors=["Video dimensions exceed the configured pre-sampling safety bound."],
        )
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return _report(
            media,
            status=ProcessingStatus.UNAVAILABLE,
            sampling_status=ProcessingStatus.UNAVAILABLE,
            sampling_strategy="ffmpeg_fps_filter",
            limitations=["FFmpeg is unavailable; no frames were sampled or analyzed."],
            errors=["ffmpeg executable was not found on PATH."],
        )

    duration = min(float(media.metadata["duration_seconds"]), config.max_duration_seconds)
    sampling_interval = min(config.interval_seconds, duration)
    expected_samples = min(config.max_frames, max(1, int(duration / sampling_interval) + 1))
    root = Path(media.source_path).parent
    frame_directory = root / f"video-frames-{uuid.uuid4().hex}"
    frame_directory.mkdir()
    pattern = frame_directory / "frame_%06d.png"
    filter_graph = (
        f"fps=1/{sampling_interval:g}:start_time=0,"
        f"scale={config.max_frame_side}:{config.max_frame_side}:force_original_aspect_ratio=decrease,"
        "format=rgb24,showinfo"
    )
    command = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "info",
        "-threads", "1", "-filter_threads", "1",
        "-t", f"{duration:.6f}", "-i", media.source_path,
        "-map", "0:v:0", "-an", "-sn", "-dn",
        "-vf", filter_graph, "-frames:v", str(expected_samples),
        "-fps_mode", "passthrough", "-start_number", "0", "-c:v", "png",
        str(pattern),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=config.timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired:
        return _report(
            media,
            status=ProcessingStatus.FAILED,
            sampling_status=ProcessingStatus.FAILED,
            sampling_strategy="ffmpeg_fps_filter",
            errors=["FFmpeg exceeded the configured sampling timeout."],
        )

    frame_paths = sorted(frame_directory.glob("frame_*.png"))
    total_bytes = sum(path.stat().st_size for path in frame_paths)
    if total_bytes > config.max_total_frame_bytes:
        for path in frame_paths:
            path.unlink(missing_ok=True)
        return _report(
            media,
            status=ProcessingStatus.FAILED,
            sampling_status=ProcessingStatus.FAILED,
            sampling_strategy="ffmpeg_fps_filter",
            errors=["Extracted frames exceed the configured total artifact size limit."],
        )
    timestamps = [float(value) for value in _PTS_PATTERN.findall(completed.stderr)]
    frame_results: list[VideoFrameResult] = []
    failed_frame_samples: list[int] = []
    for index, path in enumerate(frame_paths):
        try:
            with Image.open(path) as frame:
                frame.verify()
            with Image.open(path) as frame:
                width, height = frame.size
                if max(width, height) > config.max_frame_side:
                    continue
            frame_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            frame_media = IngestedMedia(
                schema_version="1.0",
                source_id=f"{media.source_id}:sample:{index}",
                source_name=path.name,
                source_sha256=frame_hash,
                detected_type=MediaType.IMAGE,
                original_size_bytes=path.stat().st_size,
                original_format="PNG",
                metadata={"width": width, "height": height, "video_source_id": media.source_id},
                preprocessing={"frame_extracted": True, "source_video_sha256": media.source_sha256},
                source_path=str(path),
                normalized_image_path=str(path),
            )
            assessment = analyze_image(frame_media, detector=detector)
            frame_results.append(VideoFrameResult(
                sample_index=index,
                source_frame_index=None,
                timestamp_seconds=timestamps[index] if index < len(timestamps) else None,
                artifact_reference=f"frame-{index:06d}",
                sha256=frame_hash,
                image_assessment=assessment.to_dict(),
            ))
        except (OSError, ValueError):
            failed_frame_samples.append(index)
            continue

    extraction_error = completed.returncode != 0
    status = ProcessingStatus.PARTIAL if frame_results else ProcessingStatus.FAILED
    sampling_status = (
        ProcessingStatus.PARTIAL if extraction_error and frame_results
        else ProcessingStatus.SUCCESS if frame_results
        else ProcessingStatus.FAILED
    )
    warnings = [
        "Sparse frame sampling does not examine every video frame.",
        "Frame indices from the original stream are unavailable; actual sampled presentation timestamps are retained when FFmpeg reports them.",
        "No validated temporal analysis or report-level video classification is performed.",
    ]
    if duration < float(media.metadata["duration_seconds"]):
        warnings.append("Sampling stopped at the configured duration cap; the remainder of the source was not sampled.")
    errors = ["FFmpeg reported a decode or extraction error; available sampled frames are partial."] if extraction_error else []
    report = _report(
        media,
        status=status,
        sampling_status=sampling_status,
        sampling_strategy="ffmpeg_fps_filter",
        frame_results=frame_results,
        limitations=warnings,
        errors=errors,
        sampled_duration=duration,
    )
    report.sampling["requested_interval_seconds"] = config.interval_seconds
    report.sampling["interval_seconds"] = sampling_interval
    report.sampling["requested_max_frames"] = config.max_frames
    report.sampling["sampling_gaps_expected"] = True
    report.sampling["source_frame_indices_available"] = False
    report.sampling["extracted_frame_count"] = len(frame_paths)
    report.sampling["frame_processing_failures"] = len(failed_frame_samples)
    report.temporal_analysis = _temporal_measurement(frame_paths, timestamps)
    if failed_frame_samples:
        report.errors.append(
            f"{len(failed_frame_samples)} extracted frame(s) could not be validated or analyzed."
        )
    if sampling_interval < config.interval_seconds:
        report.limitations.append(
            "The requested sampling interval exceeded the analyzed duration; the interval was reduced to the video duration to retain a starting frame."
        )
    return report
