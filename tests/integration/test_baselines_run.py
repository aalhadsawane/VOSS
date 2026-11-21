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
    inv = r.recorder.frame(Table.INVOCATIONS)
    assert (inv.outcome == "ok").mean() > 0.5  # hosts join and serve (trusted hosts once never got a certificate)


LONG = ["horizon_s=1000", "scenario.workers=120", "scenario.load.rate=8", "voss.keys.max_holders=2"]


@pytest.mark.parametrize(("group", "name"), CASES, ids=[f"{g}-{n}" for g, n in CASES])
def test_holder_budget_holds_across_certificate_requotes(group: str, name: str) -> None:
    """Guardrail 16 (equal budgets), development log iteration 3: K holders means at most K at every instant, for
    every system (provisioning and failure handling), also after session certificates were extended by re-quotes
    (900 s validity, re-quote every 600 s);
    the key service once freed a place at the expiry the certificate had at release."""
    from voss.runtime.invariants import holders_within_budget

    r = run_system(load_config(REPO / "configs/smoke.yaml", [*LONG, *PRESETS[group][name]["overrides"]]))
    keys = sorted(set(r.recorder.frame(Table.EVENTS).tenant.dropna()))
    assert holders_within_budget(r.recorder, dict.fromkeys(keys, 2)) == []
