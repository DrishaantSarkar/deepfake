"""Audio analysis pipeline and experimental forensic descriptors for TRUSTLENS.

AUDIO DETECTION — BETA:
Audio detection is experimental. Results may contain false positives or false
negatives and should not be treated as definitive proof of authenticity.
"""
from __future__ import annotations

import importlib
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

np: Any = None
try:
    np = importlib.import_module("numpy")
except (ImportError, ModuleNotFoundError):
    np = None

from .ingestion import IngestedMedia, MediaType, ProcessingStatus

AUDIO_REPORT_SCHEMA_VERSION = "1.0"
AUDIO_BETA_LABEL = "AUDIO DETECTION — BETA"
AUDIO_BETA_WARNING = (
    "Audio detection is experimental. Results may contain false positives or false "
    "negatives and should not be treated as definitive proof of authenticity."
)


@dataclass
class AudioAssessment:
    """Structured result of experimental audio analysis."""

    schema_version: str = AUDIO_REPORT_SCHEMA_VERSION
    status: ProcessingStatus = ProcessingStatus.UNAVAILABLE
    beta_label: str = AUDIO_BETA_LABEL
    beta_warning: str = AUDIO_BETA_WARNING
    technical_metadata: dict[str, Any] = field(default_factory=dict)
    signal_descriptors: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_audio(media: IngestedMedia) -> AudioAssessment:
    """Extract descriptive, non-classifying acoustic measurements from an audio upload."""
    if media.detected_type != MediaType.AUDIO:
        return AudioAssessment(
            status=ProcessingStatus.FAILED,
            limitations=[AUDIO_BETA_WARNING],
            errors=["Uploaded media is not recognized as an audio format."],
        )

    path = Path(media.source_path)
    if not path.is_file():
        return AudioAssessment(
            status=ProcessingStatus.FAILED,
            limitations=[AUDIO_BETA_WARNING],
            errors=[f"Audio file is missing from staged path: {path}"],
        )

    technical: dict[str, Any] = {}
    descriptors: dict[str, Any] = {}
    limitations = [
        AUDIO_BETA_WARNING,
        "Automated detection is currently unavailable, and the available evidence is insufficient for a reliable authenticity assessment.",
        "Acoustic signal descriptors are purely descriptive and do not constitute a calibrated deepfake prediction.",
    ]
    errors: list[str] = []

    # Attempt WAV decoding via standard library
    try:
        with wave.open(str(path), "rb") as wf:
            num_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frame_rate = wf.getframerate()
            num_frames = wf.getnframes()
            duration_s = float(num_frames) / float(frame_rate) if frame_rate > 0 else 0.0

            technical = {
                "format": "WAV_PCM",
                "channels": num_channels,
                "sample_rate_hz": frame_rate,
                "bit_depth": sample_width * 8,
                "num_frames": num_frames,
                "duration_seconds": round(duration_s, 4),
            }

            # Read up to first 5 seconds for bounded, fast descriptor extraction
            max_frames_to_read = min(num_frames, frame_rate * 5)
            raw_frames = wf.readframes(max_frames_to_read)

            if sample_width == 2 and len(raw_frames) >= 2:
                samples = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
                if num_channels > 1:
                    samples = samples.reshape(-1, num_channels).mean(axis=1)

                if len(samples) > 0:
                    rms = float(np.sqrt(np.mean(samples ** 2)))
                    peak = float(np.max(np.abs(samples)))
                    zero_crossings = int(np.sum(np.diff(samples > 0) != 0))
                    zcr = float(zero_crossings) / float(len(samples))

                    # Approximate spectral centroid via FFT
                    fft_mag = np.abs(np.fft.rfft(samples[:min(len(samples), 4096)]))
                    freqs = np.fft.rfftfreq(min(len(samples), 4096), d=1.0 / frame_rate)
                    centroid = float(np.sum(freqs * fft_mag) / (np.sum(fft_mag) + 1e-12))

                    descriptors = {
                        "sample_rate_hz": frame_rate,
                        "channels": num_channels,
                        "duration_seconds": round(duration_s, 4),
                        "rms_energy": round(rms, 6),
                        "peak_amplitude": round(peak, 6),
                        "zero_crossing_rate": round(zcr, 6),
                        "spectral_centroid_hz": round(centroid, 2),
                    }
    except wave.Error as exc:
        technical = {"format": "compressed_or_unsupported"}
        limitations.append(f"Standard PCM audio decoding unavailable: {exc}")
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        technical = {"format": "unknown"}
        errors.append(f"Acoustic measurement extraction failed: {type(exc).__name__}")

    return AudioAssessment(
        status=ProcessingStatus.UNAVAILABLE,
        beta_label=AUDIO_BETA_LABEL,
        beta_warning=AUDIO_BETA_WARNING,
        technical_metadata=technical,
        signal_descriptors=descriptors,
        limitations=limitations,
        errors=errors,
    )


def is_audio_available() -> bool:
    """Return whether the experimental audio analysis pipeline is available."""
    return True


def analyze_audio_file(file_path: str | Path) -> dict[str, Any]:
    """Analyze an audio file directly from disk and return a dictionary."""
    path = Path(file_path)
    if not path.is_file():
        return AudioAssessment(
            status=ProcessingStatus.FAILED,
            limitations=[AUDIO_BETA_WARNING],
            errors=[f"Audio file does not exist: {path}"],
        ).to_dict()

    dummy_media = IngestedMedia(
        schema_version="1.0",
        source_id="local_file",
        source_name=path.name,
        source_sha256="",
        detected_type=MediaType.AUDIO,
        original_size_bytes=path.stat().st_size,
        original_format=path.suffix.lstrip(".").upper(),
        source_path=str(path),
    )
    return analyze_audio(dummy_media).to_dict()

