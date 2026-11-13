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


ADV = ["scenario.adversary={regime: adversary_all, alpha: 0.25, mix: {black_hole: 1.0}}", "horizon_s=240"]


def test_omissions_are_detected_and_recovered_by_backups() -> None:
    """Black-hole owners drop results (plan V7 exit): the watchdog blames only them, and an omitted invocation whose
    backup ran on an honest holder in another failure domain succeeds; at least one meets its deadline that way."""
    prog = _run([*ADV, "scenario.load.rate=16"])
    assert _violations(prog) == []  # includes: non-idempotent invocations are never duplicated
    omits = _events(prog, "adv_omit")
    bad = set(omits.worker.astype(int))
    assert len(omits) >= 3
    blamed = set(_events(prog, "watchdog").worker.astype(int))
    assert blamed and blamed <= bad  # no honest worker blamed
    att = prog.recorder.frame(Table.ATTEMPTS)
    rescue = att[(att.kind == "backup") & att.inv.isin(set(omits.inv.astype(int))) & ~att.worker.isin(bad)]
    inv = prog.recorder.frame(Table.INVOCATIONS).set_index("inv").loc[sorted(set(rescue.inv))]
    assert len(inv) >= 3 and (inv.outcome == "ok").all()
    assert (inv.e2e <= inv.deadline).sum() >= 1


def test_baseline_detectors_retry_only_when_the_deadline_still_fits() -> None:
    """``fixed`` and ``consecutive`` presume the attempt lost at the deadline; a retry then never fits, so the
    invocation is reported missed at once (``abandoned``) instead of being started cold (plan V7.1). Non-idempotent
    invocations are never retried and fail at their deadline."""
    for det in ("fixed", "consecutive"):
        r = _run([*ADV, "scenario.load.rate=8", f"voss.detection.detector={det}"])
        assert _violations(r) == []
        att = r.recorder.frame(Table.ATTEMPTS)
        assert (att.kind != "backup").all()
        inv = r.recorder.frame(Table.INVOCATIONS).set_index("inv")
        omitted = inv.loc[sorted(set(_events(r, "adv_omit").inv.astype(int)))]
        due = omitted[(omitted.t_arrive + omitted.deadline < 235.0) & omitted.idempotent.astype(bool)]
        assert len(due) and (due.outcome == "abandoned").all()
        suspects = _events(r, "worker_suspect")
        assert suspects.empty if det == "fixed" else len(suspects) > 0
