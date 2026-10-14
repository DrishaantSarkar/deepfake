"""Metadata, content-credential, and watermark capability reporting.

This module reports what the existing intake metadata can establish. It does
not verify provenance signatures or claim that a watermark was searched for.
"""

from __future__ import annotations

from typing import Any


def assess_provenance(media_type: str, metadata: dict[str, Any], *, parser_warnings: list[str] | None = None) -> dict[str, Any]:
    """Return explicit evidence states without upgrading metadata to proof."""
    if media_type not in {"image", "video", "audio"}:
        raise ValueError("Unsupported media type for metadata assessment.")
    if not isinstance(metadata, dict):
        raise ValueError("Media metadata must be an object.")

    observed: dict[str, Any] = {}
    for key in ("format", "width", "height", "mode", "codec", "container",
                "duration_seconds", "frame_rate", "streams", "audio_stream_present",
                "exif_named", "exif_status", "metadata_warnings", "container_tags", "video_stream_tags",
                "container_tags_status", "video_stream_tags_status"):
        value = metadata.get(key)
        if value is not None:
            observed[key] = value

    exif = metadata.get("exif")
    exif_fields = sorted(str(key) for key, value in exif.items() if value not in (None, "")) if isinstance(exif, dict) else []
    if exif_fields:
        observed["exif_tag_ids"] = exif_fields
    metadata_state = metadata.get("metadata_status")
    if metadata_state not in {"DETECTED", "MISSING", "PARTIAL", "ERROR"}:
        warnings = parser_warnings or []
        warning_text = " ".join(warnings).lower()
        if "unavailable" in warning_text:
            metadata_state = "UNAVAILABLE"
        elif any(term in warning_text for term in ("could not parse", "invalid", "malformed", "timed out", "no video stream")):
            metadata_state = "ERROR"
        elif warnings:
            metadata_state = "PARTIAL"
        else:
            metadata_state = "DETECTED" if observed or exif_fields else "MISSING"
    return {
        "metadata": {
            "status": metadata_state,
            "observed_fields": observed,
            "exif_tag_ids": exif_fields,
            "exif_status": metadata.get("exif_status", "MISSING"),
            "parser_warnings": list(parser_warnings or metadata.get("metadata_warnings", [])),
            "interpretation": "Metadata fields are reported as supplied by the media parser; their truth and origin are not independently verified.",
        },
        "content_credentials": {
            "status": "UNAVAILABLE",
            "reason": "No C2PA/content-credentials manifest parser or signature verifier is configured.",
        },
        "watermark": {
            "status": "UNAVAILABLE",
            "reason": "No watermark detector is configured; no watermark search was performed.",
        },
        "limitations": [
            "Metadata presence does not establish source authenticity or event truth.",
            "Missing metadata or watermark evidence is not evidence of manipulation.",
            "No provenance signature or watermark verification is claimed.",
        ],
    }
