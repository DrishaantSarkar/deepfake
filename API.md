# Local application API

The local API is served from `http://127.0.0.1:8765`. OpenAPI is available at `/api/docs` while the app is running. Local development keeps authentication disabled. Hosted demos must set `TRUSTLENS_REQUIRE_AUTH=true` and a strong `TRUSTLENS_ADMIN_KEY`; the UI then requires that shared key to issue short-lived sessions. Keep the key private. The hosted demo uses one shared workspace, not separate user accounts.

| Route | Purpose |
|---|---|
| `GET /api/health` | Check service and configured database availability |
| `GET /api/capabilities` | Report actual processing methods and unavailable model methods |
| `GET /api/stats` | Counts from saved report rows |
| `POST /api/analyses` | Multipart field `file`; optional `Idempotency-Key` header; max upload 100 MiB |
| `GET /api/analyses?limit=20&offset=0&status=SUCCESS&media_type=image&q=text` | Search and page through reports |
| `GET /api/analyses/{analysis_id}` | Saved record and full report |
| `GET /api/analyses/{analysis_id}/evidence` | Evidence, frame measurements, fusion, provenance, limitations, uncertainty |
| `GET /api/analyses/{analysis_id}/report` | Download report JSON |
| `DELETE /api/analyses/{analysis_id}` | Delete one report/history record |

State-changing requests with an `Origin` header must match the request host over HTTP. Upload idempotency keys are limited to 128 safe ASCII characters. Repeating a key with the same source hash replays the existing saved result; using the same key for different bytes returns `409`. Invalid or unsupported media returns `422`; oversized requests return `413`; local DB failures return `503`. Responses use a small `{ "error": { "code": "...", "message": "..." } }` shape for API errors.

## Data and lifecycle

The request upload is hashed before processing. `analyze_upload()` stages/validates media, produces the report, and cleans staged originals and derived frame files before returning. SQLite (local runs) or PostgreSQL (hosted demo) persists the report JSON and its extracted source metadata, including parser-observed fields; it does not persist original image/video bytes or retrievable video-frame images. The history list stores display filename, media type, source SHA-256, status, timestamps, and report content. A hash is an integrity identifier, not proof of provenance or custody.

The default DB path is outside the workspace under the current OS user's local application data directory. Override with `TRUSTLENS_DB_PATH`; override media staging with `TRUSTLENS_TEMP_DIR`. SQLite is not encrypted by this application. Access is governed by the OS account and filesystem permissions. Hosted sessions use short-lived bearer tokens stored in browser session storage. All authenticated users share one workspace and can view or delete its analyses. The Render free demo connects to a managed PostgreSQL database, so history survives backend restarts and redeploys. Render's free PostgreSQL tier is limited to 1 GB, has no backups, and expires 30 days after creation; data is deleted after the 14-day upgrade grace period. Upgrade the database before expiry to keep the data. The app still does not persist uploaded source media.

