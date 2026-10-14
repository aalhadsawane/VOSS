"""SeBS 50x.graph-mst: python-igraph on a Barabási-Albert graph (10,000 vertices per input unit)."""

from __future__ import annotations

import igraph


def make_input(size_kb: int) -> igraph.Graph:
    return igraph.Graph.Barabasi(10_000 * size_kb, 10)


def handler(g: igraph.Graph) -> int:
    return len(g.spanning_tree(None, False))  # return_tree=False gives the list of tree edge ids
