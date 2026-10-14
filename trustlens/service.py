"""Backend-facing orchestration and versioned report contract.

This module provides a real in-process workflow for an eventual application
backend. It deliberately does not define HTTP routes, persistence, or auth,
because those contracts are not present in the repository.
"""

from __future__ import annotations

import json
import re
import uuid
import platform
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, BinaryIO

from .evidence_fusion import fuse_reports
from .evidence_graph import build_evidence_graph, validate_evidence_graph
from .image_analysis import ImageDetector, analyze_image
from .ingestion import IngestedMedia, MediaLimits, MediaType, ProcessingStatus, ingest_media
from .provenance import assess_provenance
from .video_analysis import VideoSamplingConfig, analyze_video


REPORT_SCHEMA_VERSION = "1.1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OUTCOMES = {"LIKELY_AUTHENTIC", "AI_GENERATED", "MANIPULATED", "INSUFFICIENT_EVIDENCE_REVIEW"}


def validate_analysis_report(report: AnalysisReport | dict[str, Any]) -> None:
    """Validate the public report envelope before it leaves the service layer.

    This is a dependency-free contract validator, not a replacement for the
    consuming application's API framework or its authorization checks.
    """
    value = report.to_dict() if isinstance(report, AnalysisReport) else report
    if not isinstance(value, dict):
        raise ValueError("Analysis report must be an object.")
    required = {
        "schema_version", "report_id", "processing_status", "proposed_outcome",
        "human_review_required", "source", "validation", "analysis", "fusion",
        "uncertainty", "limitations", "errors",
    }
    if not required.issubset(value):
        raise ValueError("Analysis report is missing required top-level fields.")
    if value["schema_version"] not in {"1.0", REPORT_SCHEMA_VERSION}:
        raise ValueError("Analysis report schema_version is unsupported.")
    if value["schema_version"] == REPORT_SCHEMA_VERSION:
        try:
            generated_at = datetime.fromisoformat(value["generated_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError("Analysis report generated_at must be an ISO-8601 timestamp.") from exc
        if generated_at.tzinfo is None or not isinstance(value.get("producer"), dict):
            raise ValueError("Analysis report reproducibility metadata is incomplete.")
        if value["producer"].get("name") != "TRUSTLENS" or value["producer"].get("version") != "LOCAL_UNVERSIONED":
            raise ValueError("Analysis report producer identity is invalid.")
    try:
        uuid.UUID(value["report_id"])
        status = ProcessingStatus(value["processing_status"])
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Analysis report id or processing status is invalid.") from exc
    if not isinstance(value["proposed_outcome"], str) or value["proposed_outcome"] not in _OUTCOMES or not isinstance(value["human_review_required"], bool):
        raise ValueError("Analysis report outcome or review flag is invalid.")

    source = value["source"]
    if not isinstance(source, dict) or any(key not in source for key in ("source_id", "filename", "media_type", "sha256", "size_bytes", "metadata")):
        raise ValueError("Analysis report source is incomplete.")
    if not isinstance(source["source_id"], str) or not source["source_id"] or not isinstance(source["filename"], str) or not source["filename"]:
        raise ValueError("Analysis report source identity is invalid.")
    if source["filename"] in {".", ".."} or any(char in source["filename"] for char in ("/", "\\")) or any(ord(char) < 32 for char in source["filename"]):
        raise ValueError("Analysis report filename must be a sanitized display name, not a path.")
    if not isinstance(source["media_type"], str) or source["media_type"] not in {item.value for item in MediaType}:
        raise ValueError("Analysis report media type is unsupported.")
    if not isinstance(source["sha256"], str) or not _SHA256.fullmatch(source["sha256"]):
        raise ValueError("Analysis report source hash must be a lowercase SHA-256 digest.")
    if not isinstance(source["size_bytes"], int) or isinstance(source["size_bytes"], bool) or source["size_bytes"] <= 0:
        raise ValueError("Analysis report source size must be a positive integer.")
    if not isinstance(source["metadata"], dict):
        raise ValueError("Analysis report source metadata must be an object.")
    if value["schema_version"] == REPORT_SCHEMA_VERSION:
        validate_evidence_graph(
            value.get("evidence_graph"), source_id=source["source_id"],
            source_sha256=source["sha256"], report_id=value["report_id"],
        )

    validation = value["validation"]
    analysis = value["analysis"]
    uncertainty = value["uncertainty"]
    if not isinstance(validation, dict) or not isinstance(analysis, dict) or not isinstance(uncertainty, dict):
        raise ValueError("Validation, analysis, and uncertainty sections must be objects.")
    try:
        validation_status = ProcessingStatus(validation.get("status"))
        analysis_status = ProcessingStatus(analysis.get("status"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Analysis report contains an invalid phase status.") from exc
    for container, key in ((validation, "warnings"), (validation, "errors"), (value, "limitations"), (value, "errors")):
        if not isinstance(container.get(key), list) or not all(isinstance(item, str) for item in container[key]):
            raise ValueError(f"Analysis report {key} must be a list of strings.")
    if not isinstance(validation.get("preprocessing", {}), dict):
        raise ValueError("Analysis report preprocessing must be an object.")
    expected_kind = source["media_type"]
    if analysis.get("kind") != expected_kind:
        raise ValueError("Analysis kind must match the uploaded media type.")
    if expected_kind == MediaType.AUDIO.value:
        if analysis.get("result") is not None or value["fusion"] is not None or status not in {ProcessingStatus.UNAVAILABLE, ProcessingStatus.FAILED}:
            raise ValueError("Deferred audio reports must be unavailable or failed and contain no detector or fusion result.")
        if analysis_status != status:
            raise ValueError("Audio analysis and overall processing statuses must match.")
        if status == ProcessingStatus.FAILED and (not isinstance(analysis.get("failure_stage"), str) or not analysis["failure_stage"]):
            raise ValueError("Failed audio processing must identify the failed stage.")
    elif analysis_status == ProcessingStatus.FAILED:
        if analysis.get("result") is not None or value["fusion"] is not None or status != ProcessingStatus.FAILED:
            raise ValueError("Failed analyses must not include a result or fusion assessment.")
        if not isinstance(analysis.get("failure_stage"), str) or not analysis["failure_stage"]:
            raise ValueError("Failed analyses must identify the failed processing stage.")
        if status != _status(validation_status, analysis_status):
            raise ValueError("Overall processing status must match validation and analysis statuses.")
    else:
        result = analysis.get("result")
        fusion = value["fusion"]
        if not isinstance(result, dict) or not isinstance(fusion, dict):
            raise ValueError("Image/video reports require analysis and fusion objects.")
        if fusion.get("schema_version") != "1.0":
            raise ValueError("Fusion report schema_version is unsupported.")
        try:
            ProcessingStatus(fusion.get("processing_status"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Fusion report processing status is invalid.") from exc
        if result.get("source_id") != source["source_id"] or result.get("source_sha256") != source["sha256"]:
            raise ValueError("Analysis provenance must match the report source.")
        if result.get("processing_status") != analysis_status.value:
            raise ValueError("Analysis status must match the embedded assessment status.")
        if fusion.get("schema_version") is None or fusion.get("proposed_outcome") != "INSUFFICIENT_EVIDENCE_REVIEW" or fusion.get("human_review_required") is not True:
            raise ValueError("Fusion report must preserve the current abstention contract.")
        source_refs = fusion.get("source_reports")
        if not isinstance(source_refs, list) or not any(
            isinstance(item, dict) and item.get("source_id") == source["source_id"] and item.get("source_sha256") == source["sha256"]
            for item in source_refs
        ):
            raise ValueError("Fusion report must retain the uploaded source reference.")
        if status != _status(validation_status, analysis_status):
            raise ValueError("Overall processing status must match validation and analysis statuses.")
    if not isinstance(uncertainty.get("calibration_status"), str) or not isinstance(uncertainty.get("abstention_reason"), str):
        raise ValueError("Uncertainty report must include calibration status and abstention reason.")
    if not isinstance(uncertainty.get("uncertainty_status", "NOT_ASSESSED"), str):
        raise ValueError("Uncertainty status must be text.")
    if status == ProcessingStatus.SUCCESS and analysis_status != ProcessingStatus.SUCCESS:
        raise ValueError("Overall SUCCESS requires successful analysis.")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Analysis report is not strict JSON serializable.") from exc


@dataclass
class AnalysisReport:
    """Serializable response envelope for one uploaded media analysis."""

    schema_version: str
    report_id: str
    processing_status: ProcessingStatus
    proposed_outcome: str
    human_review_required: bool
    source: dict[str, Any]
    validation: dict[str, Any]
    analysis: dict[str, Any]
    fusion: dict[str, Any] | None
    uncertainty: dict[str, Any]
    limitations: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready report using string enum values."""
        report = asdict(self)
        report["processing_status"] = self.processing_status.value
        report["producer"] = {"name": "TRUSTLENS", "version": "LOCAL_UNVERSIONED", "python_version": platform.python_version()}
        report["evidence_graph"] = build_evidence_graph(report)
        return report


def _status(media_status: ProcessingStatus, analysis_status: ProcessingStatus) -> ProcessingStatus:
    statuses = (media_status, analysis_status)
    if ProcessingStatus.FAILED in statuses:
        return ProcessingStatus.FAILED
    if ProcessingStatus.PARTIAL in statuses:
        return ProcessingStatus.PARTIAL
    if ProcessingStatus.UNAVAILABLE in statuses:
        return ProcessingStatus.UNAVAILABLE
    return ProcessingStatus.SUCCESS


def _unavailable_audio_report(media: IngestedMedia) -> AnalysisReport:
    reason = "Audio forensic analysis is deferred; this upload was validated but not analyzed."
    return AnalysisReport(
        schema_version=REPORT_SCHEMA_VERSION,
        report_id=str(uuid.uuid4()),
        processing_status=ProcessingStatus.UNAVAILABLE,
        proposed_outcome="INSUFFICIENT_EVIDENCE_REVIEW",
        human_review_required=True,
        source={
            "source_id": media.source_id,
            "filename": media.source_name,
            "media_type": media.detected_type.value,
            "sha256": media.source_sha256,
            "size_bytes": media.original_size_bytes,
            "metadata": media.metadata,
        },
        validation={
            "status": media.status.value,
            "warnings": list(media.warnings),
            "errors": list(media.errors),
        },
        analysis={"kind": "audio", "status": ProcessingStatus.UNAVAILABLE.value, "result": None},
        fusion=None,
        uncertainty={
            "calibration_status": "NOT_APPLICABLE",
            "uncertainty_status": "NOT_ASSESSED",
            "abstention_reason": reason,
        },
        limitations=[reason],
        errors=[],
    )


def _failed_report(media: IngestedMedia, stage: str) -> AnalysisReport:
    """Create a safe failure response without exposing exception internals."""
    kind = media.detected_type.value
    message = f"Analysis failed during {stage}; no forensic assessment was produced."
    report = AnalysisReport(
        schema_version=REPORT_SCHEMA_VERSION,
        report_id=str(uuid.uuid4()),
        processing_status=ProcessingStatus.FAILED,
        proposed_outcome="INSUFFICIENT_EVIDENCE_REVIEW",
        human_review_required=True,
        source={
            "source_id": media.source_id,
            "filename": media.source_name,
            "media_type": kind,
            "sha256": media.source_sha256,
            "size_bytes": media.original_size_bytes,
            "metadata": media.metadata,
        },
        validation={
            "status": media.status.value,
            "warnings": list(media.warnings),
            "errors": list(media.errors),
            "preprocessing": media.preprocessing,
        },
        analysis={
            "kind": kind,
            "status": ProcessingStatus.FAILED.value,
            "result": None,
            "failure_stage": stage,
        },
        fusion=None,
        uncertainty={
            "calibration_status": "NOT_ASSESSED",
            "uncertainty_status": "NOT_ASSESSED",
            "abstention_reason": "The analysis pipeline failed before producing evidence.",
        },
        limitations=["No forensic assessment was produced because processing failed."],
        errors=[message],
    )
    validate_analysis_report(report)
    return report


def analyze_upload(
    source: BinaryIO,
    filename: str,
    *,
    detector: ImageDetector | None = None,
    limits: MediaLimits | None = None,
    video_config: VideoSamplingConfig | None = None,
) -> AnalysisReport:
    """Run the available upload→analysis→fusion workflow and return a report.

    The caller owns ``source``. The staged original and temporary derived files
    are removed before this function returns. Invalid uploads raise
    ``IngestionError`` for the caller to map to its own API error contract.
    """
    media = ingest_media(source, filename, limits=limits)
    stage = "analysis"
    try:
        if media.detected_type == MediaType.AUDIO:
            report = _unavailable_audio_report(media)
            validate_analysis_report(report)
            return report

        if media.detected_type == MediaType.IMAGE:
            assessment = analyze_image(media, detector=detector)
            analysis_kind = "image"
        elif media.detected_type == MediaType.VIDEO:
            assessment = analyze_video(media, detector=detector, config=video_config)
            analysis_kind = "video"
        else:  # Defensive guard for future media types.
            raise ValueError(f"Unsupported analysis media type: {media.detected_type.value}")

        assessment_dict = assessment.to_dict()
        assessment_dict["provenance"] = assess_provenance(
            analysis_kind, media.metadata, parser_warnings=media.warnings,
        )
        stage = "fusion"
        fusion_dict = fuse_reports(assessment_dict).to_dict()
        analysis_status = assessment.processing_status
        overall_status = _status(media.status, analysis_status)
        limitations = list(getattr(assessment, "limitations", []))
        errors = list(getattr(assessment, "errors", []))
        if analysis_kind == "video":
            limitations.append(
                "Sampled frame artifacts are temporary and removed before this report is returned; artifact_reference values are report-local labels, not retrievable URLs."
            )
        limitations.extend(item for item in media.warnings if item not in limitations)
        errors.extend(item for item in media.errors if item not in errors)
        calibration_status = (
            assessment_dict.get("uncertainty", {}).get("calibration_status", "NOT_ASSESSED")
            if analysis_kind == "image" else "NOT_CALIBRATED"
        )
        report = AnalysisReport(
            schema_version=REPORT_SCHEMA_VERSION,
            report_id=str(uuid.uuid4()),
            processing_status=overall_status,
            proposed_outcome="INSUFFICIENT_EVIDENCE_REVIEW",
            human_review_required=True,
            source={
                "source_id": media.source_id,
                "filename": media.source_name,
                "media_type": media.detected_type.value,
                "sha256": media.source_sha256,
                "size_bytes": media.original_size_bytes,
                "metadata": media.metadata,
            },
            validation={
                "status": media.status.value,
                "warnings": list(media.warnings),
                "errors": list(media.errors),
                "preprocessing": media.preprocessing,
            },
            analysis={
                "kind": analysis_kind,
                "status": analysis_status.value,
                "result": assessment_dict,
            },
            fusion=fusion_dict,
            uncertainty={
                "calibration_status": calibration_status,
                "uncertainty_status": "NOT_ASSESSED",
                "abstention_reason": "No calibrated classification or fusion decision is configured.",
            },
            limitations=limitations,
            errors=errors,
        )
        stage = "report_validation"
        validate_analysis_report(report)
        return report
    except Exception:
        return _failed_report(media, stage)
    finally:
        media.cleanup()
