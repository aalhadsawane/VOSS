"""Round-4 analysis (docs/architecture/06-experiments.md §8): E04b and E25 against the pre-registered H12-H16.

Reads raw run directories (``runs/E04b``, ``runs/E25``), computes per-run metrics with a 300 s warm-up, pairs systems by
seed (same scenario hash), and reports the mean of per-seed ratios with a paired bootstrap 95% CI, the median and a
Wilcoxon signed-rank p-value. Usage: ``python -m experiments.analysis.round4 E04b|E25 [out.csv]``;
``... amort <csv> <runs dir>`` adds the key-release amortisation columns from ``events.parquet``.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
from voss.core.rng import stream

from experiments.analysis.common import bootstrap_ci, latency_metrics, manifest, table

PLAIN_NAMES = {  # one plain name per system, used in the paper's table and figure (doc 06 §8)
    "plan_none": "On demand",
    "keepalive_ttl": "Keep-alive, 10 min",
    "keepalive_inf": "Keep-alive, unbounded",
    "hist_prewarm": "Histogram keep-alive",
    "provisioned_keys": "Early keys",
    "plan_greedy": "Greedy provisioning",
    "plan_milp": "Exact provisioning",
    "erlang_greedy": "Loss-model provisioning",
    "erlang_dpp": "Loss-model, exposure budget",
}

WARMUP_S = 300.0
SINGLE_LOOPS = ("keepalive_ttl", "keepalive_inf", "hist_prewarm")
E25_SHAPES = (0.6, 1.0)
E25_MULTS = (0.25, 1.0, 4.0)


def amortisation(run: Path) -> dict[str, float]:
    """Key-release amortisation of one run: synchronous requests served per ``key_release`` event (doc 04 §6; the
    tenant key broker logs one per released key, i.e. per (worker session, tenant)), counted after the warm-up and over
    the whole run. NaN when ``events.parquet`` is absent (the E04b release archive carries it, ``runs/`` may not)."""
    nan = {"sync_served": np.nan, "key_releases": np.nan, "sync_per_release": np.nan, "sync_per_release_all": np.nan}
    if not (run / "events.parquet").exists():
        return nan
    inv, ev = table(run, "invocations"), table(run, "events")
    ok = inv[(inv.slo_class == 0) & (inv.outcome == "ok")]
    rel = ev[ev.kind == "key_release"]
    late_n, late_k = int((ok.t_arrive >= WARMUP_S).sum()), int((rel.t >= WARMUP_S).sum())
    return {
        "sync_served": float(late_n),
        "key_releases": float(late_k),
        "sync_per_release": late_n / late_k if late_k else np.nan,
        "sync_per_release_all": len(ok) / len(rel) if len(rel) else np.nan,
    }


def add_amortisation(df: pd.DataFrame, runs: Path) -> pd.DataFrame:
    """Merge ``amortisation`` of every run under ``runs`` (``index.csv`` + run dirs) into a per-run frame, keyed by
    (label, scenario hash): a seed repeats across regimes, so (label, seed) is not unique."""
    idx = pd.read_csv(runs / "index.csv")
    idx = idx[idx.status.isin(["ok", "cached"])]
    rows = [
        {"label": r.label, "scenario_hash": r.scenario_hash, **amortisation(runs / Path(r.run_dir).name)}
        for r in idx.itertuples()
    ]
    keep = [c for c in df.columns if c not in rows[0] or c in ("label", "scenario_hash")]
    return df[keep].merge(pd.DataFrame(rows), on=["label", "scenario_hash"], how="left", validate="1:1")


def per_run(
    exp: str,
    warmup_s: float = WARMUP_S,
    root: Path = Path("runs"),
    extra: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """One row per run: label, seed, regime/cell keys, P99 sync, success, met, warm_mb, exposure, trust-cold share.

    ``warmup_s`` is the warm-up window (300 s for the round-4 specs, 60 s for the pilot reruns E10b/E17b/E20ab/E24b),
    ``root`` the directory holding ``<exp>/index.csv`` and the run directories, ``extra`` adds per-run columns from
    the run directory and its config (grid keys, cost)."""
    idx = pd.read_csv(root / exp / "index.csv")
    rows = []
    for r in idx[idx.status.isin(["ok", "cached"])].itertuples():
        run = root / exp / Path(r.run_dir).name
        cfg = manifest(run)["config"]
        inv, cache = table(run, "invocations"), table(run, "cache")
        m = latency_metrics(inv, warmup_s)
        late = cache[cache.t >= warmup_s]
        sync = inv[(inv.t_arrive >= warmup_s) & (inv.slo_class == 0) & (inv.outcome == "ok")]
        cold = float((sync.trust > 0).mean()) if "trust" in sync and len(sync) else np.nan
        rows.append(
            {
                "label": r.label,
                "seed": int(r.seed),
                "regime": cfg["scenario"].get("regime"),
                "churn": str(cfg["scenario"].get("churn")),
                "p99": m["p99_sync"],
                "p50": m["p50_sync"],
                "success": m["success"],
                "met": m["met"],
                "warm_mb": float(late.warm_mb.mean()),
                "exposure": float(late.exposure.mean()),
                "trust_cold": cold,
                "scenario_hash": r.scenario_hash,
                **amortisation(run),
                **(extra(run, cfg) if extra else {}),
            }
        )
    return pd.DataFrame(rows)


def paired(df: pd.DataFrame, cell: tuple[str, Any], cand: str, ref: str, col: str = "p99") -> dict[str, float]:
    """Ratio candidate/reference per seed within one cell (same scenario hash), summarised."""
    a = df[(df[cell[0]] == cell[1]) & (df.label == cand)].set_index("seed")[col]
    b = df[(df[cell[0]] == cell[1]) & (df.label == ref)].set_index("seed")[col]
    s = a.index.intersection(b.index)
    ratio = (a[s] / b[s]).to_numpy()
    mean, lo, hi = bootstrap_ci(ratio, n=10000)
    try:
        p = float(wilcoxon(a[s] - b[s]).pvalue)
    except ValueError:
        p = float("nan")
    return {
        "n": float(len(s)),
        "mean_ratio": mean,
        "lo": lo,
        "hi": hi,
        "median_ratio": float(np.median(ratio)),
        "wilcoxon_p": p,
    }


def boot_p(ratio: np.ndarray, bound: float, n: int = 10000) -> float:
    """One-sided bootstrap p-value for H0: mean ratio >= bound (small = evidence that the ratio is below the bound)."""
    g = stream(0, "analysis.round4.p", len(ratio))
    means = ratio[g.integers(0, len(ratio), (n, len(ratio)))].mean(axis=1)
    return float((means >= bound).mean())


def holm(pvals: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm step-down: reject the smallest p while p_i <= alpha / (m - i)."""
    out, m = {}, len(pvals)
    stop = False
    for i, (k, p) in enumerate(sorted(pvals.items(), key=lambda kv: kv[1])):
        stop = stop or p > alpha / (m - i)
        out[k] = not stop
    return out


