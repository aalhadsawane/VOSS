"""Metrics of one run (docs/REVISION_PLAN.md V2, D-88). Every function takes logged tables as pandas frames.

Invocation classes follow the router's terminal row: ``ok`` within the deadline is *met*; ``ok`` after it is *late*;
``timeout`` and ``unfinished`` are *lost*; ``rejected`` is *rejected*. Only synchronous invocations (``slo_class`` 0)
that arrive after the warm-up count, unless a function says otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SYNC = 0
LOST = ("timeout", "unfinished")


def sync_after(inv: pd.DataFrame, warmup_s: float) -> pd.DataFrame:
    """Synchronous invocations that arrived at or after ``warmup_s``."""
    out: pd.DataFrame = inv[(inv.slo_class == SYNC) & (inv.t_arrive >= warmup_s)]
    return out


def classify(inv: pd.DataFrame) -> pd.Series:
    """``met``, ``late``, ``lost`` or ``rejected`` per invocation."""
    on_time = inv.e2e <= inv.deadline
    out = np.select(
        [(inv.outcome == "ok") & on_time, inv.outcome == "ok", inv.outcome.isin(LOST)],
        ["met", "late", "lost"],
        default="rejected",
    )
    return pd.Series(out, index=inv.index)


def deadline_met(inv: pd.DataFrame, warmup_s: float) -> float:
    """Share of synchronous invocations answered correctly within their deadline (the primary metric, G5)."""
    d = sync_after(inv, warmup_s)
    return float((classify(d) == "met").mean()) if len(d) else float("nan")


@dataclass(frozen=True)
class Censored:
    value: float  # the percentile
    censored: float  # share of invocations entered at their deadline because they were lost or rejected
    lower_bound: bool  # True when the percentile falls in the censored mass: the true value is at least this


def latency_censored(inv: pd.DataFrame, q: float, warmup_s: float) -> Censored:
    """Percentile ``q`` (0-1) of synchronous latency; lost and rejected invocations enter at their deadline."""
    d = sync_after(inv, warmup_s)
    if not len(d):
        return Censored(float("nan"), float("nan"), False)
    gone = ~d.outcome.eq("ok")
    lat = np.where(gone, d.deadline, d.e2e)
    share = float(gone.mean())
    return Censored(float(np.quantile(lat, q)), share, share > 1.0 - q)


def slowdown(inv: pd.DataFrame, warm_s: pd.Series, q: float, warmup_s: float) -> float:
    """Percentile ``q`` of response time / warm run time at the invocation's input size (``warm_s`` indexed by
    ``inv``); lost invocations enter at their deadline."""
    d = sync_after(inv, warmup_s)
    if not len(d):
        return float("nan")
    lat = np.where(d.outcome.eq("ok"), d.e2e, d.deadline)
    base = warm_s.reindex(d.inv).to_numpy(dtype=float)
    return float(np.quantile(lat / np.maximum(base, 1e-9), q))


@dataclass(frozen=True)
class Holders:
    mean: float  # time-averaged concurrent holders
    peak: int  # most holders at one time
    distinct: int  # distinct workers that held the key during the window
    releases_per_h: float
    distinct_per_version: float = 0.0  # mean over key versions of the distinct workers that received that version


def _intervals(events: pd.DataFrame, key: str, t_end: float) -> list[tuple[int, float, float]]:
    """(worker, start, end) of each holding of ``key``: a release opens it, the next drop on that worker closes it."""
    ev = events[(events.tenant == key) & events.kind.isin(("key_release", "key_dropped"))]
    open_at: dict[int, float] = {}
    out = []
    for r in ev.sort_values("t", kind="stable").itertuples():
        w = int(r.worker)
        if r.kind == "key_release":
            open_at.setdefault(w, float(r.t))
        elif w in open_at:
            out.append((w, open_at.pop(w), float(r.t)))
    out += [(w, t0, t_end) for w, t0 in sorted(open_at.items())]
    return out


def holders(events: pd.DataFrame, key: str, t0: float, t1: float) -> Holders:
    """Holder statistics of one key over ``[t0, t1)`` (D-88)."""
    iv = [(w, max(a, t0), min(b, t1)) for w, a, b in _intervals(events, key, t1) if b > t0 and a < t1]
    span = max(t1 - t0, 1e-9)
    mean = sum(b - a for _, a, b in iv) / span
    pts = sorted([(a, 1) for _, a, _ in iv] + [(b, -1) for _, _, b in iv])
    peak = cur = 0
    for _, step in pts:
        cur += step
        peak = max(peak, cur)
    rel = events[(events.kind == "key_release") & (events.tenant == key) & (events.t >= t0) & (events.t < t1)]
    per_version = rel.groupby("value").worker.nunique().mean() if "value" in rel and len(rel) else 0.0
    return Holders(mean, peak, len({w for w, _, _ in iv}), len(rel) / span * 3600.0, float(per_version))


def utilisation(samples: pd.DataFrame, t0: float) -> float:
    """Time-averaged busy concurrency over offered concurrency of attested workers, from ``t0`` on."""
    s = samples[samples.t >= t0]
    cap = float(s.capacity.sum())
    return float(s.busy.sum() / cap) if cap > 0 else float("nan")


def warm_memory_mb(cache: pd.DataFrame, t0: float) -> float:
    """Time-averaged MB held by warm sandboxes, from ``t0`` on."""
    c = cache[cache.t >= t0]
    return float(c.warm_mb.mean()) if len(c) else float("nan")


def episodes(inv: pd.DataFrame, warmup_s: float, window_s: float = 10.0, miss: float = 0.5) -> pd.DataFrame:
    """Intervals in which one function's synchronous deadline-miss rate over ``window_s`` exceeded ``miss``: one row
    per merged run of such windows with ``fn``, ``start``, ``end``, ``invocations`` and ``missed``."""
    d = sync_after(inv, warmup_s).assign(miss=lambda x: classify(x) != "met")
    d = d.assign(win=(d.t_arrive // window_s).astype(int))
    g = d.groupby(["fn", "win"]).agg(n=("miss", "size"), missed=("miss", "sum")).reset_index()
    bad = g[g.missed / g.n > miss].sort_values(["fn", "win"], kind="stable")
    rows = []
    for fn, b in bad.groupby("fn", sort=True):
        runs = (b.win.diff() != 1).cumsum()
        for _, r in b.groupby(runs):
            rows.append((fn, r.win.min() * window_s, (r.win.max() + 1) * window_s, int(r.n.sum()), int(r.missed.sum())))
    return pd.DataFrame(rows, columns=["fn", "start", "end", "invocations", "missed"])


def detection(events: pd.DataFrame) -> pd.DataFrame:
    """Per adversarial worker: first dropped result (``adv_omit``) and first suspicion; ``NaN`` delay = not detected.
    Suspicions of workers that never dropped anything are the false ejections."""
    adv = events[events.kind == "adv_omit"].groupby("worker").t.min()
    sus = events[events.kind == "worker_suspect"].groupby("worker").t.min()
    out = pd.DataFrame({"first_drop": adv}).join(sus.rename("suspected"), how="outer")
    out["delay"] = out.suspected - out.first_drop
    out["false_ejection"] = out.first_drop.isna()
    return out
