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


def test_after_progress_waits_for_the_deadline_and_at_least_one_probe_timeout() -> None:
    """A late attempt that answers 'running' is not probed again at once (plan V10: probe storm at 10,000 workers)."""
    from voss.core.config import DetectionConfig
    from voss.policy.detect import detector

    d = detector("voss", DetectionConfig(), 3)
    expiry = d.expiry_s(t_dispatch=0.0, q_completion=1.0, t_deadline=5.0, now=3.0)
    assert expiry == 0.0  # the completion quantile has passed
    assert d.after_progress_s(expiry, t_deadline=5.0, now=3.0, probe_timeout_s=2.0) == 2.0
    assert d.after_progress_s(expiry, t_deadline=30.0, now=3.0, probe_timeout_s=2.0) == 27.0
    assert d.after_progress_s(expiry, t_deadline=2.0, now=3.0, probe_timeout_s=2.0) == 2.0  # past the deadline


def test_watchdog_quantile_uses_the_scheduler_round_trip() -> None:
    """Development log iteration 2: the timer runs from the dispatch at the scheduler to the outcome there, so its
    quantile adds the scheduler-worker round trip in place of the router's; mean and budget stay the router's."""
    import numpy as np
    from voss.policy.cost.components import CostMatrix, completion_of
    from voss.runtime.schedlib.decide import _timing

    one = np.ones((1, 1))
    tts, net, ex, var = 0.02 * one, 0.05 * one, 0.10 * one, 0.001 * one
    comp = completion_of(tts, net, ex, var)
    cm = CostMatrix(
        {"tts": tts, "net": net, "exec": ex, "exec_var": var},
        np.array([[0]]),
        np.ones((1, 1), bool),
        comp,
        np.zeros((1, 1)),
        np.full((1, 1), 1.0),
    )
    same = _timing(cm, 0, 0, 0.95)
    far = _timing(cm, 0, 0, 0.95, relay=0.12)
    assert same.q == float(comp.quantile(0.95)[0, 0])
    assert far.q > same.q + 0.1 and far.mean == same.mean and far.budget == same.budget
