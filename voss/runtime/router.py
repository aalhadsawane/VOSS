"""Regional router (doc 03 §3, doc 07 §2, doc 09 §3): picks a cluster per invocation from orchestrator-pushed
summaries (priced trust-cold spillover), keeps the pending table, runs the dispatch watchdog with spillover after
``T_spill``, verifies attested receipts (batched to the DB), and reports per-cluster SLO health."""

from __future__ import annotations

import numpy as np

from voss.core.ids import Addr, ClusterId, InvId, NodeId
from voss.core.messages import (
    Accepted,
    Assigned,
    Cancel,
    DbAppendReceipts,
    Enqueue,
    Input,
    Invoke,
    Message,
    Receipt,
    Reject,
    Result,
    RevokeSession,
    RouterStats,
    SchedulerAddr,
    Summaries,
    Withdraw,
)
from voss.core.messages_ft import Stall
from voss.core.registry import REGISTRY
from voss.core.types import ClusterCard, Invocation, Outcome, SloClass
from voss.metrics.schema import Table
from voss.policy import route as _routes  # noqa: F401  (registers routing policies)
from voss.policy.route import RouteRequest, home_cluster
from voss.runtime.actor import Actor, ActorContext
from voss.runtime.routerlib.pending import Pending, row
from voss.world.workload import SLO_CLASSES


