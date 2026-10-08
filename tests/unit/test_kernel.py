"""Kernel semantics and determinism (doc 01 §2, §3)."""

from __future__ import annotations

import pytest
from voss.core.kernel import Kernel
from voss.core.rng import RngFactory


def _trace(seed: int) -> list[tuple[float, int]]:
    k, rng = Kernel(), RngFactory(seed)
    out: list[tuple[float, int]] = []

    def fire(i: int, g_name: str) -> None:
        out.append((k.now, i))
        g = rng.stream(g_name, i, len(out))
        if k.now < 50:
            k.after(float(g.exponential(1.0)), fire, (i + 1) % 7, g_name)

    for i in range(7):
        k.at(0.0, fire, i, "trace")
    k.run(100.0)
    return out


def test_ties_break_by_insertion_order() -> None:
    k, seen = Kernel(), []
    for i in range(5):
        k.at(1.0, seen.append, i)
    k.run(2.0)
    assert seen == [0, 1, 2, 3, 4]
    assert k.now == 2.0


def test_cancel_and_past() -> None:
    k, seen = Kernel(), []
    h = k.after(1.0, seen.append, "x")
    k.after(2.0, seen.append, "y")
    k.cancel(h)
    k.run(3.0)
    assert seen == ["y"]
    with pytest.raises(ValueError):
        k.at(1.0, seen.append, "z")
    with pytest.raises(ValueError):
        k.after(-1.0, seen.append, "z")


def test_run_stops_at_until() -> None:
    k, seen = Kernel(), []
    k.at(5.0, seen.append, 1)
    k.run(4.0)
    assert seen == [] and k.now == 4.0
    k.run(5.0)
    assert seen == [1]


def test_kernel_determinism() -> None:
    assert _trace(3) == _trace(3)
    assert _trace(3) != _trace(4)