def ratios(df: pd.DataFrame, regime: str, cand: str, ref: str, col: str = "p99") -> np.ndarray:
    a = df[(df.regime == regime) & (df.label == cand)].set_index("seed")[col]
    b = df[(df.regime == regime) & (df.label == ref)].set_index("seed")[col]
    s = a.index.intersection(b.index)
    return np.asarray((a[s] / b[s]).to_numpy(), dtype=float)


def hypotheses(df: pd.DataFrame) -> pd.DataFrame:
    """H12-H15 (pre-registered thresholds, Holm over the eight P99 comparisons)."""
    rows, pv = [], {}
    for reg, margin in (("churn_med", 1.05), ("churn_high", 1.10)):
        best = best_single(df, reg)
        tests = {
            f"H12 {reg}: plan_greedy / {best}": (ratios(df, reg, "plan_greedy", best), 0.95),
            f"H13 {reg}: erlang_greedy / plan_greedy": (ratios(df, reg, "erlang_greedy", "plan_greedy"), margin),
            f"H14b {reg}: erlang_dpp / erlang_greedy": (ratios(df, reg, "erlang_dpp", "erlang_greedy"), 1.05),
            f"H15 {reg}: plan_greedy / provisioned_keys": (ratios(df, reg, "plan_greedy", "provisioned_keys"), 0.95),
        }
        for name, (r, bound) in tests.items():
            m, lo, hi = bootstrap_ci(r, n=10000)
            pv[name] = boot_p(r, bound)
            rows.append(
                {
                    "test": name,
                    "n": len(r),
                    "mean_ratio": m,
                    "ci_lo": lo,
                    "ci_hi": hi,
                    "median": float(np.median(r)),
                    "bound": bound,
                    "p_boot": pv[name],
                    "seeds_below_1": int((r < 1).sum()),
                }
            )
    ok = holm(pv)
    out = pd.DataFrame(rows)
    out["holm_supported"] = out.test.map(ok)
    return out


def h13_resources(df: pd.DataFrame) -> dict[tuple[str, str], float]:
    """H13 secondary criteria: mean paired ratio erlang_greedy / plan_greedy of warm memory and exposure per regime."""
    return {
        (reg, col): float(ratios(df, reg, "erlang_greedy", "plan_greedy", col).mean())
        for reg in ("churn_med", "churn_high")
        for col in ("warm_mb", "exposure")
    }


