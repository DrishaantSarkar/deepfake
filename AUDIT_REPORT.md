# TRUSTLENS non-ML application audit

Audit date: 2026-10-13  
Scope: Local workspace `C:\Users\KIIT\OneDrive\Documents\deepfake`. ML inference and accuracy are excluded as requested.

## Repository baseline

- **Verified:** This directory contains the Python `trustlens` package, a FastAPI wrapper, static HTML/CSS/JavaScript, SQLite persistence, tests, and Markdown documentation.
- **Verified:** No `.git` directory is present in the workspace. Git status/diff and uncommitted-change inspection were therefore unavailable. The linked GitHub repository was not available here as a complete checked-out source tree; this audit does not make claims about unseen remote files.
- **Verified:** The frontend is static and served by FastAPI. There is no frontend package manifest, build, lint, type-check, or CI configuration.
- **Verified:** The API and page use same-origin routes. The only server entry point is `python -m trustlens.web`, which binds to `127.0.0.1:8765`.

## Component checklist

| Component | Status | Evidence / boundary |
|---|---|---|
| Python package imports and backend startup | **Verified** | Full tests imported modules; an actual Uvicorn process started and `/api/health` returned `available`. |
| Frontend files and routing | **Partially verified** | Static page, CSS, and JS are served; static assets returned 200 in API tests. Navigation and controls are wired in `app.js`; visual/browser interaction was not completed. |
| Frontend build/lint | **Unverified / not configured** | No frontend build or lint tooling exists for plain static assets. `node --check trustlens\static\app.js` passes. |
| Frontend-to-backend communication | **Partially verified** | API tests and actual HTTP workflows passed. Browser-driven requests, console, and responsive visual checks remain unverified. |
| Health and capabilities | **Verified** | Health checks SQLite; capabilities disclose unavailable trained detectors, localization, temporal classifier, C2PA, watermark, and audio analysis. |
| Image intake and preprocessing | **Verified** | Existing suite covers valid real image fixtures, color modes, hashes, metadata, normalization, mismatch, corrupt, pixel, and file-size checks. Actual HTTP image flow passed. |
| Video metadata, decoding, sampling | **Verified** | Diagnostics and suite used real generated MPEG-4 and H.264 fixtures with FFmpeg/ffprobe; actual HTTP upload produced frame results and retained report metadata. Sparse sampling limitations remain. |
| Audio intake | **Partially verified** | WAV/MP3 recognition is explicit, but analysis is `UNAVAILABLE`; no audio-forensic result is claimed. |
| Evidence fusion | **Verified** | Unit suite validates preservation, identities/hashes/timestamps, label-space behavior, correlation handling, malformed inputs, and abstention using isolated synthetic fixtures. Synthetic fixtures are not presented as detector results by the app. |
| SQLite initialization, queries, and persistence | **Verified** | API tests cover isolated DB creation, stats, filters/search, detail, restart/reopen, delete, idempotency, and report-only persistence. Corrupt DB and write failures map to sanitized 503 responses. |
| Analysis job lifecycle | **Partially implemented by design** | Processing is synchronous in the upload request. There is no queue, job-status endpoint, or intermediate state-transition history. Reports persist the final processing status. |
| Report and evidence retrieval | **Verified** | Detail, evidence, JSON export, and delete paths are tested. Reports use the existing schema and state abstention/human review. |
| Temporary file lifecycle | **Verified** | Service cleanup tests cover success/failure; real HTTP flow verified its dedicated media staging directory was empty after image/video analyses. |
| Upload security and input validation | **Partially verified** | Content/extension checks, pixel/file limits, test-configured body cap, host/origin checks, path/control-character filename sanitization, parameterized SQL, and browser headers are tested/inspected. A full 100 MiB network upload and stress/concurrency load were not run. |
| Authentication and authorization | **Not implemented / documented** | No credentials, tokens, cookies, user identity, tenant boundary, or record ownership model exists. The app is deliberately local single-user and loopback-bound; it is not safe to expose to a network or treat as multi-user isolation. |
| Logging and operational observability | **Partially implemented** | Uvicorn defaults provide process/request logs. There is no structured application audit log, job telemetry, or user-attributed access trail. |
| Documentation and dependencies | **Verified** | Run instructions, API contract, architecture, integration boundaries, requirements, and data lifecycle are documented. `pip check` passes. |

