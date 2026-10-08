"""P2 exit: attested execution end to end on a small scenario (invariants, components, trust, determinism)."""

from __future__ import annotations

from pathlib import Path

import pytest
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.invariants import COMPONENTS
from voss.runtime.system import RunResult, run_system

REPO = Path(__file__).resolve().parents[2]
SMALL = ["horizon_s=240", "drain_s=10", "scenario.workers=150", "scenario.load.rate=8"]


@pytest.fixture(scope="module")
def result() -> RunResult:
    return run_system(load_config(REPO / "configs/smoke.yaml", SMALL))


def test_invariants_hold(result: RunResult) -> None:
    ev = result.recorder.frame(Table.EVENTS)
    viol = ev[ev.kind == "invariant_violation"]
    assert viol.empty, viol.detail.tolist()


def test_invocations_complete_and_components_sum(result: RunResult) -> None:
    inv = result.recorder.frame(Table.INVOCATIONS)
    ok = inv[inv.outcome == "ok"]
    assert len(ok) / len(inv) > 0.9
    total = ok[list(COMPONENTS)].sum(axis=1)
    assert (abs(total - ok.e2e) < 1e-6).all()
    assert set(ok.start_level) >= {"L0", "L3"}


def test_trust_cold_vs_warm_visible(result: RunResult) -> None:
    ok = result.recorder.frame(Table.INVOCATIONS).query("outcome == 'ok'")
    cold, warm = ok[ok.trust_cold], ok[~ok.trust_cold]
    assert len(cold) > 0 and len(warm) > 0
    assert (cold.trust > 0).all() and (warm.trust == 0).all()
    assert cold.trust.median() > 0.01


def test_attestation_and_appointment(result: RunResult) -> None:
    ev = result.recorder.frame(Table.EVENTS)
    assert (ev.kind == "session_attested").sum() > 10
    assert (ev.kind == "appoint").sum() >= 1
    assert (ev.kind == "key_release").sum() > 0
    rc = result.recorder.frame(Table.RECEIPTS)
    assert len(rc) >= (result.recorder.frame(Table.INVOCATIONS).outcome == "ok").sum()


def test_deterministic_rerun(result: RunResult) -> None:
    again = run_system(load_config(REPO / "configs/smoke.yaml", SMALL))
    assert again.recorder.result_hash() == result.recorder.result_hash()
    assert again.scenario_hash == result.scenario_hash
