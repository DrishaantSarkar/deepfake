"""Safe local checks for TRUSTLENS media dependencies and real processing paths."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import io
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

class DiagnosticState(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    MISCONFIGURED = "misconfigured"
    FAILED_VERIFICATION = "failed_verification"


@dataclass
class DiagnosticItem:
    component: str
    status: DiagnosticState
    version: str | None = None
    detail: str = ""


@dataclass
class DiagnosticReport:
    schema_version: str
    python_version: str
    checks: list[DiagnosticItem]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "python_version": self.python_version,
            "checks": [
                asdict(item) | {"status": item.status.value}
                for item in self.checks
            ],
        }


def _module_check(module_name: str, component: str, distribution: str | None = None) -> tuple[DiagnosticItem, Any | None]:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".", 1)[0] != module_name.split(".", 1)[0]:
            return DiagnosticItem(component, DiagnosticState.MISCONFIGURED, detail="An import dependency is missing."), None
        return DiagnosticItem(component, DiagnosticState.MISSING, detail="Python package is not installed in this environment."), None
    except Exception as exc:
        return DiagnosticItem(component, DiagnosticState.MISCONFIGURED, detail=f"Import failed ({type(exc).__name__})."), None
    try:
        version = importlib.metadata.version(distribution or module_name)
    except importlib.metadata.PackageNotFoundError:
        version = str(getattr(module, "__version__", "unknown"))
    return DiagnosticItem(component, DiagnosticState.AVAILABLE, version, "Import succeeded."), module


def _executable_check(name: str, timeout_seconds: float) -> tuple[DiagnosticItem, str | None]:
    executable = shutil.which(name)
    if not executable:
        return DiagnosticItem(name, DiagnosticState.MISSING, detail="Executable was not found on PATH."), None
    try:
        completed = subprocess.run(
            [executable, "-version"], capture_output=True, text=True,
            timeout=timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired:
        return DiagnosticItem(name, DiagnosticState.MISCONFIGURED, detail="Version check timed out."), executable
    except OSError as exc:
        return DiagnosticItem(name, DiagnosticState.MISCONFIGURED, detail=f"Executable could not start ({type(exc).__name__})."), executable
    if completed.returncode != 0:
        return DiagnosticItem(name, DiagnosticState.MISCONFIGURED, detail="Version check returned a nonzero exit code."), executable
    version = next((line.strip() for line in completed.stdout.splitlines() if line.strip()), "unknown version")
    return DiagnosticItem(name, DiagnosticState.AVAILABLE, version=version, detail="Version command succeeded; processing is checked separately."), executable


def _image_fixture_checks(checks: list[DiagnosticItem], modules: dict[str, Any | None]) -> None:
    if modules.get("PIL") is None:
        checks.append(DiagnosticItem("pillow_image_decode_normalization", DiagnosticState.MISSING, detail="Pillow is required for image normalization."))
        checks.append(DiagnosticItem("numpy_opencv_image_decode", DiagnosticState.MISSING, detail="Pillow, NumPy, and OpenCV are required for image decode verification."))
        return
    try:
        image_module = importlib.import_module("PIL.Image")
        from .ingestion import IngestionError, ingest_media
    except Exception as exc:
        checks.append(DiagnosticItem(
            "pillow_image_decode_normalization", DiagnosticState.MISCONFIGURED,
            detail=f"Image processing imports failed ({type(exc).__name__}).",
        ))
        checks.append(DiagnosticItem(
            "numpy_opencv_image_decode", DiagnosticState.MISCONFIGURED,
            detail="Image processing modules could not be initialized.",
        ))
        return

    root = Path(__file__).resolve().parents[1] / ".trustlens-tmp"
    root.mkdir(exist_ok=True)
    modes = [("RGB", "RGB"), ("RGBA", "RGBA"), ("L", "RGB")]
    failures: list[str] = []
    for index, (mode, expected) in enumerate(modes):
        color = (127, 127, 127, 255) if mode == "RGBA" else (127, 127, 127) if mode == "RGB" else 127
        image = image_module.new(mode, (17, 13), color)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        try:
            record = ingest_media(io.BytesIO(buffer.getvalue()), f"diagnostic-{index}.png")
            try:
                with image_module.open(record.normalized_image_path) as normalized:
                    if normalized.mode != expected or normalized.size != (17, 13):
                        failures.append(f"{mode} normalization mismatch")
            finally:
                record.cleanup()
        except (IngestionError, OSError, ValueError) as exc:
            failures.append(f"{mode} normalization failed ({type(exc).__name__})")

    np_module = modules.get("numpy")
    if np_module is not None:
        high_depth = image_module.fromarray(np_module.arange(17 * 13, dtype=np_module.uint16).reshape((13, 17)) * 257)
        buffer = io.BytesIO()
        high_depth.save(buffer, format="PNG")
        try:
            record = ingest_media(io.BytesIO(buffer.getvalue()), "diagnostic-16bit.png")
            try:
                with image_module.open(record.normalized_image_path) as normalized:
                    if normalized.mode != "RGB" or record.preprocessing.get("high_bit_depth_handling") == "not detected":
                        failures.append("16-bit normalization metadata mismatch")
            finally:
                record.cleanup()
        except (IngestionError, OSError, ValueError) as exc:
            failures.append(f"16-bit normalization failed ({type(exc).__name__})")
    else:
        failures.append("NumPy is missing; required high-bit-depth normalization could not run")

    checks.append(DiagnosticItem(
        "pillow_image_decode_normalization",
        DiagnosticState.FAILED_VERIFICATION if failures else DiagnosticState.AVAILABLE,
        version=str(getattr(image_module, "__version__", "unknown")),
        detail="; ".join(failures) if failures else "RGB, RGBA, grayscale, and 16-bit grayscale fixtures decoded and normalized.",
    ))

    cv2_module = modules.get("cv2")
    if np_module is None or cv2_module is None:
        checks.append(DiagnosticItem(
            "numpy_opencv_image_decode",
            DiagnosticState.MISSING,
            detail="NumPy and OpenCV imports are both required for this processing check.",
        ))
        return
    rgb = np_module.zeros((13, 17, 3), dtype=np_module.uint8)
    rgb[:, :, 0] = 200
    bgr = cv2_module.cvtColor(rgb, cv2_module.COLOR_RGB2BGR)
    success, encoded = cv2_module.imencode(".png", bgr)
    decoded = cv2_module.imdecode(np_module.frombuffer(encoded.tobytes(), dtype=np_module.uint8), cv2_module.IMREAD_COLOR) if success else None
    channel_roundtrip = False
    if decoded is not None and decoded.shape == (13, 17, 3):
        rgb_roundtrip = cv2_module.cvtColor(decoded, cv2_module.COLOR_BGR2RGB)
        channel_roundtrip = bool(np_module.array_equal(rgb_roundtrip, rgb))
    valid = decoded is not None and decoded.shape == (13, 17, 3) and decoded.size == rgb.size and channel_roundtrip
    checks.append(DiagnosticItem(
        "numpy_opencv_image_decode",
        DiagnosticState.AVAILABLE if valid else DiagnosticState.FAILED_VERIFICATION,
        version=str(getattr(cv2_module, "__version__", "unknown")),
        detail="Generated PNG encoded and decoded to BGR, then converted back to the expected RGB channels." if valid else "OpenCV encode/decode or BGR-to-RGB channel check failed.",
    ))


def _video_fixture_checks(
    checks: list[DiagnosticItem],
    ffmpeg: str | None,
    ffprobe: str | None,
    timeout_seconds: float,
) -> None:
    if not ffprobe:
        checks.append(DiagnosticItem("video_metadata_extraction", DiagnosticState.MISSING, detail="ffprobe is required to inspect video streams."))
    if not ffmpeg:
        checks.append(DiagnosticItem("video_frame_decoding", DiagnosticState.MISSING, detail="ffmpeg is required to generate and decode the real video fixture."))
    if not ffmpeg or not ffprobe:
        checks.append(DiagnosticItem("trustlens_video_sampling", DiagnosticState.MISSING, detail="Both FFmpeg tools are required for end-to-end sampling verification."))
        return

    root = Path(__file__).resolve().parents[1] / ".trustlens-tmp"
    root.mkdir(exist_ok=True)
    try:
        from .ingestion import MediaLimits, ingest_media
        from .video_analysis import VideoSamplingConfig, analyze_video

        with tempfile.TemporaryDirectory(prefix="diagnostic-video-", dir=root) as temporary:
            metadata_details: list[str] = []
            decoded_ok: list[bool] = []
            sampling_ok: list[bool] = []
            fixture_specs = (("mpeg4", 64, 48, 4, "mpeg4"), ("h264", 96, 64, 6, "libx264"))
            for label, width, height, rate, encoder in fixture_specs:
                fixture = Path(temporary) / f"generated-{label}.mp4"
                created = subprocess.run(
                    [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-threads", "1",
                     "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate={rate}:duration=1", "-t", "1",
                     "-an", "-c:v", encoder, "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(fixture)],
                    capture_output=True, timeout=timeout_seconds, check=False,
                )
                if created.returncode != 0 or not fixture.is_file() or fixture.stat().st_size == 0:
                    raise RuntimeError(f"{label} fixture generation failed")

                probe = subprocess.run(
                    [ffprobe, "-v", "error", "-show_entries",
                     "format=duration,format_name:stream=codec_type,codec_name,width,height,avg_frame_rate,nb_frames",
                     "-of", "json", str(fixture)],
                    capture_output=True, text=True, timeout=timeout_seconds, check=False,
                )
                if probe.returncode != 0:
                    raise RuntimeError(f"ffprobe failed on {label} fixture")
                probe_data = json.loads(probe.stdout)
                video_stream = next((s for s in probe_data.get("streams", []) if s.get("codec_type") == "video"), None)
                if not video_stream or not video_stream.get("width") or not video_stream.get("height"):
                    raise RuntimeError(f"ffprobe omitted {label} video dimensions")
                format_name = probe_data.get("format", {}).get("format_name", "unknown")
                duration = video_stream.get("duration", probe_data.get("format", {}).get("duration"))
                avg_rate = video_stream.get("avg_frame_rate")
                frame_count = video_stream.get("nb_frames")
                audio_present = any(s.get("codec_type") == "audio" for s in probe_data.get("streams", []))
                metadata_details.append(
                    f"{label}: container={format_name}, codec={video_stream.get('codec_name', 'unknown')}, "
                    f"dimensions={video_stream['width']}x{video_stream['height']}, "
                    f"duration={duration if duration is not None else 'unavailable'}, "
                    f"avg_rate={avg_rate if avg_rate is not None else 'unavailable'}, "
                    f"frame_count={frame_count if frame_count is not None else 'unavailable'}, audio={audio_present}"
                )

                with fixture.open("rb") as source:
                    media = ingest_media(
                        source, f"diagnostic-{label}.mp4",
                        limits=MediaLimits(max_file_bytes=8 * 1024 * 1024, max_video_seconds=5,
                                           max_video_fps=30, max_video_side=128,
                                           probe_timeout_seconds=timeout_seconds),
                    )
                try:
                    direct = subprocess.run(
                        [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", media.source_path,
                         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                        capture_output=True, timeout=timeout_seconds, check=False,
                    )
                    expected_bytes = int(media.metadata["width"]) * int(media.metadata["height"]) * 3
                    decoded_ok.append(direct.returncode == 0 and len(direct.stdout) == expected_bytes and expected_bytes > 0)
                    report = analyze_video(
                        media,
                        config=VideoSamplingConfig(interval_seconds=0.25, max_frames=4,
                                                  max_duration_seconds=1, max_frame_side=64,
                                                  timeout_seconds=timeout_seconds,
                                                  max_total_frame_bytes=8 * 1024 * 1024),
                    )
                    sampling_ok.append(report.sampling.get("sampled_count", 0) > 0 and all(
                        frame.timestamp_seconds is not None for frame in report.frames
                    ))
                finally:
                    media.cleanup()

            checks.append(DiagnosticItem(
                "video_metadata_extraction", DiagnosticState.AVAILABLE,
                version="ffprobe",
                detail="ffprobe metadata from real fixtures: " + "; ".join(metadata_details) + ".",
            ))
            checks.append(DiagnosticItem(
                "video_frame_decoding",
                DiagnosticState.AVAILABLE if all(decoded_ok) else DiagnosticState.FAILED_VERIFICATION,
                detail="FFmpeg decoded real MPEG-4 and H.264 frames to their expected nonempty RGB byte counts." if all(decoded_ok) else "A real fixture did not decode to a complete RGB frame.",
            ))
            checks.append(DiagnosticItem(
                "trustlens_video_sampling",
                DiagnosticState.AVAILABLE if all(sampling_ok) else DiagnosticState.FAILED_VERIFICATION,
                detail="TRUSTLENS sampled both generated codecs, preserved timestamps, and ran the image analysis path." if all(sampling_ok) else "TRUSTLENS did not produce timestamped sampled-frame results for every fixture.",
            ))
    except subprocess.TimeoutExpired:
        existing = {item.component for item in checks}
        for component in ("video_metadata_extraction", "video_frame_decoding", "trustlens_video_sampling"):
            if component not in existing:
                checks.append(DiagnosticItem(component, DiagnosticState.FAILED_VERIFICATION, detail="Real fixture verification timed out."))
    except Exception as exc:
        existing = {item.component for item in checks}
        for component in ("video_metadata_extraction", "video_frame_decoding", "trustlens_video_sampling"):
            if component not in existing:
                checks.append(DiagnosticItem(component, DiagnosticState.FAILED_VERIFICATION, detail=f"Real fixture verification failed ({type(exc).__name__})."))


def run_media_diagnostics(*, timeout_seconds: float = 12.0) -> DiagnosticReport:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    checks: list[DiagnosticItem] = [DiagnosticItem(
        "python", DiagnosticState.AVAILABLE, version=sys.version.split()[0], detail="Current diagnostic interpreter.",
    )]
    modules: dict[str, Any | None] = {}
    for module_name, component, distribution in (("numpy", "numpy", "numpy"), ("PIL", "pillow", "Pillow"), ("cv2", "opencv", "opencv-python-headless")):
        item, module = _module_check(module_name, component, distribution)
        checks.append(item)
        modules[module_name] = module
    _image_fixture_checks(checks, modules)
    ffmpeg_item, ffmpeg = _executable_check("ffmpeg", timeout_seconds)
    ffprobe_item, ffprobe = _executable_check("ffprobe", timeout_seconds)
    checks.extend((ffmpeg_item, ffprobe_item))
    _video_fixture_checks(checks, ffmpeg, ffprobe, timeout_seconds)
    return DiagnosticReport("1.0", sys.version.split()[0], checks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local TRUSTLENS media dependency and processing checks.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--timeout", type=float, default=12.0, help="Per-process timeout in seconds.")
    args = parser.parse_args()
    report = run_media_diagnostics(timeout_seconds=args.timeout)
    print(json.dumps(report.to_dict(), indent=2 if args.json else None))


if __name__ == "__main__":
    main()
