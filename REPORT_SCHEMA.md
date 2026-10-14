# TRUSTLENS analysis report contract

**Current schema:** `1.1` (the validator also accepts legacy `1.0` reports)  
**Producer:** `trustlens.service.analyze_upload()`  
**Format:** JSON-ready mapping returned by `AnalysisReport.to_dict()`

## Current application boundary

This package is also hosted by the local single-user FastAPI application in
`trustlens/web.py`. It serves the same-origin UI and routes documented in
`API.md`, persists report JSON and metadata in SQLite through
`trustlens/persistence.py`, and binds to loopback. The app has no login,
bearer-token, tenant, or per-record ownership system; it must not be exposed to
a network. This report contract itself remains framework-independent.

## Fields

| Field | Meaning |
|---|---|
| `schema_version`, `report_id` | Report contract version and UUID. New reports use `1.1`; old `1.0` reports remain valid. |
| `generated_at` | UTC ISO-8601 timestamp captured when the report object is created. |
| `producer` | TRUSTLENS producer identity, runtime Python version, and explicit `LOCAL_UNVERSIONED` source version. This is not a source commit/build identifier. |
| `evidence_graph` | Versioned report-local nodes and edges for source, assessment, report, and sampled frames. It carries no inference beyond existing report data. |
| `processing_status` | Overall `SUCCESS`, `PARTIAL`, `FAILED`, `UNAVAILABLE`, or `NOT_APPLICABLE` status. |
| `proposed_outcome`, `human_review_required` | Currently always abstains as `INSUFFICIENT_EVIDENCE_REVIEW` and requires review. |
| `source` | Sanitized display name, media type, original-byte SHA-256, size, source id, and extracted metadata. The hash is not proof of origin or custody. |
| `validation`, `analysis`, `fusion` | Ingestion/preprocessing, image/video assessment, and evidence-preserving fusion. Audio is explicitly unavailable and unfused. |
| `uncertainty`, `limitations`, `errors` | Calibration/abstention status and bounded processing notes. |

`validate_analysis_report()` checks schema compatibility, timestamp/producer
metadata on `1.1`, graph referential integrity and digest syntax, statuses,
cross-section source identity, abstention invariants, and strict JSON
serialization. It does not authenticate callers or authorize access.

The graph's sampled-frame nodes use `artifact_status: NOT_RETAINED`: frame
images are temporary and deleted before the report returns. Their SHA-256 and
timestamps describe the processing output; graph links do not make the bytes
retrievable. Graph node IDs are stable within a report, not global identifiers.

Image/video assessments report metadata observations and mark C2PA/content
credential verification and watermark detection `UNAVAILABLE`. Video temporal
measurements are descriptive and unevaluated. No trained model, calibrated
probability, or authenticity decision is implied.

## Lifecycle

The caller owns the upload stream. `analyze_upload()` stages and validates the
source, assembles a report, then cleans the staged original and derived files.
The local web app persists the report JSON and extracted metadata in SQLite;
it does not persist uploaded originals or sampled-frame bytes. SQLite is not
encrypted by the application. See `API.md` for routes and lifecycle.

Invalid media raises `IngestionError` for the host to map. Unexpected
post-ingestion failures produce a sanitized `FAILED` report with no assessment
or fusion result. Schema 1.0 dictionaries are accepted without the 1.1 fields
for backwards compatibility.
