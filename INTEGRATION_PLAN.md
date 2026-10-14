# TRUSTLENS repository and integration audit

> **Historical baseline:** The initial audit below captured the library-only
> workspace on 2026-10-13. The local MVP was implemented afterward. Use the
> `Local MVP implementation addendum` and `API.md` for current app behavior;
> this document is retained to distinguish verified baseline facts from later
> integration work.

Audit date: 2026-10-13

## Scope and evidence

This audit describes the available workspace at `C:\Users\KIIT\OneDrive\Documents\deepfake`. It is a Python package workspace, not a Git checkout. Through the connected GitHub app, the default-branch README was fetched and a repository code search for `TRUSTLENS` returned no results; the connector did not enumerate the full remote tree. Conclusions about implementation are limited to the local files and those narrow remote checks.

Labels used below:

- **Verified** — directly visible in the workspace or exercised by the existing test suite.
- **Missing** — searched for in the workspace and not found.
- **Proposed** — a narrow next step that requires no assumption about application architecture.
- **Unresolved** — requires a repository, contract, or asset not available here.

## Verified architecture and contracts

| Concern | Verified implementation | Current boundary |
|---|---|---|
| Package/runtime | Python package `trustlens`; pinned dependencies in `requirements.txt` | No packaging/build, deployment, or application entrypoint configuration is present. |
| Media intake | `trustlens/ingestion.py` exposes `ingest_media()` and typed `IngestedMedia`, `MediaLimits`, and processing statuses | Local temporary staging; caller-provided stream remains caller-owned. `IngestionError` must be translated by a host application. |
| Image detector extension | `trustlens/image_analysis.py` defines `ImageDetector`, `DetectorDescriptor`, and `DetectorOutput`; `analyze_image()` accepts an optional adapter | The default does not perform trained deepfake classification. Descriptive frequency evidence is not a classifier. |
| Video processing | `trustlens/video_analysis.py` samples bounded frames with FFmpeg and invokes the image-analysis interface | Sparse sampling only; no validated temporal model. Extracted frames are temporary. |
| Fusion | `trustlens/evidence_fusion.py` validates and retains evidence/provenance and abstains | No calibrated fusion model or final authenticity decision. |
| Service boundary | `trustlens/service.py`: `analyze_upload(source, filename, ...) -> AnalysisReport`; `validate_analysis_report()` | In-process Python call, not an HTTP endpoint. No auth, authorization, job queue, persistence, or artifact-serving behavior. |
| Public exports | `trustlens/__init__.py` lazily exports ingestion, detector/video/fusion, and service APIs | No web framework or UI exports. |
| Report contract | `REPORT_SCHEMA.md`, schema version `1.0`; validated JSON-ready mapping | Prose/in-process contract, not an OpenAPI or JSON Schema API definition. |
| Tests | `tests/` exercises ingestion, image/video analysis, fusion, diagnostics, and service/report behavior | Tests do not measure forensic accuracy or exercise a host application/API. |

## Available and missing assets

**Verified available:** the Python source and tests above; requirements manifest; workspace virtual environment; FFmpeg/ffprobe were available in the current host environment when diagnostics were last run. The existing status report records 45 passing unit tests and 11 successful environment/processing diagnostics before this audit.

**Searched for and not found in the workspace:** frontend source; a separate backend/application entrypoint; HTTP routes or API framework configuration; auth/authorization middleware; persistence/database configuration or schema; model weight files (`.pt`, `.pth`, `.onnx`, `.safetensors`, `.pb`, `.tflite`, `.ckpt`, `.h5`); labeled evaluation data; model calibration/fusion assets; artifact retention or reviewer workflow.

**Unresolved:** whether these exist in a separate repository, remote branch, private service, or external storage. No API, identity, tenant, ownership, storage, retention, or evaluation contract can be inferred from the present files.

## Request and data flow that is actually implemented