class Router(Actor):
    role = "router"

    def __init__(self, host: NodeId, ctx: ActorContext, region: str, origins: np.ndarray) -> None:
        super().__init__(host, ctx)
        self.region, self.origins = region, origins  # origins[i] = (lat, lon) of metro i
        self.policy = REGISTRY.get("route", ctx.cfg.voss.router.name)
        self.gen = ctx.rng.stream("router", region)
        self.scheds: dict[int, tuple[int, Addr]] = {}
        self.epochs: dict[int, int] = {}
        self.cards: dict[int, ClusterCard] = {}
        self.pending: dict[InvId, Pending] = {}
        self.unrouted: list[InvId] = []
        self.finished: set[InvId] = set()
        self.revoked: set[str] = set()
        self.batch: list[tuple[Receipt, float, str]] = []
        self.stats: dict[int, list[int]] = {}
        self.home: dict[tuple[int, str], int] = {}
        self.fires: dict[int, list[tuple[float, InvId]]] = {}
        self.stalled: dict[int, float] = {}
        self.last_accept: dict[int, float] = {}
        rc = ctx.cfg.voss.router
        self.after(rc.receipt_batch_s, self._flush_tick)
        self.after(rc.stats_s, self._stats_tick)

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, Invoke):
            self._invoke(msg.inv)
        elif isinstance(msg, Assigned):
            self._assigned(msg)
        elif isinstance(msg, Accepted):
            p = self.pending.get(msg.inv)
            if p is not None:
                p.accepted = True
                if p.cluster is not None:
                    self.last_accept[p.cluster] = self.now
        elif isinstance(msg, Result):
            self._result(msg.outcome, msg.receipt)
        elif isinstance(msg, SchedulerAddr):
            self._scheduler(msg)
        elif isinstance(msg, Summaries):
            self.cards = {c.cluster: c for c in msg.cards}
        elif isinstance(msg, RevokeSession):
            self.revoked.add(msg.cert_id)
        elif isinstance(msg, Reject):
            p = self.pending.get(msg.inv)
            if p is not None:
                self._finalize(p, "rejected", None)

    # --- request path ------------------------------------------------------------------------------------------
    def _invoke(self, inv: Invocation) -> None:
        p = Pending(inv)
        self.pending[inv.id] = p
        give_up = self.ctx.cfg.voss.router.give_up_s[SLO_CLASSES[int(inv.slo_class)]]
        p.timers.append(self.after(max(0.0, inv.t_arrive + give_up - self.now), self._give_up, inv.id))
        self.after(self.ctx.clock.charge("route", work=max(1, len(self.scheds))), self._route, inv.id)

    def _choose(self, p: Pending) -> int | None:
        live = [c for c in sorted(self.scheds) if c not in p.excluded]
        if not live:
            return None
        cards = tuple(self.cards[c] for c in live if c in self.cards)
        if not cards:
            return live[0]
        lat, lon = self.origins[p.inv.origin]
        rc = self.ctx.cfg.voss.router
        req = RouteRequest(
            (float(lat), float(lon)),
            p.inv.tenant,
            p.inv.fn,
            cards,
            frozenset(p.excluded),
            rc.exposure_s,
            rc.health_s,
            self.ctx.cfg.voss.clusters.slo_theta,
        )
        choice: int | None = self.policy(req, self.gen)
        return choice if choice in self.scheds else live[0]

    def _route(self, inv_id: InvId) -> None:
        p = self.pending.get(inv_id)
        if p is None:
            return
        cluster = self._choose(p)
        if cluster is None:
            self.unrouted.append(inv_id)
            return
        if p.cluster is None:
            self._count_home(p)
        p.cluster, p.t_cluster, p.accepted = cluster, self.now, False
        self._enqueue(inv_id)

    def _count_home(self, p: Pending) -> None:
        lat, lon = self.origins[p.inv.origin]
        home = home_cluster((float(lat), float(lon)), tuple(self.cards[c] for c in sorted(self.cards)))
        if home is not None:
            for key in (str(p.inv.tenant), f"fn:{p.inv.fn}"):
                self.home[(home, key)] = self.home.get((home, key), 0) + 1

    def _enqueue(self, inv_id: InvId) -> None:
        p = self.pending.get(inv_id)
        if p is None or p.cluster not in self.scheds:
            return
        if p.t_first_enqueue is None:
            p.t_first_enqueue = self.now
        self.send(self.scheds[p.cluster][1], Enqueue(p.inv, self.addr, self.now))
        p.timers.append(self.after(self.ctx.cfg.voss.router.T_dispatch, self._watchdog, inv_id))

    def _watchdog(self, inv_id: InvId) -> None:
        """Doc 07 §2: no ``ACCEPTED`` within ``T_dispatch`` → re-send; after ``T_spill`` a sync invocation spills
        over to the next-best cluster (doc 03 §3)."""
        p = self.pending.get(inv_id)
        if p is None or p.accepted:
            return
        rc = self.ctx.cfg.voss.router
        if p.cluster is not None:
            self._stall(p.cluster, inv_id)
        if p.inv.slo_class == SloClass.SYNC and self.now - p.t_cluster >= rc.T_spill and len(self.scheds) > 1:
            assert p.cluster is not None
            if p.cluster in self.scheds:
                self.send(self.scheds[p.cluster][1], Withdraw(inv_id))
            p.excluded.add(p.cluster)
            p.spills += 1
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="spillover", worker=-1, value=float(p.cluster), inv=int(inv_id)
            )
            self._route(inv_id)
        elif p.resends < rc.max_resends:
            p.resends += 1
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="dispatch_watchdog", worker=-1, value=p.resends, inv=int(inv_id)
            )
            self._enqueue(inv_id)

    def _stall(self, cluster: int, inv_id: InvId) -> None:
        """Doc 07 §2 cluster stall: dispatch-watchdog fires for ``stall_n`` distinct invocations of one cluster
        within ``stall_window_s`` → ``STALL`` to the orchestrator (progress evidence, not a heartbeat)."""
        dc = self.ctx.cfg.voss.detection
        if dc.mode != "progress" or cluster not in self.scheds:
            return
        fires = [(t, i) for t, i in self.fires.get(cluster, []) if self.now - t < dc.stall_window_s and i != inv_id]
        fires.append((self.now, inv_id))
        self.fires[cluster] = fires
        if len(fires) >= dc.stall_n and self.now - self.stalled.get(cluster, -1e9) >= dc.stall_window_s:
            self.fires[cluster], self.stalled[cluster] = [], self.now
            epoch = self.scheds[cluster][0]
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="stall", worker=-1, value=float(len(fires)), cluster=cluster
            )
            idle = self.now - self.last_accept.get(cluster, -1e9)
            self.send(self.ctx.directory.orchestrator, Stall(ClusterId(cluster), epoch, len(fires), idle))

    def _scheduler(self, m: SchedulerAddr) -> None:
        cid = int(m.cluster)
        if m.epoch < self.epochs.get(cid, -1):
            return
        self.epochs[cid] = m.epoch
        if m.addr is None:
            self.scheds.pop(cid, None)
            self.cards.pop(cid, None)
        else:
            self.scheds[cid] = (m.epoch, m.addr)
        waiting, self.unrouted = self.unrouted, []
        for inv_id in waiting:
            self._route(inv_id)
        for inv_id, p in sorted(self.pending.items()):
            if p.cluster == cid and p.t_first_enqueue is not None and not p.accepted:
                if m.addr is None:
                    self._route(inv_id)
                else:
                    self._enqueue(inv_id)

    def _assigned(self, m: Assigned) -> None:
        p = self.pending.get(m.inv)
        if p is not None and 0 <= m.cluster != p.cluster:
            self.send(("agent", m.worker), Cancel(m.inv, m.attempt))  # a cluster we spilled away from
            return
        if p is None or m.attempt in p.workers:
            return  # unknown, finished, or a re-announced assignment whose input is already on its way
        p.workers[m.attempt] = m.worker
        self.send(("agent", m.worker), Input(m.inv, m.attempt, m.token, int(p.inv.in_bytes)))

    # --- completion ---------------------------------------------------------------------------------------------
    def _result(self, o: Outcome, r: Receipt) -> None:
        p = self.pending.get(o.inv)
        if p is None:
            if o.inv in self.finished:
                self.ctx.rec.log(
                    Table.EVENTS, t=self.now, kind="duplicate_result", worker=o.worker, value=o.attempt, inv=int(o.inv)
                )
            return
        if r.cert_id in self.revoked or r.inv != o.inv:
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="receipt_rejected", worker=o.worker, value=o.attempt, inv=int(o.inv)
            )
            return
        self.batch.append((r, self.now, self.region))
        self._finalize(p, "ok", o)

    def _give_up(self, inv_id: InvId) -> None:
        p = self.pending.get(inv_id)
        if p is not None:
            self._finalize(p, "timeout", None)

    def finalize_all(self) -> None:
        """End of run: still-pending invocations get a terminal ``unfinished`` row."""
        for _, p in sorted(self.pending.items()):
            self._finalize(p, "unfinished", None)
        self._flush()

    def _finalize(self, p: Pending, status: str, o: Outcome | None) -> None:
        for h in p.timers:
            self.ctx.kernel.cancel(h)
        del self.pending[p.inv.id]
        self.finished.add(p.inv.id)
        r = row(p, self.region, status, o, self.now)
        self.ctx.rec.log(Table.INVOCATIONS, **r)
        if p.cluster is not None:
            s = self.stats.setdefault(p.cluster, [0, 0])
            s[0] += 1
            s[1] += int(not r["met"])

    def _stats_tick(self) -> None:
        if self.stats or self.home:
            stats = tuple((c, n, m) for c, (n, m) in sorted(self.stats.items()))
            home = tuple((c, k, n) for (c, k), n in sorted(self.home.items()))
            self.send(self.ctx.directory.orchestrator, RouterStats(stats, home))
            self.stats, self.home = {}, {}
        self.after(self.ctx.cfg.voss.router.stats_s, self._stats_tick)

    def _flush_tick(self) -> None:
        self._flush()
        self.after(self.ctx.cfg.voss.router.receipt_batch_s, self._flush_tick)

    def _flush(self) -> None:
        if self.batch:
            self.send(self.ctx.directory.opdb, DbAppendReceipts(tuple(self.batch)))
            self.batch = []
