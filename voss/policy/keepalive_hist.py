"""Hybrid-histogram keep-alive policy of Azure Functions (doc 03 §7, D-77; Shahrad et al., "Serverless in the Wild",
USENIX ATC 2020). Pure and simulator-free: idle times in, windows out.

Per function the policy keeps a histogram of the idle times of its sandbox instances (how long a parked sandbox waits
until it is used again: with several sandboxes per function an inter-arrival gap would be about 0). The pre-warm
window is a low percentile of the histogram shortened by a margin; the keep-alive window is a high percentile
lengthened by the margin, measured from the moment the sandbox is re-loaded. With too few samples, too many
out-of-range idle times, or a histogram whose bin counts are too flat (coefficient of variation at or below a
threshold), the policy falls back to a fixed keep-alive TTL. Differences from the paper: no ARIMA model for
out-of-range idle times (they trigger the fallback), one histogram per function (the paper uses one per application),
and unloading only when the function's pool would otherwise be empty.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class HistParams:
    """Policy parameters (``core.config.KeepaliveHistConfig``). tag: literature for percentiles, margin, CV."""

    bin_s: float = 60.0
    range_s: float = 14400.0
    head_pct: float = 5.0  # TODO verify
    tail_pct: float = 99.0  # TODO verify
    margin: float = 0.10  # TODO verify
    min_samples: int = 10
    cv_min: float = 2.0  # TODO verify
    oob_max: float = 0.2
    fallback_ttl_s: float = 600.0

    @property
    def n_bins(self) -> int:
        return max(1, math.ceil(self.range_s / self.bin_s))


@dataclass(frozen=True)
class Windows:
    """What to do after an invocation ends: unload and re-load after ``prewarm_s`` (0: stay loaded), then keep the
    sandbox for ``keepalive_s``. ``fallback`` marks the fixed-TTL path."""

    prewarm_s: float
    keepalive_s: float
    fallback: bool

    def keep_loaded(self) -> Windows:
        """Same total lifetime, but no unload (other sandboxes of the function exist, so the pool never empties)."""
        return Windows(0.0, self.prewarm_s + self.keepalive_s, self.fallback)


@dataclass
class IdleHistogram:
    """Counts of idle times in fixed-width bins, plus the number beyond the range."""

    p: HistParams
    counts: list[int] = field(default_factory=list)
    oob: int = 0

    def __post_init__(self) -> None:
        if not self.counts:
            self.counts = [0] * self.p.n_bins

    @property
    def n(self) -> int:
        """Samples in range."""
        return sum(self.counts)

    def add(self, idle_s: float) -> None:
        b = int(max(0.0, idle_s) // self.p.bin_s)
        if b >= len(self.counts):
            self.oob += 1
        else:
            self.counts[b] += 1

    def percentile_bin(self, pct: float) -> int:
        """Index of the bin holding the ``pct``-th percentile of the in-range samples (smallest bin whose cumulative
        count reaches ``pct`` %)."""
        need = pct / 100.0 * self.n
        cum = 0
        for i, c in enumerate(self.counts):
            cum += c
            if cum >= need and cum > 0:
                return i
        return len(self.counts) - 1

    def cv(self) -> float:
        """Coefficient of variation of the bin counts (the paper's 'representative' test)."""
        k = len(self.counts)
        mean = self.n / k
        if mean == 0:
            return 0.0
        var = sum((c - mean) ** 2 for c in self.counts) / k
        return math.sqrt(var) / mean


def windows(h: IdleHistogram) -> Windows:
    """Histogram to windows (see module docstring); the fallback is a plain TTL with no unloading."""
    p = h.p
    fallback = Windows(0.0, p.fallback_ttl_s, True)
    total = h.n + h.oob
    if h.n < p.min_samples or h.oob > p.oob_max * total or h.cv() <= p.cv_min:
        return fallback
    head = h.percentile_bin(p.head_pct) * p.bin_s  # lower edge of the head bin
    tail = (h.percentile_bin(p.tail_pct) + 1) * p.bin_s  # upper edge of the tail bin
    prewarm = head * (1.0 - p.margin)
    if prewarm < p.bin_s:  # head in the first bin: the paper does not unload
        prewarm = 0.0
    keepalive = tail * (1.0 + p.margin) - prewarm
    return Windows(prewarm, keepalive, False)


def pick_holder(candidates: list[tuple[int, float]], prefer: int) -> int | None:
    """Worker for a re-warm among current key holders ``(worker, free_mb)``: the original worker if it still holds
    the key and has memory, else the holder with the most free memory (lowest id on ties)."""
    free = {w: m for w, m in candidates if m > 0}
    if prefer in free:
        return prefer
    return min(free, key=lambda w: (-free[w], w)) if free else None


class IdleTracker:
    """Per-function learner over sandbox instances. The scheduler mirrors each worker's LIFO warm stack: ``end``
    parks a sandbox (remembering when), ``dispatch`` takes the most recently parked one and records how long it sat
    idle. ``pending`` holds the due time of each function's scheduled re-warm."""

    def __init__(self, params: HistParams) -> None:
        self.p = params
        self.hist: dict[str, IdleHistogram] = {}
        self.parked: dict[str, dict[int, list[float]]] = {}
        self.pending: dict[str, float] = {}

    def _stack(self, fn: str, worker: int) -> list[float]:
        return self.parked.setdefault(fn, {}).setdefault(worker, [])

    def idle_count(self, fn: str) -> int:
        return sum(len(v) for v in self.parked.get(fn, {}).values())

    def dispatch(self, fn: str, worker: int, now: float) -> None:
        """A request for ``fn`` goes to ``worker``: it takes that worker's most recently parked sandbox, if any."""
        st = self._stack(fn, worker)
        while st and now - st[0] > self.p.range_s:
            st.pop(0)  # long gone: expired or evicted, not an idle sample
        if st:
            self.hist.setdefault(fn, IdleHistogram(self.p)).add(now - st.pop())
        self.pending.pop(fn, None)  # a request is being served: any scheduled re-warm is moot

    def loaded(self, fn: str, worker: int, now: float) -> None:
        self._stack(fn, worker).append(now)

    def end(self, fn: str, worker: int, now: float, others_busy: bool) -> Windows:
        """An invocation finished on ``worker``; return the windows for its sandbox."""
        self.loaded(fn, worker, now)
        h = self.hist.get(fn)
        w = windows(h) if h is not None else Windows(0.0, self.p.fallback_ttl_s, True)
        if self.idle_count(fn) > 1 or others_busy:
            return w.keep_loaded()
        if w.prewarm_s > 0:
            self._stack(fn, worker).pop()  # unloaded now, re-loaded by ``loaded`` at the pre-warm time
        return w