1. A host caller supplies an open binary stream and display filename to `analyze_upload()`.
2. Ingestion stages and hashes the original bytes, validates media, and performs available normalization/probing.
3. Images go to `analyze_image()`; videos go through bounded FFmpeg sampling and frame-level image analysis. Audio receives an explicit unavailable report.
4. Image/video assessments are passed to `fuse_reports()`. With no evaluated calibrated fusion, the result abstains and requires human review.
5. `AnalysisReport` is assembled, checked by `validate_analysis_report()`, serialized by `to_dict()` when desired, and staged artifacts are cleaned before return.

There is no implemented network request/response flow, login/token flow, identity propagation, authorization check, report lookup, database write, or artifact retrieval flow.

## Integration plan mapped to actual files

1. **Keep the stable library boundary:** adapt the existing host's upload stream to `trustlens.service.analyze_upload()` and map `IngestionError`/report statuses to its established API contract. Do not add routes or framework dependencies until the host repository and conventions are available.
2. **Authentication and access control:** implement only inside the actual application boundary once its identity/auth contract is inspected. Require the host to authorize report reads and artifact access by owner/tenant; this package currently has no identity input and must not be treated as an authorization layer.
3. **Persistence and artifacts:** map `AnalysisReport.to_dict()` into the actual persistence schema only after inspecting that schema and retention requirements. Decide explicitly whether video artifacts need retention; current cleanup means the report's frame labels cannot be fetched later.
4. **Detector integration:** implement an adapter for a supplied trained model that meets `ImageDetector`; record model identity, input preprocessing, label/score semantics, evaluation, calibration, and limitations in `DetectorDescriptor`. No substitute weights or mock production predictions.
5. **Calibration and fusion:** require labeled, representative evaluation data and a documented validation/calibration protocol before thresholds, calibrated probabilities, or aggregate authenticity outcomes are introduced.
6. **Verification:** when actual application files/contracts are supplied or discovered, add boundary-level tests using its existing test framework and verify auth, ownership isolation, persistence, failure mapping, cleanup/retention, and report version compatibility. The present suite verifies only the library workflow.

## Decisions that remain blocked on missing inputs

- Which backend and frontend repositories/frameworks are authoritative?
- What are the API routes, request limits, response/error format, and compatibility policy?
- Which identity provider and authorization model apply (roles, ownership, tenant boundaries)?
- Where are reports and source/derived artifacts stored, and what are retention/deletion rules?
- Which trained detector(s), licenses, runtime constraints, labeled evaluation corpus, and calibration protocol are approved?
- What human review lifecycle and audit records are required?

No implementation choice for these items is made by this audit.

## Local MVP implementation addendum (2026-10-13)

The user selected a **local single-user MVP**. This authorizes a local wrapper around the inspected Python package; it does not resolve or imply any external host repository, frontend/backend, identity, deployment, or evidence-retention contract. The baseline inventory above records the workspace before this increment.

| Integration seam | Implemented location | Contract and limit |
|---|---|---|
| HTTP host and same-origin UI | `trustlens/web.py`, `trustlens/static/` | FastAPI serves UI and JSON endpoints; binds to `127.0.0.1:8765`; loopback-only, no app login, no LAN/public deployment |
| Upload to existing analysis | `POST /api/analyses` → `trustlens.service.analyze_upload()` | Multipart `file`, max 100 MiB, SHA-256 idempotency; existing service remains responsible for media validation, analysis, and cleanup |
| Report/history persistence | `trustlens/persistence.py` | SQLite stores report JSON and metadata; no original media or video-frame files are persisted |
| Human review | Report detail UI and existing report contract | Displays abstention/status, evidence, provenance, uncertainty, and limitations; no reviewer identity or adjudication workflow |
| External app contracts | Not available / not integrated | Linked GitHub repo was not available as a full source checkout/tree in this workspace; no inference is made about remote code |
| Authentication / authorization | Not implemented by design | Single local OS-user process only. There are no credentials/tokens, tenant boundaries, or per-record ownership checks. Do not expose network routes. |
| Detectors / calibration | Not available | No production weights or labeled evaluation corpus; capability endpoint reports methods and limits explicitly |

The current API contract and data handling are documented in `API.md`; run steps are in `README.md`. Boundary tests are in `tests/test_web_app.py`. The suite does not validate production security, forensic accuracy, calibration, or multi-user behavior.
