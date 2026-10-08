"""RNG stream independence (doc 01 §3)."""

from __future__ import annotations

import numpy as np
from voss.core.rng import RngFactory, stream


def test_same_inputs_same_sequence() -> None:
    a = stream(7, "x", 1, "k").random(100)
    b = stream(7, "x", 1, "k").random(100)
    assert np.array_equal(a, b)


def test_different_keys_differ() -> None:
    base = stream(7, "x", 1).random(100)
    for other in (stream(8, "x", 1), stream(7, "y", 1), stream(7, "x", 2), stream(7, "x", "1")):
        assert not np.array_equal(base, other.random(100))


def test_adding_a_consumer_does_not_perturb_others() -> None:
    rng = RngFactory(11)
    alone = rng.stream("workers").random(50)
    rng2 = RngFactory(11)
    _ = rng2.stream("new_component").random(10_000)
    assert np.array_equal(alone, rng2.stream("workers").random(50))


def test_streams_uncorrelated() -> None:
    a = stream(1, "a").standard_normal(20_000)
    b = stream(1, "b").standard_normal(20_000)
    assert abs(float(np.corrcoef(a, b)[0, 1])) < 0.03
