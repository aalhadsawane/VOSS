"""Detector profiles and their timers (docs/REVISION_PLAN.md V7.1-V7.2)."""

from __future__ import annotations

import numpy as np
import pytest
from voss.core.config import DetectionConfig
from voss.policy.detect import detector, fits
from voss.policy.omission import BetaCusum, PriorOnly

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


def test_watchdog_quantile_uses_the_scheduler_round_trip_and_the_input_arrival() -> None:
    """Development log iteration 2: the timer runs from the dispatch at the scheduler to the outcome there, so its
    network is the scheduler-worker round trip, and execution cannot start before the input arrives from the router;
    mean and budget stay the router's."""
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
    router = _timing(cm, 0, 0, 0.95)
    assert router.q == float(comp.quantile(0.95)[0, 0])
    far = _timing(cm, 0, 0, 0.95, span=(0.17, 0.0))  # scheduler round trip 0.17 s, input already there
    late_input = _timing(cm, 0, 0, 0.95, span=(0.17, 0.06))  # input arrives 0.06 s after the dispatch is received
    assert far.q > router.q + 0.1 and late_input.q > far.q + 0.03
    assert far.mean == late_input.mean == router.mean and far.budget == router.budget


def test_ablation_profiles_of_r06() -> None:
    """D-128: backups off keeps VOSS's timer and ejection; drop estimate off keeps the prior for every worker."""
    full, ablated = detector("voss", DetectionConfig(), 3), detector("voss_no_backup", DetectionConfig(), 3)
    assert ablated.on_expiry == "probe" and full.on_expiry == "backup"
    assert (ablated.timer, ablated.streak, ablated.change_point) == (full.timer, full.streak, full.change_point)
    off, on = PriorOnly(), BetaCusum()
    for _ in range(50):
        assert off.update(7, True, 0.0) is None
        on.update(7, True, 0.0)
    assert float(off.p_omit(np.array([7]))[0]) == float(BetaCusum().p_omit(np.array([7]))[0])
    assert float(on.p_omit(np.array([7]))[0]) > float(off.p_omit(np.array([7]))[0])
