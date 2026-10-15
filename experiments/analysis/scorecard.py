"""Hypothesis scorecard (doc 06 §3, §6): every hypothesis H1-H11, H-FT1 and H-FT3 as one or more *paired* comparisons
between two levels of one factor on the same scenarios, evaluated on the 10-seed runs. Verdicts depend only on the 95%
bootstrap CI of the per-seed difference:

- ``supported``     the CI excludes 0 in the predicted direction by at least the stated relative margin
                    (``equivalent``: the whole CI lies within ± margin of the baseline mean)
- ``weak``          the CI excludes 0 in the predicted direction but the effect is below the margin
- ``inconclusive``  the CI includes 0 (or, for ``equivalent``, is wider than the margin)
- ``refuted``       the CI excludes 0 in the opposite direction (``equivalent``: it lies outside the margin)
- ``no data``       the experiment has no runs

Regimes where the baseline wins therefore appear in the table (doc 06 §6), and ``negative_results`` lists them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.analysis.lib import collect, run_dirs
from experiments.analysis.viability import paired_by_seed


@dataclass(frozen=True)
class Comparison:
    hid: str
    claim: str
    exp: str
    base: str  # level of ``factor`` the effect is measured against
    test: str  # level that is predicted to differ
    metric: str
    kind: str  # lower | higher | equivalent | info
    where: dict[str, str] = field(default_factory=dict)  # column -> substring ("==x" for equality)
    factor: str = "label"
    margin: float = 0.05
    note: str = ""


def select(df: pd.DataFrame, where: dict[str, str]) -> pd.DataFrame:
    for col, want in where.items():
        v = df[col].astype(str)
        df = df[v == want[2:]] if want.startswith("==") else df[v.str.contains(want, regex=False)]
    return df


def evaluate(df: pd.DataFrame, t: Comparison) -> dict[str, object]:
    """Paired difference test - base on the seeds both levels share, inside the filtered cell."""
    d = select(df, t.where) if len(df) else df
    row: dict[str, object] = {
        "id": t.hid,
        "claim": t.claim,
        "exp": t.exp,
        "cmp": f"{t.test} vs {t.base}",
        "cell": ", ".join(f"{k.split('.')[-1]}={v.lstrip('=')}" for k, v in t.where.items()),
        "metric": t.metric,
    }
    if not len(d) or t.test not in set(d[t.factor]) or t.base not in set(d[t.factor]):
        return row | {"verdict": "no data", "delta": np.nan, "lo": np.nan, "hi": np.nan, "base": np.nan, "n": 0}
    g = d.rename(columns={t.factor: "label"}) if t.factor != "label" else d
    delta, lo, hi = paired_by_seed(g, t.test, t.base, t.metric)
    base = float(g[g.label == t.base][t.metric].mean())
    n = len(set(g[g.label == t.test].seed) & set(g[g.label == t.base].seed))
    return row | {"verdict": verdict(t, delta, lo, hi, base), "delta": delta, "lo": lo, "hi": hi, "base": base, "n": n}


def verdict(t: Comparison, delta: float, lo: float, hi: float, base: float) -> str:
    m = t.margin * abs(base)
    if t.kind == "info":
        return "info"
    if t.kind == "equivalent":
        if -m <= lo and hi <= m:
            return "supported"
        return "refuted" if lo > m or hi < -m else "inconclusive"
    sign = -1.0 if t.kind == "lower" else 1.0  # predicted sign of (test - base)
    lo_s, hi_s = (lo, hi) if sign > 0 else (-hi, -lo)  # predicted direction made positive
    if lo_s > 0:
        return "supported" if sign * delta >= m else "weak"
    return "refuted" if hi_s < 0 else "inconclusive"


COMPARISONS: tuple[Comparison, ...] = (
    Comparison(
        "H1",
        "MILP planner cuts sync P99 vs no planning",
        "E04",
        "plan_none",
        "plan_milp",
        "p99_sync",
        "lower",
        {"scenario.regime": "==churn_med"},
    ),
    Comparison(
        "H1",
        "MILP planner cuts sync P99 vs no planning",
        "E04",
        "plan_none",
        "plan_milp",
        "p99_sync",
        "lower",
        {"scenario.regime": "==churn_high"},
    ),
    Comparison(
        "H1",
        "... and vs keep-alive TTL",
        "E04",
        "keepalive_ttl",
        "plan_milp",
        "p99_sync",
        "lower",
        {"scenario.regime": "==churn_med"},
        note="not at equal donor memory: see the warm_mb row",
    ),
    Comparison(
        "H1",
        "... and vs keep-alive TTL",
        "E04",
        "keepalive_ttl",
        "plan_milp",
        "p99_sync",
        "lower",
        {"scenario.regime": "==churn_high"},
    ),
    Comparison(
        "H1",
        "donor memory held warm: MILP vs keep-alive TTL (cost side)",
        "E04",
        "keepalive_ttl",
        "plan_milp",
        "warm_mb",
        "info",
        {"scenario.regime": "==churn_med"},
    ),
    Comparison(
        "H2",
        "f-robust plans keep success where non-robust collapse (α=0.2 mixed)",
        "E08",
        "voss",
        "f0",
        "success",
        "lower",
        {"scenario.adversary": "=={alpha: 0.2, regime: adversary_mixed}"},
        margin=0.005,
    ),
    Comparison(
        "H4",
        "progress detection beats heartbeat-only on success under α=0.2",
        "E08",
        "voss",
        "heartbeat_only",
        "success",
        "lower",
        {"scenario.adversary": "=={alpha: 0.2, regime: adversary_mixed}"},
        margin=0.005,
    ),
    Comparison(
        "H6",
        "GDSF + P2P + HDD tier beat LRU without P2P/HDD (sync P99)",
        "E09",
        "gdsf_p2p_hdd",
        "lru_no_p2p_no_hdd",
        "p99_sync",
        "higher",
    ),
    Comparison("H6", "... GDSF vs LRU alone", "E09", "gdsf_p2p_hdd", "lru", "p99_sync", "higher"),
    Comparison(
        "H7",
        "geo clusters reduce sync P99 vs one global scheduler (EU)",
        "E05",
        "none_global",
        "dynamic",
        "p99_sync",
        "lower",
        {"scenario.geo.regions": "==[eu]"},
    ),
    Comparison(
        "H7", "... EU+NA", "E05", "none_global", "dynamic", "p99_sync", "lower", {"scenario.geo.regions": "==[eu, na]"}
    ),
    Comparison(
        "H7", "... world", "E05", "none_global", "dynamic", "p99_sync", "lower", {"scenario.geo.regions": "==[]"}
    ),
    Comparison(
        "H8",
        "planner MILP beats greedy by ≥5% sync P99 (high churn)",
        "E04",
        "plan_greedy",
        "plan_milp",
        "p99_sync",
        "lower",
        {"scenario.regime": "==churn_high"},
        margin=0.05,
    ),
    Comparison(
        "H9",
        "distribution-aware (quantile) beats expectation-only on P99 at high churn",
        "E03",
        "expected",
        "quantile",
        "p99_sync",
        "lower",
        {"scenario.regime": "==churn_high", "voss.predictor.name": "==blr"},
        factor="voss.cost.scalarizer",
    ),
    Comparison(
        "H10",
        "accounting is off the critical path: settlement period 10 s vs 300 s",
        "E13",
        "s10_b1",
        "s300_b1",
        "p99_sync",
        "equivalent",
        {"scenario.faults": "==[]"},
        margin=0.05,
    ),
    Comparison(
        "H10",
        "... receipt batch 0.2 s vs 5 s",
        "E13",
        "s60_b02",
        "s60_b5",
        "p99_sync",
        "equivalent",
        {"scenario.faults": "==[]"},
        margin=0.05,
    ),
    Comparison(
        "H11",
        "simple baseline matches VOSS when homogeneous, stable and benign",
        "E10",
        "voss",
        "simple",
        "p99_sync",
        "equivalent",
        {"scenario.hw_mix": "=={C1: 1.0}"},
        margin=0.1,
    ),
    Comparison(
        "H-FT1",
        "progress detection vs heartbeat-only: success with a black-holed scheduler",
        "E15",
        "heartbeat_only",
        "progress",
        "success",
        "higher",
        {"scenario.faults": "sched_blackhole"},
        margin=0.01,
    ),
    Comparison(
        "H-FT3",
        "risk-proportional hedging (θ=.3, 5%) cuts sync P99 under α=0.1",
        "E16",
        "hedge_off",
        "rp_t03_b005",
        "p99_sync",
        "lower",
        {"scenario.adversary": "=={alpha: 0.1, regime: adversary_mixed}"},
    ),
    Comparison(
        "H-FT3",
        "... at what extra-attempt cost",
        "E16",
        "hedge_off",
        "rp_t03_b005",
        "waste",
        "info",
        {"scenario.adversary": "=={alpha: 0.1, regime: adversary_mixed}"},
    ),
    Comparison(
        "RQ15",
        "VOSS vs Lambda-like reference, sync P99 at 20 inv/s",
        "E17",
        "ref_lambda_like",
        "voss",
        "p99_sync",
        "info",
        {"scenario.load.rate": "==20"},
    ),
)


def order_key(hid: pd.Series) -> pd.Series:
    """H1..H11, then H-FT1.., then RQ rows (a natural order, not alphabetical)."""
    return hid.map(
        lambda h: (1 if h.startswith("H-") else 2 if h.startswith("RQ") else 0, int(re.sub(r"\D", "", h) or 0))
    )


def run_all(root: Path, tests: tuple[Comparison, ...] = COMPARISONS) -> pd.DataFrame:
    frames: dict[str, pd.DataFrame] = {}
    rows = []
    for t in tests:
        if t.exp not in frames:
            has = (root / t.exp).exists() and bool(run_dirs(t.exp, root))
            frames[t.exp] = collect(t.exp, root) if has else pd.DataFrame()
        df = frames[t.exp]
        rows.append(evaluate(df, t) if len(df) else evaluate(pd.DataFrame(columns=["label"]), t))
    return pd.DataFrame(rows)


def markdown(sc: pd.DataFrame) -> str:
    lines = [
        "# Hypothesis scorecard",
        "",
        "Paired by seed on the same scenarios; Δ = test − baseline with its 95% bootstrap CI; relative to the baseline "
        "mean. Verdict rules: `experiments/analysis/scorecard.py`.",
        "",
        "| H | Claim | Experiment | Cell | Comparison | Metric | n | Δ [95% CI] | Δ rel | Verdict |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in sc.iterrows():
        if r.verdict == "no data":
            lines.append(f"| {r.id} | {r.claim} | {r.exp} | {r.cell} | {r.cmp} | {r.metric} | 0 | | | no data |")
            continue
        rel = f"{100 * r.delta / r.base:+.1f}%" if r.base else ""
        ci = "" if np.isnan(r.lo) else f" [{r.lo:+.3g}, {r.hi:+.3g}]"
        lines.append(
            f"| {r.id} | {r.claim} | {r.exp} | {r.cell} | {r.cmp} | {r.metric} | {r.n} | "
            f"{r.delta:+.3g}{ci} | {rel} | {r.verdict} |"
        )
    return "\n".join(lines) + "\n"


def negative_results(sc: pd.DataFrame) -> str:
    bad = sc[sc.verdict.isin(["refuted", "inconclusive", "weak"])]
    lines = ["# Negative and inconclusive results (scorecard)", ""]
    if not len(bad):
        return "\n".join([*lines, "None: every scorecard comparison with a prediction was supported.", ""])
    lines += ["| H | Claim | Experiment | Cell | Comparison | Δ rel | Verdict |", "|---|---|---|---|---|---|---|"]
    for _, r in bad.iterrows():
        rel = f"{100 * r.delta / r.base:+.1f}%"
        if not np.isnan(r.lo):
            rel += f" [{100 * r.lo / r.base:+.1f}, {100 * r.hi / r.base:+.1f}]"
        lines.append(
            f"| {r.id} | {r.claim} | {r.exp} | {getattr(r, 'cell', '')} | {r.cmp} ({r.metric}) | {rel} | {r.verdict} |"
        )
    return "\n".join([*lines, ""])
