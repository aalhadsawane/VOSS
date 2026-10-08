"""Toy system for the P0 scaffold: nodes ping each other with random think times and fixed delays.

It exercises the kernel, rng streams, recorder and manifest so ``voss repro`` can be tested before the world exists.
"""

from __future__ import annotations

from voss.core.config import RunConfig
from voss.core.kernel import Kernel
from voss.core.registry import register
from voss.core.rng import RngFactory
from voss.metrics.recorder import Recorder
from voss.metrics.schema import Table
from voss.runtime.system import RunResult


class _ToyNode:
    def __init__(self, idx: int, n: int, kernel: Kernel, rng: RngFactory, rec: Recorder) -> None:
        self.idx, self.n, self.k, self.rec = idx, n, kernel, rec
        self.gen = rng.stream("toy.node", idx)
        self.received = 0

    def start(self) -> None:
        self.k.after(float(self.gen.exponential(1.0)), self.tick)

    def tick(self) -> None:
        dst = int(self.gen.integers(0, self.n))
        delay = 0.01 + 0.001 * abs(dst - self.idx)
        self.rec.log(Table.EVENTS, t=self.k.now, kind="send", src=self.idx, dst=dst)
        self.k.after(delay, self.peers[dst].deliver, self.idx)
        self.k.after(float(self.gen.exponential(1.0)), self.tick)

    def deliver(self, src: int) -> None:
        self.received += 1
        self.rec.log(Table.EVENTS, t=self.k.now, kind="recv", src=src, dst=self.idx)

    peers: list[_ToyNode]


@register("system", "toy")
def run_toy(cfg: RunConfig) -> RunResult:
    kernel, rng, rec = Kernel(), RngFactory(cfg.seed), Recorder()
    n = int(cfg.scenario.get("workers", 10))
    nodes = [_ToyNode(i, n, kernel, rng, rec) for i in range(n)]
    for node in nodes:
        node.peers = nodes
        node.start()
    kernel.run(cfg.horizon_s)
    return RunResult(rec, None, kernel.events_run)
