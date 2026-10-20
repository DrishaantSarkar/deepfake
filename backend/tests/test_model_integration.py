"""Automated test suite for PyTorch model adapter and backend-ML integration."""

from __future__ import annotations

import importlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from trustlens.detector_adapter import PyTorchModelDetector
from trustlens.ingestion import ProcessingStatus
from trustlens.persistence import AnalysisStore
from trustlens.service import analyze_upload, validate_analysis_report
from trustlens.web import create_app

torch: Any = None
nn: Any = None
resnet18: Any = None

try:
    torch = importlib.import_module("torch")
    nn = importlib.import_module("torch.nn")
    _models = importlib.import_module("torchvision.models")
    resnet18 = getattr(_models, "resnet18", None)
except (ImportError, ModuleNotFoundError):
    torch = None
    nn = None
    resnet18 = None


def _create_test_checkpoint(path: Path, *, model_id: str = "test-resnet18", threshold: float = 0.5) -> Path:
    """Create a valid standalone ResNet-18 checkpoint matching the baseline schema."""
    model = resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 1)
    payload = {
        "schema_version": "1.0",
        "model_id": model_id,
        "model_state_dict": model.state_dict(),
        "image_size": 224,
        "mean": (0.485, 0.456, 0.406),
        "std": (0.229, 0.224, 0.225),
        "threshold": threshold,
        "trained": True,
    }
    torch.save(payload, path)
    return path


def _sample_png_bytes(color: tuple[int, int, int] = (100, 150, 200)) -> bytes:
    image = Image.new("RGB", (64, 48), color)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@unittest.skipIf(torch is None or nn is None or resnet18 is None, "PyTorch and torchvision are required")
class PyTorchModelDetectorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="trustlens-model-test-")
        self.checkpoint_path = Path(self.temp_dir.name) / "best_model.pt"
        _create_test_checkpoint(self.checkpoint_path, threshold=0.6)
        self.detector = PyTorchModelDetector(self.checkpoint_path, device="cpu")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_detector_initialization_and_descriptor(self):
        self.assertEqual(self.detector.descriptor.name, "test-resnet18")
        self.assertEqual(self.detector.descriptor.output_labels, ("real", "synthetic"))
        self.assertIn("RGB Pillow image", self.detector.descriptor.supported_inputs)
        self.assertFalse(self.detector.model.training)
        self.assertEqual(self.detector.threshold, 0.6)

    def test_detector_predict_produces_valid_probabilities_and_deterministic_output(self):
        with Image.open(io.BytesIO(_sample_png_bytes((50, 100, 150)))) as img:
            out1 = self.detector.predict(img)
            out2 = self.detector.predict(img)

        self.assertEqual(out1.status, ProcessingStatus.SUCCESS)
        self.assertIn("synthetic", out1.raw_scores)
        self.assertIn("real", out1.raw_scores)
        self.assertAlmostEqual(out1.raw_scores["synthetic"] + out1.raw_scores["real"], 1.0, places=5)
        self.assertIn(out1.predicted_label, {"real", "synthetic"})
        # Deterministic
        self.assertEqual(out1.raw_scores, out2.raw_scores)
        self.assertEqual(out1.predicted_label, out2.predicted_label)

    def test_detector_evaluates_different_inputs(self):
        with Image.open(io.BytesIO(_sample_png_bytes((10, 10, 10)))) as dark_img:
            dark_out = self.detector.predict(dark_img)
        with Image.open(io.BytesIO(_sample_png_bytes((240, 240, 240)))) as bright_img:
            bright_out = self.detector.predict(bright_img)

        self.assertEqual(dark_out.status, ProcessingStatus.SUCCESS)
        self.assertEqual(bright_out.status, ProcessingStatus.SUCCESS)

    def test_missing_and_corrupt_checkpoint_handling(self):
        with self.assertRaises(FileNotFoundError):
            PyTorchModelDetector(Path(self.temp_dir.name) / "nonexistent.pt")

        corrupt_path = Path(self.temp_dir.name) / "corrupt.pt"
        corrupt_path.write_bytes(b"not a valid torch file")
        with self.assertRaises(ValueError):
            PyTorchModelDetector(corrupt_path)

        empty_dict_path = Path(self.temp_dir.name) / "empty_dict.pt"
        torch.save({"schema_version": "1.0"}, empty_dict_path)
        with self.assertRaises(ValueError):
            PyTorchModelDetector(empty_dict_path)

    def test_invalid_input_to_predict(self):
        out = self.detector.predict("not an image")  # type: ignore
        self.assertEqual(out.status, ProcessingStatus.FAILED)
        self.assertIsNotNone(out.error)


