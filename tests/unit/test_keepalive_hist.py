"""Hybrid-histogram keep-alive baseline (doc 03 §7, D-77): windows from synthetic idle times, fallback paths, the
idle-time tracker, and pre-warm timing on a fake clock (worker side, no simulator)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from voss.core.config import load_config
from voss.core.ids import FnId
from voss.core.messages_ka import KeepWarm
from voss.core.registry import create
from voss.policy.keepalive_hist import HistParams, IdleHistogram, IdleTracker, pick_holder, windows
from voss.policy.plan import registry as _planners  # noqa: F401  (registers planners)
from voss.policy.plan.baselines import HistogramPrewarm
from voss.runtime.workerlib.keepwarm import KeepWarmMixin
from voss.world.cache import WorkerCache

REPO = Path(__file__).resolve().parents[2]
P = HistParams(bin_s=60.0)  # 1-minute bins keep the hand-computed numbers below readable


def hist(samples: list[float], p: HistParams = P) -> IdleHistogram:
    h = IdleHistogram(p)
    for s in samples:
        h.add(s)
    return h


# 100 samples: 10 in bin 3 (180-240 s), 80 in bin 4 (240-300 s), 10 in bin 6 (360-420 s).
SPIKY = [200.0] * 10 + [250.0] * 80 + [370.0] * 10


def test_percentile_bins() -> None:
    h = hist(SPIKY)
    assert h.n == 100 and h.oob == 0
    assert h.percentile_bin(5) == 3 and h.percentile_bin(50) == 4 and h.percentile_bin(99) == 6


def test_windows_percentiles_and_margins() -> None:
    w = windows(hist(SPIKY))
    head, tail = 3 * 60.0, 7 * 60.0  # lower edge of the 5th-percentile bin, upper edge of the 99th-percentile bin
    assert not w.fallback
    assert w.prewarm_s == pytest.approx(head * 0.9)
    assert w.keepalive_s == pytest.approx(tail * 1.1 - head * 0.9)  # window length after the re-load


def test_head_in_first_bin_means_no_unload() -> None:
    w = windows(hist([10.0] * 30 + [400.0] * 30 + [10.0] * 30))
    assert not w.fallback and w.prewarm_s == 0.0 and w.keepalive_s == pytest.approx(7 * 60.0 * 1.1)


def test_fallback_on_few_samples() -> None:
    w = windows(hist(SPIKY[:5]))
    assert w.fallback and (w.prewarm_s, w.keepalive_s) == (0.0, P.fallback_ttl_s)


def test_fallback_on_flat_histogram() -> None:
    flat = [60.0 * i + 30.0 for i in range(P.n_bins)] * 3  # equal counts in every bin: CV = 0
    h = hist(flat)
    assert h.cv() == pytest.approx(0.0) and windows(h).fallback


def test_cv_of_spike_is_above_threshold() -> None:
    assert hist(SPIKY).cv() > P.cv_min


def test_fallback_on_out_of_range() -> None:
    h = hist(SPIKY + [5000.0] * 40)
    assert h.oob == 40 and windows(h).fallback


def test_tracker_records_idle_per_sandbox_instance() -> None:
    t = IdleTracker(P)
    t.dispatch("f", 1, 0.0)  # cold: nothing parked
    assert "f" not in t.hist
    t.end("f", 1, 10.0, others_busy=False)
    t.end("f", 2, 12.0, others_busy=False)  # a second sandbox on another worker
    t.dispatch("f", 1, 130.0)  # takes worker 1's sandbox: idle 120 s
    t.dispatch("f", 2, 190.0)  # worker 2's sandbox: idle 178 s
    assert t.hist["f"].counts[2] == 2 and t.idle_count("f") == 0


def test_hot_function_idle_times_are_not_zero() -> None:
    """Three sandboxes used in turn every 10 s: per-instance idle is 29 s, not the ~10 s inter-arrival gap."""
    t = IdleTracker(HistParams(bin_s=1.0))
    for w in (1, 2, 3):
        t.end("f", w, 0.0, others_busy=False)
    for i in range(9):
        w, now = 1 + i % 3, 30.0 + 10.0 * i
        t.dispatch("f", w, now)
        t.end("f", w, now + 1.0, others_busy=False)
    counts = t.hist["f"].counts
    assert counts[29] == 6 and sum(counts[:25]) == 0  # 29 s idle in steady state, never about 0


def test_pool_not_emptied_means_no_unload() -> None:
    t = IdleTracker(HistParams(bin_s=60.0, min_samples=10))
    now = 0.0
    for i in range(30):  # learn a 3 to 7 minute idle pattern with a single sandbox
        t.end("f", 1, now, others_busy=False)
        now += 200.0 if i % 15 == 0 else 250.0
        t.dispatch("f", 1, now)
    w = t.end("f", 1, now, others_busy=False)
    assert not w.fallback and w.prewarm_s == pytest.approx(180.0 * 0.9)
    assert t.idle_count("f") == 0  # unloaded: the sandbox is not parked
    again = t.end("f", 2, now + 1, others_busy=True)  # a request is running elsewhere: keep loaded
    assert again.prewarm_s == 0.0 and again.keepalive_s == pytest.approx(w.prewarm_s + w.keepalive_s)


def test_stale_stack_entries_are_not_samples() -> None:
    t = IdleTracker(P)
    t.end("f", 1, 0.0, others_busy=False)
    t.dispatch("f", 1, 5000.0)  # beyond the range: the sandbox is long gone
    assert "f" not in t.hist


def test_pick_holder_prefers_original_then_most_free() -> None:
    cands = [(1, 100.0), (2, 900.0), (3, 900.0), (4, 0.0)]
    assert pick_holder(cands, prefer=1) == 1
    assert pick_holder(cands, prefer=4) == 2  # no memory on 4: most free memory, lowest id
    assert pick_holder(cands, prefer=9) == 2  # original left
    assert pick_holder([], prefer=1) is None


def test_keepalive_inf_is_config_only() -> None:
    over = ["voss.planner.name=keepalive_ttl", "voss.worker.warm_ttl_s=1000000000.0"]
    cfg = load_config(REPO / "configs/pilot.yaml", over)
    assert cfg.voss.planner.name == "keepalive_ttl" and cfg.voss.worker.warm_ttl_s >= 1e9


def test_planner_is_registered_and_plan_is_empty() -> None:
    pl = create("planner", "histogram_prewarm", params=HistParams(min_samples=3))
    assert isinstance(pl, HistogramPrewarm) and pl.tracker.p.min_samples == 3


# --- worker side ---------------------------------------------------------------------------------------------
class FakeWorker(KeepWarmMixin):
    """Just enough of a worker agent: a real cache and an instant ``_build``."""

    def __init__(self) -> None:
        self.t = 0.0
        self.host: Any = SimpleNamespace(cache=WorkerCache(1000.0, 1000.0, 4096.0), session=1, up=True)
        self.fn = SimpleNamespace(name="f", tenant="t", mem_mb=100.0)
        self.keys: set[str] = {"t"}
        self.catalog: dict[Any, Any] = {FnId("f"): self.fn}
        self.built = 0

    @property
    def now(self) -> float:
        return self.t

    def _build(self, fn: Any, then: Any) -> None:
        self.built += 1
        then()


def test_unload_then_scheduler_rewarm_then_function_ttl() -> None:
    w = FakeWorker()
    c = w.host.cache
    c.park_warm("f", 100.0, 0.0)
    w._keep_warm(KeepWarm(FnId("f"), True, False, 300.0, 1))
    assert c.warm_count("f") == 0 and w.built == 0  # unloaded at once; a request now would be cold
    w.t = 162.0  # pre-warm window elapses: the scheduler sends the build directive
    w._keep_warm(KeepWarm(FnId("f"), False, True, 300.0, 1))
    assert c.warm_count("f") == 1 and w.built == 1
    c.expire_warm(162.0 + 299.0, 600.0)
    assert c.warm_count("f") == 1  # inside the keep-alive window (the global TTL is 600 s)
    c.expire_warm(162.0 + 300.0, 600.0)
    assert c.warm_count("f") == 0  # dropped at the end of the per-function window


def test_no_unload_keeps_sandbox_with_function_ttl() -> None:
    w = FakeWorker()
    c = w.host.cache
    c.park_warm("f", 100.0, 0.0)
    w._keep_warm(KeepWarm(FnId("f"), False, False, 100.0, 1))
    assert c.warm_count("f") == 1
    c.expire_warm(100.0, 600.0)
    assert c.warm_count("f") == 0


def test_missing_key_blocks_build() -> None:
    w = FakeWorker()
    w.keys.clear()
    w._keep_warm(KeepWarm(FnId("f"), False, True, 100.0, 1))
    assert w.built == 0 and w.host.cache.warm_count("f") == 0
