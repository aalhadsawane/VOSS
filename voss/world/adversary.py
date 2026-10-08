"""Adversary behaviors and their precomputed schedules (doc 02 §7).

The trace is ground truth: which worker defects, how, and when. Effects are applied by the runtime (P6) through
``defecting`` and the per-worker parameters; policies never see this module.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from voss.core.config import ScenarioConfig
from voss.core.paths import load_data_yaml
from voss.core.rng import RngFactory
from voss.world.config_merge import merged
from voss.world.workers import WorkerTable

BEHAVIORS: tuple[str, ...] = (
    "benign",
    "omit_random",
    "black_hole",
    "on_off",
    "throttle",
    "fake_signals",
    "replay",
    "colluding_domain",
    "selective",
)
INF = float("inf")


class AdversaryParams(BaseModel):
    """Behavior parameters (doc 02 §7). tag: assumed; swept by E08."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    omit_p: float = Field(default=0.5, ge=0, le=1)
    on_off_good_s: float = Field(default=1800.0, gt=0)
    on_off_bad_s: float = Field(default=600.0, gt=0)
    throttle_f: float = Field(default=0.3, gt=0, le=1)
    fake_drain_rate_per_h: float = Field(default=1.0, ge=0)
    fake_drain_lead_s: float = Field(default=120.0, gt=0)
    replay_rate_per_h: float = Field(default=10.0, ge=0)
    collude_t: float = Field(default=1200.0, ge=0)
    selective_hot_k: int = Field(default=3, ge=1)
    start_t: float = Field(default=0.0, ge=0)


class AdversaryRegime(BaseModel):
    """``configs/regimes/adversary_*.yaml`` merged with inline ``scenario.adversary`` overrides."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    regime: str = "adversary_none"
    alpha: float = Field(default=0.0, ge=0, le=1)
    mix: dict[str, float] = Field(default_factory=dict)
    params: AdversaryParams = Field(default_factory=AdversaryParams)


@dataclass(frozen=True)
class AdversaryTrace:
    """Per-worker behavior, parameters and defection windows ``[start, end)``."""

    behavior: np.ndarray
    omit_p: np.ndarray
    throttle_f: np.ndarray
    windows: tuple[tuple[tuple[float, float], ...], ...]
    params: AdversaryParams

    def name(self, w: int) -> str:
        return BEHAVIORS[int(self.behavior[w])]

    def defecting(self, w: int, t: float) -> bool:
        return any(a <= t < b for a, b in self.windows[w])

    def adversaries(self) -> np.ndarray:
        return np.flatnonzero(self.behavior != 0)

    def to_frame(self) -> pd.DataFrame:
        rows = [
            {"worker": w, "behavior": self.name(w), "start": a, "end": b}
            for w in range(len(self.behavior))
            for a, b in self.windows[w]
        ]
        return pd.DataFrame(rows, columns=["worker", "behavior", "start", "end"])


def load_adversary_regime(sc: ScenarioConfig) -> AdversaryRegime:
    name = str(sc.adversary.get("regime", "adversary_none"))
    return AdversaryRegime.model_validate(merged(load_data_yaml(f"regimes/{name}.yaml"), sc.adversary))


def _counts(n_adv: int, mix: dict[str, float]) -> dict[str, int]:
    """Largest-remainder split of ``n_adv`` by ``mix`` (sorted names for determinism)."""
    names = sorted(k for k, v in mix.items() if v > 0)
    if not names:
        return {}
    total = sum(mix[k] for k in names)
    exact = {k: n_adv * mix[k] / total for k in names}
    out = {k: int(np.floor(v)) for k, v in exact.items()}
    rest = sorted(names, key=lambda k: (-(exact[k] - out[k]), k))
    for k in rest[: n_adv - sum(out.values())]:
        out[k] += 1
    return out


def _colluders(gen: np.random.Generator, domain: np.ndarray, target: int) -> list[int]:
    """Whole failure domains, in random order, until at least ``target`` workers are covered."""
    picked: list[int] = []
    for d in gen.permutation(np.unique(domain)):
        if len(picked) >= target:
            break
        picked.extend(int(w) for w in np.flatnonzero(domain == d))
    return picked


def _windows(beh: str, p: AdversaryParams, horizon: float, gen: np.random.Generator) -> tuple[tuple[float, float], ...]:
    if beh in ("benign", "fake_signals", "replay"):
        return ()
    if beh == "colluding_domain":
        return ((p.collude_t, INF),)
    if beh != "on_off":
        return ((p.start_t, INF),)
    period = p.on_off_good_s + p.on_off_bad_s
    t = p.start_t - gen.random() * period
    out = []
    while t < horizon:
        a, b = t + p.on_off_good_s, t + period
        if b > p.start_t:
            out.append((max(a, p.start_t), b))
        t += period
    return tuple(out)


def _omit_p(behavior: np.ndarray, p: AdversaryParams) -> np.ndarray:
    """Probability of dropping an accepted invocation's result while defecting."""
    full = np.isin(behavior, [BEHAVIORS.index(b) for b in ("black_hole", "on_off", "colluding_domain")])
    partial = np.isin(behavior, [BEHAVIORS.index(b) for b in ("omit_random", "selective")])
    return np.where(full, 1.0, np.where(partial, p.omit_p, 0.0))


def generate_adversaries(sc: ScenarioConfig, workers: WorkerTable, horizon: float, rng: RngFactory) -> AdversaryTrace:
    """Doc 02 §7: assign ``round(α·N)`` adversaries by mix; colluders take whole failure domains."""
    reg = load_adversary_regime(sc)
    n = len(workers)
    gen = rng.stream("adversary.assign")
    counts = _counts(round(reg.alpha * n), reg.mix)
    behavior = np.zeros(n, dtype=np.int64)
    taken = _colluders(gen, workers.domain, counts.pop("colluding_domain", 0))
    behavior[taken] = BEHAVIORS.index("colluding_domain")
    free = gen.permutation(np.setdiff1d(np.arange(n), taken))
    pos = 0
    for name in sorted(counts):
        sel = free[pos : pos + counts[name]]
        behavior[sel] = BEHAVIORS.index(name)
        pos += counts[name]
    g_win = rng.stream("adversary.windows")
    windows = tuple(_windows(BEHAVIORS[b], reg.params, horizon, g_win) for b in behavior)
    return AdversaryTrace(
        behavior=behavior,
        omit_p=_omit_p(behavior, reg.params),
        throttle_f=np.where(behavior == BEHAVIORS.index("throttle"), reg.params.throttle_f, 1.0),
        windows=windows,
        params=reg.params,
    )
