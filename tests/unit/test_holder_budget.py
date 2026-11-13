"""Holder budget K per function key (D-85, docs/REVISION_PLAN.md V4)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.policy.keys.budget import may_add_holder, truncate
from voss.runtime.system import run_system
from voss.world.workload import load_catalog

REPO = Path(__file__).resolve().parents[2]


def test_may_add_holder() -> None:
    assert may_add_holder(3, None) and may_add_holder(3, 0) and may_add_holder(1, 2)
    assert not may_add_holder(2, 2)


def test_truncate_keeps_existing_holders_then_most_reserved() -> None:
    y = np.array([[True, True, True, True], [True, False, True, False]])
    c = np.array([[1.0, 4.0, 3.0, 2.0], [1.0, 0.0, 1.0, 0.0]])
    prev = np.array([[False, False, False, True], [False, False, False, False]])
    out = truncate(y, c, prev, np.array([2, 0]))
    assert out[0].tolist() == [False, True, False, True]  # worker 3 already held it; then the largest c
    assert out[1].tolist() == [True, False, True, False]  # 0 = no budget


@settings(max_examples=50, deadline=None)
@given(st.integers(1, 5), st.integers(1, 6), st.integers(0, 2**31 - 1))
def test_truncate_never_exceeds_the_budget(k: int, n_t: int, seed: int) -> None:
    g = np.random.default_rng(seed)
    y = g.random((n_t, 12)) < 0.6
    out = truncate(y, g.random((n_t, 12)), g.random((n_t, 12)) < 0.3, np.full(n_t, k))
    assert (out.sum(axis=1) <= k).all() and not (out & ~y).any()


def test_every_function_is_its_own_key_domain() -> None:
    cfg = load_config(REPO / "configs/smoke.yaml", [])
    cat = load_catalog(cfg.scenario, cfg.calibration)
    assert len(cat.tenants) == len(cat.functions)
    for f in cat.functions:
        assert f.tenant == f"{f.owner}/{f.name}" and f.tenant in {t.id for t in cat.tenants}


def test_a_run_never_exceeds_the_budget_and_the_key_service_refuses() -> None:
    over = ["horizon_s=240", "scenario.workers=120", "scenario.load.rate=16", "voss.keys.max_holders=2"]
    r = run_system(load_config(REPO / "configs/smoke.yaml", over))
    ev = r.recorder.frame(Table.EVENTS)
    assert ev[ev.kind == "invariant_violation"].empty, list(ev[ev.kind == "invariant_violation"].detail)
    rel = ev[ev.kind == "key_release"]
    assert len(rel) and rel.groupby("tenant").worker.nunique().max() >= 2
    inv = r.recorder.frame(Table.INVOCATIONS)
    assert (inv.outcome == "ok").mean() > 0.5  # the budget limits holders, it does not stop the system


def test_holder_invariant_detects_a_violation() -> None:
    from voss.metrics.recorder import Recorder
    from voss.runtime.invariants import holders_within_budget

    rec = Recorder()
    for t, w in ((0.0, 1), (1.0, 2), (2.0, 3)):
        rec.log(Table.EVENTS, t=t, kind="key_release", worker=w, tenant="a/f", value=0.0)
    rec.log(Table.EVENTS, t=1.5, kind="key_dropped", worker=1, tenant="a/f", value=0.0)
    assert holders_within_budget(rec, {"a/f": 2}) == []
    rec.log(Table.EVENTS, t=3.0, kind="key_release", worker=4, tenant="a/f", value=0.0)
    assert holders_within_budget(rec, {"a/f": 2}) == ["key a/f: 3 holders > budget 2 at t=3.000"]
