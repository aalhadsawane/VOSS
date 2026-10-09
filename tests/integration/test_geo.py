"""P5: geo hierarchy end to end: several clusters, routing across them, bounded moves, invariants per mode."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.system import RunResult, run_system

REPO = Path(__file__).resolve().parents[2]
SMALL = [
    "horizon_s=300",
    "drain_s=10",
    "scenario.workers=240",
    "scenario.load.rate=8",
    "voss.planner.name=greedy",
    "voss.clusters.target_size=15",
    "voss.clusters.min_size=5",
    "voss.clusters.max_size=30",
]


def _run(extra: list[str]) -> RunResult:
    return run_system(load_config(REPO / "configs/smoke.yaml", SMALL + extra))


@pytest.fixture(scope="module")
def dynamic() -> RunResult:
    return _run([])


def _violations(r: RunResult) -> list[str]:
    ev = r.recorder.frame(Table.EVENTS)
    bad = ev[ev.kind == "invariant_violation"]
    return list(bad.detail) if len(bad) else []


def test_several_clusters_serve_traffic(dynamic: RunResult) -> None:
    inv = dynamic.recorder.frame(Table.INVOCATIONS)
    ok = inv[inv.outcome == "ok"]
    assert ok.cluster.nunique() >= 3
    assert len(ok) / len(inv) > 0.95
    ev = dynamic.recorder.frame(Table.EVENTS)
    assert ev[ev.kind == "appoint"].cluster.nunique() >= 3


def test_moves_bounded_and_invariants_hold(dynamic: RunResult) -> None:
    assert _violations(dynamic) == []
    ev = dynamic.recorder.frame(Table.EVENTS)
    moves = ev[ev.kind == "move"]
    if len(moves):
        assert moves.groupby("worker").size().max() <= 3  # max_moves_per_h, horizon < 1 h


def test_nearby_cluster_wins(dynamic: RunResult) -> None:
    """Most sync invocations run in a cluster closer than the median cluster (routing uses geography)."""
    inv = dynamic.recorder.frame(Table.INVOCATIONS)
    ok = inv[(inv.outcome == "ok") & (inv.slo_class == 0)]
    assert np.median(ok.net_in) < 0.25


@pytest.mark.parametrize("mode", ["none_global", "static_regions", "static_kmeans"])
def test_baseline_modes_run_clean(mode: str) -> None:
    r = _run([f"voss.clusters.mode={mode}", "horizon_s=180"])
    assert _violations(r) == []
    inv = r.recorder.frame(Table.INVOCATIONS)
    assert (inv.outcome == "ok").mean() > 0.9
    if mode == "none_global":
        assert inv[inv.outcome == "ok"].cluster.nunique() == 1
