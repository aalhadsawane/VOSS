"""SeBS 50x.graph-pagerank: python-igraph on a Barabási-Albert graph (10,000 vertices per input unit)."""

from __future__ import annotations

import igraph


def make_input(size_kb: int) -> igraph.Graph:
    return igraph.Graph.Barabasi(10_000 * size_kb, 10)


def handler(g: igraph.Graph) -> float:
    return float(max(g.pagerank()))