## Defects reproduced and fixed

### AUD-01 — Untrusted multipart filenames could contain control characters

- **Severity:** Medium (malformed report / server error risk; no evidence of filesystem path execution).
- **Reproduction:** A valid PNG submitted with a filename containing a newline could pass through basename extraction but fail report filename validation. A sufficiently long name could lose its `.png` suffix if truncated naively.
- **Root cause:** Filename path stripping did not remove control characters or bound the display name before report validation.
- **Fix:** `trustlens/ingestion.py` strips path components and Unicode control characters, bounds names to 255 characters, and preserves a reasonable suffix. The web layer persists only the sanitized display name.
- **Regression evidence:** `test_filename_removes_path_and_control_characters_and_preserves_extension` and `test_upload_filename_path_is_sanitized_in_saved_report` pass.

### AUD-02 — SQLite transaction contexts did not close connections

- **Severity:** Low/Medium (handle/resource leakage over repeated operations).
- **Root cause:** SQLite's connection context manager commits or rolls back but does not close the connection.
- **Fix:** `AnalysisStore._session()` now wraps transaction handling and closes every connection in `finally`; all store operations use it.
- **Regression evidence:** Repeated API upload/replay/list/detail/delete and failure paths pass without the prior unclosed-connection warning.

### AUD-03 — Report detail obscured the abstention outcome and provenance states

- **Severity:** Medium (investigator-facing clarity).
- **Root cause:** The detail summary preferred the analysis phase status (`PARTIAL`) over the report's explicit `proposed_outcome`; parsed provenance checks were present in the API but not rendered in the detail view.
- **Fix:** The result card now displays the report's proposed outcome first, and the detail view renders metadata, content-credential, and watermark statuses and their explanations.
- **Regression evidence:** `node --check trustlens\static\app.js` passes; the API report/evidence tests and actual HTTP image/video smoke pass. Browser-rendered appearance remains unverified.

### AUD-04 — Upload controls could be re-enabled during an in-flight upload

- **Severity:** Low/Medium (duplicate or mismatched UI submission risk).
- **Root cause:** Selection/consent changes could recalculate the submit button while the original request was still pending.
- **Fix:** A client-side in-flight guard prevents a second submit, locks the file input/consent checkbox while processing, and ignores drop/selection events until completion.
- **Regression evidence:** JavaScript syntax check passes; actual upload/idempotency backend smoke passes. Browser interaction timing was not exercised because browser automation was blocked.

### AUD-05 — TestClient hostname was included in the production Host allowlist

- **Severity:** Low (unnecessary development-host surface).
- **Root cause:** `testserver` was accepted by `TrustedHostMiddleware` to accommodate the default test-client hostname.
- **Fix:** Removed the test hostname from the application allowlist. Tests now use a loopback Host and explicitly verify that both `testserver` and an arbitrary Host receive 400.
- **Regression evidence:** API host-boundary test and final full suite pass.

### AUD-06 — Setup instructions invoked pip from a venv without pip installed

- **Severity:** Low (fresh environment setup failure).
- **Root cause:** This workspace's `.venv` has no `pip` module, while the README/test guide invoked `.venv\Scripts\python.exe -m pip`.
- **Fix:** Run pip from the host interpreter with `--python .venv\Scripts\python.exe` to target the environment, matching the actual successful installation/check commands on this host.
- **Regression evidence:** Dependencies were installed and `pip check` passed through the documented target-interpreter command. The full test suite passed in that environment.

### AUD-07 — Malformed Origin syntax could raise during URL parsing

