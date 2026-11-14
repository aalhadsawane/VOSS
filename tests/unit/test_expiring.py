"""Bounded memory of finished invocations (voss/runtime/expiring.py, plan V9.5)."""

from __future__ import annotations

from voss.runtime.expiring import ExpiringDict, ExpiringSet


def test_entries_are_forgotten_after_keep_s() -> None:
    now = [0.0]
    d: ExpiringDict[int, str] = ExpiringDict(10.0, lambda: now[0])
    d[1] = "a"
    now[0] = 5.0
    d[2] = "b"
    assert d.get(1) == "a" and 2 in d and len(d) == 2
    now[0] = 10.5  # entry 1 is 10.5 s old, entry 2 is 5.5 s old; pruning happens on the next insert
    d[3] = "c"
    assert d.get(1) is None and d[2] == "b" and len(d) == 2


def test_a_set_forgets_too_and_overwrite_keeps_first_time() -> None:
    now = [0.0]
    s: ExpiringSet[int] = ExpiringSet(1.0, lambda: now[0])
    s.add(7)
    now[0] = 0.9
    s.add(7)  # already there: keeps its first insertion time
    now[0] = 2.0
    s.add(8)
    assert 7 not in s and 8 in s and len(s) == 1
