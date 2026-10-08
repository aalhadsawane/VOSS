"""Placer interface (doc 05 §4): ``place(req) -> Placement``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from voss.core.types import ClusterView, Invocation, Placement


@dataclass(frozen=True)
class PlaceRequest:
    """Invocations to place against one view at decision time ``now``."""

    invs: tuple[Invocation, ...]
    view: ClusterView
    now: float
    gen: np.random.Generator
    expiry_margin_s: float = 5.0


class Placer(Protocol):
    def place(self, req: PlaceRequest) -> Placement: ...
