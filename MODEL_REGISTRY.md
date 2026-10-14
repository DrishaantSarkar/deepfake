# TRUSTLENS model and method registry

No trained deepfake detector, face model, spatial localization model, C2PA verifier, watermark detector, or calibrated fusion model is configured in this workspace. A test-only detector fixture is not a production model.

| Name | Kind | Version | Status | Inputs/outputs | Evaluation/calibration |
|---|---|---:|---|---|---|
| Configured image detector | Adapter contract | N/A | Unavailable unless caller injects an `ImageDetector` | RGB Pillow image; raw declared labels/scores | No production model artifact; no calibrated output claimed. |
| DCT frequency descriptor | Descriptive feature | 1 | Available | 32×32 grayscale thumbnail; non-DC DCT energy fractions | Not a classifier; no threshold/evaluation/calibration. |
| Adjacent sampled-frame luma difference | Descriptive feature | 1 | Available when at least two valid sampled timestamps exist | Adjacent extracted frames resized to 64×64 grayscale; normalized MAE | Not a manipulation signal; no threshold/evaluation/calibration. |
| Metadata presence inspection | Parser evidence | 1 | Available | Parsed image/video metadata fields; image EXIF includes named date/device/software where present and video tags are bounded | Does not authenticate metadata or establish provenance; bounded video tag overflow is reported as partial. |
| C2PA/content-credential verifier | Provenance verifier | — | Unavailable | No verifier configured | No signature verification claim. |
| Watermark detector | Detector | — | Unavailable | No detector configured | No watermark-search claim. |
| Fusion classifier | Classifier | — | Unavailable | Evidence records preserved; narrow conflict flags only | No aggregation, calibrated probability, or final authenticity claim. |

Production registration requires model artifact identity/hash, license, runtime, preprocessing, label semantics, resource bounds, evaluation protocol/results, calibration protocol/results, and limitations. Do not register placeholders or test fixtures as production models.
