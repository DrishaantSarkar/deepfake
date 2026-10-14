# TRUSTLENS testing

Install the test dependencies with `python -m pip --python .venv\Scripts\python.exe install -r requirements-dev.txt`. From the project root in PowerShell, run:

```powershell
$machinePath = [Environment]::GetEnvironmentVariable('Path','Machine')
$userPath = [Environment]::GetEnvironmentVariable('Path','User')
$env:Path = "$machinePath;$userPath"
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TRUSTLENS_TEMP_DIR = "$PWD\.trustlens-test-tmp"
$env:TMP = "$PWD\.trustlens-test-tmp"
$env:TEMP = "$PWD\.trustlens-test-tmp"
.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check trustlens\static\app.js
python -m pip --python .venv\Scripts\python.exe check
.venv\Scripts\python.exe -m trustlens.diagnostics --json
```

For the real HTTP smoke test, start an isolated server in one PowerShell window:

```powershell
$env:TRUSTLENS_DB_PATH = "$PWD\.trustlens-test-tmp\http-smoke.sqlite3"
$env:TRUSTLENS_TEMP_DIR = "$PWD\.trustlens-test-tmp\http-smoke-media"
.venv\Scripts\python.exe -m trustlens.web
```

In a second window, restore the host PATH, set the same media directory, and run:

```powershell
$machinePath = [Environment]::GetEnvironmentVariable('Path','Machine')
$userPath = [Environment]::GetEnvironmentVariable('Path','User')
$env:Path = "$machinePath;$userPath"
$env:TRUSTLENS_TEMP_DIR = "$PWD\.trustlens-test-tmp\http-smoke-media"
.venv\Scripts\python.exe tests\http_smoke.py
```

## Previous verification (2026-10-13)

- Full unittest suite: **PASS**, 62 tests, no skips, failures, or errors.
- `trustlens.diagnostics --json`: **PASS**, all 11 checks available after restoring the host PATH.
- `pip check`: **PASS**, no broken requirements. `node --check`: **PASS**.
- Actual Uvicorn + `tests/http_smoke.py`: **PASS** for health/capabilities, image/video upload, truthful model-unavailable abstention, idempotency, invalid media, reports/history, deletion, temp cleanup, and shutdown.
- Browser visual/click-based checks remain blocked; see `TEST_REPORT.md` for the Computer Use failure and remaining verification limits.
- Starlette emits an HTTPX TestClient deprecation warning, but the suite passes. The managed sandbox can block local sockets and OS temp-file cleanup; use the host PATH and writable test temp root shown above.

## UI redesign verification

- Updated `trustlens/static/index.html`, `app.css`, and `app.js` in the existing no-build static frontend; backend routes and report semantics are unchanged.
- `node --check trustlens\static\app.js`: **PASS**.
- `test_local_app_serves_ui_capabilities_and_health`: **PASS** as part of the current 62-test suite, verifying the app still serves its UI and same-origin API.
- UI interactions now check `/api/health` plus `/api/capabilities` for backend/database readiness, copy the actual report SHA-256 to the clipboard where supported, ask before deleting a record, and invoke browser print for the active report.
- Browser-rendered visual review, mobile screenshots, keyboard walkthrough, and automated WCAG scan were **not run** because browser automation could not establish the active browser URL in the prior verification attempt. Responsive and focus treatments were implemented in CSS but visual behavior is not confirmed in a browser.

## Latest verification (2026-10-14)

- Full unittest suite: **PASS**, 64 tests, 0 skips, failures, or errors.
- Focused stored-report integrity regressions: **PASS**, both row mismatch and non-finite metadata cases return sanitized 503 responses.
- `trustlens.diagnostics --json`: **PASS**, all 11 checks available with the installed FFmpeg directory added to `PATH` and `TMP`/`TEMP` set to `.trustlens-test-tmp`.
- `node --check trustlens\static\app.js`: **PASS**.
- Actual Uvicorn + `tests/http_smoke.py`: **PASS** for health/capabilities, image/video uploads, hash and abstention semantics, idempotency, invalid input, history/detail/evidence/export, deletion, and temporary media cleanup.
- Browser page load: **PARTIAL**; Chrome visibly rendered the local New analysis screen, then the computer-use helper detected concurrent user input at the first in-page navigation click and automation stopped. No further UI interactions or accessibility review were completed.
- Latest `pip check` is **UNAVAILABLE** because this project virtual environment does not contain the `pip` module; a prior successful check is documented for the earlier environment.
- The test client emits a Starlette deprecation warning for HTTPX integration. The tests pass; dependency cleanup has not been performed.

Exact isolated smoke setup: use a temporary `TRUSTLENS_DB_PATH` and `TRUSTLENS_TEMP_DIR`, with separate `TMP`/`TEMP` for the test runner. Keeping the runner's `TemporaryDirectory` separate avoids counting its active fixture as an application media-staging leftover.

## Stored report/history consistency increment (2026-10-14)

- `AnalysisStore._serialize()` checks report identity/status/review/source fields against the SQLite history row.
- The changed module passes `py_compile`; a direct serializer check accepted a matching row and rejected a source-hash mismatch.
- The new web regression and full suite are **not verified** in this environment: `.venv` references a missing Python 3.14 base executable, and the available bundled Python lacks OpenCV (`cv2`). Restore/recreate the project environment before treating this regression as test-passed.

The tests establish software behavior only; they do not establish model accuracy, calibration, forensic validity, chain of custody, multi-user isolation, or production security.