- **Severity:** Low (malformed state-changing request handling).
- **Root cause:** `urlsplit()` may raise `ValueError` for malformed bracketed-host syntax before the middleware can compare origins.
- **Fix:** Catch parse errors and reject them with the same sanitized 403 cross-origin response.
- **Regression evidence:** API test sends `Origin: http://[` and verifies 403; the focused API suite passes.

## Verified model-unavailable behavior

- The image pipeline reports detector `UNAVAILABLE`, null model/output fields, no prediction, and `INSUFFICIENT_EVIDENCE_REVIEW`.
- Reports require human review and remain `PARTIAL` when descriptive methods run but trained methods are absent.
- The capability endpoint says trained image detector, face/localization, temporal classifier, signature verification, watermark detection, and audio analysis are unavailable.
- Actual HTTP image/video workflows completed non-ML processing without inventing an ML output. **ML accuracy, confidence, calibration, or forensic validity were excluded.**

## Remaining issues and risks

- Browser-level route/button behavior, console/network inspection, mobile visual responsiveness, and form-to-visible-result interactions remain **unverified**. On 2026-10-14, Chrome rendered the local New analysis page, but Computer Use detected concurrent user input at the first in-page navigation click and stopped. The earlier URL-identification blocker is superseded; no retry was made after user input was detected.
- Frontend controls are connected in source, but only static assets and backend/API effects were programmatically verified.
- No analysis queue/job-status API or incremental progress protocol exists; users wait for the synchronous request.
- No application login, authorization/ownership isolation, encryption-at-rest, formal chain of custody, structured audit log, rate limit, or deployment hardening is provided. Keep bound to loopback.
- SQLite has schema creation but no migration framework. Reports can contain extracted EXIF/video metadata, potentially sensitive; deletion removes the report row but does not promise secure media erasure from OS temporary storage or backup media.
- Full-size upload stress, adversarial codec corpus, concurrent-load behavior, and browser accessibility/responsive visual QA remain unverified.
- FFmpeg/ffprobe were available after refreshing the host PATH. Earlier sandbox diagnostics falsely showed missing tools and Pillow temp permission failures; the corrected host-path run passed all 11 diagnostics.

## Files changed in this verification increment

- `trustlens/ingestion.py` — sanitize and bound upload display names.
- `trustlens/web.py` — remove the test-only hostname from the production Host allowlist.
- `trustlens/static/index.html`, `trustlens/static/app.js` — clarify audio availability, render the actual abstention outcome and provenance, prevent overlapping UI uploads.
- `README.md`, `TESTING.md` — correct pip commands for this environment's pip-less virtualenv and document HTTP smoke testing.
- `tests/test_ingestion.py`, `tests/test_web_app.py` — filename, request-size, corrupt DB, restart, DB-write failure, retrieval, and boundary regressions.
- `tests/http_smoke.py` — reusable real-loopback HTTP smoke workflow.
- `AUDIT_REPORT.md`, `TEST_REPORT.md`, `IMPLEMENTATION_STATUS.md` — evidence-based verification record.

## Omega Milestone B — bounded video metadata parser fix (2026-10-13)

### Finding OMEGA-B-01 — malformed ffprobe JSON escaped the parser boundary

- **Severity:** Medium (input-driven unexpected exception and invalid numeric metadata could disrupt report validation; no fabricated success observed).
- **Evidence before fix:** Focused tests using mocked ffprobe outputs `[]`, a null stream entry, and an array-valued `format` field raised `AttributeError` instead of producing the parser's documented warning/unavailable metadata. A payload with `duration: "NaN"` retained NaN, and `_ratio("inf/1")` returned infinity.
- **Root cause:** `_probe_video()` assumed subprocess JSON fields had the standard dict/list shape and did not reject non-finite/non-positive parsed values. Its exception boundary covered conversions but not all consequences of shape mismatch.
- **Fix:** `trustlens/ingestion.py` now validates root, stream-list, stream-entry, and format object shapes; rejects non-positive dimensions; treats non-finite/non-positive duration and frame rate as unavailable; malformed shapes return empty metadata plus a bounded warning.
- **Regression coverage:** Two new ingestion tests cover malformed JSON shapes and non-finite duration/frame-rate handling. They failed before the fix and passed after it.
- **Verification:** Focused tests **PASS**; complete suite **PASS**, 61 tests, 0 failures/errors/skips; `node --check` **PASS**; `pip check` **PASS**; diagnostics **PASS**, all 11 checks available; isolated live HTTP image/video smoke **PASS**, including generated MPEG-4 sampling and cleanup.
- **Files changed for this increment:** `trustlens/ingestion.py`, `tests/test_ingestion.py`, `TEST_REPORT.md`, `TESTING.md`, `IMPLEMENTATION_STATUS.md`, `AUDIT_REPORT.md`.
- **Residual limitations:** This does not bound all subprocess stdout/stderr memory or verify adversarial codec exhaustion, concurrent load, browser behavior, or deployment security. The working directory still has no Git metadata, so a source-control diff cannot be generated; changes were reviewed directly against the current files.

