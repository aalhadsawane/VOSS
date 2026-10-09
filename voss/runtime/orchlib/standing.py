"""Identity standing at the orchestrator (doc 09 §2, doc 08 §3 ``reputation``): declared-tier commitments,
verified work from settlements, the schedulers' omission summaries and cache accruals; tie-break scores pushed to
the schedulers and logged; scheduler-role records written for scheduler credit (doc 09 §4)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from voss.core.ids import Addr, ClusterId, WorkerId
from voss.core.messages_acct import DbAccrual, ReportEvents, ReputationScores, RoleRecord, Settled
from voss.core.registry import create
from voss.metrics.schema import Table
from voss.policy import reputation as _rep  # noqa: F401  (registers reputation rules)
from voss.policy.reputation import RepParams, Standing, decayed, newcomer, tie_break_scores
from voss.runtime.actor import ActorContext
from voss.runtime.orchlib.book import Book, Cluster


class StandingMixin:
    ctx: ActorContext
    book: Book

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def after(self, dt: float, fn: Any, *args: Any) -> Any: ...

    def _init_standing(self) -> None:
        rc = self.ctx.cfg.voss.reputation
        self.rep_rule: Any = create("reputation", rc.name)
        self.rep_p = RepParams(rc.half_life_h * 3600, rc.prior, rc.quantile, rc.probation_h * 3600, rc.explore_floor)
        self.standing: dict[WorkerId, Standing] = {}
        self.declared: dict[WorkerId, tuple[str, float]] = {}  # declared tier and session start
        self.scores: dict[int, float] = {}
        self.share: dict[int, float] = {}  # share of the last settlement's verified work
        self.after(rc.push_s, self._push_scores)

    def _credit(self, w: WorkerId, good: float, bad: float, reason: str) -> None:
        s = self.standing.get(w) or newcomer(self.now, self.rep_p)
        self.standing[w] = self.rep_rule.update(s, self.now, good, bad, self.rep_p)
        if bad > 0:
            self.ctx.rec.log(Table.EVENTS, t=self.now, kind="rep_penalty", worker=w, value=bad, reason=reason)

    def _session_start(self, w: WorkerId, tier: str) -> None:
        self.declared[w] = (tier, self.now)
        self.standing.setdefault(w, newcomer(self.now, self.rep_p))

    def _session_end(self, w: WorkerId, abrupt: bool) -> None:
        """A session shorter than the declared tier's commitment is a breach (half weight with a graceful notice);
        session ends never count otherwise, except in the ``survival_informed`` variant (doc 09 §1)."""
        rc = self.ctx.cfg.voss.reputation
        tier, start = self.declared.pop(w, ("", self.now))
        commit = rc.commit_s.get(tier, 0.0)
        if commit > 0 and self.now - start < commit:
            self._credit(w, 0.0, rc.breach_w.get(tier, 1.0) * (1.0 if abrupt else 0.5), f"breach_{tier}")
        elif abrupt and self.rep_rule.survival_inputs:
            self._credit(w, 0.0, 1.0, "abrupt_end")
        else:
            self._credit(w, rc.honor_w, 0.0, "honored")

    def _report_events(self, m: ReportEvents) -> None:
        c = self.book.clusters.get(int(m.cluster))
        if c is None or m.epoch != c.epoch:
            return  # scheduler writes are epoch-fenced (doc 08 §3.2)
        rc = self.ctx.cfg.voss.reputation
        rows = tuple(("cache", w, mb_s) for w, mb_s in m.pinned_mb_s if w in c.members and mb_s > 0)
        if rows:
            self.send(self.ctx.directory.opdb, DbAccrual(rows))
        for w in m.change_points:
            self._credit(w, 0.0, rc.change_point_w, "change_point")
        for w in m.suspects:
            self._credit(w, 0.0, rc.suspect_w, "suspect")

    def _settled(self, m: Settled) -> None:
        rc = self.ctx.cfg.voss.reputation
        total = sum(a + b for _, a, b in m.rows)
        self.share = {int(w): (a + b) / total for w, a, b in m.rows} if total > 0 else {}
        for w, on_time, late in m.rows:
            self._credit(w, rc.result_w * on_time, rc.late_w * late, "late")

    def _push_scores(self) -> None:
        delay = self.ctx.clock.charge("orchestrate", work=len(self.standing))
        states = {int(w): s for w, s in self.standing.items()}
        self.scores = tie_break_scores(self.rep_rule, states, self.now, self.rep_p)
        cap = self.ctx.cfg.voss.reputation.share_cap
        capped = {w for w, sh in self.share.items() if sh > cap and len(self.share) * cap >= 1.0}
        for w in capped:  # concentration guard (doc 09 §2): no bonus for identities already holding a large share
            self.scores[w] = 0.0
        hl = self.rep_p.half_life_s if self.rep_rule.decays else math.inf
        for w in sorted(self.standing):
            s = decayed(self.standing[w], self.now, hl, self.rep_p.prior)
            tier = self.declared.get(w, ("", 0.0))[0]
            self.ctx.rec.log(
                Table.REPUTATION, t=self.now, worker=int(w), alpha=s.alpha, beta=s.beta, score=self.scores[int(w)],
                tier=tier, active=w in self.book.members, capped=int(w) in capped,
            )  # fmt: skip
        for cid in sorted(self.book.clusters):
            self.after(delay, self._send_scores, cid)
        self.after(self.ctx.cfg.voss.reputation.push_s, self._push_scores)

    def _send_scores(self, cid: int) -> None:
        c = self.book.clusters.get(cid)
        if c is None or c.holder is None:
            return
        scores = tuple((w, self.scores[int(w)]) for w in sorted(c.members) if int(w) in self.scores)
        self.send(("sched", c.holder[0]), ReputationScores(ClusterId(cid), c.epoch, scores))

    def _role_record(self, c: Cluster, holder: WorkerId, standby: WorkerId | None, epoch: int) -> None:
        self.send(self.ctx.directory.opdb, RoleRecord(ClusterId(c.cid), epoch, holder, standby, self.now))
