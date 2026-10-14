# Master prompt requirements traceability

**Current-state correction (2026-10-14):** this table contains historical
pre-MVP rows. The local MVP addendum below supersedes entries that say the
workspace has no HTTP app, persistence, or frontend. Current implementation is
in `trustlens/web.py`, `trustlens/persistence.py`, and `trustlens/static/`;
routes and data handling are documented in `API.md`. The latest report schema
is 1.1 with a versioned report-local evidence graph; see `REPORT_SCHEMA.md`.

Status describes the **local TRUSTLENS workspace**. `Verified` means source/tests support the statement; documentation alone is not verification.

| Prompt area | Status | Implementation/evidence | Remaining work or blocker |
|---|---|---|---|
| P0 repository map and dependency inventory | Partial | `INTEGRATION_PLAN.md`, `requirements.txt`, source/tests | Remote repository full tree is not verified; no deployment/app stack found locally. |
| P0 secure media intake | Implemented and tested | `trustlens/ingestion.py`; bounded streams, magic/content checks, size/dimension/duration/rate limits, SHA-256, normalization, cleanup | Hash is not chain of custody; representative broader codec/media coverage remains. |
| P0 metadata | Partial | Image format/dimensions/mode/raw and named EXIF fields; bounded video container/stream tags, codec/streams/rates/duration; `trustlens/provenance.py` distinguishes missing/error/unavailable states | No signed provenance verifier; tag bounds can omit excess fields and report PARTIAL. |
| P1 image preprocessing | Implemented and tested | `trustlens/ingestion.py`, `trustlens/image_analysis.py` | — |
| P1 frequency evidence | Partial | DCT band energy in `trustlens/image_analysis.py` | Descriptive only; not validated as forensic signal. |
| P1 real detector / face / spatial / patch analysis | Blocked | Typed `ImageDetector` interface and honest unavailable statuses | Requires approved trained weights, compatible runtime, model licensing and evaluation data. |
| P1 localization / explainability | Unavailable | Report explicitly marks localization unavailable | Requires model-supported output or defensible evaluated method. |
| P2 frame sampling / timestamps / reuse | Implemented with limits | `trustlens/video_analysis.py`; real generated video tests | Source frame indices remain null; broader source codecs unverified. |
| P2 lightweight temporal measurement | Implemented, descriptive | Adjacent sampled-frame 64×64 grayscale MAE in `trustlens/video_analysis.py`; retained by fusion | Not a manipulation detector; sparse and unevaluated. No thresholds/classification. |
| P2 video localization / validated temporal inference | Unavailable | Explicit unavailable report states | Requires validated method/model and suitable labeled video data. |
| P3 metadata / C2PA / watermark evidence | Partial | Metadata presence surfaced; C2PA and watermark states explicitly `UNAVAILABLE` via `trustlens/provenance.py` | Signature verification and watermark detector assets/dependencies absent. |
| P3 evidence preservation / conflict handling | Partial | `trustlens/evidence_fusion.py` preserves channels, source hashes, temporal and provenance states; narrow label conflict checks | Calibrated fusion, contribution reliability, correlation evidence, and broader provenance integration unavailable. |
| P3 uncertainty / abstention | Partial | Raw score semantics retained; reports abstain and require review | Calibration, OOD, and empirical uncertainty evaluation absent. |
| P4 structured report | Implemented in process | `trustlens/service.py`, `REPORT_SCHEMA.md` | Not an HTTP/OpenAPI contract. |
| P4 backend/auth/persistence/jobs | Local MVP partial | FastAPI routes and SQLite report persistence are available; no login/tokens, multi-user authorization, jobs, or original-media retention | Keep loopback only until an identity/authorization and deployment contract exists. |
| P4 frontend/reviewer experience | Local MVP partial | Same-origin UI in `trustlens/static/` supports upload and report/history review; no reviewer assignment/adjudication workflow | Formal reviewer lifecycle remains undefined. |
| P5 unit/integration/robustness software tests | Partial | Test count is tracked in `IMPLEMENTATION_STATUS.md`; local API boundary tests and generated-media tests exist | Security/fuzz tests, browser E2E and CI/build configuration remain outstanding. |
| P5 forensic evaluation/calibration | Blocked | No dataset or evaluation artifacts found locally | Requires approved representative labeled corpus, protocol and model artifacts. |
| P6 audio forensics | Deferred | Audio is identified and explicitly unavailable in service | Keep deferred until image/video stability gate and audio requirements are met. |
| Formal chain of custody | Not implemented | Hash comparison only | Requires policy, controlled storage, access/audit records, trusted timestamps/signatures and procedural validation. |

## Required external inputs for remaining end-to-end completion

1. The complete authoritative app repository (including branches/submodules if relevant) and existing contracts.
2. Approved model weights/runtime/license and model preprocessing/output specifications.
3. Labeled representative evaluation data and the desired evaluation/calibration protocol.
4. For deployment integration: identity/authorization rules, persistence and retention policy, artifact delivery requirements, and human-review lifecycle.
