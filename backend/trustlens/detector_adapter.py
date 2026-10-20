"""PyTorch model adapter implementing the ImageDetector protocol for TRUSTLENS."""
from __future__ import annotations

import importlib
import math
import os
from pathlib import Path
from typing import Any

from PIL import Image

from .image_analysis import DetectorDescriptor, DetectorOutput
from .ingestion import ProcessingStatus

torch: Any = None
nn: Any = None
transforms: Any = None
resnet18: Any = None
TORCH_AVAILABLE = False

try:
    torch = importlib.import_module("torch")
    nn = importlib.import_module("torch.nn")
    transforms = importlib.import_module("torchvision.transforms")
    _models = importlib.import_module("torchvision.models")
    resnet18 = getattr(_models, "resnet18", None)
    TORCH_AVAILABLE = bool(torch is not None and nn is not None and transforms is not None and resnet18 is not None)
except (ImportError, ModuleNotFoundError):
    torch = None
    nn = None
    transforms = None
    resnet18 = None
    TORCH_AVAILABLE = False

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class PyTorchModelDetector:
    """Adapter bridging a PyTorch frame-classifier checkpoint to ImageDetector."""

    def __init__(
        self,
        checkpoint_path: str | Path,
        *,
        device: str = "auto",
        threshold: float | None = None,
    ):
        if not TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch and Torchvision are required for PyTorchModelDetector. "
                "Please ensure torch and torchvision are installed in your active environment."
            )

        path = Path(checkpoint_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Checkpoint file not found: {path}")

        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        elif device in {"cpu", "cuda"}:
            if device == "cuda" and not torch.cuda.is_available():
                raise ValueError("CUDA was requested but is unavailable")
            self.device = torch.device(device)
        else:
            raise ValueError(f"Unsupported device: {device}")

        try:
            checkpoint = torch.load(path, map_location=self.device, weights_only=True)
        except Exception as exc:
            raise ValueError(f"Could not load checkpoint from {path}: {exc}") from exc

        if not isinstance(checkpoint, dict):
            raise TypeError(f"Invalid checkpoint format in {path}; expected a dict")

        state_dict = checkpoint.get("model_state_dict") or checkpoint.get("state_dict")
        if state_dict is None:
            raise ValueError("Checkpoint does not contain valid model weights (model_state_dict or state_dict)")
        if not isinstance(state_dict, dict):
            raise TypeError("Model weights in checkpoint must be a dictionary")

        self.model_id = str(checkpoint.get("model_id", "resnet18-frame-classifier"))
        self.image_size = int(checkpoint.get("image_size", 224))
        self.threshold = float(threshold if threshold is not None else checkpoint.get("threshold", 0.5))
        mean = tuple(checkpoint.get("mean", IMAGENET_MEAN))
        std = tuple(checkpoint.get("std", IMAGENET_STD))

        model = resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, 1)

        # Handle weight key matching (supports both baseline and visual branch of multimodal)
        try:
            model.load_state_dict(state_dict)
        except RuntimeError:
            prefix = "visual."
            adjusted_state = {k[len(prefix):]: v for k, v in state_dict.items() if k.startswith(prefix)}
            if adjusted_state:
                model.fc = nn.Identity()
                model.load_state_dict(adjusted_state)
                head_weight = state_dict.get("visual_head.weight")
                head_bias = state_dict.get("visual_head.bias")
                if head_weight is not None:
                    head = nn.Linear(head_weight.shape[1], 1)
                    head.weight = nn.Parameter(head_weight)
                    if head_bias is not None:
                        head.bias = nn.Parameter(head_bias)
                    model = nn.Sequential(model, head)
            else:
                raise

        self.model = model.to(self.device)
        self.model.eval()

        self.transform = transforms.Compose([
            transforms.Resize((self.image_size, self.image_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean, std),
        ])

        trained = bool(checkpoint.get("trained", False))
        self.descriptor = DetectorDescriptor(
            name=self.model_id,
            version="1.0.0",
            supported_inputs=("RGB Pillow image",),
            preprocessing=f"Resize to ({self.image_size}, {self.image_size}), ToTensor, Normalize(mean={mean}, std={std})",
            output_labels=("real", "synthetic"),
            score_semantics="Sigmoid synthetic probability in [0, 1] relative to decision threshold",
            resource_requirements=f"PyTorch CPU/CUDA, device={self.device}",
            limitations=(
                "Frame classifier baseline; does not model temporal dynamics or crop faces.",
                "Scores are model outputs and are not calibrated forensic guarantees.",
            ),
            evaluation_status="EVALUATED" if trained else "NOT_EVALUATED",
            calibration_status="NOT_CALIBRATED",
            label_space="binary",
        )

    def predict(self, image: Image.Image) -> DetectorOutput:
        if not isinstance(image, Image.Image):
            return DetectorOutput(
                status=ProcessingStatus.FAILED,
                error="Input must be a Pillow Image",
            )

        try:
            tensor = self.transform(image.convert("RGB")).unsqueeze(0).to(self.device)
            with torch.inference_mode():
                logit = self.model(tensor)
                raw_val = float(logit.flatten()[0].item())
                score = float(torch.sigmoid(logit.flatten()[0]).item())

            if not math.isfinite(score) or not math.isfinite(raw_val):
                return DetectorOutput(
                    status=ProcessingStatus.FAILED,
                    error="Model produced non-finite prediction score",
                )

            score_synthetic = max(0.0, min(1.0, score))
            score_real = 1.0 - score_synthetic
            predicted_label = "synthetic" if score_synthetic >= self.threshold else "real"

            return DetectorOutput(
                status=ProcessingStatus.SUCCESS,
                raw_scores={"real": score_real, "synthetic": score_synthetic},
                predicted_label=predicted_label,
            )
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            return DetectorOutput(
                status=ProcessingStatus.FAILED,
                error=f"Model inference failed ({type(exc).__name__}: {exc})",
            )


def load_model_detector(
    model_path: str | Path | None = None,
    *,
    device: str = "auto",
    threshold: float | None = None,
) -> PyTorchModelDetector | None:
    """Load detector from specified path or TRUSTLENS_MODEL_PATH environment variable."""
    target = model_path or os.environ.get("TRUSTLENS_MODEL_PATH")
    if not target:
        return None
    return PyTorchModelDetector(target, device=device, threshold=threshold)
