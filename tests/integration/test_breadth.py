"""P8 end to end: every substrate profile and both reference clouds run with invariants intact; a sweep records
failures instead of aborting, writes its index, and a registered figure renders from it with run provenance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from experiments import sweep as sweep_mod
from experiments.analysis import lib
from experiments.figures import FigureSpec, render
from experiments.figures.p8 import e19_ablations
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.system import run_system

REPO = Path(__file__).resolve().parents[2]
TINY = ["horizon_s=150", "scenario.workers=120", "scenario.load.rate=4", "voss.planner.name=greedy"]


def _violations(cfg_over: list[str]) -> tuple[list[str], float]:
    r = run_system(load_config(REPO / "configs/smoke.yaml", [*TINY, *cfg_over]))
    ev, inv = r.recorder.frame(Table.EVENTS), r.recorder.frame(Table.INVOCATIONS)
    bad = ev[ev.kind == "invariant_violation"] if len(ev) else ev
    return (list(bad.detail) if len(bad) else []), float((inv.outcome == "ok").mean())


@pytest.mark.parametrize("sub", ["none", "appliance_tpm", "drtm_hv", "cvm_snp", "coco_pool"])
def test_every_substrate_runs(sub: str) -> None:
    bad, ok = _violations([f"scenario.substrate_mix={{{sub}: 1.0}}"])
    assert bad == [] and ok > 0.6  # `none` cannot serve tenants with an assurance floor


@pytest.mark.parametrize("ref", ["ref_lambda_like", "ref_azure_like"])
def test_reference_clouds_run(ref: str) -> None:
    bad, ok = _violations(["system=reference_cloud", f"reference={ref}"])
    assert bad == [] and ok > 0.95


def test_sweep_index_and_figure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = {
        "experiment": "TINY",
        "base": str(REPO / "configs/smoke.yaml"),
        "overrides": TINY,
        "systems": {"voss_full": [], "no_hdd": ["voss.cache.hdd_tier=false"], "broken": ["voss.placer.sync=nope"]},
        "seeds": [1],
        "report": {"keys": ["label"], "baseline": "voss_full", "metrics": ["p99_sync", "success"]},
    }
    path = tmp_path / "TINY.yaml"
    path.write_text(yaml.safe_dump(spec))
    monkeypatch.setattr(sweep_mod, "spec_path", lambda exp: path)
    monkeypatch.setattr(lib, "spec", lambda exp: spec)
    df = sweep_mod.sweep("TINY", jobs=1, out_root=tmp_path / "runs")
    assert dict(zip(df.label, df.status, strict=True)) == {"broken": "failed", "no_hdd": "ok", "voss_full": "ok"}
    assert "nope" in df[df.label == "broken"].error.iloc[0]
    again = sweep_mod.sweep("TINY", jobs=1, out_root=tmp_path / "runs")
    assert set(again[again.label != "broken"].status) == {"cached"}
    out = render(FigureSpec("tiny", "TINY", ("p99_sync", "success", "exposure"), e19_ablations), tmp_path / "runs",
                 tmp_path / "figs")  # fmt: skip
    assert out is not None and out.exists() and out.stat().st_size > 0
    side = json.loads(out.with_suffix(".json").read_text())
    assert len(side["runs"]) == 2 and all(r["result_hash"] for r in side["runs"])
    assert lib.report("TINY", lib.collect("TINY", tmp_path / "runs")).count("no_hdd") == 2
