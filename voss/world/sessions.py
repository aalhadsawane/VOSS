"""Donation sessions: availability ground truth (doc 02 §2; plan V9.2).

Every worker replays one traced host's week of availability intervals (the SETI@home trace, Failure Trace Archive
seti09). Ends are graceful (a drain notice with lead time) or abrupt; whether a session ends with notice is not in the
data, so ``graceful_frac`` is an axis. Fake drain notices come from ``fake_signals`` adversaries. The v1 synthetic
per-tier session process and its regional shocks are deleted (checklist 2.9); the trace carries the correlation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from voss.core.config import ScenarioConfig
from voss.core.dist import Dist, LogNormal
from voss.core.paths import REPO_ROOT, load_data_yaml
from voss.core.rng import RngFactory
from voss.world.config_merge import merged
from voss.world.geo import Metros
from voss.world.workers import WorkerTable


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionRegime(_M):
    """``configs/regimes/churn_*.yaml`` merged with ``scenario.churn`` overrides."""

    regime: str = ""
    graceful_frac: float = Field(default=0.5, ge=0, le=1)
    drain_lead: Dist = LogNormal(median=120.0, sigma=0.7)
    # traced availability (plan V9.2): data/traces/<trace>/sessions_<split>.parquet from tools/traces/fta.py; each
    # worker replays one sampled host's week of availability intervals, repeated to cover the run.
    trace: str = ""
    trace_root: str = "data/traces"
    split: str = "dev"


@dataclass(frozen=True)
class SessionTrace:
    """Sessions as intervals plus fake drains and platform membership (doc 01 §4 ``SessionTrace``)."""

    sessions: pd.DataFrame  # worker, start, end, drain_t (NaN if abrupt), reason
    fake_drains: pd.DataFrame  # worker, t, deadline
    join_t: np.ndarray
    leave_t: np.ndarray

    def active_at(self, t: float) -> np.ndarray:
        s = self.sessions
        return np.unique(s.worker[(s.start <= t) & (s.end > t)].to_numpy())

    def events(self) -> pd.DataFrame:
        """Time-sorted events: SESSION_START, DRAIN_NOTICE, SESSION_END (``deadline``, ``is_fake``, ``graceful``)."""
        s, f = self.sessions, self.fake_drains
        g = s[s.drain_t.notna()]
        nan = np.nan
        parts = [
            pd.DataFrame(
                {"t": s.start, "kind": "SESSION_START", "worker": s.worker, "deadline": nan, "is_fake": False}
            ),
            pd.DataFrame(
                {"t": g.drain_t, "kind": "DRAIN_NOTICE", "worker": g.worker, "deadline": g.end, "is_fake": False}
            ),
            pd.DataFrame({"t": s.end, "kind": "SESSION_END", "worker": s.worker, "deadline": nan, "is_fake": False}),
            pd.DataFrame(
                {"t": f.t, "kind": "DRAIN_NOTICE", "worker": f.worker, "deadline": f.deadline, "is_fake": True}
            ),
        ]
        ev = pd.concat([p for p in parts if len(p)], ignore_index=True)
        order = {"SESSION_END": 0, "SESSION_START": 1, "DRAIN_NOTICE": 2}
        ev["_o"] = ev.kind.map(order)
        return ev.sort_values(["t", "_o", "worker"], kind="stable").drop(columns="_o").reset_index(drop=True)


def load_session_regime(sc: ScenarioConfig) -> SessionRegime:
    name = str(sc.regime)
    base = load_data_yaml(f"regimes/{name}.yaml") if name else {}
    return SessionRegime.model_validate(merged(base, sc.churn))


def _ends(reg: SessionRegime, sess: pd.DataFrame, g: np.random.Generator) -> None:
    """Graceful ends get a drain notice ``lead`` seconds before the end (lead clipped to the session)."""
    n = len(sess)
    graceful = g.random(n) < reg.graceful_frac
    lead = np.minimum(np.asarray(reg.drain_lead.sample(g, n)), (sess.end - sess.start).to_numpy())
    sess["drain_t"] = np.where(graceful, sess.end.to_numpy() - lead, np.nan)
    sess["reason"] = np.where(graceful, "graceful", "abrupt")


def _fake_drains(
    sessions: pd.DataFrame, fake_workers: np.ndarray, rate_per_h: float, lead_s: float, g: np.random.Generator
) -> pd.DataFrame:
    rows = []
    for row in sessions[sessions.worker.isin(fake_workers)].itertuples():
        lo, hi = max(row.start, 0.0), row.end
        if hi <= lo:
            continue
        for t in np.sort(lo + (hi - lo) * g.random(g.poisson(rate_per_h * (hi - lo) / 3600))):
            rows.append((row.worker, float(t), float(t) + lead_s))
    return pd.DataFrame(rows, columns=["worker", "t", "deadline"])


WEEK_S = 7 * 86400.0


def _traced_rows(
    reg: SessionRegime, n: int, lo: float, hi: float, g: np.random.Generator
) -> list[tuple[int, float, float]]:
    """Each worker takes one traced host (a random assignment, without repeats while hosts last) and replays its week
    of intervals, shifted by whole weeks to cover ``[lo, hi)``."""
    if not reg.trace:
        raise ValueError("a run needs a traced session regime (scenario.regime or scenario.churn.trace; D-107, V9.2)")
    d = Path(reg.trace_root) / reg.trace / f"sessions_{reg.split}.parquet"
    tab = pd.read_parquet(d if d.is_absolute() else REPO_ROOT / d)
    hosts = np.sort(tab.host.unique())
    by_host = {int(h): grp[["start_s", "end_s"]].to_numpy() for h, grp in tab.groupby("host", sort=True)}
    order = g.permutation(len(hosts))
    rows: list[tuple[int, float, float]] = []
    for w in range(n):
        iv = by_host[int(hosts[order[w % len(hosts)]])]
        for k in range(int(np.floor(lo / WEEK_S)), int(np.ceil(hi / WEEK_S)) + 1):
            for s0, e0 in iv:
                s, e = max(s0 + k * WEEK_S, lo), min(e0 + k * WEEK_S, hi)
                if e > s:
                    rows.append((w, float(s), float(e)))
    return rows


def generate_sessions(
    sc: ScenarioConfig,
    workers: WorkerTable,
    metros: Metros,
    horizon: float,
    rng: RngFactory,
    fake: tuple[np.ndarray, float, float] = (np.zeros(0, np.int64), 0.0, 0.0),
) -> SessionTrace:
    """Doc 02 §2 over ``[-warmup, horizon)``; ``fake = (workers, rate_per_h, lead_s)`` for fake drain notices."""
    reg = load_session_regime(sc)
    lo = -sc.warmup_s
    rows = _traced_rows(reg, len(workers), lo, horizon, rng.stream("sessions.trace"))
    sess = pd.DataFrame(rows, columns=["worker", "start", "end"])
    _ends(reg, sess, rng.stream("sessions.ends"))
    n = len(workers)
    join, leave = np.zeros(n), np.full(n, np.inf)
    fakes = _fake_drains(sess, fake[0], fake[1], fake[2], rng.stream("sessions.fake"))
    return SessionTrace(sess.reset_index(drop=True), fakes, join, leave)
