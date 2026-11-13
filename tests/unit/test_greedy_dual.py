"""FaaSCache greedy-dual keep-alive on the warm-sandbox pool (Fuerst and Sharma, ASPLOS 2021; plan V8)."""

from __future__ import annotations

from voss.world.cache import WorkerCache


def _cache() -> WorkerCache:
    c = WorkerCache(ssd_mb=0, hdd_mb=0, mem_mb=1000)
    c.warm_policy = "greedy_dual"
    return c


def test_evicts_lowest_frequency_times_cost_per_size() -> None:
    c = _cache()
    for _ in range(5):
        c.park_warm("hot", 400, 0.0, cost_s=2.0, invoked=True)
        c.take_warm("hot")
    c.park_warm("hot", 400, 1.0, cost_s=2.0, invoked=True)  # priority 6 × 2 / 400
    c.park_warm("cold", 400, 2.0, cost_s=2.0, invoked=True)  # priority 1 × 2 / 400, idle for less time
    c.park_warm("new", 400, 3.0, cost_s=2.0, invoked=True)  # needs room: greedy-dual evicts "cold", not "hot"
    assert c.warm_count("hot") == 1 and c.warm_count("cold") == 0 and c.warm_count("new") == 1
    assert c.gd_clock == 1 * 2.0 / 400 and "cold" not in c.gd_freq  # clock rises; frequency reset


def test_lru_still_evicts_the_longest_idle() -> None:
    c = WorkerCache(ssd_mb=0, hdd_mb=0, mem_mb=1000)
    c.park_warm("a", 400, 0.0)
    c.park_warm("b", 400, 1.0)
    c.park_warm("c", 400, 2.0)
    assert c.warm_count("a") == 0 and c.warm_count("b") == 1
