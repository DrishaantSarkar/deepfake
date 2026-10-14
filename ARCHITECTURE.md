# TRUSTLENS architecture (verified local implementation)

```text
Caller-owned binary stream
        │
        ▼
trustlens.ingestion.ingest_media
  ├─ content/size/decode checks, SHA-256, metadata
  └─ normalized image or isolated temporary source
        │
        ├─ image ──► image_analysis (detector adapter + DCT descriptor)
        │
        └─ video ──► FFmpeg bounded sampler ──► image_analysis per frame
                                  └────────────► descriptive adjacent-sample luma differences
        │
        ▼
provenance states (metadata observed; C2PA/watermark explicitly unavailable)
        │
        ▼
evidence_fusion (preserve records, limited comparable-label conflicts; no scoring)
        │
        ▼
service.AnalysisReport → validation → caller mapping/serialization → temporary cleanup
```

The diagram describes the processing package. A local-only application wrapper was added later (see below). The wrapper has no user identity or authorization model and must not be exposed to a network.

## Boundaries and failure behavior

- Ingestion rejects invalid/oversized content with `IngestionError`; callers map it to their transport contract.
- Image/video work returns explicit statuses and abstains when models are absent. The service converts unexpected downstream failures to a limited `FAILED` report and cleans staged data.
- Video sampling is capped by `VideoSamplingConfig`; timestamps are retained when available, original frame indices are null, and artifacts are removed at service return.
- Fusion validates and retains evidence but never aggregates uncalibrated scores or resolves a final authenticity decision.
- `provenance.py` distinguishes parser metadata from verification; content credentials and watermarks remain unavailable.

## Local single-user application wrapper

```text
Browser (same origin)
  ├─ GET static TRUSTLENS UI
  └─ JSON requests ─► FastAPI (127.0.0.1:8765)
                         ├─ UploadFile + request bounds + origin/host checks
                         ├─ run_in_threadpool(trustlens.service.analyze_upload)
                         │    └─ temporary media → report → cleanup
                         └─ SQLite reports/history (no source media files)
```

`trustlens/web.py` exposes `/api/health`, `/api/capabilities`, `/api/stats`, and `/api/analyses` routes for upload, history, detail, evidence, report download, and deletion. `trustlens/persistence.py` stores report JSON and searchable columns. The static dashboard consumes only same-origin APIs and escapes values before inserting rendered report content. See `API.md` for request/response boundaries and lifecycle details.

There is no login, cookie, bearer token, user identity, or record ownership layer. The current boundary is loopback binding plus the logged-in operating-system account and local filesystem. This is a local MVP, not a security boundary for other local users and not a production deployment design. SQLite is unencrypted; reports may contain extracted metadata. Originals and derived frame files are deleted by the service, while report JSON remains until the user deletes the history record.
