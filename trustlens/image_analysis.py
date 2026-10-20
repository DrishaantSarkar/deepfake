"""Image-analysis contracts and measured, non-classifying evidence.

No deepfake model or compatible tensor runtime is present in this workspace.
Accordingly, this module never invents detector scores or a media verdict.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageOps

from .ingestion import IngestedMedia, MediaType, ProcessingStatus


REPORT_SCHEMA_VERSION = "1.0"
FREQUENCY_METHOD = "orthonormal-2d-dct-ii-thumbnail-v1"


@dataclass(frozen=True)
class DetectorDescriptor:
    """Declared behavior and provenance for a real image detector adapter."""

    name: str
    version: str
    supported_inputs: tuple[str, ...]
    preprocessing: str
    output_labels: tuple[str, ...]
    score_semantics: str
    resource_requirements: str
    limitations: tuple[str, ...]
    evaluation_status: str
    calibration_status: str
    label_space: str | None = None


@dataclass(frozen=True)
class DetectorOutput:
    """Raw model output; values are not assumed to be probabilities."""

    status: ProcessingStatus
    raw_scores: dict[str, float] = field(default_factory=dict)
    predicted_label: str | None = None
    error: str | None = None


class ImageDetector(Protocol):
    descriptor: DetectorDescriptor

    def predict(self, image: Image.Image) -> DetectorOutput:
        """Run actual model inference on an RGB Pillow image."""


@dataclass
class EvidenceChannel:
    source: str
    method: str
    method_version: str
    status: ProcessingStatus
    measured_signal: dict[str, Any] = field(default_factory=dict)
    output_semantics: str = ""
    limitations: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ImageAssessment:
    schema_version: str
    source_id: str
    source_sha256: str
    media_type: MediaType
    processing_status: ProcessingStatus
    proposed_outcome: str
    human_review_required: bool
    detector: dict[str, Any]
    evidence: list[EvidenceChannel]
    localization: dict[str, Any]
    uncertainty: dict[str, Any]
    limitations: list[str]
    preprocessing: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready assessment preserving explicit enum values."""
        return asdict(self) | {
            "media_type": self.media_type.value,
            "processing_status": self.processing_status.value,
            "evidence": [
                asdict(channel) | {"status": channel.status.value}
                for channel in self.evidence
            ],
        }


def _dct_matrix(size: int) -> list[list[float]]:
    """Build an orthonormal DCT-II transform matrix."""
    scale0 = math.sqrt(1.0 / size)
    scale = math.sqrt(2.0 / size)
    return [
        [
            (scale0 if frequency == 0 else scale)
            * math.cos(math.pi * (2 * sample + 1) * frequency / (2 * size))
            for sample in range(size)
        ]
        for frequency in range(size)
    ]


def _frequency_measurement(image: Image.Image, size: int = 32) -> EvidenceChannel:
    """Measure coarse DCT energy bands on a fixed-size grayscale thumbnail.

    This is a descriptive signal only. It does not detect manipulation and has
    no validated anomaly threshold. The thumbnail resize itself affects energy.
    """
    gray = ImageOps.grayscale(image)
    gray.thumbnail((size, size), Image.Resampling.LANCZOS)
    sample = gray.resize((size, size), Image.Resampling.LANCZOS)
    pixels = []
    for y in range(size):
        row = []
        for x in range(size):
            p_val = sample.getpixel((x, y))
            num = float(p_val[0] if isinstance(p_val, (tuple, list)) else p_val)  # type: ignore[arg-type]
            row.append(num - 127.5)
        pixels.append(row)
    transform = _dct_matrix(size)
    # Separable two-dimensional DCT-II: O(N^3), with a fixed small N.
    horizontal = [
        [sum(transform[u][x] * pixels[y][x] for x in range(size)) for u in range(size)]
        for y in range(size)
    ]
    coefficients = [
        [sum(transform[v][y] * horizontal[y][u] for y in range(size)) for u in range(size)]
        for v in range(size)
    ]
    bands = {"low": 0.0, "mid": 0.0, "high": 0.0}
    for v in range(size):
        for u in range(size):
            if u == 0 and v == 0:
                continue
            band = "low" if max(u, v) <= 3 else "high" if max(u, v) >= 16 else "mid"
            bands[band] += coefficients[v][u] ** 2
    total = sum(bands.values())
    measured: dict[str, Any]
    if total == 0:
        measured = {"thumbnail_width": size, "thumbnail_height": size, "ac_energy": 0.0,
                    "energy_fraction_by_band": None}
        semantics = "No non-DC DCT energy was measured; band fractions are undefined."
    else:
        measured = {
            "thumbnail_width": size,
            "thumbnail_height": size,
            "ac_energy": total,
            "energy_fraction_by_band": {key: value / total for key, value in bands.items()},
        }
        semantics = "Fractions of measured non-DC squared DCT energy in coarse frequency bands."
    return EvidenceChannel(
        source="frequency_descriptor",
        method=FREQUENCY_METHOD,
        method_version="1",
        status=ProcessingStatus.SUCCESS,
        measured_signal=measured,
        output_semantics=semantics,
        limitations=[
            "Descriptive transform statistics only; no anomaly threshold or manipulation inference is defined.",
            "Thumbnail resizing, compression, and ordinary editing affect the measured spectrum.",
            "Not evaluated or calibrated for synthetic-media detection.",
        ],
    )


