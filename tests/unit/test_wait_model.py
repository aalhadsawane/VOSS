"""Per-worker slot-wait estimate and sync-priority slot queue (D-77, C-46)."""

from __future__ import annotations

import pytest
from voss.core.config import RunConfig
from voss.policy.cost.wait import OVERDUE_FRAC, JobEst, expected_wait
from voss.world.resources import Slots


def test_idle_worker_has_no_wait() -> None:
    assert expected_wait(2, [], now=10.0, default_s=1.0) == 0.0


def test_free_slot_means_no_wait() -> None:
    assert expected_wait(2, [JobEst(9.0, 6.0)], now=10.0, default_s=1.0) == 0.0


def test_remaining_time_of_running_jobs() -> None:
    jobs = [JobEst(8.0, 6.0), JobEst(9.0, 6.0)]  # end at 14 and 15
    assert expected_wait(2, jobs, now=10.0, default_s=1.0) == pytest.approx(4.0)


def test_queued_long_jobs_count_their_own_length() -> None:
    jobs = [JobEst(8.0, 6.0), JobEst(9.0, 6.0), JobEst(9.5, 6.0)]  # third starts at 14, ends 20
    assert expected_wait(2, jobs, now=10.0, default_s=1.0) == pytest.approx(5.0)  # next free slot: 15


def test_long_queue_looks_long_unlike_the_scheduler_wide_mean() -> None:
    jobs = [JobEst(9.0, 6.0) for _ in range(6)]  # 3 slots: 3 run until 15, 3 queued until 21; new job starts at 15
    ewma = max(0, 6 - 3 + 1) * 1.0 / 3  # (busy+queued-slots+1)^+ * svc / slots with svc = 1 s
    assert expected_wait(3, jobs, now=10.0, default_s=1.0) == pytest.approx(11.0)
    assert ewma < 2.0


def test_overdue_job_holds_slot_for_a_fraction() -> None:
    assert expected_wait(1, [JobEst(0.0, 2.0)], now=10.0, default_s=1.0) == pytest.approx(OVERDUE_FRAC * 2.0)


def test_unknown_duration_uses_default() -> None:
    assert expected_wait(1, [JobEst(9.0, 0.0)], now=10.0, default_s=3.0) == pytest.approx(2.0)


def test_unseen_load_is_assumed_default_length() -> None:
    assert expected_wait(1, [], now=10.0, default_s=2.0, unseen=1) == pytest.approx(2.0)
    assert expected_wait(1, [], now=10.0, default_s=2.0, unseen=2) == pytest.approx(4.0)


def test_sync_priority_skips_queued_async() -> None:
    jobs = [JobEst(8.0, 6.0), JobEst(9.0, 6.0, False), JobEst(9.5, 6.0, False)]  # one slot: first runs until 14
    fifo = expected_wait(1, jobs, 10.0, 1.0, arrival_sync=True)
    prio = expected_wait(1, jobs, 10.0, 1.0, arrival_sync=True, sync_priority=True)
    assert fifo == pytest.approx(16.0) and prio == pytest.approx(4.0)
    assert expected_wait(1, jobs, 10.0, 1.0, arrival_sync=False, sync_priority=True) == pytest.approx(16.0)


def test_sync_priority_still_waits_behind_queued_sync() -> None:
    jobs = [JobEst(8.0, 6.0), JobEst(9.0, 2.0, True), JobEst(9.5, 6.0, False)]
    assert expected_wait(1, jobs, 10.0, 1.0, arrival_sync=True, sync_priority=True) == pytest.approx(6.0)


def _drain(s: Slots, order: list[str]) -> None:
    s.acquire(lambda _t: order.append("first"))
    for name, prio in (("a1", 1), ("s1", 0), ("f", 2), ("s2", 0), ("a2", 1)):
        s.acquire(lambda _t, n=name: order.append(n), prio)
    for _ in range(6):
        for t in sorted(s.held):
            s.release(t)


def test_slots_default_is_fifo() -> None:
    order: list[str] = []
    _drain(Slots(1), order)
    assert order == ["first", "a1", "s1", "f", "s2", "a2"]


def test_slots_sync_priority_is_stable_and_deterministic() -> None:
    runs = []
    for _ in range(2):
        order: list[str] = []
        _drain(Slots(1, priority=True), order)
        runs.append(order)
    assert runs[0] == runs[1] == ["first", "s1", "s2", "a1", "a2", "f"]


def test_slots_withdraw_waiting_with_priority() -> None:
    s = Slots(1, priority=True)
    order: list[str] = []
    s.acquire(lambda _t: order.append("x"))
    tok = s.acquire(lambda _t: order.append("gone"), 0)
    s.acquire(lambda _t: order.append("y"), 1)
    s.release(tok)
    s.release(0)
    assert order == ["x", "y"] and s.queued == 0


def test_defaults_do_not_change_config_hash() -> None:
    base = RunConfig().config_hash()
    assert RunConfig.model_validate({"voss": {"cost": {"wait_model": "per_worker"}}}).config_hash() != base
    assert RunConfig.model_validate({"voss": {"worker": {"sync_priority": True}}}).config_hash() != base
    assert RunConfig.model_validate({"voss": {"cost": {"wait_model": "ewma"}}}).config_hash() == base
