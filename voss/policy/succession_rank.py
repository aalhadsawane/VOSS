"""Scheduler succession ranking (doc 07 §3). P2 uses ``speed × assurance`` with ties by worker id; P6 adds
survival, centrality and failure-domain diversity."""

from __future__ import annotations

from collections.abc import Mapping

from voss.core.ids import WorkerId


def rank(
    candidates: Mapping[WorkerId, tuple[float, float]], exclude: frozenset[WorkerId] = frozenset()
) -> list[WorkerId]:
    """``candidates[w] = (speed, assurance)``; best first."""
    pool = [w for w in candidates if w not in exclude]
    return sorted(pool, key=lambda w: (-candidates[w][0] * candidates[w][1], w))
