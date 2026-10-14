# TRUSTLENS implementation decisions

## D-001 — Preserve the existing Python library boundary

**Decision:** Keep `trustlens.service.analyze_upload()` as the in-process processing boundary. Initially no web/database/auth/frontend stack was introduced without an inspected host contract. The later user-approved D-006 local MVP is a narrowly scoped wrapper around this service; it does not replace the service or invent multi-user auth.

**Reason:** The local workspace contains only a Python package and tests. The GitHub connection verified the default README content but did not expose a complete remote tree in this turn. Host API, identity, ownership, retention, and user-flow contracts are unresolved.

## D-002 — No synthetic detector, weights, calibration, or evaluation claims

**Decision:** Missing production models and evaluation data remain explicitly unavailable. Never substitute test fixtures, random weights, or heuristic score thresholds for validated detectors.

**Reason:** Unsupported authenticity claims create false forensic confidence and conflict with the master prompt.

## D-003 — Temporal feature is descriptive only

**Decision:** Record adjacent sampled-frame normalized grayscale MAE with timestamps and limitations. It does not classify, score manipulation likelihood, or alter abstention.

**Reason:** This is a measurable lightweight signal that can be implemented with existing dependencies; it is unevaluated and can respond to ordinary motion, cuts, exposure changes, compression, and edits.

## D-004 — Provenance states distinguish parser metadata from verification

**Decision:** Report observed metadata separately; report content-credential signature verification and watermark detection as unavailable until actual verifiers are configured.

**Reason:** Metadata inspection is not cryptographic verification, and missing provenance/watermarks do not imply manipulation.

## D-005 — Continue to abstain

**Decision:** Reports continue to require human review and use `INSUFFICIENT_EVIDENCE_REVIEW` until evaluated detector/fusion methods support a different operating policy.

**Reason:** No labeled evaluation corpus or calibration evidence exists in the workspace.

## D-006 — Local single-user application MVP

**Proposal:** If approved, add a local-only FastAPI application in the existing Python runtime, SQLite persistence for report/history metadata, and a same-origin lightweight browser interface. Keep uploaded originals in the current temporary-processing lifecycle and delete them when analysis returns. Bind the development server to loopback only. Do not claim multi-user authentication, production deployment, or durable media retention.

**Reason:** No frontend/backend stack, database, identity provider, or deployment contract is present locally; FastAPI can call the existing Python service without introducing a separate service boundary, and SQLite is a small local persistence option. The current service cleans source and sampled artifacts before it returns, so the proposal must not imply retained originals or retrievable frame files.

**Status:** Approved by the user for a local single-user MVP. Implemented in `trustlens.web`, `trustlens.persistence`, and `trustlens.static`. The application is deliberately loopback-only and has no authentication system. This decision does not authorize LAN/public deployment or claim multi-user isolation.
