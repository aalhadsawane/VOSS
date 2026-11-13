"""Knative Pod Autoscaler baseline against its published rules (docs/REVISION_PLAN.md V8)."""

from __future__ import annotations

from voss.policy.plan.kpa import KpaParams, KpaState, decide, place

P = KpaParams()


def _run(st: KpaState, start: float, end: float, conc: float) -> int:
    t, want = start, 0
    while t < end:
        st.observe(t, conc, P.stable_s)
        want = decide(st, t, P)
        t += 2.0
    return want


def test_steady_load_targets_70_percent_of_one_request_per_sandbox() -> None:
    assert _run(KpaState(), 0.0, 120.0, 3.5) == 5  # ceil(3.5 / 0.7)


def test_scale_down_is_at_most_halving_per_tick() -> None:
    st = KpaState()
    _run(st, 0.0, 120.0, 7.0)  # 10 sandboxes
    st.observe(120.0, 0.0, P.stable_s)
    assert decide(st, 120.0, P) >= 5


def test_burst_starts_panic_and_panic_never_scales_down() -> None:
    st = KpaState()
    _run(st, 0.0, 60.0, 0.7)  # 1 sandbox
    burst = _run(st, 60.0, 66.0, 7.0)
    assert st.panic_since is not None and burst >= 2
    calm = _run(st, 66.0, 90.0, 0.7)
    assert calm >= burst  # still in panic: no decrease within a stable window of the last panic tick
    assert _run(st, 90.0, 300.0, 0.7) == 1 and st.panic_since is None


def test_zero_only_after_stable_window_and_grace() -> None:
    st = KpaState()
    _run(st, 0.0, 60.0, 0.7)
    assert _run(st, 60.0, 140.0, 0.0) == 1  # 80 s idle < 60 + 30
    assert _run(st, 140.0, 160.0, 0.0) == 0


def test_place_spreads_over_holders_first() -> None:
    assert place(3, [2, 0, 1], [1, 5, 2]) == {2: 1, 0: 1, 1: 1}  # one per worker per pass, in order
    assert place(4, [2, 0], [1, 5, 2]) == {2: 2, 0: 1}  # worker 0 has room for one
    assert place(10, [0, 1], [1, 1]) == {0: 1, 1: 1}  # no room left: fewer than wanted
