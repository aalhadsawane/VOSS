"""The experiment pipeline's partition and sample (docs/REVISION_PLAN.md V6)."""

from __future__ import annotations

import pytest
from experiments.sweep import shard
from experiments.verify import sample


def test_shards_partition_the_run_list() -> None:
    parts = [shard(10, f"{i}/3") for i in range(3)]
    assert sorted(k for p in parts for k in p) == list(range(10))
    assert parts[0] == [0, 3, 6, 9]


def test_bad_shard_is_refused() -> None:
    with pytest.raises(ValueError):
        shard(10, "3/3")


def test_sample_is_deterministic_and_at_least_one() -> None:
    runs = [f"r{i:02d}" for i in range(25)]
    assert sample(runs, 0.1, 7) == sample(runs, 0.1, 7)
    assert len(sample(runs, 0.1, 7)) == 3
    assert len(sample(runs[:3], 0.1, 1)) == 1
