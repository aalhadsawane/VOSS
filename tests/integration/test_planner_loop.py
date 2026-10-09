"""P4: the slow loop runs, sends actions, workers confirm them, and invariants still hold."""

from __future__ import annotations

from pathlib import Path

import pytest
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.system import RunResult, run_system

REPO = Path(__file__).resolve().parents[2]
SMALL = ["horizon_s=240", "drain_s=10", "scenario.workers=120", "scenario.load.rate=8", "voss.planner.T_plan=30"]


@pytest.fixture(scope="module")
def result() -> RunResult:
    return run_system(load_config(REPO / "configs/smoke.yaml", SMALL))


def test_plans_logged_and_actions_sent(result: RunResult) -> None:
    plans = result.recorder.frame(Table.PLANS)
    assert len(plans) >= 5
    assert (plans.trust_pairs > 0).all() and (plans.actions >= 0).all()
    assert set(plans.status) <= {"optimal", "reused"} | {s for s in plans.status if ":" in s}
    msgs = result.recorder.frame(Table.MESSAGES).set_index("kind")
    assert msgs.loc["Prepare", "count"] > 0 and msgs.loc["Warm", "count"] > 0


def test_planned_trust_reduces_cold_starts(result: RunResult) -> None:
    inv = result.recorder.frame(Table.INVOCATIONS)
    late = inv[(inv.t_arrive > 120) & (inv.outcome == "ok")]
    assert late.trust_cold.mean() < 0.05


def test_invariants_hold_with_planner(result: RunResult) -> None:
    ev = result.recorder.frame(Table.EVENTS)
    viol = ev[ev.kind == "invariant_violation"]
    assert viol.empty, viol.detail.tolist()
