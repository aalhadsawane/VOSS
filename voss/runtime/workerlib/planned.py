"""Plan actions on the worker (doc 03 §4.4): ``PREPARE``, ``PIN_SNAPSHOT``, ``WARM``, ``RELEASE``, plus serving
artifacts to peers (P2P, doc 02 §6). Mixed into the worker agent; mechanics come from ``world``."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from voss.core.ids import Addr, FnId, TenantId, WorkerId
from voss.core.messages import PinSnapshot, Prepare, Release, Warm
from voss.metrics.schema import Table
from voss.runtime.actor import ActorContext
from voss.runtime.workerlib.host import HostLocal
from voss.world.lifecycle import OpEnv, OpRun, artifact_sizes, cache_level, ops_of, split_path
from voss.world.workload import FunctionSpec

MB = 1024 * 1024


class PlannedMixin:
    host: HostLocal
    ctx: ActorContext
    addr: Addr
    catalog: dict[FnId, FunctionSpec]
    digests: dict[FnId, dict[str, str]]
    keys: set[str]
    epoch: int
    prepared: set[str]

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def after(self, dt: float, fn: Any, *args: Any) -> Any: ...
        def request_key(self, tenant: str, cont: Callable[[bool], None]) -> None: ...
        def fetch(
            self,
            fn: FunctionSpec,
            artifacts: tuple[str, ...],
            cont: Callable[[], None],
            sources: tuple[WorkerId, ...] = (),
        ) -> None: ...
        def touched_frac(self) -> float: ...

    def _plan_action(self, m: Prepare | PinSnapshot | Warm | Release) -> None:
        if m.epoch < self.epoch or not self.host.attested:
            return
        if isinstance(m, Prepare):
            self._prepare(m)
        elif isinstance(m, PinSnapshot):
            self._pin_snapshot(m)
        elif isinstance(m, Warm):
            self._warm(m)
        else:
            self._release(m)

    def _prepare(self, m: Prepare) -> None:
        fns = [self.catalog[f] for f in m.fns if f in self.catalog]
        session = self.host.session

        def keyed(ok: bool) -> None:
            if not ok or session != self.host.session:
                return
            left = {"n": len(fns)}

            def one() -> None:
                left["n"] -= 1
                if left["n"] <= 0 and session == self.host.session:
                    for f in fns:
                        for a in ("bundle", "rootfs"):
                            self.host.cache.pin(self.digests[FnId(f.name)][a])
                    self.prepared.add(m.tenant)

            if not fns:
                one()
            for f in fns:
                self.fetch(f, ("bundle", "rootfs"), one, m.sources)

        self.request_key(m.tenant, keyed)

    def _pin_snapshot(self, m: PinSnapshot) -> None:
        fn = self.catalog.get(m.fn)
        if fn is None:
            return
        h, d = self.host, self.digests[m.fn]["snapshot"]
        if h.cache.tier_of(d) is not None:
            h.cache.pin(d)
        elif m.sources and self.ctx.cfg.voss.cache.p2p:
            self.fetch(fn, ("snapshot",), lambda: h.cache.pin(d), m.sources)
        elif fn.tenant in self.keys:
            self._build(fn, then=lambda: self._snapshot_done(fn, d))

    def _snapshot_done(self, fn: FunctionSpec, d: str) -> None:
        h = self.host
        env = OpEnv(
            self.ctx.kernel,
            self.ctx.rng.stream("worker.plan", h.worker, h.session),
            speed=h.speed,
            disks=h.disks,
            sizes=artifact_sizes(fn, 1.0),
            fn=fn,
        )
        session = h.session

        def done(_d: float) -> None:
            if session == h.session and h.up:
                h.cache.insert(d, "snapshot", fn.snapshot_mb, self.now)
                h.cache.pin(d)

        OpRun(h.profile.ladder.after_init, env, done).start()

    def _build(self, fn: FunctionSpec, then: Callable[[], None]) -> None:
        """Bring ``fn`` to the ready level in the background (no slot: planned warm-up, doc 03 §4.4)."""
        h = self.host
        level, _ = cache_level(h.cache, fn, h.profile.ladder, h.snapshot_class, self.digests[FnId(fn.name)])
        prep, rest = split_path(h.profile.ladder, level)
        tiers = {a: h.cache.tier_of(dg) or "ssd" for a, dg in self.digests[FnId(fn.name)].items()}
        tiers["snapshot_touched"] = tiers["snapshot"]
        env = OpEnv(
            self.ctx.kernel,
            self.ctx.rng.stream("worker.plan", h.worker, h.session),
            speed=h.speed,
            io_slowdown=h.io_slowdown,
            tpm=h.tpm,
            psp=h.psp,
            disks=h.disks,
            sizes=artifact_sizes(fn, self.touched_frac()),
            tiers=tiers,
            fn=fn,
        )
        env.fetch = lambda arts, cont: self.fetch(fn, arts, cont)
        session = h.session
        OpRun(
            ops_of(h.profile.ladder, prep + rest), env, lambda _d: then() if session == h.session and h.up else None
        ).start()

    def _warm(self, m: Warm) -> None:
        fn = self.catalog.get(m.fn)
        if fn is None:
            return
        h = self.host
        h.cache.warm_pins[fn.name] = m.n
        missing = m.n - h.cache.warm_count(fn.name)
        if fn.tenant not in self.keys:
            return

        def park() -> None:
            h.cache.park_warm(fn.name, fn.mem_mb, self.now)

        for _ in range(max(0, missing)):
            self._build(fn, then=park)

    def _release(self, m: Release) -> None:
        h = self.host
        self.prepared.discard(m.tenant)
        for fid, fn in sorted(self.catalog.items()):
            if fn.tenant != m.tenant:
                continue
            h.cache.warm_pins.pop(fn.name, None)
            for d in self.digests[fid].values():
                h.cache.pin(d, False)
        self.after(self.ctx.cfg.voss.planner.T_linger, self._linger_over, m.tenant, h.session)

    def _linger_over(self, tenant: TenantId, session: int) -> None:
        busy = any(a.inv.tenant == tenant for a in getattr(self, "attempts", {}).values())
        if session == self.host.session and tenant not in self.prepared and not busy:
            self.keys.discard(tenant)
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="key_dropped", worker=self.host.worker, value=0.0, tenant=tenant
            )
