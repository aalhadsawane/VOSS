"""SeBS 411.image-recognition: ResNet-50 inference on one image (PyTorch, CPU). Weights at /voss/data/resnet50.pth."""

from __future__ import annotations

import torch
from torchvision.models import resnet50

MODEL = resnet50()
MODEL.load_state_dict(torch.load("/voss/data/resnet50.pth"))
MODEL.eval()


def make_input(size_kb: int) -> torch.Tensor:
    side = 224 if size_kb <= 100 else 448
    return torch.rand(1, 3, side, side)


def handler(x: torch.Tensor) -> int:
    with torch.no_grad():
        return int(MODEL(x).argmax())