def best_single(df: pd.DataFrame, regime: str) -> str:
    """Best single loop of a regime: lowest mean P99 of the three single-loop baselines (chosen on the test seeds)."""
    single = {k: df[(df.regime == regime) & (df.label == k)].p99.mean() for k in SINGLE_LOOPS}
    return min(single, key=lambda k: single[k])


def e25_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``M`` (session-length multiple) and ``k`` (idle-tier Weibull shape) parsed from the churn column."""
    out = df.copy()
    mult = {5400.0: 0.25, 21600.0: 1.0, 86400.0: 4.0}
    parsed = [ast.literal_eval(s)["tiers"] for s in out.churn]
    out["M"] = [mult[float(t["nightly"]["length"]["median"])] for t in parsed]
    out["k"] = [float(t["idle"]["length"]["shape"]) for t in parsed]
    return out


def e25_get(df: pd.DataFrame, m: float, k: float, label: str) -> pd.Series:
    """P99 per seed of one system in one (M, k) cell (``df`` from ``e25_cells``)."""
    return df[(m == df.M) & (df.k == k) & (df.label == label)].set_index("seed").p99


def e25_best(df: pd.DataFrame, m: float, k: float) -> str:
    """Best single loop of an E25 cell (lowest mean P99 of keepalive_inf, hist_prewarm)."""
    return min(("keepalive_inf", "hist_prewarm"), key=lambda lab: e25_get(df, m, k, lab).mean())


def e25_advantage(df: pd.DataFrame, m: float, k: float) -> np.ndarray:
    """Per-seed advantage A = 1 - P99(plan_greedy) / P99(best single loop) in cell (M, k)."""
    return np.asarray(
        (1 - e25_get(df, m, k, "plan_greedy") / e25_get(df, m, k, e25_best(df, m, k))).to_numpy(), dtype=float
    )


def e25_blind(df: pd.DataFrame, m: float, k: float) -> np.ndarray:
    """Per-seed survival dependence B = P99(plan_greedy_blind) / P99(plan_greedy) - 1 in cell (M, k)."""
    return np.asarray(
        (e25_get(df, m, k, "plan_greedy_blind") / e25_get(df, m, k, "plan_greedy") - 1).to_numpy(), dtype=float
    )


def e25_table(df: pd.DataFrame) -> pd.DataFrame:
    """H16 table: A and B with bootstrap CIs per (k, M)."""
    rows = []
    for k in E25_SHAPES:
        for m in E25_MULTS:
            a, b = bootstrap_ci(e25_advantage(df, m, k), n=10000), bootstrap_ci(e25_blind(df, m, k), n=10000)
            rows.append(
                {
                    "k": k,
                    "M": m,
                    "best": e25_best(df, m, k),
                    "A": a[0],
                    "A_lo": a[1],
                    "A_hi": a[2],
                    "B": b[0],
                    "B_lo": b[1],
                    "B_hi": b[2],
                }
            )
    return pd.DataFrame(rows)


def e25_differences(df: pd.DataFrame, k: float) -> dict[float, tuple[float, float, float]]:
    """A(M=1) - A(M) with bootstrap CI for M in (0.25, 4) at shape ``k`` (H16a)."""
    ref = e25_advantage(df, 1.0, k)
    return {m: bootstrap_ci(ref - e25_advantage(df, m, k), n=10000) for m in (0.25, 4.0)}


def summary(df: pd.DataFrame, key: str) -> pd.DataFrame:
    g = df.groupby([key, "label"])
    out = g.agg(
        n=("seed", "size"),
        p99=("p99", "mean"),
        p99_med=("p99", "median"),
        success=("success", "mean"),
        met=("met", "mean"),
        warm_gb=("warm_mb", lambda x: x.mean() / 1e3),
        exposure=("exposure", "mean"),
    )
    return out.round(3)


def main(argv: list[str]) -> int:
    if argv[0] == "amort":  # amort <per-run csv> <runs dir with events.parquet>: add the amortisation columns in place
        csv = Path(argv[1])
        add_amortisation(pd.read_csv(csv), Path(argv[2])).to_csv(csv, index=False)
        return 0
    exp = argv[0]
    df = per_run(exp)
    if len(argv) > 1:
        df.to_csv(argv[1], index=False)
    key = "regime" if exp == "E04b" else "churn"
    pd.set_option("display.width", 200)
    print(summary(df, key).to_string())
    if exp == "E04b":
        print(hypotheses(df).round(3).to_string())
        for (reg, col), v in h13_resources(df).items():
            print(f"H13 {reg} {col}: erlang_greedy / plan_greedy mean ratio {v:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
