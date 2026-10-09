"""Plan diff and actions (doc 03 §4.4) and cache value policies (doc 02 §6)."""

from __future__ import annotations

import numpy as np
from voss.core.ids import FnId, TenantId, WorkerId
from voss.policy.cache_value import GdsfState, gdsf_value, lru_value, source_score
from voss.policy.plan.diff import diff, rate_limit
from voss.policy.plan.types import Plan
from voss.world.cache import WorkerCache

T, F, W = (TenantId("a"), TenantId("b")), (FnId("fa"), FnId("fb")), (WorkerId(1), WorkerId(2), WorkerId(3))
FN_TENANT = {"fa": "a", "fb": "b"}


def plan(y: list[list[int]], s: list[list[int]], w: list[list[int]]) -> Plan:
    return Plan(T, F, W, np.array(y, bool), np.array(s, bool), np.array(w, int), np.zeros((2, 3)), 60.0)


def test_diff_produces_idempotent_actions() -> None:
    prev = plan([[1, 0, 0], [0, 1, 0]], [[0, 0, 0], [0, 0, 0]], [[0, 0, 0], [0, 0, 0]])
    new = plan([[1, 1, 0], [0, 0, 0]], [[0, 1, 0], [0, 0, 0]], [[1, 0, 0], [0, 0, 0]])
    acts = diff(prev, new, FN_TENANT, {"fa": 5.0, "fb": 1.0})
    kinds = [(a.kind, int(a.worker), str(a.tenant)) for a in acts]
    assert kinds[0] == ("RELEASE", 2, "b")  # releases first
    assert ("PREPARE", 2, "a") in kinds and ("PIN_SNAPSHOT", 2, "a") in kinds and ("WARM", 1, "a") in kinds
    assert not diff(new, new, FN_TENANT, {})  # no change → no actions


def test_rate_limit_keeps_releases() -> None:
    new = plan([[1, 1, 1], [1, 1, 1]], [[0] * 3] * 2, [[0] * 3] * 2)
    acts = diff(None, new, FN_TENANT, {}) + diff(new, plan([[0] * 3] * 2, [[0] * 3] * 2, [[0] * 3] * 2), FN_TENANT, {})
    out = rate_limit(acts, per_worker=1)
    assert sum(a.kind == "PREPARE" for a in out) == 3 and sum(a.kind == "RELEASE" for a in out) == 6


def test_gdsf_prefers_dense_value_and_ages() -> None:
    st = GdsfState(saved_s={"big": 2.0, "small": 2.0})
    assert gdsf_value(st, "small", 3, 10.0, 0.0) > gdsf_value(st, "big", 3, 500.0, 0.0)
    st.inflation = 7.0
    assert gdsf_value(st, "big", 0, 500.0, 0.0) == 7.0
    assert lru_value(st, "x", 0, 1.0, 42.0) == 42.0
    c = WorkerCache(ssd_mb=100, hdd_mb=0, mem_mb=0, hdd_tier=False)
    c.value = lambda e: gdsf_value(st, e.digest, e.hits, e.size_mb, e.last_used)
    c.insert("hot", "bundle", 50, now=0)
    for t in range(5):
        c.touch("hot", now=float(t))
    c.insert("cold", "bundle", 50, now=10)
    c.insert("new", "bundle", 50, now=11)  # evicts the low-density "cold", keeps "hot" despite older use
    assert c.tier_of("hot") == "ssd" and c.tier_of("cold") is None


def test_warm_pins_survive_ttl_and_pressure() -> None:
    c = WorkerCache(ssd_mb=0, hdd_mb=0, mem_mb=300, hdd_tier=False)
    c.warm_pins["f"] = 1
    c.park_warm("f", 128, now=0)
    assert c.expire_warm(now=10_000, ttl=60) == 0
    c.park_warm("g", 128, now=1)
    assert not c.park_warm("h", 128, now=2) or c.warm_count("f") == 1  # f is never the victim
    assert c.warm_count("f") == 1


def test_source_score_orders_peers() -> None:
    near_fast = source_score(0.01, 50e6, 100e6, 0, "ssd")
    far_busy = source_score(0.1, 50e6, 100e6, 3, "hdd")
    assert near_fast < far_busy
