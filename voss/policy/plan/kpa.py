"""``kpa`` provisioning baseline: the Knative Pod Autoscaler (concurrency mode) as published (docs/REVISION_PLAN.md V8).

Every tick (``voss.planner.T_plan``, Knative's 2 s) the observed number of in-flight requests of each function is
sampled. With the per-sandbox target ``t = container_concurrency × target_utilization``:

- stable desired = ``ceil(mean concurrency over the stable window / t)``; panic desired: the same over the panic
  window;
- both are bounded by the scale-up and scale-down rates relative to the sandboxes kept now;
- panic starts when panic desired ≥ ``panic_threshold`` × sandboxes kept, and ends one stable window after the
  condition last held; in panic the count never decreases;
- zero is reached only after the stable window and the scale-to-zero grace period without any request.

Defaults are Knative Serving's autoscaler defaults (``stable-window`` 60 s, ``panic-window-percentage`` 10,
``panic-threshold-percentage`` 200, ``container-concurrency-target-percentage`` 70, ``max-scale-down-rate`` 2,
``max-scale-up-rate`` 1000, ``scale-to-zero-grace-period`` 30 s) with ``containerConcurrency`` 1: a sandbox serves one
invocation at a time. # TODO verify against the Knative release cited in the paper.
Deviations (stated in ``configs/baselines.yaml``): sandboxes are placed on key holders first, then on the most reliable
eligible workers (Knative leaves placement to the Kubernetes scheduler); keys follow the sandboxes, within ``K``.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class KpaParams:
    stable_s: float = 60.0
    panic_s: float = 6.0
    panic_threshold: float = 2.0
    container_concurrency: float = 1.0
    target_utilization: float = 0.70
    max_scale_up_rate: float = 1000.0
    max_scale_down_rate: float = 2.0
    scale_to_zero_grace_s: float = 30.0

    @property
    def per_pod(self) -> float:
        return self.container_concurrency * self.target_utilization


@dataclass
class KpaState:
    """One function's autoscaler state."""

    samples: deque[tuple[float, float]] = field(default_factory=deque)  # (t, in-flight requests)
    ready: int = 0  # sandboxes kept now (the last decision)
    panic_since: float | None = None
    panic_last: float = -math.inf  # last tick at which the panic condition held
    panic_max: int = 0
    last_active: float = -math.inf

    def observe(self, now: float, inflight: float, keep_s: float) -> None:
        self.samples.append((now, float(inflight)))
        while self.samples and self.samples[0][0] < now - keep_s:
            self.samples.popleft()
        if inflight > 0:
            self.last_active = now

    def mean(self, now: float, window_s: float) -> float:
        xs = [c for t, c in self.samples if t > now - window_s]
        return sum(xs) / len(xs) if xs else 0.0


def decide(st: KpaState, now: float, p: KpaParams) -> int:
    """Desired sandboxes for one function at ``now`` (module docstring); updates the panic state and ``ready``."""
    ready = max(st.ready, 1)
    up, down = math.ceil(p.max_scale_up_rate * ready), math.floor(st.ready / p.max_scale_down_rate)
    stable = min(max(math.ceil(st.mean(now, p.stable_s) / p.per_pod), down), up)
    panic = min(max(math.ceil(st.mean(now, p.panic_s) / p.per_pod), down), up)
    if panic / ready >= p.panic_threshold:
        st.panic_last = now
        if st.panic_since is None:
            st.panic_since, st.panic_max = now, st.ready
    elif st.panic_since is not None and now - st.panic_last >= p.stable_s:
        st.panic_since = None
    want = stable
    if st.panic_since is not None:  # never scale down in panic
        want = max(panic, st.panic_max)
        st.panic_max = want
    if want == 0 and now - st.last_active < p.stable_s + p.scale_to_zero_grace_s:
        want = min(st.ready, 1) if st.ready else 0  # keep one until the grace period has passed
    st.ready = want
    return want


def place(units: int, order: list[int], room: list[int]) -> dict[int, int]:
    """Spread ``units`` sandboxes over workers in ``order`` (index into ``room``), one per worker per pass, while each
    worker has room: holders first keeps keys where they are."""
    out: dict[int, int] = {}
    left = units
    while left > 0:
        placed = False
        for j in order:
            if left == 0:
                break
            if out.get(j, 0) < room[j]:
                out[j] = out.get(j, 0) + 1
                left -= 1
                placed = True
        if not placed:
            break
    return out
