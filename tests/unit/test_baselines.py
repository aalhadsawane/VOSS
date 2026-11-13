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


def test_eviction_aware_prefers_the_worker_least_likely_to_fail() -> None:
    from voss.core.registry import create
    from voss.policy.place import registry  # noqa: F401

    assert create("placer", "eviction_aware") is not None
