"""Cache value policies (doc 02 §6, doc 03 §4): what to keep, and where to fetch from.

- ``gdsf``: GreedyDual-Size-Frequency value density ``v = L + hits × start-up saved / size``; ``L`` (the inflation
  value) rises to each evicted entry's value so old popularity ages out. Optional per-artifact forecast hits (from
  plan actions) add to the observed frequency.
- ``lru``: last use time (baseline).
- ``source_score``: P2P source choice by RTT, transfer time over the source's uplink headroom, and disk tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from voss.core.registry import register

TIER_PENALTY_S = {"ram": 0.0, "ssd": 0.0, "hdd": 0.05}


@dataclass
class GdsfState:
    """Per-worker GDSF bookkeeping (lives with the cache; lost never: it is just a ranking)."""

    inflation: float = 0.0
    forecast: dict[str, float] = field(default_factory=dict)  # digest → predicted hits in horizon
    saved_s: dict[str, float] = field(default_factory=dict)  # digest → start-up seconds a hit saves


@register("cache_value", "gdsf")
def gdsf_value(state: GdsfState, digest: str, hits: int, size_mb: float, last_used: float) -> float:
    freq = hits + state.forecast.get(digest, 0.0)
    return state.inflation + freq * state.saved_s.get(digest, 1.0) / max(size_mb, 1e-3)


@register("cache_value", "lru")
def lru_value(state: GdsfState, digest: str, hits: int, size_mb: float, last_used: float) -> float:
    return last_used


def source_score(rtt_s: float, nbytes: float, uplink_bps: float, busy_uploads: int, tier: str) -> float:
    """Expected seconds to pull ``nbytes`` from a peer (lower is better)."""
    headroom = uplink_bps / (1 + busy_uploads)
    return rtt_s + nbytes * 8 / max(headroom, 1.0) + TIER_PENALTY_S.get(tier, 0.1)