def _to_analysis_rgb(image: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
    """Prepare declared RGB model input without silently dropping transparency."""
    alpha_present = "A" in image.getbands() or "transparency" in image.info
    if alpha_present:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        rgb = Image.alpha_composite(background, rgba).convert("RGB")
        alpha_policy = "alpha composited onto white for RGB analysis; normalized source artifact retains alpha"
    else:
        rgb = image.convert("RGB")
        alpha_policy = "no alpha channel"
    return rgb, {"model_input_color_mode": "RGB", "alpha_present": alpha_present, "alpha_policy": alpha_policy}


def _detector_result(image: Image.Image, detector: ImageDetector | None) -> dict[str, Any]:
    if detector is None:
        return {
            "status": ProcessingStatus.UNAVAILABLE.value,
            "model": None,
            "raw_scores": None,
            "predicted_label": None,
            "score_semantics": None,
            "evaluation_status": "NOT_EVALUATED",
            "calibration_status": "NOT_CALIBRATED",
            "label_space": None,
            "error": "No compatible configured image detector or model weights are available.",
        }
    descriptor = detector.descriptor
    if "RGB Pillow image" not in descriptor.supported_inputs:
        return {
            "status": ProcessingStatus.UNAVAILABLE.value,
            "model": {"name": descriptor.name, "version": descriptor.version},
            "raw_scores": None,
            "predicted_label": None,
            "score_semantics": descriptor.score_semantics,
            "evaluation_status": descriptor.evaluation_status,
            "calibration_status": descriptor.calibration_status,
            "label_space": descriptor.label_space,
            "error": "Detector does not declare support for the normalized RGB Pillow input.",
        }
    try:
        output = detector.predict(image)
    except Exception as exc:
        return {
            "status": ProcessingStatus.FAILED.value,
            "model": {"name": descriptor.name, "version": descriptor.version},
            "raw_scores": None,
            "predicted_label": None,
            "score_semantics": descriptor.score_semantics,
            "evaluation_status": descriptor.evaluation_status,
            "calibration_status": descriptor.calibration_status,
            "label_space": descriptor.label_space,
            "error": f"Model inference failed ({type(exc).__name__}).",
        }
    valid_labels = set(descriptor.output_labels)
    if not descriptor.name or not descriptor.version or output.status != ProcessingStatus.SUCCESS:
        return {
            "status": output.status.value,
            "model": {"name": descriptor.name, "version": descriptor.version},
            "raw_scores": None,
            "predicted_label": None,
            "score_semantics": descriptor.score_semantics,
            "evaluation_status": descriptor.evaluation_status,
            "calibration_status": descriptor.calibration_status,
            "label_space": descriptor.label_space,
            "error": output.error or "Detector did not return a successful inference.",
        }
    if output.predicted_label is not None and output.predicted_label not in valid_labels:
        raise ValueError("Detector returned a label not declared in its descriptor.")
    if any(label not in valid_labels or not math.isfinite(score) for label, score in output.raw_scores.items()):
        raise ValueError("Detector scores must be finite and use declared output labels.")
    return {
        "status": ProcessingStatus.SUCCESS.value,
        "model": {
            "name": descriptor.name,
            "version": descriptor.version,
            "supported_inputs": list(descriptor.supported_inputs),
            "preprocessing": descriptor.preprocessing,
            "output_labels": list(descriptor.output_labels),
            "label_space": descriptor.label_space,
            "resource_requirements": descriptor.resource_requirements,
            "limitations": list(descriptor.limitations),
        },
        "raw_scores": dict(output.raw_scores),
        "predicted_label": output.predicted_label,
        "score_semantics": descriptor.score_semantics,
        "evaluation_status": descriptor.evaluation_status,
        "calibration_status": descriptor.calibration_status,
        "label_space": descriptor.label_space,
        "error": None,
    }


def analyze_image(media: IngestedMedia, detector: ImageDetector | None = None) -> ImageAssessment:
    """Analyze a successfully ingested image and return a versioned assessment.

    With no configured detector, the result explicitly abstains. Frequency
    measurements are retained as a separate descriptive evidence channel.
    """
    if media.detected_type != MediaType.IMAGE:
        raise ValueError("Image analysis requires ingested image media.")
    if not media.normalized_image_path or not Path(media.normalized_image_path).is_file():
        raise ValueError("The normalized image artifact is unavailable; ingest the image first.")
    with Image.open(media.normalized_image_path) as opened:
        image, input_preprocessing = _to_analysis_rgb(opened)
        frequency = _frequency_measurement(image)
        detector_result = _detector_result(image, detector)
    detector_status = ProcessingStatus(detector_result["status"])
    outcome = "INSUFFICIENT_EVIDENCE_REVIEW"
    whole_image = EvidenceChannel(
        source="whole_image_detector",
        method=detector_result["model"]["name"] if detector_result["model"] else "configured_image_detector",
        method_version=detector_result["model"]["version"] if detector_result["model"] else "unavailable",
        status=detector_status,
        measured_signal={"raw_scores": detector_result["raw_scores"],
                         "predicted_label": detector_result["predicted_label"]},
        output_semantics=detector_result["score_semantics"] or "No detector output was produced.",
        limitations=["Raw detector outputs are not assumed to be calibrated probabilities."],
        error=detector_result["error"],
    )
    spatial = EvidenceChannel(
        source="spatial_detector",
        method="spatial_localization_model",
        method_version="unavailable",
        status=ProcessingStatus.UNAVAILABLE,
        output_semantics="No spatial localization is emitted without a model that supports it.",
        limitations=["No compatible spatial deepfake detector or model weights are configured."],
    )
    face = EvidenceChannel(
        source="face_regions",
        method="face_detection_and_region_crops",
        method_version="unavailable",
        status=ProcessingStatus.UNAVAILABLE,
        output_semantics="Face presence and regions were not assessed.",
        limitations=["OpenCV and a configured face detector are unavailable; no conclusion about faces is made."],
    )
    localization = {
        "regions": [],
        "status": ProcessingStatus.UNAVAILABLE.value,
        "explanation": "No model-supported localization or explainability output is available.",
    }
    limitations = [
        "No deepfake classification is produced because no configured model inference is available.",
        "The frequency descriptor is not a classifier and has no validated decision threshold.",
        "No calibrated confidence, out-of-distribution assessment, or manipulation probability is available.",
    ]
    return ImageAssessment(
        schema_version=REPORT_SCHEMA_VERSION,
        source_id=media.source_id,
        source_sha256=media.source_sha256,
        media_type=MediaType.IMAGE,
        processing_status=ProcessingStatus.PARTIAL,
        proposed_outcome=outcome,
        human_review_required=True,
        detector=detector_result,
        evidence=[whole_image, spatial, frequency, face],
        localization=localization,
        uncertainty={
            "calibration_status": detector_result["calibration_status"],
            "uncertainty_status": "NOT_ASSESSED",
            "out_of_distribution_status": "NOT_ASSESSED",
            "abstention_reason": "Required trained detector evidence is unavailable.",
        },
        limitations=limitations,
        preprocessing=input_preprocessing,
    )
