"""Detector profiles and their timers (docs/REVISION_PLAN.md V7.1-V7.2)."""

from __future__ import annotations

import pytest
from voss.core.config import DetectionConfig
from voss.policy.detect import detector, fits

DC = DetectionConfig()


def test_voss_timer_is_the_predicted_quantile_without_a_floor() -> None:
    d = detector("voss", DC, 3)
    assert d.expiry_s(t_dispatch=10.0, q_completion=0.4, t_deadline=11.0, now=10.1) == pytest.approx(0.3)
    assert d.on_expiry == "backup" and d.change_point and d.max_attempts == 3


@pytest.mark.parametrize("name", ["fixed", "consecutive"])
def test_baseline_timers_are_the_deadline(name: str) -> None:
    d = detector(name, DC, 3)
    assert d.expiry_s(10.0, 0.4, 11.0, 10.1) == pytest.approx(0.9)
    assert d.on_expiry == "retry" and d.max_attempts == 2 and not d.change_point


def test_ejection_rules() -> None:
    assert detector("fixed", DC, 3).streak == 0
    c = detector("consecutive", DC, 3)
    assert (c.streak, c.eject_s) == (5, 30.0)
    with pytest.raises(KeyError):
        detector("nope", DC, 3)


def test_fit_rule() -> None:
    assert fits(0.5, 0.6) and not fits(0.7, 0.6)
