"""Baselines as published (docs/REVISION_PLAN.md V8): each rule against its source, and every preset is a valid run."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml
from voss.core.config import DetectionConfig, KeepaliveHistConfig, load_config
from voss.policy.detect import HEDGE_MIN_SAMPLES, detector
from voss.policy.keepalive_hist import HistParams

REPO = Path(__file__).resolve().parents[2]
PRESETS = yaml.safe_load((REPO / "configs/baselines.yaml").read_text())


def test_histogram_parameters_are_the_published_ones() -> None:
    for p in (HistParams(), KeepaliveHistConfig()):
        assert (p.bin_s, p.range_s, p.head_pct, p.tail_pct, p.margin) == (60.0, 14400.0, 5.0, 99.0, 0.10)


def test_hedged_timer_is_the_observed_p95() -> None:
    d = detector("hedged", DetectionConfig(), 3)
    lat = list(np.linspace(0.1, 2.0, 100))
    assert d.expiry_s(5.0, 0.4, 60.0, 5.0, lat) == pytest.approx(float(np.quantile(lat, 0.95)))
    assert d.expiry_s(5.0, 0.4, 60.0, 5.0, lat[: HEDGE_MIN_SAMPLES - 1]) == pytest.approx(55.0)  # too few: deadline
    assert d.backup_scope == "any" and not d.probe and d.streak == 0


@pytest.mark.parametrize(("group", "name"), [(g, n) for g in sorted(PRESETS) for n in sorted(PRESETS[g])], ids=str)
def test_every_preset_is_a_valid_config(group: str, name: str) -> None:
    entry = PRESETS[group][name]
    assert entry["source"] and isinstance(entry["deviations"], list)
    load_config(REPO / "configs/smoke.yaml", list(entry["overrides"]))


def test_min_worker_set_is_algorithm_1_of_the_harvest_paper() -> None:
    """Zhang et al. SOSP 2021 §5.2: the set grows clockwise from the home worker until its slots reach u_f, and the
    invocation goes to the least loaded worker of the set."""
    from voss.policy.place.baselines.eviction_aware import ring_position, worker_set

    workers = np.arange(10, 20)
    slots = np.full(10, 2)
    one = worker_set("f", workers, slots, 0.5)
    assert len(one) == 1  # light function: its home worker only
    pos = sorted((ring_position(f"worker:{w}"), i) for i, w in enumerate(workers))
    after = [i for p, i in pos if p >= ring_position("fn:f")] + [i for p, i in pos if p < ring_position("fn:f")]
    assert list(worker_set("f", workers, slots, 5.0)) == after[:3]  # 3 workers x 2 slots >= 5
    assert len(worker_set("f", workers, slots, 100.0)) == 10  # more than the pool: every worker (JSQ)
    rest = workers[workers != workers[one[0]]]
    assert worker_set("f", rest, np.full(9, 2), 0.5)[0] == list(rest).index(workers[after[1]])  # consistent hashing
    busy_home = slots.copy()
    busy_home[after[0]] = 0  # the home worker has no usable resources left: the set grows past it
    assert list(worker_set("f", workers, busy_home, 0.5)) == after[:2]
    assert list(worker_set("f", workers, slots, 0.0)) == after[:1]
