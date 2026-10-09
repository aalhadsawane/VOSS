"""P6: progress-based detection and succession end to end (doc 07): scheduler crash, black-hole, partition and
slowness are detected and failed over; black-hole workers are suspected; a benign run raises no suspicion."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.system import RunResult, run_system

REPO = Path(__file__).resolve().parents[2]
SMALL = ["horizon_s=260", "scenario.workers=200", "scenario.load.rate=8", "voss.planner.name=greedy"]
FAULTS = (
    "scenario.faults=[{t: 80, kind: sched_crash, target: 'cluster:0', duration_s: 60},"
    " {t: 120, kind: sched_blackhole, target: 'cluster:1', duration_s: 60},"
    " {t: 160, kind: sched_partition, target: 'cluster:2', duration_s: 40},"
    " {t: 205, kind: sched_slow, target: 'cluster:0', duration_s: 40, factor: 400}]"
)


def _run(extra: list[str]) -> RunResult:
    return run_system(load_config(REPO / "configs/smoke.yaml", SMALL + extra))


def _events(r: RunResult, kind: str) -> pd.DataFrame:
    ev = r.recorder.frame(Table.EVENTS)
    return ev[ev.kind == kind]


def _violations(r: RunResult) -> list[str]:
    bad = _events(r, "invariant_violation")
    return list(bad.detail) if len(bad) else []


@pytest.fixture(scope="module")
def faulty() -> RunResult:
    return _run([FAULTS])


@pytest.mark.parametrize(("kind", "bound_s"), [("sched_crash", 6), ("sched_blackhole", 15), ("sched_partition", 6)])
def test_scheduler_faults_are_detected_and_replaced(faulty: RunResult, kind: str, bound_s: float) -> None:
    start = _events(faulty, "fault_start")
    f = start[start.reason == kind].iloc[0]
    sus = _events(faulty, "scheduler_suspect")
    hit = sus[(sus.worker == f.worker) & (sus.t >= f.t) & (sus.t <= f.t + bound_s)]
    assert len(hit), f"{kind} not detected within {bound_s} s"
    app = _events(faulty, "appoint")
    assert ((app.cluster == f.cluster) & (app.t >= hit.t.iloc[0]) & (app.worker != f.worker)).any()


def test_slow_scheduler_hands_over(faulty: RunResult) -> None:
    start = _events(faulty, "fault_start")
    f = start[start.reason == "sched_slow"].iloc[0]
    sus = _events(faulty, "scheduler_suspect")
    hit = sus[(sus.worker == f.worker) & (sus.t >= f.t) & (sus.t <= f.t + 20)]
    assert len(hit) and hit.reason.iloc[0] == "decision_slo"


def test_partitioned_scheduler_self_fences_and_invariants_hold(faulty: RunResult) -> None:
    start = _events(faulty, "fault_start")
    f = start[start.reason == "sched_partition"].iloc[0]
    fence = _events(faulty, "self_fence")
    bound = 5.0 + 1.0 + 2.0  # lease from the last keepalive before the partition, logged when it next tries to act
    assert ((fence.worker == f.worker) & (fence.t >= f.t) & (fence.t <= f.t + bound)).any()
    assert _violations(faulty) == []
    assert len(_events(faulty, "checkpoint_restore")) >= 3


def test_benign_run_raises_no_suspicion() -> None:
    r = _run(["horizon_s=200"])
    assert _events(r, "scheduler_suspect").empty and _events(r, "worker_suspect").empty
    assert _violations(r) == []


def test_omissions_are_detected_and_recovered() -> None:
    """Black-hole owners drop results: the watchdog blames only them and every omitted invocation still succeeds
    (retried elsewhere); without progress detection the same omissions turn into timeouts."""
    adv = [
        "scenario.adversary={regime: adversary_all, alpha: 0.25, mix: {black_hole: 1.0}}",
        "horizon_s=240",
        "scenario.load.rate=16",
    ]
    prog = _run(adv)
    hb = _run([*adv, "voss.detection.mode=heartbeat_only"])
    assert _violations(prog) == [] and _violations(hb) == []
    omits = _events(prog, "adv_omit")
    assert len(omits) >= 3
    blamed = set(_events(prog, "watchdog").worker.astype(int))
    assert blamed and blamed <= set(omits.worker.astype(int))  # no benign worker blamed
    inv = prog.recorder.frame(Table.INVOCATIONS).set_index("inv")
    early = omits[omits.t < 200].inv.astype(int)
    assert (inv.loc[early, "outcome"] == "ok").all()
    inv_h = hb.recorder.frame(Table.INVOCATIONS)
    assert (inv.outcome == "ok").sum() > (inv_h.outcome == "ok").sum()
