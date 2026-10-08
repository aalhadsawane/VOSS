"""FIFO and processor-sharing servers (doc 01 §6)."""

from __future__ import annotations

import pytest
from voss.core.dist import Const
from voss.core.kernel import Kernel
from voss.core.rng import stream
from voss.world.resources import Cpu, Disk, PsServer, Tpm


def test_cpu_slots_fifo() -> None:
    k = Kernel()
    cpu = Cpu(k, slots=2, speed=2.0)
    done: list[tuple[str, float]] = []
    for name in "abc":
        cpu.run(2.0, lambda n=name: done.append((n, k.now)))
    k.run(10.0)
    assert done == [("a", 1.0), ("b", 1.0), ("c", 2.0)]


def test_ps_sharing() -> None:
    k = Kernel()
    ps = PsServer(k, capacity=10.0)
    done: dict[str, float] = {}
    ps.submit(10.0, lambda: done.__setitem__("a", k.now))
    k.run(0.5)
    ps.submit(5.0, lambda: done.__setitem__("b", k.now))
    k.run(100.0)
    # a: 5 units alone by 0.5; then both at 5/s: b finishes at 1.5, a has 0 left at 1.5 too.
    assert done["b"] == pytest.approx(1.5)
    assert done["a"] == pytest.approx(1.5)


def test_reset_drops_work() -> None:
    k = Kernel()
    disk = Disk(k, "hdd", read_MBps=1.0, write_MBps=1.0)
    hit: list[int] = []
    disk.read(1e6, lambda: hit.append(1))
    disk.reset()
    k.run(10.0)
    assert hit == []


def test_tpm_serializes_quotes() -> None:
    k = Kernel()
    tpm = Tpm(k, Const(value=0.3), stream(1, "tpm"))
    done: list[float] = []
    for _ in range(3):
        tpm.quote(lambda: done.append(k.now))
    k.run(5.0)
    assert done == pytest.approx([0.3, 0.6, 0.9])
