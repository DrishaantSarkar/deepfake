"""Evidence-preserving fusion for TRUSTLENS image and video reports.

This phase organizes evidence and flags narrowly defined disagreements. It does
not average scores or produce a media-authenticity decision without calibrated
fusion and evaluated detectors.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .ingestion import ProcessingStatus


FUSION_SCHEMA_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class EvidenceRecord:
    evidence_id: str
    source_id: str
    source_sha256: str
    media_type: str
    evidence_source: str
    method: str
    method_version: str
    status: str
    measured_signal: dict[str, Any]
    output_semantics: str
    limitations: list[str] = field(default_factory=list)
    error: str | None = None
    model: dict[str, Any] | None = None
    label_space: str | None = None
    output_labels: list[str] | None = None
    correlation_group: str | None = None
    parent_video_id: str | None = None
    parent_video_sha256: str | None = None
    frame_sha256: str | None = None
    timestamp_seconds: float | None = None


@dataclass
class FusionAssessment:
    schema_version: str
    processing_status: str
    proposed_outcome: str
    human_review_required: bool
    calibrated: bool
    aggregation_method: str
    evidence: list[EvidenceRecord]
    conflicts: list[dict[str, Any]]
    source_reports: list[dict[str, Any]]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase 64-character SHA-256 digest.")
    return value


def _safe_signal(signal: Any) -> dict[str, Any]:
    if not isinstance(signal, dict):
        raise ValueError("Evidence measured_signal must be an object.")
    def walk(value: Any) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Evidence signals cannot contain non-finite numbers.")
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError("Evidence signal object keys must be strings.")
            for child in value.values():
                walk(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                walk(child)
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("Evidence signals must contain JSON-compatible values.")
    walk(signal)
    return deepcopy(signal)


def _record(source_id: str, digest: str, media_type: str, channel: dict[str, Any], *,
            parent_video_id: str | None = None, parent_video_sha256: str | None = None,
            frame_sha256: str | None = None, timestamp_seconds: float | None = None,
            model: dict[str, Any] | None = None, label_space: str | None = None,
            correlation_group: str | None = None) -> EvidenceRecord:
    required = ("source", "method", "method_version", "status")
    if any(not isinstance(channel.get(key), str) or not channel[key].strip() for key in required):
        raise ValueError("Evidence requires non-empty source, method, version, and status fields.")
    if isinstance(timestamp_seconds, bool):
        raise ValueError("Frame timestamp must be a finite non-negative number.")
    try:
        status = ProcessingStatus(channel["status"]).value
    except (TypeError, ValueError) as exc:
        raise ValueError("Evidence status is not a recognized processing status.") from exc
    if timestamp_seconds is not None and (not isinstance(timestamp_seconds, (int, float)) or not math.isfinite(timestamp_seconds) or timestamp_seconds < 0):
        raise ValueError("Frame timestamp must be a finite non-negative number.")
    measured = _safe_signal(channel.get("measured_signal", {}))
    if status == ProcessingStatus.SUCCESS.value and not measured:
        raise ValueError("Successful evidence must retain a measured signal.")
    semantics = channel.get("output_semantics", "")
    limitations = channel.get("limitations", [])
    error = channel.get("error")
    if not isinstance(semantics, str) or not isinstance(limitations, list) or not all(isinstance(item, str) for item in limitations):
        raise ValueError("Evidence semantics must be text and limitations must be a list of strings.")
    if error is not None and not isinstance(error, str):
        raise ValueError("Evidence error must be text or null.")
    identity = {
        "source_id": source_id, "source_sha256": digest, "source": channel["source"],
        "method": channel["method"], "method_version": channel["method_version"],
        "frame_sha256": frame_sha256,
    }
    identity_bytes = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    evidence_id = hashlib.sha256(identity_bytes).hexdigest()
    return EvidenceRecord(
        evidence_id=evidence_id, source_id=source_id, source_sha256=digest,
        media_type=media_type, evidence_source=channel["source"], method=channel["method"],
        method_version=channel["method_version"], status=status, measured_signal=measured,
        output_semantics=semantics,
        limitations=list(limitations), error=error,
        model=model, label_space=label_space, output_labels=(list(model["output_labels"]) if model and isinstance(model.get("output_labels"), list) else None),
        correlation_group=correlation_group,
        parent_video_id=parent_video_id, parent_video_sha256=parent_video_sha256,
        frame_sha256=frame_sha256, timestamp_seconds=timestamp_seconds,
    )


def _image_records(report: dict[str, Any], *, parent_video_id: str | None = None,
                   parent_video_sha256: str | None = None, frame_sha256: str | None = None,
                   timestamp_seconds: float | None = None) -> list[EvidenceRecord]:
    source_id = report.get("source_id")
    digest = _validate_sha256(report.get("source_sha256"), "source_sha256")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("Each report requires a non-empty source_id.")
    records: list[EvidenceRecord] = []
    channels = report.get("evidence")
    if not isinstance(channels, list):
        raise ValueError("Image report evidence must be a list.")
    detector_raw = report.get("detector")
    detector: dict[str, Any] = detector_raw if isinstance(detector_raw, dict) else {}
    model_raw = detector.get("model")
    model: dict[str, Any] | None = model_raw if isinstance(model_raw, dict) else None
    label_space = detector.get("label_space")
    detector_correlation_group = detector.get("correlation_group")
    detector_status = detector.get("status")
    if detector_status is not None:
        try:
            detector_status = ProcessingStatus(detector_status).value
        except (TypeError, ValueError) as exc:
            raise ValueError("Detector status is not a recognized processing status.") from exc
    if label_space is not None and (not isinstance(label_space, str) or not label_space.strip()):
        raise ValueError("Detector label_space must be a non-empty string when provided.")
    if detector_correlation_group is not None and (not isinstance(detector_correlation_group, str) or not detector_correlation_group.strip()):
        raise ValueError("Detector correlation_group must be a non-empty string when provided.")
    if detector_status == ProcessingStatus.SUCCESS.value:
        if not isinstance(model, dict) or any(not isinstance(model.get(key), str) or not model[key].strip() for key in ("name", "version")):
            raise ValueError("Successful detector output requires non-empty model name and version metadata.")
        labels = model.get("output_labels")
        if not isinstance(labels, list) or not labels or any(not isinstance(label, str) or not label.strip() for label in labels):
            raise ValueError("Successful detector output requires declared non-empty output_labels.")
        if len(labels) != len(set(labels)):
            raise ValueError("Detector output_labels must be unique.")
    for channel in channels:
        if not isinstance(channel, dict):
            raise ValueError("Evidence channels must be objects.")
        channel_model = model if channel.get("source") == "whole_image_detector" else None
        if channel_model and detector_status is not None and channel.get("status") != detector_status:
            raise ValueError("Whole-image evidence status must match the detector result status.")
        if channel_model and channel.get("status") == ProcessingStatus.SUCCESS.value:
            if detector_status != ProcessingStatus.SUCCESS.value or not model:
                raise ValueError("Successful whole-image evidence requires a matching successful detector result.")
            signal = channel.get("measured_signal", {})
            if not isinstance(signal, dict):
                raise ValueError("Successful whole-image evidence requires a measured signal object.")
            prediction = signal.get("predicted_label")
            raw_labels = model.get("output_labels") if model else None
            labels_list = raw_labels if isinstance(raw_labels, list) else []
            if prediction is not None and prediction not in labels_list:
                raise ValueError("Predicted label must be declared in model output_labels.")
            raw_scores = signal.get("raw_scores")
            if raw_scores is not None and (not isinstance(raw_scores, dict) or any(
                key not in labels_list or not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
                for key, value in raw_scores.items()
            )):
                raise ValueError("Raw detector scores must be finite numeric values for declared model labels.")
        records.append(_record(
            source_id, digest, str(report.get("media_type", "image")), channel,
            parent_video_id=parent_video_id, parent_video_sha256=parent_video_sha256,
            frame_sha256=frame_sha256, timestamp_seconds=timestamp_seconds,
            model=channel_model, label_space=label_space if channel_model else None,
            correlation_group=detector_correlation_group if channel_model else None,
        ))
    return records


def _conflicts(records: Iterable[EvidenceRecord]) -> list[dict[str, Any]]:
    by_subject: dict[tuple[str, str], list[EvidenceRecord]] = {}
    for record in records:
        if record.status != ProcessingStatus.SUCCESS.value or not record.label_space or not record.output_labels:
            continue
        label = record.measured_signal.get("predicted_label")
        if isinstance(label, str):
            subject_id = record.parent_video_id or record.source_id
            by_subject.setdefault((subject_id, record.label_space), []).append(record)
    conflicts = []
    for (subject, label_space), group in by_subject.items():
        for i, left in enumerate(group):
            for right in group[i + 1:]:
                left_label = left.measured_signal.get("predicted_label")
                right_label = right.measured_signal.get("predicted_label")
                if left_label == right_label or set(left.output_labels or []) != set(right.output_labels or []):
                    continue
                if (not left.correlation_group or not right.correlation_group
                        or left.correlation_group == right.correlation_group):
                    continue
                conflicts.append({
                    "source_id": subject, "label_space": label_space,
                    "evidence_ids": [left.evidence_id, right.evidence_id],
                    "labels": [left_label, right_label],
                    "interpretation": "Comparable successful outputs disagree; this is a review flag, not a resolved verdict.",
                })
    return conflicts


def fuse_reports(*reports: dict[str, Any]) -> FusionAssessment:
    """Validate and collate image/video reports; never infer a verdict by averaging."""
    evidence: list[EvidenceRecord] = []
    references: list[dict[str, Any]] = []
    report_statuses: list[str] = []
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("Reports must be JSON-ready objects.")
        media_type = report.get("media_type")
        source_id = report.get("source_id")
        digest = _validate_sha256(report.get("source_sha256"), "source_sha256")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("Each report requires a non-empty source_id.")
        report_status = report.get("processing_status")
        if report_status is not None:
            try:
                report_status = ProcessingStatus(report_status).value
            except (TypeError, ValueError) as exc:
                raise ValueError("Report processing_status is not recognized.") from exc
            report_statuses.append(report_status)
        errors = report.get("errors", [])
        limitations = report.get("limitations", [])
        if not isinstance(errors, list) or not all(isinstance(item, str) for item in errors):
            raise ValueError("Report errors must be a list of strings.")
        if not isinstance(limitations, list) or not all(isinstance(item, str) for item in limitations):
            raise ValueError("Report limitations must be a list of strings.")
        references.append({
            "source_id": source_id, "source_sha256": digest, "media_type": str(media_type),
            "processing_status": report_status or "UNKNOWN", "errors": list(errors),
            "limitations": list(limitations),
        })
        if media_type == "image":
            evidence.extend(_image_records(report))
            evidence.extend(_provenance_records(report, source_id, digest, "image"))
        elif media_type == "video":
            frames = report.get("frames", [])
            if not isinstance(frames, list):
                raise ValueError("Video report frames must be a list.")
            for frame in frames:
                if not isinstance(frame, dict):
                    raise ValueError("Video frame records must be objects.")
                frame_hash = _validate_sha256(frame.get("sha256"), "frame sha256")
                child_report = frame.get("image_assessment")
                if not isinstance(child_report, dict):
                    raise ValueError("Each sampled frame requires its image assessment.")
                child_hash = _validate_sha256(child_report.get("source_sha256"), "frame assessment source_sha256")
                if child_hash != frame_hash:
                    raise ValueError("Frame artifact hash must match its image assessment source hash.")
                if child_report.get("media_type") != "image":
                    raise ValueError("A sampled video frame assessment must have image media_type.")
                evidence.extend(_image_records(
                    child_report, parent_video_id=source_id, parent_video_sha256=digest,
                    frame_sha256=frame_hash, timestamp_seconds=frame.get("timestamp_seconds"),
                ))
            temporal = report.get("temporal_analysis")
            if isinstance(temporal, dict):
                temporal_status = temporal.get("status", ProcessingStatus.UNAVAILABLE.value)
                evidence.append(_record(
                    source_id, digest, "video", {
                        "source": "temporal_analysis",
                        "method": temporal.get("method") or "temporal_analysis_unavailable",
                        "method_version": "1",
                        "status": temporal_status,
                        "measured_signal": {"pairs": temporal.get("pairs", [])},
                        "output_semantics": temporal.get("semantics", temporal.get("reason", "No temporal signal was produced.")),
                        "limitations": temporal.get("limitations", []),
                    },
                ))
            evidence.extend(_provenance_records(report, source_id, digest, "video"))
        else:
            raise ValueError("Only image and video reports can be fused.")
    ids = [item.evidence_id for item in evidence]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate evidence identities were produced by the supplied reports.")
    evidence.sort(key=lambda item: item.evidence_id)
    references.sort(key=lambda item: (item["source_id"], item["source_sha256"], item["media_type"]))
    conflicts = _conflicts(evidence)
    conflicts.sort(key=lambda item: tuple(item["evidence_ids"]))
    has_success = any(item.status == ProcessingStatus.SUCCESS.value for item in evidence)
    all_success = bool(evidence) and all(item.status == ProcessingStatus.SUCCESS.value for item in evidence)
    pipeline_failed = bool(report_statuses) and all(status == ProcessingStatus.FAILED.value for status in report_statuses) and not has_success
    has_partial_or_failure = any(status in {ProcessingStatus.PARTIAL.value, ProcessingStatus.FAILED.value,
                                           ProcessingStatus.UNAVAILABLE.value} for status in report_statuses)
    if pipeline_failed:
        fusion_status = ProcessingStatus.FAILED.value
    elif all_success and not has_partial_or_failure:
        fusion_status = ProcessingStatus.SUCCESS.value
    elif has_success or (evidence and not all_success) or ProcessingStatus.PARTIAL.value in report_statuses:
        fusion_status = ProcessingStatus.PARTIAL.value
    elif ProcessingStatus.FAILED.value in report_statuses:
        fusion_status = ProcessingStatus.FAILED.value
    else:
        fusion_status = ProcessingStatus.UNAVAILABLE.value
    return FusionAssessment(
        schema_version=FUSION_SCHEMA_VERSION,
        processing_status=fusion_status,
        proposed_outcome="INSUFFICIENT_EVIDENCE_REVIEW", human_review_required=True,
        calibrated=False, aggregation_method="none",
        evidence=evidence, conflicts=conflicts, source_reports=references,
        limitations=[
            "Evidence is preserved as reported; no scores are averaged, normalized, or reinterpreted.",
            "No evaluated and calibrated fusion model is configured, so the system abstains.",
            "Disagreement is flagged only for successful predictions with the same explicit label space; repeated frames from the same video method are treated as correlated.",
        ],
    )


def _provenance_records(report: dict[str, Any], source_id: str, digest: str,
                        media_type: str) -> list[EvidenceRecord]:
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        return []
    records: list[EvidenceRecord] = []
    metadata = provenance.get("metadata")
    if isinstance(metadata, dict):
        state = metadata.get("status")
        if state not in {"DETECTED", "MISSING", "PARTIAL", "INVALID", "ERROR", "UNVERIFIABLE", "UNAVAILABLE"}:
            raise ValueError("Metadata evidence has an invalid evidence state.")
        records.append(_record(source_id, digest, media_type, {
            "source": "metadata_inspection", "method": "parsed_metadata_presence",
            "method_version": "1", "status": ProcessingStatus.SUCCESS.value,
            "measured_signal": {"state": state, "observed_fields": metadata.get("observed_fields", {}),
                                "exif_tag_ids": metadata.get("exif_tag_ids", [])},
            "output_semantics": metadata.get("interpretation", "Parser-observed fields only; not provenance verification."),
            "limitations": ["Metadata presence or absence does not establish authenticity or event truth."],
        }))
    for key, name in (("content_credentials", "content_credentials"), ("watermark", "watermark")):
        item = provenance.get(key)
        if isinstance(item, dict):
            state = item.get("status")
            if state not in {"DETECTED", "VERIFIED", "MISSING", "INVALID", "UNVERIFIABLE", "UNAVAILABLE", "ERROR"}:
                raise ValueError(f"{name} evidence has an invalid evidence state.")
            processing_status = ProcessingStatus.UNAVAILABLE if state == "UNAVAILABLE" else ProcessingStatus.SUCCESS
            records.append(_record(source_id, digest, media_type, {
                "source": name, "method": f"{name}_assessment", "method_version": "1",
                "status": processing_status.value,
                "measured_signal": {"state": state},
                "output_semantics": item.get("reason", f"Evidence state: {state}."),
                "limitations": ["This state is not a media-authenticity decision."],
            }))
    return records
