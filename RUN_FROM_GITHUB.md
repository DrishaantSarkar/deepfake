# Run TRUSTLENS from GitHub (Windows)

This guide gets the local TRUSTLENS web app running from a fresh GitHub clone.

## 1. Install prerequisites

Install Git and Python 3.11 or newer. During Python setup, enable the Python launcher (`py`) if the installer offers it.

Open PowerShell and check that both are available:

```powershell
git --version
py --version
```

## 2. Clone the repository

```powershell
git clone https://github.com/akagyani/DEEPFAKE-.git
Set-Location DEEPFAKE-
```

## 3. Create a virtual environment

```powershell
py -m venv .venv
```

If PowerShell says `py` is not recognized, use `python -m venv .venv` instead. The selected Python must be version 3.11 or newer.

## 4. Install Python dependencies

```powershell
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 5. Start TRUSTLENS

```powershell
.\.venv\Scripts\python.exe -m trustlens.web
```

Keep this PowerShell window open while using the app.

## 6. Open the app

Visit [http://127.0.0.1:8765](http://127.0.0.1:8765) in your browser. If port 8765 is already in use, stop the other process or choose another port before starting TRUSTLENS:

```powershell
$env:TRUSTLENS_PORT = "8766"
.\.venv\Scripts\python.exe -m trustlens.web
```

Then visit [http://127.0.0.1:8766](http://127.0.0.1:8766).

## 7. Stop the app

Return to the PowerShell window running TRUSTLENS and press **Ctrl+C**.

TRUSTLENS is a local, single-user app with no login. It binds only to `127.0.0.1`; do not expose it to a LAN, reverse proxy, or the public internet. Local analysis history may contain sensitive media metadata.
