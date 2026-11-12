"""Under random adversarial owners (black-hole and on-off workers) and seeds, every invocation has exactly one
terminal row, latency components still sum, and keys are never used without a release (doc 05 §7, doc 07)."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.system import run_system

REPO = Path(__file__).resolve().parents[2]
BASE = ["horizon_s=200", "scenario.workers=150", "scenario.load.rate=8", "voss.planner.name=greedy", "drain_s=40"]


@settings(max_examples=6, deadline=None)
@given(alpha=st.sampled_from([0.0, 0.15, 0.3]), seed=st.integers(1, 50))
def test_invariants_hold_under_random_owner_faults(alpha: float, seed: int) -> None:
    adv = f"scenario.adversary={{regime: adversary_all, alpha: {alpha}, mix: {{black_hole: 1, on_off: 1}}}}"
    cfg = load_config(REPO / "configs/smoke.yaml", [*BASE, adv, f"seed={seed}"])
    ev = run_system(cfg).recorder.frame(Table.EVENTS)
    bad = ev[ev.kind == "invariant_violation"]
    assert bad.empty, list(bad.detail)[:5]
