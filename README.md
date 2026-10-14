# TRUSTLENS local investigation workspace

TRUSTLENS is an AI-assisted media-forensics library with a local browser application. The app calls the existing `trustlens.service.analyze_upload()` pipeline, stores report/history JSON in SQLite, and serves its interface and API from one origin.

## Run locally

Use Python 3.11 or newer. In PowerShell from this directory:

```powershell
python -m venv .venv
python -m pip --python .venv\Scripts\python.exe install -r requirements.txt
.venv\Scripts\python.exe -m trustlens.web
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The server binds only to `127.0.0.1`. It has no login or multi-user authentication; do not expose it to a LAN, reverse proxy, or the public internet.

Set `TRUSTLENS_PORT` to choose another port (1–65535); the bind address remains loopback-only.

To clone the project from GitHub and run it on Windows, follow the [step-by-step tutorial](RUN_FROM_GITHUB.md).

The local data file defaults to `%LOCALAPPDATA%\TRUSTLENS\analyses.sqlite3` on Windows and `$XDG_DATA_HOME/TRUSTLENS/analyses.sqlite3` (or `~/.local/share/TRUSTLENS/analyses.sqlite3`) elsewhere. Set `TRUSTLENS_DB_PATH` to choose a different SQLite file. Set `TRUSTLENS_TEMP_DIR` to choose where temporary media is staged. Originals and derived frame artifacts are removed after the service call; SQLite retains report JSON and extracted metadata, which may include sensitive media metadata. Deleting a history item deletes its report row.

Run the software tests with the development test dependency:

```powershell
python -m pip --python .venv\Scripts\python.exe install -r requirements-dev.txt
$env:TRUSTLENS_TEMP_DIR = "$PWD\.trustlens-test-tmp"
$env:TMP = "$PWD\.trustlens-test-tmp"
$env:TEMP = "$PWD\.trustlens-test-tmp"
.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check trustlens\static\app.js
```

For real loopback HTTP smoke coverage, first start the application in one PowerShell window with an isolated test DB and media directory:

```powershell
$env:TRUSTLENS_DB_PATH = "$PWD\.trustlens-test-tmp\http-smoke.sqlite3"
$env:TRUSTLENS_TEMP_DIR = "$PWD\.trustlens-test-tmp\http-smoke-media"
.venv\Scripts\python.exe -m trustlens.web
```

In a second window, set the same `TRUSTLENS_TEMP_DIR` and run `.venv\Scripts\python.exe tests\http_smoke.py`. The smoke script creates temporary image/video fixtures, exercises upload/idempotency/retrieval/error/deletion flows, and removes only its own report rows.

For an isolated backend process-restart/persistence check, run `.venv\Scripts\python.exe tests\http_restart_smoke.py` with no app already listening on the randomly selected loopback port. It creates a temporary database/media directory, starts and restarts TRUSTLENS, verifies the record/hash, then removes the report and its temporary directory.

## Current capability limits

The application provides upload validation, source hashing, available descriptive image/video processing, report/history browsing, JSON report export, and local report deletion. It requires human review and does not claim calibrated authenticity probabilities. No trained deepfake model, calibrated fusion model, C2PA verifier, watermark detector, audio forensic model, user authentication, or durable media artifact store is configured. See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md), [REPORT_SCHEMA.md](REPORT_SCHEMA.md), and [INTEGRATION_PLAN.md](INTEGRATION_PLAN.md).
