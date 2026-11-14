"""The hetero provisioning policy and its ablations run end to end within the holder budget (plan §11, V5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.system import run_system

REPO = Path(__file__).resolve().parents[2]
BASE = ["horizon_s=200", "scenario.workers=100", "scenario.load.rate=10", "voss.planner.name=hetero"]


@pytest.mark.parametrize("ablate", ["[]", "[homogeneous]", "[binary]", "[reliability_blind]"])
def test_hetero_runs_clean_within_the_budget(ablate: str) -> None:
    over = [*BASE, "voss.keys.max_holders=3", f"voss.planner.ablate={ablate}"]
    r = run_system(load_config(REPO / "configs/smoke.yaml", over))
    ev = r.recorder.frame(Table.EVENTS)
    assert ev[ev.kind == "invariant_violation"].empty, list(ev[ev.kind == "invariant_violation"].detail)
    plans = r.recorder.frame(Table.PLANS)
    assert len(plans) and (plans.planner == "hetero").any()
    inv = r.recorder.frame(Table.INVOCATIONS)
    assert (inv.outcome == "ok").mean() > 0.8


def test_deadline_probability_of_no_workers_is_empty() -> None:
    """A planning tick with no candidate workers (all traced hosts away) must not fail (V9 traced smoke)."""
    import numpy as np
    from voss.runtime.schedlib.hetero_inputs import _phi

    assert _phi(np.zeros(0)).shape == (0,) and _phi(np.zeros(2)).tolist() == [0.5, 0.5]
