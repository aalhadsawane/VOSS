"""Scheduler succession ranking (doc 07 §3): the product of per-candidate factors (speed, assurance, centrality,
remaining session ...), best first, ties by worker id."""

from __future__ import annotations

import math
from collections.abc import Mapping

from voss.core.ids import WorkerId


def rank(
    candidates: Mapping[WorkerId, tuple[float, ...]], exclude: frozenset[WorkerId] = frozenset()
) -> list[WorkerId]:
    """``candidates[w]`` = multiplicative factors (e.g. speed, assurance, centrality, survival); best first."""
    pool = [w for w in candidates if w not in exclude]
    return sorted(pool, key=lambda w: (-math.prod(candidates[w]), w))
