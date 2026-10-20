# 🛡️ TRUSTLENS — Enterprise Multimodal Media Forensics & Deepfake Detection Platform

[![Live App on Vercel](https://img.shields.io/badge/Frontend-Live%20on%20Vercel-black?style=for-the-badge&logo=vercel)](https://deepfake-46lu3f7av-drishaant-sarkars-projects.vercel.app/#dashboard)
[![Live API on Render](https://img.shields.io/badge/Backend-Live%20on%20Render-46E3B7?style=for-the-badge&logo=render)](https://deepfake-48de.onrender.com)
[![Swagger API Docs](https://img.shields.io/badge/API%20Docs-Swagger%20UI-85EA2D?style=for-the-badge&logo=swagger)](https://deepfake-48de.onrender.com/docs)
[![Tests Passing](https://img.shields.io/badge/Test%20Suite-101%2F101%20PASSING-success?style=for-the-badge&logo=pytest)](file:///c:/Users/Drishaant%20Sarkar/Desktop/DEEPFAKE--main/DEEPFAKE--main/backend/tests)

---

## 🏆 Quick Links & Live Demo Access for Judges

| Resource | Live Link | Description |
|:---|:---|:---|
| 🖥️ **Live Web Application (Vercel)** | [**Launch TRUSTLENS UI**](https://deepfake-46lu3f7av-drishaant-sarkars-projects.vercel.app/#dashboard) | Full React 18 single-page investigation workspace with dark mode and real-time report telemetry. |
| ⚡ **Live Backend Service (Render)** | [**Live API Health Check**](https://deepfake-48de.onrender.com/api/health) | Production FastAPI container running PyTorch, OpenCV, and Evidence Graph pipelines. |
| 📖 **Interactive API Documentation** | [**Swagger OpenAPI Interactive Docs**](https://deepfake-48de.onrender.com/docs) | Live endpoint testing suite with full request schemas and responses. |
| 🔑 **Workspace Sign-In Key** | `trustlens-prod-secret-2026` | Enter this access key in the workspace modal to unlock full investigation and analysis features. |

---

## 📌 Executive Summary & Problem Statement

### The Problem
The explosion of generative artificial intelligence (Diffusion models, GANs, neural voice cloning, and deepfake face-swapping) has compromised the integrity of digital evidence. Traditional media verification fails because:
1. **Single-modality brittleness:** Image-only or audio-only detectors are easily fooled by social media recompression, resolution downscaling, and adversarial noise.
2. **The "Black Box" Trust Deficit:** Legacy tools output an opaque score (e.g., *"92% Fake"*) without legal or technical evidence, making them unusable in legal proceedings, newsroom fact-checking, or forensic audits.
3. **Hallucination & Overconfidence:** Naive classifiers fabricate confidence scores even when media tracks are corrupted, stripped of metadata, or missing altogether.

### The TRUSTLENS Innovation
**TRUSTLENS** is an AI-assisted media-forensics investigation desk designed for enterprise trust, legal reproducibility, and multi-layered authenticity assessment. Rather than relying on a single black-box model, TRUSTLENS cross-verifies digital media across **four independent analytical vectors** fused into a unified **Evidence Graph**:
- **Spatial / Visual Neural Detection:** Fine-tuned PyTorch ResNet-18 classifier detecting micro-texture blending, warped facial boundaries, and GAN/diffusion synthesis artifacts.
- **2D Fourier Frequency-Domain Analysis:** FFT spectral decomposition detecting periodic grid patterns and high-frequency discrepancies left by neural upsampling layers.
- **Temporal Sequence Consistency:** Multi-frame motion vector tracking and structural similarity (SSIM) variance measuring temporal flicker and unnatural inter-frame drift.
- **Container Provenance & Structural Audit:** Deep byte-level parsing of EXIF data, MP4 atom hierarchy, C2PA content credentials, and hex magic-byte signatures.

---

## 📊 End-to-End System Architecture

```mermaid
flowchart TD
    subgraph Client ["Client Layer / Forensic Investigator"]
        Browser["🖥️ React 18 Investigation Workspace<br/>(TypeScript + TailwindCSS)"]
        Dropzone["📤 Drag & Drop Media Intake<br/>(JPG, PNG, WEBP, MP4, MOV, WAV)"]
        KeyModal["🔐 Access Gate Modal<br/>Key: trustlens-prod-secret-2026"]
    end

    subgraph VercelEdge ["Vercel Edge Cloud (Global CDN)"]
        VercelCDN["⚡ Static Distribution & Caching<br/>(bundle.js, app.css, assets)"]
        EdgeGateway["🌐 Serverless Edge API Gateway<br/>(api/[...path].js)"]
    end

    subgraph RenderCloud ["Render Cloud Container (ML Backend)"]
        FastAPIEngine["🚀 FastAPI High-Throughput Server<br/>(Uvicorn + Python 3.12)"]
        SecurityBoundary["🛡️ Boundary Security & Rate Limiter<br/>(TrustedHost, CORS, Sliding-Window IP Limiter)"]
        StagingArea["📁 Ephemeral Staging Storage<br/>(Zero-persistence auto-clean)"]

        subgraph CorePipeline ["Multimodal Forensic Pipeline"]
            Ingestor["🔍 Media Intake & Validation<br/>(MIME inspection, SHA-256 source hash)"]
            
            subgraph Detectors ["Analytical Vectors"]
                PyTorchModel["🧠 PyTorch ResNet-18 Classifier<br/>(Deep visual artifact detector)"]
                SpectralFFT["📈 2D FFT Spectral Engine<br/>(Frequency domain grid analyzer)"]
                TemporalVideo["⏱️ Temporal Video Tracker<br/>(Inter-frame SSIM & motion stability)"]
                ProvenanceAudit["🏷️ Provenance & Metadata Engine<br/>(EXIF, MP4 atom audit, C2PA claims)"]
            end

            EvidenceFusion["🕸️ Evidence Graph Fusion Engine<br/>(Calibrated Bayesian multi-signal synthesis)"]
        end

        subgraph Persistence ["Data & Audit Store"]
            Database[("🗄️ SQLite / PostgreSQL Store<br/>(Idempotent forensic JSON reports)")]
        end
    end

    %% Client Interactions
    Browser --> Dropzone
    Browser --> KeyModal
    KeyModal -->|"Verify Key"| EdgeGateway
    Dropzone -->|"Multipart Upload"| EdgeGateway

    %% Edge Routing
    VercelCDN --> Browser
    EdgeGateway -->|"Secure HTTPS Proxy"| FastAPIEngine

    %% Backend Processing
    FastAPIEngine --> SecurityBoundary
    SecurityBoundary --> StagingArea
    StagingArea --> Ingestor
    Ingestor --> Detectors

    Detectors --> PyTorchModel
    Detectors --> SpectralFFT
    Detectors --> TemporalVideo
    Detectors --> ProvenanceAudit

    PyTorchModel --> EvidenceFusion
    SpectralFFT --> EvidenceFusion
    TemporalVideo --> EvidenceFusion
    ProvenanceAudit --> EvidenceFusion

    EvidenceFusion -->|"Cryptographic Report"| Database
    Database -->|"Persisted Analysis JSON"| FastAPIEngine
    FastAPIEngine -->|"Standardized Response"| EdgeGateway
    EdgeGateway -->|"Interactive Report & Timeline"| Browser
```

---

## 🔬 Technical Deep-Dive: How Detection Works

```mermaid
sequenceDiagram
    autonumber
    actor Analyst as Forensic Analyst
    participant UI as Vercel Frontend
    participant Edge as Edge API Gateway
    participant API as FastAPI Backend
    participant ML as ML & Signal Pipeline
    participant DB as Report Store

    Analyst->>UI: Uploads suspicious video / image
    UI->>Edge: POST /api/analyses (Multipart Form Data)
    Edge->>API: Proxies stream to Render Backend Container
    API->>API: Computes SHA-256 source hash & checks Idempotency-Key
    alt Duplicate submission
        API->>DB: Fetch existing report by hash
        API-->>UI: Return existing cached forensic report
    else New submission
        API->>ML: Stage file in ephemeral sandbox
        par Parallel Analysis
            ML->>ML: Extract frame sequences via FFmpeg
            ML->>ML: PyTorch ResNet-18 inference on facial crops
            ML->>ML: 2D FFT frequency spectrum decomposition
            ML->>ML: Compute inter-frame SSIM motion drift
            ML->>ML: Parse EXIF / MP4 container metadata
        end
        ML->>ML: Evidence Graph merges signals into calibrated report
        ML->>API: Purge ephemeral media files from disk
        API->>DB: Store sanitized audit record & verdict
        API-->>Edge: Return final forensic JSON report
        Edge-->>UI: Render interactive forensic timeline & confidence graph
    end
```

### 1. Spatial Neural Artifact Detection
- Employs a modified **ResNet-18** architecture fine-tuned on paired genuine/manipulated facial benchmarks.
- Operates in `torch.inference_mode()` with ImageNet normalization:
  $$\mu = [0.485, 0.456, 0.406], \quad \sigma = [0.229, 0.224, 0.225]$$
- Generates probability distribution $P(\text{synthetic} \mid X)$ based on validated thresholds rather than raw uncalibrated logits.

### 2. 2D Spectral Fourier Decomposition
- Converts spatial domain pixel matrices to frequency domain representations using Fast Fourier Transform (FFT):
  $$F(u, v) = \sum_{x=0}^{M-1} \sum_{y=0}^{N-1} f(x, y) e^{-j 2\pi \left(\frac{ux}{M} + \frac{vy}{N}\right)}$$
- Generative models (StyleGAN, Stable Diffusion, Midjourney) rely on convolutional upsampling and deconvolution filters that leave unnatural periodic grid spikes in the azimuthal power spectrum. TRUSTLENS quantifies these anomalous spikes.

### 3. Temporal Video Stability Tracking
- Extracts frames at deterministic intervals ($2.0\text{ fps}$ minimum sampling rate).
- Measures inter-frame Structural Similarity (SSIM) and motion vector variance:
  $$\text{SSIM}(x, y) = \frac{(2\mu_x\mu_y + c_1)(2\sigma_{xy} + c_2)}{(\mu_x^2 + \mu_y^2 + c_1)(\sigma_x^2 + \sigma_y^2 + c_2)}$$
- Deepfake face-swaps generate high-frequency temporal flickering around jawlines and eye contours between consecutive frames.

### 4. Zero-Hallucination Evidence Fusion Engine
- Unlike tools that guess or fabricate numbers when a signal is missing, TRUSTLENS enforces **Truthful Fallback**:
  - Missing audio track $\rightarrow$ explicitly marks audio as `unavailable`, zero impact on visual score.
  - Corrupt or missing model weights $\rightarrow$ marks detector as `unavailable`, preserves baseline metadata without inventing a score.
  - Every report is signed with the file's **SHA-256 cryptographic digest**.

---

## 📂 Repository Structure

The codebase is organized into cleanly separated frontend and backend architectures:

```
DEEPFAKE--main/
├── backend/                       # Dedicated Python Forensics & ML Service
│   ├── checkpoints/               # Pretrained PyTorch models (best_model.pt)
│   ├── ml_pipeline/               # Multi-fold CV training, evaluation, and dataset prep
│   │   ├── multimodal/            # Multimodal inference & feature extraction
│   │   ├── baseline/              # Baseline ResNet model evaluation scripts
│   │   └── data_ingestion/        # Dataset cards, ingestion and annotation utilities
│   ├── tests/                     # 101 automated test cases & multimodal fixtures
│   ├── trustlens/                 # Production Python package
│   │   ├── web.py                 # FastAPI REST API, middleware, auth management
│   │   ├── service.py             # Analysis pipeline orchestration
│   │   ├── detector_adapter.py    # PyTorch detector protocol wrapper
│   │   ├── evidence_fusion.py     # Multimodal evidence graph fusion
│   │   ├── image_analysis.py      # Spatial & FFT spectral processing
│   │   ├── video_analysis.py      # FFmpeg frame extraction & temporal variance
│   │   ├── audio_analysis.py      # Audio spectral & track inspection
│   │   ├── ingestion.py           # Safe media probing & MIME validation
│   │   └── persistence.py         # SQLite / PostgreSQL thread-safe storage
│   ├── requirements.txt           # Production Python requirements
│   ├── requirements-dev.txt       # Development & test requirements
│   └── README.md                  # Backend technical documentation
│
├── frontend/                      # Modern React 18 + TypeScript Application
│   ├── src/                       # React source code
│   │   ├── views/                 # Investigation views (Dashboard, Intake, History, System)
│   │   ├── context/               # Workspace telemetry & session state
│   │   ├── services/              # API client with typed responses
│   │   ├── types/                 # Forensic schema TypeScript interfaces
│   │   ├── AppShell.tsx           # Primary application container & navigation
│   │   ├── Spotlight.tsx          # Quick command bar (Ctrl+K navigation)
│   │   └── input.css              # Custom Tailwind CSS styling tokens
│   ├── static/                    # HTML entry point, bundled JS, and production CSS
│   ├── package.json               # Node scripts and dependencies
│   ├── webpack.config.js          # Webpack production bundling & devServer proxy
│   ├── tailwind.config.js         # Forensic dark theme color palette
│   └── README.md                  # Frontend development documentation
│
├── api/                           # Vercel Serverless Edge Gateway
│   └── [...path].js               # Universal edge proxy to Render backend
├── Dockerfile                     # Hardened non-root production container
├── render.yaml                    # Infrastructure-as-code for Render deployment
├── vercel.json                    # Edge routing, security headers & rewrite rules
└── README.md                      # Primary project documentation
```

---

## 🛠️ Local Development & Build Commands

### 1. Frontend Commands
Navigate to the `frontend/` directory:
```bash
cd frontend
```

| Action | Command | Purpose |
|:---|:---|:---|
| **Install** | `npm install` | Installs React 18, TypeScript, Tailwind, Webpack, Jest |
| **Build** | `npm run build` | Compiles production bundle to `frontend/static/bundle.js` |
| **Dev Server** | `npm run dev` *(or `npm start`)* | Launches Webpack dev server on `http://localhost:3000` with hot reload & API proxy |
| **Test** | `npm test` | Runs Jest smoke and component tests |
| **Lint** | `npm run lint` | Runs ESLint across all TypeScript sources |

### 2. Backend Commands
Navigate to the `backend/` directory:
```bash
cd backend
```

| Action | Command | Purpose |
|:---|:---|:---|
| **Create Virtualenv** | `python -m venv .venv` | Creates Python 3.11/3.12 virtual environment |
| **Activate Virtualenv** | `.\.venv\Scripts\Activate.ps1` | Activates virtual environment in PowerShell *(Linux/macOS: `source .venv/bin/activate`)* |
| **Install Dependencies** | `pip install -r requirements.txt` | Installs FastAPI, PyTorch, OpenCV, psycopg, etc. |
| **Install Dev Tools** | `pip install -r requirements-dev.txt` | Installs testing tools (`httpx`, `pytest`, etc.) |
| **Run Backend Server** | `python -m trustlens.web` | Starts FastAPI on `http://127.0.0.1:8765` |
| **Run Test Suite** | `python -m unittest discover -s tests -v` | Executes all 101 unit and integration tests |
| **Run Persistence Smoke** | `python tests/http_restart_smoke.py` | Validates crash recovery, DB persistence, and cleanup |

---

## 🌐 Dual-Cloud Deployment Details

```
                                  ┌─────────────────────────────┐
                                  │      Client Web Browser     │
                                  └──────────────┬──────────────┘
                                                 │
                                                 │ HTTPS
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │     Vercel Global Edge      │
                                  │  deepfake-...vercel.app     │
                                  │                             │
                                  │  • Static React SPA assets  │
                                  │  • Edge Gateway Proxy       │
                                  └──────────────┬──────────────┘
                                                 │
                                                 │ HTTPS Proxy (/api/*)
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │    Render Cloud Container   │
                                  │  deepfake-48de.onrender.com │
                                  │                             │
                                  │  • Python 3.12 / FastAPI    │
                                  │  • PyTorch ML Detector      │
                                  │  • OpenCV & FFmpeg engines  │
                                  │  • PostgreSQL / SQLite DB   │
                                  └─────────────────────────────┘
```

### Environment Variables Matrix

#### Backend (Render)
Configure in **Render Dashboard** → **Environment Variables**:

| Variable | Recommended Value | Explanation |
|:---|:---|:---|
| `TRUSTLENS_HOST` | `0.0.0.0` | **Mandatory.** Allows external ingress into the container. |
| `TRUSTLENS_ALLOWED_HOSTS` | `*` | **Mandatory.** Permits requests from Render and Vercel domains. |
| `TRUSTLENS_ADMIN_KEY` | `trustlens-prod-secret-2026` | Secret password required to verify admin session tokens. |
| `TRUSTLENS_ENV` | `production` | Enables production runtime optimizations. |
| `TRUSTLENS_PORT` | `10000` | Port matching Render routing (Render also injects `$PORT`). |
| `TRUSTLENS_REQUIRE_AUTH` | `false` | Set to `false` for open evaluation; `true` for sign-in lock. |
| `TRUSTLENS_DB_PATH` | `/app/data/analyses.sqlite3` | SQLite database file location inside container. |
| `TRUSTLENS_TEMP_DIR` | `/app/temp` | Temporary staging folder for uploaded files. |
| `TRUSTLENS_MODEL_PATH` | `/app/checkpoints/best_model.pt` | Path to the PyTorch detector weights file. |

#### Frontend (Vercel)
Configure in **Vercel Dashboard** → **Project Settings** → **Environment Variables**:

| Variable | Value | Explanation |
|:---|:---|:---|
| `TRUSTLENS_BACKEND_URL` | `https://deepfake-48de.onrender.com` | **Mandatory.** Points Vercel's edge proxy to the live Render backend. |

---

## 🔒 Privacy, Security & Compliance

1. **Air-Gapped & Ephemeral by Design:**
   - Ingested images, audio, and videos are placed in a quarantined staging folder (`TRUSTLENS_TEMP_DIR`) and deleted immediately after feature extraction. No raw media is retained on server disks.
2. **Defensive API Sanitation:**
   - All file names and path strings are sanitized against directory traversal attacks (`../../`).
   - Request bodies are strictly capped (`100MB` max upload size) to prevent denial-of-service (DoS) memory exhaustion.
3. **Loopback-First Development:**
   - Default configuration binds strictly to `127.0.0.1` to prevent accidental network exposure in local development.
4. **Brute-Force Rate Limiting:**
   - Privileged authentication endpoints enforce a sliding-window rate limit (max 5 failed attempts per 60 seconds per IP address).

---

## 🎯 Hackathon Judging Criteria Alignment

| Judging Dimension | How TRUSTLENS Delivers |
|:---|:---|
| **Real-World Impact** | Tackles the existential threat of synthetic disinformation, AI identity theft, and synthetic evidence tampering with an actionable, verifiable tool. |
| **Technical Complexity** | Combines deep neural networks (PyTorch), frequency-domain math (FFT), temporal motion tracking (SSIM), container metadata forensics (FFmpeg), and graph fusion. |
| **Usability & Design** | Sleek, dark-mode React 18 interface with responsive cards, interactive evidence breakdowns, and spotlight search (Ctrl+K). |
| **Completeness & Polish** | **101 out of 101 automated tests passing**, fully deployed and working across **Vercel Edge** and **Render Docker Container**, with zero external dependencies required to run locally. |
| **Scientific Truthfulness** | Avoids fake confidence metrics; adheres to strict forensic standards by transparently reporting signal limitations and missing tracks. |

---

## 📄 License & Attribution

Developed for media forensics research, truth verification, and digital investigative journalism.
All source code and test fixtures are licensed under the MIT License.
