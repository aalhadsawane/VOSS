"""Emulation-versus-simulator comparison (plan V13, handoff Part E step 3): pairing, spread and disagreements.

Runs are synthetic: only the manifests (label, seed, scenario hash) and fake metric dicts are needed, so the pairing,
the spread and the report are tested without parquet tables or a real run.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from tools.emu.compare import (
    FLOOR,
    Cell,
    Run,
    cells,
    disagreements,
    emu_runs,
    pair_up,
    report_md,
    sim_runs,
    table_md,
)

HASH = "scn123"


def write_run(root: Path, rel: str, label: str, seed: int, scenario_hash: str = HASH) -> Path:
    d = root / rel
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps(
            {
                "seed": seed,
                "scenario_hash": scenario_hash,
                "config": {"label": label, "horizon_s": 7200.0, "scenario": {"warmup_s": 600.0}},
            }
        )
    )
    return d


def metrics(value: float) -> dict[str, float]:
    """Every metric the table shows, all at ``value`` except the holders, which are counts."""
    keys = list(FLOOR)
    return {
        "deadline_met": value,
        "success": 99.0,  # constant: only the deadline share varies between the two sides
        "holders_mean": 2.0,
        "holders_peak": 4.0,
        "p50_s": value / 1000.0,
        "p99_s": value / 500.0,
        "level_L0": 1.0,
        "level_L1": 0.0,
        "level_L2": 2.0,
        "level_L3": 97.0,
        **{k: 0.0 for k in keys if k not in ("deadline_met", "success")},
    }


def test_runs_are_found_and_keyed_by_system_and_seed(tmp_path: Path) -> None:
    write_run(tmp_path / "emu", "voss/rep1", "voss", 1)
    write_run(tmp_path / "emu", "voss/rep2", "voss", 2)
    write_run(tmp_path / "emu", "fixed_keepalive/rep1", "fixed_keepalive", 1)
    write_run(tmp_path / "sim", "runs/a", "voss", 1)
    write_run(tmp_path / "sim", "runs/b", "voss", 2)
    write_run(tmp_path / "sim", "runs/c", "", 3)  # no label: not a compared system
    e, s = emu_runs(tmp_path / "emu"), sim_runs(tmp_path / "sim")
    assert sorted(e) == [("fixed_keepalive", 1), ("voss", 1), ("voss", 2)]
    assert sorted(s) == [("voss", 1), ("voss", 2)]
    assert e[("voss", 1)].warmup_s == 600.0 and e[("voss", 1)].horizon_s == 7200.0


def test_pairs_match_on_label_and_seed(tmp_path: Path) -> None:
    e = {"voss": 1}
    emu = {("voss", 1): Run(tmp_path, "voss", 1, HASH, 600.0, 7200.0)}
    sim = {
        ("voss", 1): Run(tmp_path, "voss", 1, HASH, 600.0, 7200.0),
        ("voss", 2): Run(tmp_path, "voss", 2, HASH, 600.0, 7200.0),
    }
    pairs = pair_up(emu, sim, metrics_of=lambda r: metrics(95.0))
    assert len(pairs) == 1 and pairs[0].comparable and pairs[0].hash_ok
    assert pairs[0].seed == 1 and e == {"voss": 1}


def test_a_different_scenario_hash_is_never_averaged_in(tmp_path: Path) -> None:
    emu = {("voss", 1): Run(tmp_path, "voss", 1, HASH, 600.0, 7200.0)}
    sim = {("voss", 1): Run(tmp_path, "voss", 1, "other", 600.0, 7200.0)}
    pairs = pair_up(emu, sim, metrics_of=lambda r: metrics(95.0))
    assert not pairs[0].hash_ok and not pairs[0].comparable
    table = cells(pairs)
    assert table["voss"][0].emu_mean == 95.0
    assert np.isnan(table["voss"][0].sim_mean)  # no comparable simulator run
    dis = disagreements(pairs, table)
    assert any("scenario hashes differ" in d for d in dis)


def test_a_missing_simulator_run_is_stated(tmp_path: Path) -> None:
    emu = {("voss", 3): Run(tmp_path, "voss", 3, HASH, 600.0, 7200.0)}
    pairs = pair_up(emu, {}, metrics_of=lambda r: metrics(90.0))
    dis = disagreements(pairs, cells(pairs))
    assert dis == ["voss rep3: no simulator run with label 'voss' and seed 3."]


def test_spread_over_repetitions_and_a_real_disagreement(tmp_path: Path) -> None:
    emu = {("voss", i): Run(tmp_path / "emu", "voss", i, HASH, 600.0, 7200.0) for i in (1, 2, 3)}
    sim = {("voss", i): Run(tmp_path / "sim", "voss", i, HASH, 600.0, 7200.0) for i in (1, 2, 3)}
    emu_m = {1: metrics(95.0), 2: metrics(96.0), 3: metrics(94.0)}
    sim_m = {1: metrics(70.0), 2: metrics(71.0), 3: metrics(70.5)}
    pairs = pair_up(emu, sim, metrics_of=lambda r: emu_m[r.seed] if r.path.name == "emu" else sim_m[r.seed])
    table = cells(pairs)["voss"]
    met = next(c for c in table if c.metric == "deadline_met")
    assert met.emu_mean == pytest.approx(95.0) and met.emu_spread == pytest.approx(2.0)
    assert met.sim_mean == pytest.approx(70.5) and met.sim_spread == pytest.approx(1.0)
    assert met.diff == pytest.approx(-24.5) and not met.within_spread
    dis = disagreements(pairs, {"voss": table})
    assert len(dis) == 1 and "deadlines met" in dis[0] and "difference of -24.5%" in dis[0]


def test_a_difference_inside_the_spread_is_not_a_disagreement() -> None:
    cells_ = [Cell("deadline_met", 95.0, 2.0, 96.0, 1.5, 1.0)]
    assert cells_[0].within_spread
    assert not Cell("deadline_met", 95.0, 0.0, 99.0, 0.0, 4.0).within_spread
    assert Cell("p50_s", 0.05, 0.0, 0.052, 0.0, 0.002).within_spread  # below the floor: noise


def test_the_tables_say_what_the_handoff_asks_for(tmp_path: Path) -> None:
    emu = {("voss", 1): Run(tmp_path, "voss", 1, HASH, 600.0, 7200.0)}
    sim = {("voss", 1): Run(tmp_path, "voss", 1, HASH, 600.0, 7200.0)}
    pairs = pair_up(emu, sim, metrics_of=lambda r: metrics(95.0))
    table = cells(pairs)
    md = "\n".join(table_md(table, pairs))
    for word in ("deadlines met", "key holders", "start-up L3", "latency p99", "within spread"):
        assert word in md
    report = report_md(table, pairs, [], tmp_path / "emu", tmp_path / "sim")
    assert "## Disagreements larger than the spread" in report
    assert "none: every metric is inside the spread" in report
    assert "What is real and what is modelled" in report
