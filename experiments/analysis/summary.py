"""One row of metrics per run (docs/REVISION_PLAN.md V2, V6): what the sweep writes to ``summary.parquet``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from experiments.analysis import metrics as m

Frame = Callable[[str], pd.DataFrame]


def summarize(frame: Frame, warmup_s: float, t_end: float) -> dict[str, Any]:
    """Metrics of one run; ``frame(table)`` returns a logged table (``Recorder.frame`` or a Parquet reader)."""
    inv, ev = frame("invocations"), frame("events")
    p99 = m.latency_censored(inv, 0.99, warmup_s)
    keys = sorted(set(ev.tenant.dropna())) if "tenant" in ev else []
    hold = [m.holders(ev, k, warmup_s, t_end) for k in keys]
    ep = m.episodes(inv, warmup_s)
    att = frame("attempts")
    return {
        "deadline_met": m.deadline_met(inv, warmup_s),
        "p50_s": m.latency_censored(inv, 0.50, warmup_s).value,
        "p99_s": p99.value,
        "p99_lower_bound": p99.lower_bound,
        "censored": p99.censored,
        "utilisation": m.utilisation(frame("samples"), warmup_s),
        "warm_mb": m.warm_memory_mb(frame("cache"), warmup_s),
        "holders_mean": float(np.mean([h.mean for h in hold])) if hold else 0.0,
        "holders_peak": max((h.peak for h in hold), default=0),
        "holders_distinct": int(sum(h.distinct for h in hold)),
        "releases_per_h": float(sum(h.releases_per_h for h in hold)),
        "distinct_per_version": float(np.mean([h.distinct_per_version for h in hold])) if hold else 0.0,
        "episodes": len(ep),
        "episode_s": float((ep.end - ep.start).sum()) if len(ep) else 0.0,
        "attempts_per_inv": len(att) / max(1, len(inv)),
        "sync_invocations": len(m.sync_after(inv, warmup_s)),
    }
