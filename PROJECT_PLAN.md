# TRUSTLENS implementation plan

This plan follows the available local Python package and the master prompt. It does not select an application stack without inspecting its actual repository/contract.

## Done and verified in this workspace

- Bounded media intake, image normalization, image/video analysis orchestration, evidence-preserving fusion, report validation, and cleanup.
- Descriptive image DCT evidence and newly added adjacent sampled-frame grayscale-difference evidence.
- Metadata presence reporting with explicit unavailable C2PA and watermark states.
- Human-review abstention and software test coverage for these library workflows.

## Next dependency-aware work

1. **Confirm app source of truth:** obtain full authoritative backend/frontend repository tree and contracts; local workspace and connected GitHub README do not expose these.
2. **Metadata/provenance:** inspect available fields and parser behavior; add standards-compliant signature verification only with a vetted verifier and test fixtures.
3. **Model-backed image analysis:** receive approved weights/runtime/license and preprocessing/label specs; add adapter plus safe inference tests.
4. **Localization and face/region methods:** implement only when actual model capability supports coordinates/heatmaps and the mapping can be verified.
5. **Temporal evaluation:** evaluate the descriptive feature on labeled videos before using it as anything beyond a reported measurement.
6. **Calibration/fusion:** require representative labeled validation data and a documented evaluation/calibration protocol.
7. **Application integration:** after inspecting host contracts, wire upload → analysis → authz → persistence → authorized result/artifact retrieval → frontend review; test ownership boundaries and failures.
8. **Stabilization:** add security/robustness/codec coverage, CI, lint/type/build checks using the host's actual tooling.

Audio remains deferred until the prompt's image/video stability gate is met. Formal chain of custody requires operational policy and controlled storage, not a hash-only code change.
