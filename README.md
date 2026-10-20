# TRUSTLENS Investigation Workspace

TRUSTLENS is an AI-assisted media-forensics platform with a decoupled React/TypeScript frontend and a FastAPI/PyTorch backend.

## Project Structure

```
.
├── backend/                  # FastAPI & PyTorch forensics backend
│   ├── checkpoints/          # Model weights (e.g., best_model.pt)
│   ├── ml_pipeline/          # ML evaluation and training pipelines
│   ├── tests/                # Automated backend test suite and media fixtures
│   ├── trustlens/            # Python package (FastAPI, detectors, fusion graph)
│   ├── requirements.txt      # Production backend requirements
│   ├── requirements-dev.txt  # Test and development dependencies
│   └── README.md             # Backend setup & commands
│
├── frontend/                 # React 18 + TypeScript SPA
│   ├── src/                  # React components, views, context, API client
│   ├── static/               # HTML entry point and static assets
│   ├── package.json          # Frontend scripts and dependencies
│   ├── tsconfig.json         # TypeScript compiler configuration
│   ├── webpack.config.js     # Webpack bundler & devServer configuration
│   └── README.md             # Frontend setup & commands
│
└── README.md                 # Root documentation
```

---

## 🛠️ Build & Run Commands

### 1. Frontend Commands

Navigate to the `frontend/` directory:
```bash
cd frontend
```

| Task | Command | Description |
|------|---------|-------------|
| **Install Dependencies** | `npm install` | Installs React, TypeScript, Tailwind, Webpack, etc. |
| **Build for Production** | `npm run build` | Compiles TypeScript & Tailwind into `frontend/static/bundle.js` |
| **Development Server** | `npm run dev` *(or `npm start`)* | Starts dev server on `http://localhost:3000` with hot reload & API proxy |
| **Unit Tests** | `npm test` | Runs Jest test suite with React Testing Library |
| **Lint & Format** | `npm run lint` | Runs ESLint across `src/` |

---

### 2. Backend Commands

Navigate to the `backend/` directory:
```bash
cd backend
```

| Task | Command | Description |
|------|---------|-------------|
| **Create Virtualenv** | `python -m venv .venv` | Creates Python 3.11+ virtual environment |
| **Activate Virtualenv** | `.\.venv\Scripts\Activate.ps1` | Activates virtual environment in PowerShell *(Linux/macOS: `source .venv/bin/activate`)* |
| **Install Dependencies** | `pip install -r requirements.txt` | Installs FastAPI, PyTorch, OpenCV, etc. |
| **Install Dev Dependencies** | `pip install -r requirements-dev.txt` | Installs test libraries (`httpx`, etc.) |
| **Build / Start Server** | `python -m trustlens.web` | Starts the FastAPI server on `http://127.0.0.1:8765` |
| **Run Unit Tests** | `python -m unittest discover -s tests -v` | Runs all 101 backend unit and integration tests |
| **Run Restart Smoke Test**| `python tests/http_restart_smoke.py` | Runs process persistence and cleanup smoke test |

---

## How Frontend & Backend Work Together

1. **Integrated Mode (Production / Local Standalone)**:
   - Build the frontend: `cd frontend && npm run build`
   - Start the backend: `cd backend && python -m trustlens.web`
   - Visit [http://127.0.0.1:8765](http://127.0.0.1:8765). The FastAPI server automatically resolves `frontend/static` and serves both the API endpoints and the built React bundle from a single origin.

2. **Decoupled Development Mode**:
   - Start the backend server: `cd backend && python -m trustlens.web` (listening on port `8765`).
   - In a second terminal, start the frontend dev server: `cd frontend && npm run dev` (listening on port `3000`).
   - The Webpack dev server proxies all `/api/*` calls automatically to the backend on `http://127.0.0.1:8765`.