@unittest.skipIf(torch is None or nn is None or resnet18 is None, "PyTorch and torchvision are required")
class BackendModelIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="trustlens-backend-model-test-")
        self.checkpoint_path = Path(self.temp_dir.name) / "best_model.pt"
        _create_test_checkpoint(self.checkpoint_path, threshold=0.5)
        self.detector = PyTorchModelDetector(self.checkpoint_path, device="cpu")
        self.db_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.store = AnalysisStore(self.db_path)
        self.app = create_app(self.store, detector=self.detector)
        self.client = TestClient(self.app, base_url="http://127.0.0.1")

    def tearDown(self):
        self.client.close()
        self.temp_dir.cleanup()

    def test_capabilities_discloses_active_detector_when_configured(self):
        caps = self.client.get("/api/capabilities").json()
        self.assertEqual(caps["image"]["trained_detector"], "available")
        self.assertEqual(caps["image"]["model"]["name"], "test-resnet18")

    def test_service_analyze_upload_with_detector_populates_report(self):
        raw_bytes = _sample_png_bytes((30, 80, 130))
        report = analyze_upload(io.BytesIO(raw_bytes), "sample.png", detector=self.detector)
        report_dict = report.to_dict()

        validate_analysis_report(report_dict)
        analysis_result = report_dict["analysis"]["result"]
        self.assertEqual(analysis_result["detector"]["status"], "SUCCESS")
        self.assertIn("synthetic", analysis_result["detector"]["raw_scores"])
        self.assertIn("real", analysis_result["detector"]["raw_scores"])
        self.assertIn(analysis_result["detector"]["predicted_label"], {"real", "synthetic"})

        # Evidence fusion retains whole_image_detector record
        fusion_sources = {entry["evidence_source"] for entry in report_dict["fusion"]["evidence"]}
        self.assertIn("whole_image_detector", fusion_sources)

    def test_api_prediction_matches_direct_inference(self):
        raw_bytes = _sample_png_bytes((120, 140, 160))

        # Direct inference
        with Image.open(io.BytesIO(raw_bytes)) as img:
            direct_output = self.detector.predict(img)

        # API inference
        resp = self.client.post(
            "/api/analyses",
            files={"file": ("sample.png", raw_bytes, "image/png")},
            headers={"Idempotency-Key": "test-key-1"},
        )
        self.assertEqual(resp.status_code, 201)
        record = resp.json()
        analysis_id = record["analysis_id"]

        report = record["report"]
        api_detector = report["analysis"]["result"]["detector"]
        self.assertEqual(api_detector["status"], "SUCCESS")
        self.assertAlmostEqual(api_detector["raw_scores"]["synthetic"], direct_output.raw_scores["synthetic"], places=5)
        self.assertAlmostEqual(api_detector["raw_scores"]["real"], direct_output.raw_scores["real"], places=5)
        self.assertEqual(api_detector["predicted_label"], direct_output.predicted_label)

        # Persistence check
        stored = self.client.get(f"/api/analyses/{analysis_id}").json()
        self.assertEqual(
            stored["report"]["analysis"]["result"]["detector"]["raw_scores"],
            api_detector["raw_scores"],
        )

    def test_environment_variable_auto_loads_detector(self):
        with patch.dict(os.environ, {"TRUSTLENS_MODEL_PATH": str(self.checkpoint_path)}):
            env_app = create_app(AnalysisStore(Path(self.temp_dir.name) / "env.sqlite3"))
            with TestClient(env_app, base_url="http://127.0.0.1") as client:
                caps = client.get("/api/capabilities").json()
                self.assertEqual(caps["image"]["trained_detector"], "available")
                self.assertEqual(caps["image"]["model"]["name"], "test-resnet18")


if __name__ == "__main__":
    unittest.main()
