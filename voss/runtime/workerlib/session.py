"""Donation-session handling for the worker agent (doc 02 §2, doc 04 §4-5, doc 08 §3.2).

``start`` → establish ops of the substrate profile (boot, TPM quote, ``ATTEST`` → ``SESSION_CERT``) → ``JOIN`` →
heartbeats once a scheduler installs its epoch; periodic re-quotes extend the certificate. ``drain`` is a hint sent
to the orchestrator and scheduler. ``end`` loses all RAM state (keys, warm VMs, attempts).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from voss.core.ids import Addr
from voss.core.messages import Attest, DrainNotice, Join, Leave, OwnerEvent, Requote, SessionCert
from voss.core.rng import RngFactory
from voss.metrics.schema import Table
from voss.runtime.actor import ActorContext
from voss.runtime.workerlib.host import HostLocal
from voss.world.lifecycle import OpEnv, OpRun
from voss.world.substrate import DelayOp, Op, PspOp, RpcOp


class SessionMixin:
    """Mixed into ``WorkerAgent``; relies on its actor plumbing."""

    host: HostLocal
    ctx: ActorContext
    addr: Addr
    attest_cont: Callable[[], None] | None
    attempts: dict[Any, Any]
    drain_deadline: float | None
    sched: Addr | None

    if TYPE_CHECKING:  # provided by Actor / WorkerAgent

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def after(self, dt: float, fn: Any, *args: Any) -> Any: ...
        def cancel_timers(self) -> None: ...
        def _init_session_state(self) -> None: ...

    def _owner(self, ev: OwnerEvent) -> None:
        if ev.kind == "start":
            self._start_session(ev.prebooted)
        elif ev.kind == "drain":
            self._drain(ev.deadline)
        elif ev.kind == "end":
            self._end_session(ev.graceful)

    def _env(self, rng: RngFactory) -> OpEnv:
        h = self.host
        env = OpEnv(self.ctx.kernel, rng.stream("session.ops", h.worker, h.session), speed=1.0, tpm=h.tpm, psp=h.psp)
        env.rpc = self._session_rpc
        return env

    def _start_session(self, prebooted: bool) -> None:
        h = self.host
        h.session += 1
        h.up = True
        ops: tuple[Op, ...] = h.profile.session.establish
        if prebooted:  # session began before t=0: the boot already happened
            ops = tuple(op for op in ops if not isinstance(op, DelayOp | PspOp))
        session = h.session
        OpRun(ops, self._env(self.ctx.rng), lambda d: self._established(session, d)).start()

    def _session_rpc(self, op: RpcOp, cont: Callable[[], None]) -> None:
        h = self.host
        self.attest_cont = cont
        if op.to != "verifier":
            raise RuntimeError(f"session rpc to {op.to} is not modeled")
        if h.cert_id:
            self.send(self.ctx.directory.verifier, Requote(h.worker, h.session, h.cert_id, self.addr))
        else:
            sub = h.profile.name
            self.send(
                self.ctx.directory.verifier, Attest(h.worker, h.identity, h.session, sub, h.known_good, self.addr)
            )

    def _session_cert(self, m: SessionCert) -> None:
        h = self.host
        if m.session != h.session or not h.up:
            return
        if not m.ok:
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="requote_failed", worker=h.worker, cert=m.cert_id, value=0.0
            )
            h.attested = False
            return
        h.cert_id, h.cert_expiry, h.assurance = m.cert_id, m.expiry, m.assurance
        cont, self.attest_cont = self.attest_cont, None
        if cont is not None:
            cont()

    def _established(self, session: int, _dur: float) -> None:
        h = self.host
        if session != h.session or not h.up or not h.cert_id:
            return
        h.attested = True
        self.ctx.rec.log(
            Table.EVENTS, t=self.now, kind="session_attested", worker=h.worker, cert=h.cert_id, value=h.cert_expiry
        )
        self.send(
            self.ctx.directory.orchestrator,
            Join(h.worker, h.cert_id, h.cert_expiry, h.assurance, h.speed, h.n_slots, h.domain, self.addr),
        )
        self.after(h.profile.session.reattest_every_s, self._reattest, session)

    def _reattest(self, session: int) -> None:
        h = self.host
        if session != h.session or not h.up:
            return
        OpRun(h.profile.session.reattest, self._env(self.ctx.rng), lambda d: None).start()
        self.after(h.profile.session.reattest_every_s, self._reattest, session)

    def _drain(self, deadline: float) -> None:
        h = self.host
        if not h.attested:
            return
        self.drain_deadline = deadline
        notice = DrainNotice(h.worker, deadline)
        self.send(self.ctx.directory.orchestrator, notice)
        if self.sched is not None:
            self.send(self.sched, notice)
        self.after(max(0.0, deadline - self.now) + 1.0, self._drain_over, h.session)

    def _drain_over(self, session: int) -> None:
        if session == self.host.session:
            self.drain_deadline = None  # a fake notice: the session simply continues

    def _end_session(self, graceful: bool) -> None:
        h = self.host
        if graceful and h.attested:
            self.send(self.ctx.directory.orchestrator, Leave(h.worker, h.cert_id))
        for att in list(self.attempts.values()):
            att.cancelled = True
            for r in att.runs:
                r.abort()
        self.cancel_timers()
        h.reset_session()
        self._init_session_state()
