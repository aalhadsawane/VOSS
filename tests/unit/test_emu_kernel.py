"""Wall-clock kernel of the emulation testbed (doc 10 §4): ordering, cancellation, cross-thread posts."""

from __future__ import annotations

import threading
import time

from tools.emu.kernel import RealtimeKernel


def test_events_run_in_time_order_and_cancel() -> None:
    k = RealtimeKernel()
    out: list[str] = []
    k.after(0.06, out.append, "c")
    k.after(0.02, out.append, "a")
    dead = k.after(0.03, out.append, "x")
    k.after(0.04, out.append, "b")
    k.cancel(dead)
    k.run(0.12)
    assert out == ["a", "b", "c"]
    assert k.now >= 0.12


def test_ties_run_in_insertion_order() -> None:
    k = RealtimeKernel()
    out: list[int] = []
    t = k.now + 0.02
    for i in range(5):
        k.at(t, out.append, i)
    k.run(0.08)
    assert out == [0, 1, 2, 3, 4]


def test_post_from_another_thread_wakes_the_loop() -> None:
    k = RealtimeKernel()
    got: list[float] = []
    threading.Timer(0.03, lambda: k.post(lambda: got.append(k.now))).start()
    t0 = time.monotonic()
    k.run(0.5)
    assert len(got) == 1 and 0.02 < got[0] < 0.2
    assert time.monotonic() - t0 >= 0.45  # run() lasts until the deadline (t0 is taken just after the kernel starts)


def test_callbacks_may_schedule_more_events() -> None:
    k = RealtimeKernel()
    out: list[int] = []

    def chain(n: int) -> None:
        out.append(n)
        if n < 3:
            k.after(0.01, chain, n + 1)

    k.after(0.0, chain, 0)
    k.run(0.15)
    assert out == [0, 1, 2, 3]
