# TRUSTLENS Backend

A high-performance media forensics backend powered by FastAPI, PyTorch, OpenCV, SQLite, and an evidence graph engine.

## Prerequisites

- **Python**: 3.11 or newer (tested with Python 3.11/3.12)
- **PowerShell** or any standard terminal

## Setup and Commands

From this directory (`backend/`):

### 1. Create and Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(On Linux/macOS: `source .venv/bin/activate`)*

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt   # Required for running tests
```

### 3. Run the Backend Server
Starts the FastAPI application on `127.0.0.1:8765`:
```powershell
python -m trustlens.web
```
- Bound to loopback address `127.0.0.1` for local, secure single-user operation.
- Automatically resolves and serves the built frontend from `../frontend/static` (or internal fallback).
- API docs available at `http://127.0.0.1:8765/docs` and schema at `/api/openapi.json`.

### 4. Run Backend Tests
```powershell
python -m unittest discover -s tests -v
```

### 5. Run Smoke and Restart Tests
```powershell
python tests/http_restart_smoke.py
```

## Environment Variables
- `TRUSTLENS_PORT`: Custom port (default: `8765`).
- `TRUSTLENS_STATIC_DIR`: Override frontend static bundle path.
- `TRUSTLENS_DB_PATH`: Custom path to SQLite database.
- `TRUSTLENS_TEMP_DIR`: Directory for temporary uploaded media staging.
- `TRUSTLENS_CHECKPOINT_PATH`: Override PyTorch model weights path (default: `checkpoints/best_model.pt`).

## Directory Structure
- `trustlens/` — Core Python forensics library, FastAPI web application, and analysis services.
- `ml_pipeline/` — Model training, cross-validation, and multimodal evaluation pipelines.
- `checkpoints/` — Trained PyTorch model artifacts (`best_model.pt`).
- `tests/` — Automated test suite and synthetic/real media test fixtures.
