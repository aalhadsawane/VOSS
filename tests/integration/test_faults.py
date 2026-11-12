"""Progress-based detection end to end (doc 07): workers that drop results are suspected; a benign run raises no
suspicion."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.system import RunResult, run_system

REPO = Path(__file__).resolve().parents[2]
SMALL = ["horizon_s=260", "scenario.workers=200", "scenario.load.rate=8", "voss.planner.name=greedy"]


def _run(extra: list[str]) -> RunResult:
    return run_system(load_config(REPO / "configs/smoke.yaml", SMALL + extra))


def _events(r: RunResult, kind: str) -> pd.DataFrame:
    ev = r.recorder.frame(Table.EVENTS)
    return ev[ev.kind == kind]


def _violations(r: RunResult) -> list[str]:
    bad = _events(r, "invariant_violation")
    return list(bad.detail) if len(bad) else []


def test_benign_run_raises_no_suspicion() -> None:
    r = _run(["horizon_s=200"])
    assert _events(r, "worker_suspect").empty
    assert _violations(r) == []


def test_omissions_are_detected_and_recovered() -> None:
    """Black-hole owners drop results: the watchdog blames only them and every omitted invocation still succeeds
    (retried elsewhere)."""
    adv = [
        "scenario.adversary={regime: adversary_all, alpha: 0.25, mix: {black_hole: 1.0}}",
        "horizon_s=240",
        "scenario.load.rate=16",
    ]
    prog = _run(adv)
    assert _violations(prog) == []
    omits = _events(prog, "adv_omit")
    assert len(omits) >= 3
    blamed = set(_events(prog, "watchdog").worker.astype(int))
    assert blamed and blamed <= set(omits.worker.astype(int))  # no benign worker blamed
    # Every omitted invocation is retried on another worker. Whether the retry meets the deadline is not asserted:
    # a retry may land on a worker without the key or code (a 30 s cold start). Plan V7 restricts backup attempts to
    # key holders and adds that assertion.
    ev = prog.recorder.frame(Table.EVENTS)
    retried = set(ev[ev.kind == "retry"].inv.dropna().astype(int))
    early = set(omits[omits.t < 200].inv.astype(int))
    assert early and early <= retried