### Finding OMEGA-B-02 — malformed persisted report data escaped the API error boundary

- **Severity:** Medium (corrupt local report data caused detail/history requests to raise rather than return a documented sanitized API failure).
- **Evidence before fix:** A valid uploaded row was updated in an isolated SQLite database with malformed JSON (`report_json = "{"`). Both `GET /api/analyses/{id}` and `GET /api/analyses` raised `JSONDecodeError` through the API test client instead of returning a controlled response.
- **Root cause:** `AnalysisStore._serialize()` directly decoded persisted JSON and assumed its root, source, size, and metadata shapes were valid; the web layer only handled SQLite exceptions.
- **Fix:** Serialization now validates the report object/source/size/metadata boundary and raises `StoredReportError`. FastAPI maps that condition to a sanitized 503 `stored_report_unavailable` response without database paths or parser details.
- **Regression coverage:** `test_malformed_persisted_report_returns_sanitized_storage_error` corrupts an isolated stored row and verifies detail and history return the sanitized response. The test failed before the fix and passes after it.
- **Verification after both Milestone B fixes:** Complete suite **PASS**, 62 tests; JavaScript syntax **PASS**; `pip check` **PASS**; diagnostics **PASS**, 11/11; isolated live HTTP smoke **PASS**, including image/video processing and sampled frames.
- **Files changed in this additional increment:** `trustlens/persistence.py`, `trustlens/web.py`, `tests/test_web_app.py`, `TEST_REPORT.md`, `TESTING.md`, `IMPLEMENTATION_STATUS.md`, `AUDIT_REPORT.md`.
- **Remaining:** This defensive check does not provide a backup/restore process, migrate old schemas, repair corrupt records, or verify every semantic field of the report. The row remains retained for operator recovery; it is not silently deleted or rewritten.

### Finding OMEGA-B-03 — non-finite values in stored JSON could escape the API boundary

- **Severity:** Medium (malformed SQLite report data could make a response fail during strict JSON serialization rather than return a controlled API error).
- **Evidence before fix:** Python's `json.loads()` accepts the non-standard tokens `NaN` and `Infinity`. A corrupted report containing one in extracted metadata could pass the serializer's shape checks, then fail when FastAPI attempted to emit strict JSON.
- **Fix:** `AnalysisStore._serialize()` now re-serializes parsed content with `allow_nan=False`, turning non-finite values into `StoredReportError`; it also rejects SQLite review flags outside the binary `0`/`1` domain before conversion to bool.
- **Regression evidence:** `test_non_finite_persisted_metadata_returns_sanitized_storage_error` stores NaN in a disposable report and verifies the API returns sanitized 503 `stored_report_unavailable`. It passes alongside the history-row mismatch regression.
- **Latest verification:** full suite **64 passed, 0 failed, 0 skipped**; diagnostics **11/11**; JavaScript syntax **PASS**; isolated real HTTP image/video smoke **PASS**. Latest dependency `pip check` is unavailable because `.venv` does not include pip. Browser verification remains unperformed.
- **Scope boundary:** strict JSON and row consistency checks do not provide cryptographic database integrity or validate every semantic field against an external signed record.
