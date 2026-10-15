"""static_regions homing after a region's cluster dissolved (found by E06 seed 7 at paper scale: KeyError on join)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from voss.runtime.orchestrator import Orchestrator


class _Book:
    def __init__(self) -> None:
        self.clusters: dict[int, Any] = {}
        self.members = {7: SimpleNamespace(lat=50.0, lon=8.0)}
        self._next = 0

    def new_cluster(self) -> SimpleNamespace:
        c = SimpleNamespace(cid=self._next)
        self.clusters[c.cid] = c
        self._next += 1
        return c


def test_static_region_gets_a_fresh_cluster_after_its_cluster_dissolved() -> None:
    book = _Book()
    orch = SimpleNamespace(mode="static_regions", book=book, region_cluster={}, region_of=lambda lat, lon: "eu")
    first = Orchestrator._home(orch, 7)  # type: ignore[arg-type]
    assert Orchestrator._home(orch, 7) == first  # type: ignore[arg-type]  # a live cluster is reused
    del book.clusters[first]  # the region's last member left and the cluster was dissolved
    second = Orchestrator._home(orch, 7)  # type: ignore[arg-type]
    assert second != first and second in book.clusters
