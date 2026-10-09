"""P6 exit: under random fault schedules (scheduler crashes, black holes, partitions, slowness, plus black-hole
workers) no dispatch is accepted under a stale epoch, no invocation is lost, every invocation has exactly one
terminal row, latency components still sum, and keys are never used without a release (doc 05 §7, doc 07)."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.system import run_system
from voss.world.scenario import FAULT_KINDS

REPO = Path(__file__).resolve().parents[2]
BASE = ["horizon_s=200", "scenario.workers=150", "scenario.load.rate=8", "voss.planner.name=greedy", "drain_s=40"]

fault = st.fixed_dictionaries(
    {
        "t": st.floats(30.0, 150.0).map(lambda x: round(x, 1)),
        "kind": st.sampled_from(FAULT_KINDS),
        "target": st.integers(0, 3).map(lambda k: f"cluster:{k}"),
        "duration_s": st.floats(5.0, 60.0).map(lambda x: round(x, 1)),
        "factor": st.sampled_from([5.0, 400.0]),
    }
)


def _yaml(faults: list[dict[str, object]]) -> str:
    items = ", ".join(
        f"{{t: {f['t']}, kind: {f['kind']}, target: '{f['target']}', duration_s: {f['duration_s']}, "
        f"factor: {f['factor']}}}"
        for f in faults
    )
    return f"scenario.faults=[{items}]"


@settings(max_examples=6, deadline=None)
@given(faults=st.lists(fault, min_size=1, max_size=3), alpha=st.sampled_from([0.0, 0.15]), seed=st.integers(1, 50))
def test_invariants_hold_under_random_faults(faults: list[dict[str, object]], alpha: float, seed: int) -> None:
    adv = f"scenario.adversary={{regime: adversary_all, alpha: {alpha}, mix: {{black_hole: 1, on_off: 1}}}}"
    cfg = load_config(REPO / "configs/smoke.yaml", [*BASE, _yaml(faults), adv, f"seed={seed}"])
    r = run_system(cfg)
    ev = r.recorder.frame(Table.EVENTS)
    bad = ev[ev.kind == "invariant_violation"]
    assert bad.empty, list(bad.detail)[:5]
    started = ev[ev.kind == "fault_start"]
    assert len(started) <= len(faults)
