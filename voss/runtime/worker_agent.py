"""Worker agent actor (doc 04 §4-6, doc 08 §4-6): donation session, attestation, membership, heartbeats, keys,
artifact fetches and dispatched attempts. Thin: protocol handling here, mechanics in ``world``."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from voss.core.ids import Addr, ClusterId, FnId, TenantId, WorkerId
from voss.core.messages import (
    Accepted,
    Cancel,
    Chunk,
    Dispatch,
    EpochInstall,
    Fetch,
    Heartbeat,
    Input,
    Key,
    KeyRequest,
    Message,
    OutcomeMsg,
    OwnerEvent,
    PinSnapshot,
    Prepare,
    Receipt,
    Release,
    Result,
    SessionCert,
    Stale,
    Warm,
)
from voss.core.types import CacheEntry, Outcome, WorkerState
from voss.metrics.schema import Table
from voss.policy.cache_value import GdsfState
from voss.runtime.actor import Actor, ActorContext
from voss.runtime.workerlib.attempt import Attempt
from voss.runtime.workerlib.fetching import FetchMixin
from voss.runtime.workerlib.host import HostLocal
from voss.runtime.workerlib.planned import PlannedMixin
from voss.runtime.workerlib.session import SessionMixin
from voss.world.execution import ExecParams
from voss.world.lifecycle import artifact_digests, artifact_sizes, cache_level
from voss.world.workload import FunctionSpec

MB = 1024 * 1024


class WorkerAgent(PlannedMixin, FetchMixin, SessionMixin, Actor):
    role = "agent"

    def __init__(
        self, host: HostLocal, ctx: ActorContext, catalog: dict[FnId, FunctionSpec], params: dict[str, object]
    ) -> None:
        super().__init__(host.worker, ctx)
        self.host = host
        self.kernel = ctx.kernel
        self.catalog = catalog
        self.params = params
        self.keys: set[str] = set()
        self.digests = {fid: artifact_digests(fn, host.snapshot_class) for fid, fn in catalog.items()}
        self._inventory: dict[FnId, CacheEntry] = {}
        self._inv_version = -1
        self.gdsf = GdsfState()
        if ctx.cfg.voss.cache.value == "gdsf":
            self.use_gdsf()
        self._init_session_state()

    def _init_session_state(self) -> None:
        self.epoch = 0
        self.cluster: ClusterId | None = None
        self.sched: Addr | None = None
        self.sched_cert = ""
        self.keys = set()
        self.key_waiters: dict[str, list[Callable[[bool], None]]] = {}
        self.fetch_waiters: dict[str, list[Callable[[], None]]] = {}
        self.fetch_kind: dict[str, tuple[str, float, float]] = {}
        self.prepared: set[str] = set()
        self.attempts: dict[tuple[int, int], Attempt] = {}
        self.early_inputs: dict[tuple[int, int], float] = {}
        self.drain_deadline: float | None = None
        self.op_gen = self.ctx.rng.stream("worker.ops", self.host.worker, self.host.session)
        self.attest_cont: Callable[[], None] | None = None
        self.hb_on = False

    # --- port for attempts ----------------------------------------------------------------------------------
    def exec_params(self) -> ExecParams:
        p = self.params["exec"]
        assert isinstance(p, ExecParams)
        return p

    def noise(self, inv: int, attempt: int) -> float:
        m = self.params["noise"]
        assert isinstance(m, np.ndarray)
        return float(m[inv, min(attempt, m.shape[1] - 1)])

    def touched_frac(self) -> float:
        return float(self.params["touched_frac"])  # type: ignore[arg-type]

    def on_exec_start(self, att: Attempt) -> None:
        h = self.host
        self.ctx.rec.log(
            Table.EVENTS,
            t=self.now,
            kind="exec_start",
            worker=h.worker,
            cert=h.cert_id,
            value=h.cert_expiry,
            inv=int(att.inv.id),
            attempt=att.inv.attempt,
            epoch=att.epoch,
            tenant=att.inv.tenant,
            needs_key=bool(h.profile.trust),
            has_key=att.inv.tenant in self.keys,
        )

    def request_key(self, tenant: str, cont: Callable[[bool], None]) -> None:
        if tenant in self.keys:
            cont(True)
            return
        waiters = self.key_waiters.setdefault(tenant, [])
        waiters.append(cont)
        if len(waiters) == 1:
            kbs = self.ctx.directory.kbs[TenantId(tenant)]
            h = self.host
            self.send(kbs, KeyRequest(h.worker, TenantId(tenant), h.cert_id, h.cert_expiry, self.addr))

    def finish(self, att: Attempt, status: str) -> None:
        key = (int(att.inv.id), att.inv.attempt)
        self.attempts.pop(key, None)
        out = Outcome(
            att.inv.id,
            att.inv.attempt,
            self.host.worker,
            status,
            att.timings,
            att.level,
            att.trust_cold,
            att.tier,
            att.ref_units,
        )
        if status == "ok":
            rcpt = Receipt(
                att.inv.id,
                att.inv.attempt,
                self.host.worker,
                self.host.cert_id,
                att.epoch,
                att.timings.exec,
                att.ref_units,
                f"out:{int(att.inv.id)}",
            )
            self.send(att.router, Result(out, rcpt, int(att.fn.out_kb * 1024)))
            self._after_success(att)
        if self.sched is not None:
            self.send(self.sched, OutcomeMsg(out))

    def _after_success(self, att: Attempt) -> None:
        h = self.host
        h.cache.park_warm(att.fn.name, att.fn.mem_mb, self.now)
        lad = h.profile.ladder
        snap = artifact_digests(att.fn, h.snapshot_class)["snapshot"]
        if lad.after_init and "L2" in lad.persistent and att.level != lad.ready and h.cache.tier_of(snap) is None:
            self._write_snapshot(att, snap)

    def _write_snapshot(self, att: Attempt, snap: str) -> None:
        from voss.world.lifecycle import OpEnv, OpRun  # noqa: PLC0415

        h = self.host
        env = OpEnv(self.kernel, att.gen, speed=h.speed, disks=h.disks, sizes=artifact_sizes(att.fn, 1.0), fn=att.fn)
        session = h.session

        def done(_d: float) -> None:
            if h.session == session and h.up:
                h.cache.insert(snap, "snapshot", att.fn.snapshot_mb, self.now)

        OpRun(h.profile.ladder.after_init, env, done).start()

    # --- messages ---------------------------------------------------------------------------------------------
    def on_message(self, msg: Message) -> None:
        if isinstance(msg, Dispatch):
            self._dispatch(msg)
        elif isinstance(msg, Input):
            self._input(msg)
        elif isinstance(msg, Key):
            self._key(msg)
        elif isinstance(msg, Chunk):
            self._chunk(msg)
        elif isinstance(msg, Fetch):
            self._serve(msg)
        elif isinstance(msg, Prepare | PinSnapshot | Warm | Release):
            self._plan_action(msg)
        elif isinstance(msg, EpochInstall):
            self._epoch_install(msg)
        elif isinstance(msg, SessionCert):
            self._session_cert(msg)
        elif isinstance(msg, Cancel):
            att = self.attempts.pop((int(msg.inv), msg.attempt), None)
            if att is not None:
                att.cancel()
        elif isinstance(msg, OwnerEvent):
            self._owner(msg)

    def _dispatch(self, m: Dispatch) -> None:
        if not self.host.cert_valid(self.now):
            return
        if m.epoch < self.epoch:
            self.send(m.scheduler, Stale(self.host.worker, self.epoch))
            return
        self.epoch = max(self.epoch, m.epoch)
        key = (int(m.inv.id), m.inv.attempt)
        if key in self.attempts:
            return
        att = Attempt(
            m.inv,
            self.catalog[m.inv.fn],
            m.epoch,
            m.token,
            m.router,
            m.t_enqueue,
            m.t_dispatch,
            self.now,
            self.op_gen,
            self,
            m.batch_wait,
            m.sources,
        )
        self.attempts[key] = att
        self._log_exec_guard(att)
        acc = Accepted(att.inv.id, att.inv.attempt, self.host.worker, att.token)
        self.send(att.router, acc)
        if self.sched is not None:
            self.send(self.sched, acc)
        att.start()
        if key in self.early_inputs:
            att.input_arrived(self.early_inputs.pop(key))

    def _log_exec_guard(self, att: Attempt) -> None:
        h = self.host
        self.ctx.rec.log(
            Table.EVENTS,
            t=self.now,
            kind="dispatch_accepted",
            worker=h.worker,
            cert=h.cert_id,
            value=h.cert_expiry,
            inv=int(att.inv.id),
            attempt=att.inv.attempt,
            epoch=att.epoch,
            epoch_installed=self.epoch,
            tenant=att.inv.tenant,
        )

    def _input(self, m: Input) -> None:
        key = (int(m.inv), m.attempt)
        att = self.attempts.get(key)
        if att is None:
            self.early_inputs[key] = self.now
            return
        att.input_arrived(self.now)

    def _key(self, m: Key) -> None:
        if m.cert_id != self.host.cert_id:
            return
        if m.ok:
            self.keys.add(m.tenant)
        for cont in self.key_waiters.pop(m.tenant, []):
            cont(m.ok)

    def _epoch_install(self, m: EpochInstall) -> None:
        if m.epoch < self.epoch or not self.host.attested:
            return
        self.epoch, self.cluster, self.sched, self.sched_cert = m.epoch, m.cluster, m.scheduler, m.cert_id
        self._heartbeat()

    # --- heartbeats ---------------------------------------------------------------------------------------------
    def state(self) -> WorkerState:
        h = self.host
        if self._inv_version != h.cache.version:
            cache = {}
            for fid, fn in self.catalog.items():
                level, tier = cache_level(h.cache, fn, h.profile.ladder, h.snapshot_class, self.digests[fid])
                if level != h.profile.ladder.levels[0]:
                    cache[fid] = CacheEntry(level, tier, h.cache.warm_count(fn.name))
            self._inventory, self._inv_version = cache, h.cache.version
        cache = self._inventory
        return WorkerState(
            worker=WorkerId(h.worker),
            slots=h.n_slots,
            busy=h.slots.busy,
            queued=h.slots.queued,
            mem_free_mb=h.cache.mem_free(),
            ssd_free_mb=h.cache.free("ssd"),
            hdd_free_mb=h.cache.free("hdd"),
            cache=cache,
            trust=frozenset(TenantId(k) for k in self.keys),
            session_expiry=h.cert_expiry,
            drain_deadline=self.drain_deadline,
            assurance=h.assurance,
            speed=h.speed,
            domain=h.domain,
            as_of=self.now,
            cert_id=h.cert_id,
            static=h.static,
            pinned=frozenset(self.prepared),
        )

    def _heartbeat(self) -> None:
        if not self.host.up or self.sched is None:
            return
        h = self.host
        if h.cache.warm:
            h.cache.expire_warm(self.now, self.ctx.cfg.voss.worker.warm_ttl_s)
        self.send(self.sched, Heartbeat(self.state()))
        if not self.hb_on:
            self.hb_on = True
            self.after(self.ctx.cfg.voss.scheduler.heartbeat_s, self._hb_tick)

    def _hb_tick(self) -> None:
        self.hb_on = False
        self._heartbeat()
