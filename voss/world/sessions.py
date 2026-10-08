"""Donation sessions: availability ground truth (doc 02 §2).

A worker alternates ``OFF ⇄ SESSION``. Starts follow per-tier processes in *local* time; lengths are heavy-tailed;
ends are graceful (drain notice with lead time) or abrupt; regional shocks end many sessions at once; identities
join and leave the platform. Fake drain notices come from ``fake_signals`` adversaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from voss.core.config import ScenarioConfig
from voss.core.dist import Dist, LogNormal
from voss.core.paths import load_data_yaml
from voss.core.rng import RngFactory
from voss.world.config_merge import merged
from voss.world.geo import Metros, diurnal, local_hour
from voss.world.workers import TIERS, WorkerTable


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TierModel(_M):
    """Session process of one tier."""

    kind: Literal["nightly", "poisson", "always"]
    start_hour: float = 23.0
    start_sd_h: float = 1.5
    p_night: float = Field(default=0.8, ge=0, le=1)
    rate_per_h: float = Field(default=0.15, ge=0)
    peak_h: float = 14.0
    amplitude: float = Field(default=0.6, ge=0, le=1)
    length: Dist
    gap: Dist = LogNormal(median=300.0, sigma=0.5)
    min_off_s: float = Field(default=60.0, ge=0)


class ShockModel(_M):
    rate_per_h: float = Field(default=0.0, ge=0)
    frac: float = Field(default=0.5, ge=0, le=1)
    scope: Literal["city", "region"] = "city"


class PlatformModel(_M):
    late_join_frac: float = Field(default=0.0, ge=0, le=1)
    leave_rate_per_day: dict[str, float] = Field(default_factory=dict)


class SessionRegime(_M):
    """``configs/regimes/churn_*.yaml`` merged with ``scenario.churn`` overrides."""

    regime: str
    tiers: dict[str, TierModel]
    graceful_frac: float = Field(ge=0, le=1)
    drain_lead: Dist
    shocks: ShockModel = Field(default_factory=ShockModel)
    platform: PlatformModel = Field(default_factory=PlatformModel)


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
    return SessionRegime.model_validate(merged(load_data_yaml(f"regimes/{sc.regime}.yaml"), sc.churn))


def _nightly(tm: TierModel, tz: float, lo: float, hi: float, start_utc_h: float, g: np.random.Generator) -> list[float]:
    out: list[float] = []
    first_day = int(np.floor((lo / 3600 + start_utc_h + tz) / 24)) - 1
    last_day = int(np.ceil((hi / 3600 + start_utc_h + tz) / 24)) + 1
    for day in range(first_day, last_day + 1):
        if g.random() < tm.p_night:
            h = tm.start_hour + tm.start_sd_h * g.standard_normal()
            out.append((day * 24 + h - tz - start_utc_h) * 3600)
    return out


def _poisson_next(tm: TierModel, tz: float, t: float, start_utc_h: float, g: np.random.Generator) -> float:
    """Next start of a non-homogeneous Poisson process (thinning) in local time."""
    lam_max = tm.rate_per_h * (1 + tm.amplitude) / 3600
    if lam_max <= 0:
        return np.inf
    while True:
        t += g.exponential(1 / lam_max)
        f = diurnal(local_hour(tz, t, start_utc_h), tm.peak_h, tm.amplitude)
        if g.random() * (1 + tm.amplitude) <= float(f):
            return t


def _worker_sessions(
    tm: TierModel, tz: float, lo: float, hi: float, start_utc_h: float, g: np.random.Generator
) -> list[tuple[float, float]]:
    """Non-overlapping ``(start, end)`` intervals for one worker over ``[lo, hi)``."""
    out: list[tuple[float, float]] = []
    if tm.kind == "nightly":
        for s in _nightly(tm, tz, lo, hi, start_utc_h, g):
            e = s + float(tm.length.sample(g))
            if (not out or s >= out[-1][1] + tm.min_off_s) and e > lo and s < hi:
                out.append((s, e))
        return out
    t = lo - (float(tm.length.sample(g)) if tm.kind == "always" else 0.0)
    while t < hi:
        s = t + float(tm.gap.sample(g)) if tm.kind == "always" else _poisson_next(tm, tz, t, start_utc_h, g)
        if s >= hi:
            break
        e = s + float(tm.length.sample(g))
        if e > lo:
            out.append((s, e))
        t = e + tm.min_off_s
    return out


def _platform(
    reg: SessionRegime, workers: WorkerTable, horizon: float, g: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    n = len(workers)
    late = g.random(n) < reg.platform.late_join_frac
    join = np.where(late, g.random(n) * horizon, -np.inf)
    rate = np.array([reg.platform.leave_rate_per_day.get(TIERS[t], 0.0) for t in workers.tier]) / 86400
    life = np.where(rate > 0, g.exponential(1 / np.maximum(rate, 1e-300)), np.inf)
    return join, np.maximum(join, 0.0) + life


def _shocks(
    reg: SessionRegime,
    sess: pd.DataFrame,
    area: np.ndarray,
    area_w: np.ndarray,
    span: tuple[float, float],
    g: np.random.Generator,
) -> None:
    """Regional shocks: end a fraction ``frac`` of the sessions live in the shocked area at the shock time."""
    sh = reg.shocks
    lo, hi = span
    if sh.rate_per_h <= 0 or sess.empty:
        return
    times = np.sort(lo + (hi - lo) * g.random(g.poisson(sh.rate_per_h * (hi - lo) / 3600)))
    w_area = area[sess.worker.to_numpy()]
    for ts in times:
        a = g.choice(len(area_w), p=area_w)
        hit = (w_area == a) & (sess.start.to_numpy() <= ts) & (sess.end.to_numpy() > ts)
        hit &= g.random(len(sess)) < sh.frac
        late_drain = hit & ~(sess.drain_t.to_numpy() < ts)
        sess.loc[hit, "end"] = ts
        sess.loc[hit, "reason"] = "shock"
        sess.loc[late_drain, "drain_t"] = np.nan


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


def _areas(workers: WorkerTable, metros: Metros, scope: str) -> tuple[np.ndarray, np.ndarray]:
    if scope == "city":
        return workers.city, metros.weights()
    names = sorted(set(metros.region))
    reg_of_city = np.array([names.index(r) for r in metros.region])
    w = np.array([metros.pop[reg_of_city == i].sum() for i in range(len(names))])
    return reg_of_city[workers.city], w / w.sum()


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
    join, leave = _platform(reg, workers, horizon, rng.stream("sessions.platform"))
    rows: list[tuple[int, float, float]] = []
    for w in range(len(workers)):
        tm = reg.tiers[TIERS[int(workers.tier[w])]]
        g = rng.stream("sessions.worker", w)
        for s0, e0 in _worker_sessions(tm, float(workers.tz[w]), lo, horizon, sc.start_utc_h, g):
            s, e = max(s0, join[w]), min(e0, leave[w])
            if e > s:
                rows.append((w, s, e))
    sess = pd.DataFrame(rows, columns=["worker", "start", "end"])
    _ends(reg, sess, rng.stream("sessions.ends"))
    area, area_w = _areas(workers, metros, reg.shocks.scope)
    _shocks(reg, sess, area, area_w, (lo, horizon), rng.stream("sessions.shocks"))
    left = sess.end.to_numpy() >= leave[sess.worker.to_numpy()]
    sess.loc[left, "reason"] = "leave"
    fakes = _fake_drains(sess, fake[0], fake[1], fake[2], rng.stream("sessions.fake"))
    return SessionTrace(sess.reset_index(drop=True), fakes, join, leave)
