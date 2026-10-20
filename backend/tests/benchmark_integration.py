"""Benchmark model loading, warm inference, and end-to-end API latency."""

import io
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import importlib
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image

from trustlens.detector_adapter import PyTorchModelDetector
from trustlens.persistence import AnalysisStore
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


def create_checkpoint(path: Path) -> Path:
    model = resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 1)
    payload = {
        "schema_version": "1.0",
        "model_id": "resnet18-benchmark",
        "model_state_dict": model.state_dict(),
        "image_size": 224,
        "mean": (0.485, 0.456, 0.406),
        "std": (0.229, 0.224, 0.225),
        "threshold": 0.5,
        "trained": True,
    }
    torch.save(payload, path)
    return path


def sample_image_bytes() -> bytes:
    img = Image.new("RGB", (224, 224), (120, 160, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def benchmark():
    if torch is None or nn is None or resnet18 is None:
        print("SKIPPED: PyTorch and torchvision are required for benchmark.")
        return
    with tempfile.TemporaryDirectory() as tmp:
        ckpt_path = Path(tmp) / "model.pt"
        create_checkpoint(ckpt_path)

        # 1. Initialization latency
        t0 = time.perf_counter()
        detector = PyTorchModelDetector(ckpt_path, device="cpu")
        init_time_ms = (time.perf_counter() - t0) * 1000

        # Warmup
        raw_bytes = sample_image_bytes()
        with Image.open(io.BytesIO(raw_bytes)) as pil_img:
            detector.predict(pil_img)

        # 2. Warm inference latency (20 iterations)
        latencies = []
        with Image.open(io.BytesIO(raw_bytes)) as pil_img:
            for _ in range(20):
                t_start = time.perf_counter()
                detector.predict(pil_img)
                latencies.append((time.perf_counter() - t_start) * 1000)

        mean_infer_ms = sum(latencies) / len(latencies)
        p95_infer_ms = sorted(latencies)[int(len(latencies) * 0.95)]

        # 3. End-to-end API latency (10 iterations)
        db_path = Path(tmp) / "bench.sqlite3"
        store = AnalysisStore(db_path)
        app = create_app(store, detector=detector)
        client = TestClient(app, base_url="http://127.0.0.1")

        api_latencies = []
        for i in range(10):
            t_start = time.perf_counter()
            resp = client.post(
                "/api/analyses",
                files={"file": (f"bench-{i}.png", raw_bytes, "image/png")},
                headers={"Idempotency-Key": f"bench-key-{i}"},
            )
            assert resp.status_code == 201
            api_latencies.append((time.perf_counter() - t_start) * 1000)
        client.close()

        mean_api_ms = sum(api_latencies) / len(api_latencies)
        p95_api_ms = sorted(api_latencies)[int(len(api_latencies) * 0.95)]

        print(f"MODEL_INIT_MS={init_time_ms:.2f}")
        print(f"WARM_INFER_MEAN_MS={mean_infer_ms:.2f}")
        print(f"WARM_INFER_P95_MS={p95_infer_ms:.2f}")
        print(f"API_E2E_MEAN_MS={mean_api_ms:.2f}")
        print(f"API_E2E_P95_MS={p95_api_ms:.2f}")


if __name__ == "__main__":
    benchmark()
