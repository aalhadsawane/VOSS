"""Incremental per-worker job index (D-77, D-114): same order and values as the old scan, no full scan per decision."""

from __future__ import annotations

from voss.core.ids import InvId, WorkerId
from voss.policy.cost.wait import JobEst
from voss.runtime.schedlib.inflight import Copy, JobIndex


def test_jobs_are_ordered_by_time_then_invocation_and_attempt() -> None:
    idx, w = JobIndex(), WorkerId(3)
    idx.add(w, InvId(2), 0, JobEst(5.0, 1.0, True))
    idx.add(w, InvId(1), 1, JobEst(5.0, 2.0, False))
    idx.add(w, InvId(1), 0, JobEst(5.0, 3.0, True))
    idx.add(w, InvId(3), 0, JobEst(6.0, 4.0, False))
    assert [j.dur_s for j in idx[w]] == [3.0, 2.0, 1.0, 4.0]


def test_drop_and_drop_all_remove_only_their_jobs() -> None:
    idx, w = JobIndex(), WorkerId(1)
    idx.add(w, InvId(1), 0, JobEst(1.0, 1.0, True))
    idx.add(w, InvId(1), 1, JobEst(1.0, 2.0, True))
    idx.add(w, InvId(2), 0, JobEst(2.0, 3.0, False))
    idx.drop(w, InvId(1), 0)
    assert [j.dur_s for j in idx[w]] == [2.0, 3.0]
    copies = {0: Copy(0, w, 1.0), 1: Copy(1, w, 1.0)}
    idx.drop_all(InvId(1), copies)
    assert [j.dur_s for j in idx[w]] == [3.0]
    idx.drop_all(InvId(2), {0: Copy(0, w, 2.0)})
    assert idx.get(w) is None and len(idx) == 0


def test_workers_are_independent() -> None:
    idx = JobIndex()
    idx.add(WorkerId(1), InvId(1), 0, JobEst(1.0, 1.0, True))
    idx.add(WorkerId(2), InvId(2), 0, JobEst(1.0, 2.0, False))
    assert idx[WorkerId(1)][0].dur_s == 1.0 and idx[WorkerId(2)][0].dur_s == 2.0
    idx.drop(WorkerId(1), InvId(1), 0)
    assert WorkerId(1) not in idx and WorkerId(2) in idx
