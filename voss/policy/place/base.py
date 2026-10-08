"""Placer interface (doc 05 §4): ``place(req) -> Placement``. All placers see the same candidates and cost matrix
(doc 03 §5.3); baselines without a cost matrix fall back to hard eligibility over the whole view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from voss.core.types import ClusterView, Invocation, Placement
from voss.policy.cost.components import CostMatrix
from voss.policy.place.candidates import eligible


@dataclass(frozen=True)
class PlaceRequest:
    """Invocations to place against one view at decision time ``now``."""

    invs: tuple[Invocation, ...]
    view: ClusterView
    now: float
    gen: np.random.Generator
    expiry_margin_s: float = 5.0
    cm: CostMatrix | None = None
    scores: np.ndarray | None = None  # [I, K] scalarized costs over cm.candidates
    slot_step: np.ndarray | None = None  # [I, K] cost added per extra invocation on the same worker

    def options(self, i: int) -> np.ndarray:
        """View indices of feasible candidates for invocation ``i`` (cost-matrix order when present)."""
        if self.cm is not None:
            c = self.cm.candidates[i]
            out: np.ndarray = c[self.cm.feasible[i]]
            return out
        return np.flatnonzero(eligible(self.view, self.invs[i], self.now, self.expiry_margin_s))


class Placer(Protocol):
    def place(self, req: PlaceRequest) -> Placement: ...


def placement(req: PlaceRequest, assign: dict[int, int]) -> Placement:
    """Build a ``Placement`` from ``{row: view index}``."""
    a = {req.invs[i].id: req.view.workers[j] for i, j in sorted(assign.items())}
    return Placement(a, status="ok" if len(a) == len(req.invs) else "partial")
