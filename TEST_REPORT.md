# TRUSTLENS non-ML verification test report

Run date: 2026-10-14  
Workspace: `C:\Users\KIIT\OneDrive\Documents\deepfake`  
ML inference and model accuracy are excluded.

## Results summary

| Check | Result | Evidence |
|---|---|---|
| Full Python regression suite | **PASS** | 64 tests, 0 failures/errors, 0 skips |
| FFmpeg/ffprobe and media diagnostics | **PASS** | All 11 diagnostic checks available, including Pillow/OpenCV image decode, MPEG-4/H.264 metadata, frame decode, and TRUSTLENS sampling |
| Python dependency consistency | **NOT VERIFIED THIS RUN** | `.venv\Scripts\python.exe -m pip check` cannot run because `pip` is not installed in the project virtual environment; a previous check passed in the earlier environment |
| Frontend JavaScript syntax | **PASS** | `node --check trustlens\static\app.js`, exit code 0 |
| FastAPI/Uvicorn process startup | **PASS** | Actual server process started; `GET /api/health` returned `available` |
| Real HTTP image + video workflows | **PASS** | `tests/http_smoke.py`; image/video reports, evidence, history, idempotency, invalid media, deletion, cleanup all checked |
| Backend process restart and persistence | **PASS** | `tests/http_restart_smoke.py` stopped and restarted the actual Uvicorn process, then verified persisted report/hash retrieval and cleanup |
| Database write/corruption failures | **PASS** | API tests verify sanitized 503 responses with no exception/path leakage |
| Request/body, host, origin, filename boundaries | **PASS** | API tests cover a small injected body cap, invalid status/media filters, rejected foreign Origin/untrusted Host, sanitized path/control filenames |
| Frontend browser interactions / screenshots | **PARTIALLY VERIFIED** | A local Chrome page-load screenshot showed the TRUSTLENS New analysis screen. The walkthrough stopped when Computer Use detected concurrent user input; no further browser clicks, console/network, responsive, or accessibility assertions were made. |
| Frontend build/lint | **NOT CONFIGURED** | Static HTML/CSS/JS; no package manifest or frontend build/lint tooling |
| ML inference and accuracy | **EXCLUDED** | No model is connected; capability/report states are checked for truthful unavailability only |

## Latest integrity regression increment (2026-10-14)

- `AnalysisStore._serialize()` now rejects stored report JSON that contains non-finite numeric values and rejects SQLite review flags outside `0`/`1`. The existing report-to-history consistency checks also cover ID, status, review flag, source hash, media type, and filename.
- Focused regression tests for mismatched report/history data and non-finite stored metadata: **PASS**, 2 tests.
- Full suite: **PASS**, 64 tests, 0 skips, 0 failures/errors.
- Diagnostics: **PASS**, 11/11 checks. The installed FFmpeg/ffprobe folder was added to `PATH`; runner temp files and application media staging used separate directories.
- Frontend syntax: **PASS**, `node --check trustlens\static\app.js`.
- Isolated live Uvicorn HTTP smoke: **PASS** for image and MPEG-4 video intake, report hash/abstention, idempotency, invalid media, list/detail/evidence/export, deletion, and temporary media cleanup.
- Git diff review remains unavailable because the local workspace is not a Git checkout. Source files and tests were inspected directly. No browser click-through or accessibility audit was completed in this increment.
- Browser note: the local New analysis screen was visibly rendered in Chrome and its page text was observed. The automation halted at the first in-page navigation click after the helper reported concurrent user input. The previously logged failure to identify Chrome's URL is superseded by this partial page-load observation; interaction, console/network inspection, and responsive visual QA remain incomplete.

## Commands and actual outcomes

### Full regression suite

PowerShell command (run outside the managed sandbox because local socket creation and temporary-file operations were blocked inside it):

