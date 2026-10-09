"""One dispatched attempt on a worker (doc 00 §6, doc 02 §5, doc 08 §5-6).

Flow: acquire a slot ∥ trust (key release if trust-cold) ∥ prep (artifact fetch, overlapping the wait) → remaining
ladder transitions to the ready level (boot / restore / warm VM) → dispatch → wait for input → execute → result.
Components are attributed so that ``wait + trust + startup + input_wait + exec = t_sent − t_received``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Protocol

import numpy as np

from voss.core.ids import Addr, FnId, WorkerId
from voss.core.kernel import Kernel
from voss.core.types import Invocation, Timings
from voss.runtime.workerlib.host import HostLocal
from voss.world.execution import ExecParams, ref_work_units, true_runtime
from voss.world.lifecycle import OpEnv, OpRun, artifact_sizes, cache_level, ops_of, split_path
from voss.world.substrate import Op, RpcOp
from voss.world.workload import SLO_CLASSES, FunctionSpec


class AgentPort(Protocol):
    """What an attempt needs from its worker agent."""

    kernel: Kernel
    host: HostLocal
    keys: set[str]
    digests: dict[FnId, dict[str, str]]

    def request_key(self, tenant: str, cont: Callable[[bool], None]) -> None: ...
    def fetch(
        self, fn: FunctionSpec, artifacts: tuple[str, ...], cont: Callable[[], None], sources: tuple[WorkerId, ...] = ()
    ) -> None: ...
    def finish(self, att: Attempt, status: str) -> None: ...
    def touched_frac(self) -> float: ...
    def on_exec_start(self, att: Attempt) -> None: ...
    def noise(self, inv: int, attempt: int) -> float: ...
    def exec_params(self) -> ExecParams: ...


@dataclass
class Attempt:
    inv: Invocation
    fn: FunctionSpec
    epoch: int
    token: int
    router: Addr
    t_enqueue: float
    t_dispatch: float
    t_received: float
    gen: np.random.Generator
    port: AgentPort
    batch_wait: float = 0.0
    sources: tuple[WorkerId, ...] = ()
    scheduler: Addr = ("sched", -1)
    input_at: float | None = None
    level: str = ""
    tier: str = ""
    trust_cold: bool = False
    timings: Timings = field(default_factory=Timings)
    slot: int | None = None
    waiting: set[str] = field(default_factory=lambda: {"slot", "trust", "prep"})
    dur: dict[str, float] = field(default_factory=dict)
    runs: list[OpRun] = field(default_factory=list)
    ready_t: float | None = None
    rest_done: bool = False
    warm: bool = False
    exec_t0: float | None = None
    cancelled: bool = False
    mem_held: float = 0.0

    def start(self) -> None:
        h = self.port.host
        lad = h.profile.ladder
        self.level, self.tier = cache_level(h.cache, self.fn, lad, h.snapshot_class, self._digests())
        self.trust_cold = bool(h.profile.trust) and self.inv.tenant not in self.port.keys
        self.slot = h.slots.acquire(lambda _tok: self._ready("slot", 0.0))
        self._run(h.profile.trust if self.trust_cold else (), lambda d: self._ready("trust", d))
        prep, _ = split_path(lad, self.level)
        self._run(ops_of(lad, prep), lambda d: self._ready("prep", d))

    def _digests(self) -> dict[str, str]:
        return self.port.digests[self.inv.fn]

    # --- op plumbing ----------------------------------------------------------------------------------------
    def _env(self) -> OpEnv:
        h = self.port.host
        tiers = {a: h.cache.tier_of(d) or "" for a, d in self._digests().items()}
        tiers["snapshot_touched"] = tiers["snapshot"]
        env = OpEnv(
            self.port.kernel,
            self.gen,
            speed=h.speed,
            io_slowdown=h.io_slowdown,
            tpm=h.tpm,
            psp=h.psp,
            disks=h.disks,
            sizes=artifact_sizes(self.fn, self.port.touched_frac()),
            tiers={a: t for a, t in tiers.items() if t},
            fn=self.fn,
        )
        env.rpc = self._rpc
        env.fetch = lambda arts, cont: self.port.fetch(self.fn, arts, cont, self.sources)
        return env

    def _rpc(self, op: RpcOp, cont: Callable[[], None]) -> None:
        if op.to != "tenant_kbs":
            raise RuntimeError(f"an attempt cannot rpc to {op.to}")
        self.port.request_key(self.inv.tenant, lambda ok: cont() if ok else self.fail("key_denied"))

    def _run(self, ops: tuple[Op, ...], done: Callable[[float], None]) -> None:
        if not ops:
            done(0.0)
            return
        self.runs.append(OpRun(ops, self._env(), done).start())

    # --- phases -----------------------------------------------------------------------------------------------
    def _ready(self, what: str, dur: float) -> None:
        if self.cancelled:
            return
        self.dur[what] = dur
        self.waiting.discard(what)
        if self.waiting:
            return
        h, lad = self.port.host, self.port.host.profile.ladder
        self.ready_t = self.port.kernel.now
        if self.level == lad.ready:
            self.warm = h.cache.take_warm(self.fn.name) is not None
            if not self.warm:  # the warm VM was evicted meanwhile: fall back to the next level down
                self.level, self.tier = cache_level(h.cache, self.fn, lad, h.snapshot_class, self._digests())
        if not self.warm:
            self.mem_held = self.fn.mem_mb
            h.cache.running_mb += self.mem_held
        _, rest = split_path(lad, self.level)
        busy = f"{lad.ready}->{lad.busy}"
        keys = rest + ([busy] if busy in lad.transitions else [])
        self._run(ops_of(lad, keys), self._rest_finished)

    def _rest_finished(self, dur: float) -> None:
        if self.cancelled:
            return
        self.dur["rest"] = dur
        self.rest_done = True
        if self.input_at is not None:
            self._exec()

    def input_arrived(self, t: float) -> None:
        self.input_at = t
        if self.rest_done:
            self._exec()

    def _exec(self) -> None:
        h, now = self.port.host, self.port.kernel.now
        if self.exec_t0 is not None or self.cancelled or self.ready_t is None:
            return
        if not h.cert_valid(now):
            self.fail("expired")
            return
        self.exec_t0 = now
        self._attribute(now)
        self.port.on_exec_start(self)
        p = self.port.exec_params()
        noise = self.port.noise(int(self.inv.id), self.inv.attempt)
        run = true_runtime(self.fn, self.inv.in_bytes, h.speed, h.slots.busy, h.n_slots, h.cpu_slowdown, noise, p)
        timeout = p.timeout_s.get(SLO_CLASSES[int(self.inv.slo_class)], 600.0)
        self.port.kernel.after(min(run, timeout), self._done, run <= timeout)

    def _attribute(self, now: float) -> None:
        assert self.ready_t is not None
        a = self.ready_t - self.t_received
        trust = min(self.dur.get("trust", 0.0), a)
        fetch = min(self.dur.get("prep", 0.0), a - trust)
        rest = self.dur.get("rest", 0.0)
        self.timings = Timings(
            t_enqueue=self.t_enqueue,
            batch_wait=self.batch_wait,
            t_dispatch=self.t_dispatch,
            t_received=self.t_received,
            wait=a - trust - fetch,
            trust=trust,
            startup=fetch + rest,
            input_wait=max(0.0, now - (self.ready_t + rest)),
        )

    def _done(self, ok: bool) -> None:
        if self.cancelled or self.exec_t0 is None:
            return
        now = self.port.kernel.now
        self.timings = replace(self.timings, exec=now - self.exec_t0, t_sent=now)
        self._release()
        self.port.finish(self, "ok" if ok else "timeout")

    def _release(self) -> None:
        h = self.port.host
        if self.slot is not None:
            h.slots.release(self.slot)
            self.slot = None
        h.cache.running_mb = max(0.0, h.cache.running_mb - self.mem_held)
        self.mem_held = 0.0

    def fail(self, status: str) -> None:
        if self.cancelled:
            return
        self.cancel()
        self.timings = replace(self.timings, t_sent=self.port.kernel.now)
        self.port.finish(self, status)

    def cancel(self) -> None:
        """Abort everything not yet finished (hedge loser, failure). Host loss resets resources separately."""
        if self.cancelled:
            return
        self.cancelled = True
        for r in self.runs:
            r.abort()
        if self.port.host.up:
            self._release()

    @property
    def ref_units(self) -> float:
        return ref_work_units(self.fn, self.inv.in_bytes)
