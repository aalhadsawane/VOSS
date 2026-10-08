"""Simulated node resources (doc 01 §6): FIFO and processor-sharing servers with calibrated rates.

- ``Cpu(slots)``: FIFO multi-server; service = work (reference-core seconds) / speed.
- ``Disk(tier)``: processor-sharing read and write channels (bytes/s).
- ``Link(up, down)``: processor-sharing access link (bytes/s).
- ``Tpm``: one quote at a time; ``Psp``: CVM launches serialize.

Every server supports ``reset()`` (the host died: pending work is dropped without callbacks).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from voss.core.dist import Dist
from voss.core.kernel import Handle, Kernel

Callback = Callable[..., Any]
_EPS = 1e-9


@dataclass(eq=False)
class Job:
    amount: float
    cb: Callback
    args: tuple[Any, ...] = ()
    seq: int = 0
    handle: Handle | None = field(default=None, repr=False)
    done: bool = False


class FifoServer:
    """``servers`` identical FIFO servers; ``submit(service_s, cb)`` calls ``cb(*args)`` on completion."""

    def __init__(self, kernel: Kernel, servers: int = 1) -> None:
        self.k, self.servers = kernel, max(1, servers)
        self.queue: deque[Job] = deque()
        self.running: set[Job] = set()

    def submit(self, service_s: float, cb: Callback, *args: Any) -> Job:
        job = Job(max(0.0, service_s), cb, args)
        self.queue.append(job)
        self._pump()
        return job

    def cancel(self, job: Job) -> None:
        if job in self.running and job.handle is not None:
            self.k.cancel(job.handle)
            self.running.discard(job)
            self._pump()
        elif job in self.queue:
            self.queue.remove(job)
        job.done = True

    def reset(self) -> None:
        for job in self.running:
            if job.handle is not None:
                self.k.cancel(job.handle)
        self.running.clear()
        self.queue.clear()

    @property
    def busy(self) -> int:
        return len(self.running)

    def _pump(self) -> None:
        while self.queue and len(self.running) < self.servers:
            job = self.queue.popleft()
            self.running.add(job)
            job.handle = self.k.after(job.amount, self._finish, job)

    def _finish(self, job: Job) -> None:
        self.running.discard(job)
        job.done = True
        self._pump()
        job.cb(*job.args)


class PsServer:
    """Processor sharing: ``capacity`` units/s split equally among jobs (each at most ``per_job_cap``)."""

    def __init__(self, kernel: Kernel, capacity: float, per_job_cap: float = float("inf")) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.k, self.capacity, self.per_job_cap = kernel, capacity, per_job_cap
        self.jobs: dict[int, Job] = {}
        self._seq = 0
        self._last = kernel.now
        self._handle: Handle | None = None

    def rate(self) -> float:
        return min(self.capacity / max(1, len(self.jobs)), self.per_job_cap)

    def submit(self, amount: float, cb: Callback, *args: Any) -> Job:
        self._advance()
        job = Job(max(0.0, amount), cb, args, self._seq)
        self._seq += 1
        self.jobs[job.seq] = job
        self._reschedule()
        return job

    def cancel(self, job: Job) -> None:
        self._advance()
        self.jobs.pop(job.seq, None)
        job.done = True
        self._reschedule()

    def reset(self) -> None:
        self.jobs.clear()
        if self._handle is not None:
            self.k.cancel(self._handle)
            self._handle = None

    def _advance(self) -> None:
        dt = self.k.now - self._last
        if dt > 0 and self.jobs:
            r = self.rate()
            for job in self.jobs.values():
                job.amount -= r * dt
        self._last = self.k.now

    def _reschedule(self) -> None:
        if self._handle is not None:
            self.k.cancel(self._handle)
            self._handle = None
        if self.jobs:
            least = min(j.amount for j in self.jobs.values())
            self._handle = self.k.after(max(0.0, least) / self.rate(), self._complete)

    def _complete(self) -> None:
        self._handle = None
        self._advance()
        tol = _EPS * max(1.0, self.capacity)
        finished = [j for _, j in sorted(self.jobs.items()) if j.amount <= tol]
        for j in finished:
            del self.jobs[j.seq]
            j.done = True
        self._reschedule()
        for j in finished:
            j.cb(*j.args)


class Cpu(FifoServer):
    """``slots`` vCPUs; ``run(work, cb)`` takes ``work / speed`` seconds."""

    def __init__(self, kernel: Kernel, slots: int, speed: float = 1.0) -> None:
        super().__init__(kernel, slots)
        self.speed = speed

    def run(self, work: float, cb: Callback, *args: Any) -> Job:
        return self.submit(work / self.speed, cb, *args)


class Disk:
    """One disk tier (``ssd`` or ``hdd``) with PS read and write channels."""

    def __init__(self, kernel: Kernel, tier: str, read_MBps: float, write_MBps: float) -> None:
        self.tier = tier
        self.reader = PsServer(kernel, max(read_MBps, 1e-6) * 1e6)
        self.writer = PsServer(kernel, max(write_MBps, 1e-6) * 1e6)

    def read(self, nbytes: float, cb: Callback, *args: Any) -> Job:
        return self.reader.submit(nbytes, cb, *args)

    def write(self, nbytes: float, cb: Callback, *args: Any) -> Job:
        return self.writer.submit(nbytes, cb, *args)

    def reset(self) -> None:
        self.reader.reset()
        self.writer.reset()


class Link:
    """Access link with PS uplink and downlink (rates in bits/s, work in bytes)."""

    def __init__(self, kernel: Kernel, up_bps: float, down_bps: float) -> None:
        self.up = PsServer(kernel, up_bps / 8)
        self.down = PsServer(kernel, down_bps / 8)

    def reset(self) -> None:
        self.up.reset()
        self.down.reset()


class Tpm(FifoServer):
    """TPM: one quote at a time; latency drawn from the calibrated quote distribution."""

    def __init__(self, kernel: Kernel, quote: Dist, gen: np.random.Generator) -> None:
        super().__init__(kernel, 1)
        self.quote_dist, self.gen = quote, gen

    def quote(self, cb: Callback, *args: Any) -> Job:
        return self.submit(float(self.quote_dist.sample(self.gen)), cb, *args)


class Psp(FifoServer):
    """AMD PSP: CVM launches on one host serialize (``cvm_snp``)."""

    def __init__(self, kernel: Kernel) -> None:
        super().__init__(kernel, 1)