```powershell
$machinePath = [Environment]::GetEnvironmentVariable('Path','Machine')
$userPath = [Environment]::GetEnvironmentVariable('Path','User')
$env:Path = "$machinePath;$userPath"
$env:TRUSTLENS_TEMP_DIR = "$PWD\.trustlens-test-tmp"
$env:TMP = "$PWD\.trustlens-test-tmp"
$env:TEMP = "$PWD\.trustlens-test-tmp"
$env:PYTHONDONTWRITEBYTECODE = '1'
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**Exit code 0.** Final run against the reviewed Milestone B files: `Ran 62 tests in 2.436s`; `OK`. The pre-fix focused tests reproduced malformed `ffprobe` JSON exceptions, non-finite duration leakage, and unhandled malformed persisted report data; all corresponding regressions pass after the fixes.

### Actual backend process restart

```powershell
.venv\Scripts\python.exe tests\http_restart_smoke.py
```

**PASS.** The script started TRUSTLENS on a dynamically selected loopback port with an isolated temporary SQLite database, uploaded an image, stopped the process, started a fresh process against the same database, verified report and source-hash integrity, deleted the report, and confirmed temporary media cleanup. All three script checks passed.

### Diagnostics, JavaScript syntax, and dependencies

```powershell
.venv\Scripts\python.exe -m trustlens.diagnostics --json
node --check trustlens\static\app.js
python -m pip --python .venv\Scripts\python.exe check
```

**Exit code 0 for all commands.** All 11 diagnostic entries were `available`; Node emitted no syntax errors; pip reported `No broken requirements found.` The FastAPI test-client import emits a Starlette deprecation warning about HTTPX; it did not fail the suite.

### Actual Uvicorn process and HTTP smoke

Run the server with an isolated database/media root, then run the smoke client from another terminal:

```powershell
$env:TRUSTLENS_DB_PATH = "$PWD\.trustlens-test-tmp\http-smoke.sqlite3"
$env:TRUSTLENS_TEMP_DIR = "$PWD\.trustlens-test-tmp\http-smoke-media"
.venv\Scripts\python.exe -m trustlens.web
```

```powershell
$machinePath = [Environment]::GetEnvironmentVariable('Path','Machine')
$userPath = [Environment]::GetEnvironmentVariable('Path','User')
$env:Path = "$machinePath;$userPath"
$env:TRUSTLENS_TEMP_DIR = "$PWD\.trustlens-test-tmp\http-smoke-media"
.venv\Scripts\python.exe tests\http_smoke.py
```

The verification run started Uvicorn hidden for the check, ran `tests/http_smoke.py` against `http://127.0.0.1:8765`, then stopped the process and verified port 8765 was closed. All seven smoke assertions passed:

- health/capabilities;
- image upload, original SHA-256/report, detector `UNAVAILABLE`, human-review abstention;
- same-key/same-bytes idempotent replay;
- real one-second MPEG-4 video upload and sampled frame output;
- invalid media returns 422 without creating a history record;
- history, detail, evidence, JSON report download, and delete;
- report count returned to its baseline and media temp directory was empty.

After the Milestone B fixes, the isolated real Uvicorn HTTP smoke was rerun and all seven assertions passed, including a generated MPEG-4 upload and sampled frames.

### Existing application test coverage

`tests/test_web_app.py` covers home/static asset response headers and content, health/capabilities/OpenAPI, image upload, list/search/filter, detail/evidence/report/download/delete, restart persistence, idempotency conflict and replay, invalid media, unknown IDs, invalid filters, simulated SQLite write failure, corrupt SQLite file, request-body limit, untrusted Host/Origin, and filename traversal sanitation.

`tests/` also includes generated image/video tests for content sniffing and extension mismatch, unsupported/corrupt/empty input, media/image bounds, image normalization, original-byte hashing, video metadata/sample timestamps/frame hashes, unavailable tools, cleanup after service errors, fusion validation and abstention, and provenance status reporting.

## Failed or blocked attempts

- An initial diagnostics run inside the managed sandbox reported Pillow fixture writes as `PermissionError` and did not find FFmpeg/ffprobe. Re-running outside the sandbox with Machine/User PATH restored produced all 11 `available` results. This was an execution-environment false negative, not an application defect.
- The first real HTTP fixture command inherited a PATH without FFmpeg and failed before media tests. The process was stopped; the rerun restored PATH and passed.
- Browser automation did not navigate: the Computer Use service reported it could not determine Chrome's current browser URL with enough confidence to enforce policy and stopped. Browser navigation, interaction, console, and responsive-layout checks remain blocked/unverified.
- No production frontend build or lint command exists, so none was claimed.

## Remaining verification limits

- The real HTTP smoke exercises backend endpoints, not browser-rendered visual correctness. The UI source wires each navigation/filter/upload/report/export/delete action, but those controls were not clicked in a browser during this run.
- No full 100 MiB network upload, stress/load, parallel-user isolation, exhaustive codec corpus, accessibility audit, or formal chain-of-custody procedure was tested.
- The app has no job queue/status endpoint: each upload is processed synchronously in its HTTP request.
- Local loopback binding is verified in the entrypoint; auth, per-user authorization, at-rest encryption, and production network exposure controls are not provided.
- No ML model or labeled evaluation dataset was used. Detector inference, accuracy, confidence, and calibration remain excluded/unavailable.
# Verification update — report schema/evidence graph (2026-10-14)

- `.venv\Scripts\python.exe -m unittest tests.test_evidence_graph tests.test_service -v` — **PASS**, 9 passed, 1 skipped. Checks cover schema 1.1 generation metadata, graph relationships, malformed/duplicate graph nodes, rejection of dangling graph references, and legacy 1.0 compatibility. Real-video service coverage was skipped because FFmpeg/ffprobe were not visible on PATH in this run.
- Full suite attempt reached `test_idempotency_replays_same_source_and_rejects_different_source` in `tests.test_web_app` and remained there beyond 60 seconds. The process was interrupted; no full-suite result is claimed for this increment. Earlier recorded full-suite results in this file apply to the earlier code state only.
- Initial focused run used the sandbox default temp location and failed with `PermissionError`. Re-running with `TEMP`, `TMP`, and `TRUSTLENS_TEMP_DIR` set to the workspace `.trustlens-test-tmp` directory passed.

