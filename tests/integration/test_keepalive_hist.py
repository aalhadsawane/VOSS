"""Histogram keep-alive baseline end to end (doc 03 §7, D-77): the scheduler learns idle times, workers get
``KeepWarm`` directives, and the run stays correct next to the fixed-TTL baseline on the same seed."""

from __future__ import annotations

from pathlib import Path

import pytest
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.system import RunResult, run_system

REPO = Path(__file__).resolve().parents[2]
SMALL = ["horizon_s=300", "drain_s=10", "scenario.workers=120", "scenario.load.rate=8"]


def run(*extra: str) -> RunResult:
    return run_system(load_config(REPO / "configs/smoke.yaml", [*SMALL, *extra]))


@pytest.fixture(scope="module")
def ttl() -> RunResult:
    return run("voss.planner.name=keepalive_ttl")


@pytest.fixture(scope="module")
def hist() -> RunResult:
    return run("voss.planner.name=histogram_prewarm", "voss.keepalive_hist.min_samples=3")


def success(r: RunResult) -> float:
    inv = r.recorder.frame(Table.INVOCATIONS)
    return float((inv.outcome == "ok").mean())


def test_directives_sent_only_by_the_histogram_system(ttl: RunResult, hist: RunResult) -> None:
    assert "KeepWarm" not in ttl.recorder.frame(Table.MESSAGES).set_index("kind").index
    assert hist.recorder.frame(Table.MESSAGES).set_index("kind").loc["KeepWarm", "count"] > 0


def test_histogram_system_serves_like_the_ttl_baseline(ttl: RunResult, hist: RunResult) -> None:
    assert success(hist) >= success(ttl) - 0.01
    assert hist.recorder.frame(Table.CACHE).warm_mb.mean() <= ttl.recorder.frame(Table.CACHE).warm_mb.mean()


def test_invariants_hold(hist: RunResult) -> None:
    ev = hist.recorder.frame(Table.EVENTS)
    assert ev[ev.kind == "invariant_violation"].empty
