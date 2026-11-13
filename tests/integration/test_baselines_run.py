"""Every baseline preset runs on the smoke pool without an invariant violation, the holder budget included
(docs/REVISION_PLAN.md V8 exit)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.system import run_system

REPO = Path(__file__).resolve().parents[2]
PRESETS = yaml.safe_load((REPO / "configs/baselines.yaml").read_text())
SMALL = ["horizon_s=150", "scenario.workers=120", "scenario.load.rate=8", "voss.keys.max_holders=4"]
CASES = [(g, n) for g in sorted(PRESETS) for n in sorted(PRESETS[g])]


@pytest.mark.parametrize(("group", "name"), CASES, ids=[f"{g}-{n}" for g, n in CASES])
def test_preset_runs_clean(group: str, name: str) -> None:
    r = run_system(load_config(REPO / "configs/smoke.yaml", [*SMALL, *PRESETS[group][name]["overrides"]]))
    ev = r.recorder.frame(Table.EVENTS)
    bad = ev[ev.kind == "invariant_violation"] if "kind" in ev else ev
    assert bad.empty, list(bad.detail)[:5]
    assert len(r.recorder.frame(Table.INVOCATIONS)) > 0
