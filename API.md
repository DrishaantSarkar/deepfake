# Local application API

The API is same-origin with the browser UI and is served only from the loopback server at `http://127.0.0.1:8765`. OpenAPI is available at `/api/docs` while the app is running. There is no application login or multi-user authorization; do not expose these routes to a network.

| Route | Purpose |
|---|---|
| `GET /api/health` | Check local service and SQLite availability |
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

The request upload is hashed before processing. `analyze_upload()` stages/validates media, produces the report, and cleans staged originals and derived frame files before returning. SQLite persists the report JSON and its extracted source metadata, including parser-observed fields; it does not persist original image/video bytes or retrievable video-frame images. The history list stores display filename, media type, source SHA-256, status, timestamps, and report content. A hash is an integrity identifier, not proof of provenance or custody.

The default DB path is outside the workspace under the current OS user's local application data directory. Override with `TRUSTLENS_DB_PATH`; override media staging with `TRUSTLENS_TEMP_DIR`. SQLite is not encrypted by this application. Access is governed by the OS account and filesystem permissions. There are no cookies or bearer tokens because this local single-user MVP has no application identity system.
