"""v2 metrics on hand-built tables (docs/REVISION_PLAN.md V2, D-88)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from experiments.analysis import metrics as m
from experiments.analysis.paired import holm, paired_diff, paired_ratio


def _inv() -> pd.DataFrame:
    rows = [  # inv, fn, slo, t_arrive, e2e, deadline, outcome
        (0, "f", 0, 5.0, 0.1, 1.0, "ok"),  # before warm-up: ignored
        (1, "f", 0, 20.0, 0.2, 1.0, "ok"),  # met
        (2, "f", 0, 21.0, 1.5, 1.0, "ok"),  # late
        (3, "f", 0, 22.0, 30.0, 1.0, "timeout"),  # lost
        (4, "f", 0, 23.0, 0.0, 1.0, "rejected"),
        (5, "g", 1, 24.0, 9.0, 60.0, "ok"),  # asynchronous: ignored
    ]
    df = pd.DataFrame(rows, columns=["inv", "fn", "slo_class", "t_arrive", "e2e", "deadline", "outcome"])
    return df


def test_classes_and_deadline_met() -> None:
    d = m.sync_after(_inv(), 10.0)
    assert list(m.classify(d)) == ["met", "late", "lost", "rejected"]
    assert m.deadline_met(_inv(), 10.0) == pytest.approx(0.25)


def test_censored_latency_flags_a_lower_bound() -> None:
    c = m.latency_censored(_inv(), 0.99, 10.0)
    assert c.censored == pytest.approx(0.5) and c.lower_bound
    assert c.value == pytest.approx(np.quantile([0.2, 1.5, 1.0, 1.0], 0.99))
    assert not m.latency_censored(_inv(), 0.4, 10.0).lower_bound


def test_slowdown_uses_warm_time_per_invocation() -> None:
    warm = pd.Series({1: 0.1, 2: 0.5, 3: 0.5, 4: 0.5})
    assert m.slowdown(_inv(), warm, 0.0, 10.0) == pytest.approx(2.0)  # 1.0 / 0.5 for the rejected one


def test_holders_from_release_and_drop_events() -> None:
    ev = pd.DataFrame(
        [
            (0.0, "key_release", 1, "t"),
            (10.0, "key_release", 2, "t"),
            (50.0, "key_dropped", 1, "t"),
            (60.0, "key_release", 1, "t"),
            (5.0, "key_release", 9, "other"),
        ],
        columns=["t", "kind", "worker", "tenant"],
    )
    h = m.holders(ev, "t", 0.0, 100.0)
    assert h.peak == 2 and h.distinct == 2
    assert h.mean == pytest.approx((50 + 90 + 40) / 100)
    assert h.releases_per_h == pytest.approx(3 / 100 * 3600)


def test_utilisation_and_warm_memory() -> None:
    s = pd.DataFrame({"t": [0.0, 10.0, 20.0], "busy": [9, 2, 6], "capacity": [10, 10, 10]})
    assert m.utilisation(s, 10.0) == pytest.approx(0.4)
    assert m.warm_memory_mb(pd.DataFrame({"t": [0.0, 30.0], "warm_mb": [100.0, 300.0]}), 1.0) == 300.0


def test_episodes_merge_consecutive_bad_windows() -> None:
    rows = [(i, "f", 0, t, e2e, 1.0, "ok") for i, (t, e2e) in enumerate([(1, 2), (11, 2), (12, 0.1), (25, 0.1)])]
    inv = pd.DataFrame(rows, columns=["inv", "fn", "slo_class", "t_arrive", "e2e", "deadline", "outcome"])
    ep = m.episodes(inv, 0.0, window_s=10.0, miss=0.4)
    assert ep.to_dict("records") == [{"fn": "f", "start": 0.0, "end": 20.0, "invocations": 3, "missed": 2}]


def test_detection_delay_and_false_ejections() -> None:
    ev = pd.DataFrame(
        [(10.0, "adv_omit", 1), (14.0, "worker_suspect", 1), (20.0, "adv_omit", 2), (30.0, "worker_suspect", 3)],
        columns=["t", "kind", "worker"],
    )
    d = m.detection(ev)
    assert d.loc[1, "delay"] == pytest.approx(4.0) and np.isnan(d.loc[2, "delay"])
    assert bool(d.loc[3, "false_ejection"]) and not bool(d.loc[1, "false_ejection"])


def test_paired_estimates_are_reproducible_and_bounded() -> None:
    a = pd.Series({s: 1.0 + 0.1 * s for s in range(10)})
    b = pd.Series({s: 0.8 + 0.1 * s for s in range(10)})
    d1, d2 = paired_diff(a, b, "x"), paired_diff(a, b, "x")
    assert d1 == d2 and d1.value == pytest.approx(-0.2) and d1.excludes(0.0)
    r = paired_ratio(a, b, "x")
    assert 0 < r.lo <= r.value <= r.hi < 1


def test_holm_step_down() -> None:
    assert holm({"a": 0.01, "b": 0.04, "c": 0.03}) == {"a": True, "c": False, "b": False}
    assert holm({"a": 0.001, "b": 0.02}) == {"a": True, "b": True}


def test_a_smoke_run_produces_every_metric() -> None:
    from pathlib import Path

    from experiments.analysis.summary import summarize
    from voss.core.config import load_config
    from voss.runtime.system import run_system

    repo = Path(__file__).resolve().parents[2]
    over = ["horizon_s=240", "scenario.workers=120", "scenario.load.rate=8", "voss.planner.name=greedy"]
    r = run_system(load_config(repo / "configs/smoke.yaml", over))
    s = summarize(r.recorder.frame, warmup_s=60.0, t_end=240.0)
    assert s["sync_invocations"] > 0 and 0.0 <= s["deadline_met"] <= 1.0
    assert s["p99_s"] > 0 and 0.0 < s["utilisation"] <= 1.0
    assert s["holders_mean"] > 0 and s["releases_per_h"] > 0
    assert s["attempts_per_inv"] > 0.9  # rejected and unfinished invocations have no attempt
    assert all(not (isinstance(v, float) and np.isnan(v)) for v in s.values()), s


def test_macros_use_two_significant_digits_and_reject_bad_names() -> None:
    from experiments.analysis.macros import render

    out = render({"DeadlineMet": 0.95123, "Holders": 12, "Workers": 1000.0, "Unit": "s"})
    assert "\\newcommand{\\VDeadlineMet}{0.95}" in out and "\\newcommand{\\VHolders}{12}" in out
    assert "\\newcommand{\\VWorkers}{1{,}000}" in out and "\\newcommand{\\VUnit}{s}" in out
    with pytest.raises(ValueError):
        render({"P99s2": 1.0})
    with pytest.raises(ValueError):
        render({"Bad": float("nan")})
