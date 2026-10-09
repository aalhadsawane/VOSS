"""P7 exit: receipts are complete and sound vs ground truth under scheduler faults and adversarial owners (doc 09 §3),
credits are settled within one settlement period (doc 09 §4), and reputation penalizes the identities that really
omitted results, not benign ones (doc 09 §2)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from voss.core.config import RunConfig, load_config
from voss.metrics.schema import Table
from voss.runtime.system import RunResult, run_system

REPO = Path(__file__).resolve().parents[2]
ARGS = [
    "horizon_s=300",
    "scenario.workers=200",
    "scenario.load.rate=10",
    "voss.planner.name=greedy",
    "voss.accounting.settle_s=30",
    "scenario.adversary={regime: adversary_all, alpha: 0.2, mix: {black_hole: 1, on_off: 1}}",
    "scenario.faults=[{t: 90, kind: sched_crash, target: 'cluster:0', duration_s: 40},"
    " {t: 150, kind: sched_partition, target: 'cluster:1', duration_s: 30}]",
]


def _cfg() -> RunConfig:
    return load_config(REPO / "configs/smoke.yaml", ARGS)


def _events(r: RunResult, kind: str) -> pd.DataFrame:
    ev = r.recorder.frame(Table.EVENTS)
    return ev[ev.kind == kind]


@pytest.fixture(scope="module")
def run() -> RunResult:
    return run_system(_cfg())


def test_receipts_match_ground_truth_under_faults(run: RunResult) -> None:
    bad = _events(run, "invariant_violation")
    assert bad.empty, list(bad.detail)[:5]
    assert len(_events(run, "adv_omit")) >= 3 and len(_events(run, "fault_start")) == 2
    rc = run.recorder.frame(Table.RECEIPTS)
    sent = _events(run, "result_sent")
    paid = rc[rc.status.isin(["ok", "duplicate"])]
    assert len(paid) <= len(sent) and len(paid) >= 0.99 * len(sent)
    assert (rc.status == "no_result").any()
    om = _events(run, "adv_omit")
    omitted = set(zip(om.inv.astype(int), om.worker.astype(int), strict=True))
    assert not omitted & set(zip(paid.inv.astype(int), paid.worker.astype(int), strict=True))  # no claim, no credit


def test_credits_settle_within_one_period(run: RunResult) -> None:
    st = _events(run, "settlement")
    assert len(st) >= 9
    cfg = _cfg()
    bound = cfg.voss.accounting.settle_s + cfg.voss.router.receipt_batch_s + 1.0
    assert float(st.lat_max.max()) <= bound
    rc = run.recorder.frame(Table.RECEIPTS)
    paid = rc[rc.status.isin(["ok", "duplicate"])]
    late = (paid.t_result - paid.t_arrive) > paid.deadline
    expected = float((paid.ref_work_units * np.where(late, cfg.voss.accounting.late_factor, 1.0)).sum())
    cr = run.recorder.frame(Table.CREDITS)
    assert float(cr[cr.kind.isin(["work", "duplicate"])].amount.sum()) == pytest.approx(expected, rel=1e-9)
    kinds = set(cr.kind)
    assert {"work", "sched_assign", "sched_active", "sched_standby", "cache"} <= kinds


def test_reputation_penalizes_omitters(run: RunResult) -> None:
    omitters = set(_events(run, "adv_omit").worker.astype(int))
    pen = _events(run, "rep_penalty")
    blamed = set(pen[pen.reason.isin(["change_point", "suspect"])].worker.astype(int))
    assert blamed and blamed <= omitters
    rep = run.recorder.frame(Table.REPUTATION)
    last = rep[rep.t == rep.t.max()].set_index("worker")
    beta = last.beta
    assert beta[beta.index.isin(omitters)].mean() > beta[~beta.index.isin(omitters)].mean()
