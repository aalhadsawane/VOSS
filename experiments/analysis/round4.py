"""Round-4 analysis (docs/architecture/06-experiments.md §8): E04b and E25 against the pre-registered hypotheses H12-H16.

Reads raw run directories (``runs/E04b``, ``runs/E25``), computes per-run metrics with a 300 s warm-up, pairs systems by
seed (same scenario hash), and reports the mean of per-seed ratios with a paired bootstrap 95% CI, the median ratio and a
Wilcoxon signed-rank p-value. Usage: ``python -m experiments.analysis.round4 E04b|E25 [out.csv]``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

from experiments.analysis.common import bootstrap_ci, latency_metrics, manifest, table

WARMUP_S = 300.0


def per_run(exp: str) -> pd.DataFrame:
    """One row per run: label, seed, regime/cell keys, P99 sync, success, met, warm_mb, exposure, trust-cold share."""
    idx = pd.read_csv(Path("runs") / exp / "index.csv")
    rows = []
    for r in idx[idx.status.isin(["ok", "cached"])].itertuples():
        run = Path(r.run_dir)
        cfg = manifest(run)["config"]
        inv, cache = table(run, "invocations"), table(run, "cache")
        m = latency_metrics(inv, WARMUP_S)
        late = cache[cache.t >= WARMUP_S]
        sync = inv[(inv.t_arrive >= WARMUP_S) & (inv.slo_class == 0) & (inv.outcome == "ok")]
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
            }
        )
    return pd.DataFrame(rows)


def paired(df: pd.DataFrame, cell: str, cand: str, ref: str, col: str = "p99") -> dict[str, float]:
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
    return {"n": float(len(s)), "mean_ratio": mean, "lo": lo, "hi": hi, "median_ratio": float(np.median(ratio)), "wilcoxon_p": p}


def boot_p(ratio: np.ndarray, bound: float, n: int = 10000) -> float:
    """One-sided bootstrap p-value for H0: mean ratio >= bound (small = evidence that the ratio is below the bound)."""
    from voss.core.rng import stream

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
    return (a[s] / b[s]).to_numpy()


def hypotheses(df: pd.DataFrame) -> pd.DataFrame:
    """H12-H15 (pre-registered thresholds, Holm over the eight P99 comparisons)."""
    rows, pv = [], {}
    for reg, margin in (("churn_med", 1.05), ("churn_high", 1.10)):
        single = {k: df[(df.regime == reg) & (df.label == k)].p99.mean() for k in ("keepalive_ttl", "keepalive_inf", "hist_prewarm")}
        best = min(single, key=lambda k: single[k])
        tests = {
            f"H12 {reg}: plan_greedy / {best}": (ratios(df, reg, "plan_greedy", best), 0.95),
            f"H13 {reg}: erlang_greedy / plan_greedy": (ratios(df, reg, "erlang_greedy", "plan_greedy"), margin),
            f"H14b {reg}: erlang_dpp / erlang_greedy": (ratios(df, reg, "erlang_dpp", "erlang_greedy"), 1.05),
            f"H15 {reg}: plan_greedy / provisioned_keys": (ratios(df, reg, "plan_greedy", "provisioned_keys"), 0.95),
        }
        for name, (r, bound) in tests.items():
            m, lo, hi = bootstrap_ci(r, n=10000)
            pv[name] = boot_p(r, bound)
            rows.append({"test": name, "n": len(r), "mean_ratio": m, "ci_lo": lo, "ci_hi": hi, "median": float(np.median(r)),
                         "bound": bound, "p_boot": pv[name], "seeds_below_1": int((r < 1).sum())})
    ok = holm(pv)
    out = pd.DataFrame(rows)
    out["holm_supported"] = out.test.map(ok)
    for reg in ("churn_med", "churn_high"):
        for col in ("warm_mb", "exposure"):
            r = ratios(df, reg, "erlang_greedy", "plan_greedy", col)
            print(f"H13 {reg} {col}: erlang_greedy / plan_greedy mean ratio {r.mean():.3f}")
    return out


def summary(df: pd.DataFrame, key: str) -> pd.DataFrame:
    g = df.groupby([key, "label"])
    out = g.agg(n=("seed", "size"), p99=("p99", "mean"), p99_med=("p99", "median"), success=("success", "mean"),
                met=("met", "mean"), warm_gb=("warm_mb", lambda x: x.mean() / 1e3), exposure=("exposure", "mean"))
    return out.round(3)


def main(argv: list[str]) -> int:
    exp = argv[0]
    df = per_run(exp)
    if len(argv) > 1:
        df.to_csv(argv[1], index=False)
    key = "regime" if exp == "E04b" else "churn"
    pd.set_option("display.width", 200)
    print(summary(df, key).to_string())
    if exp == "E04b":
        print(hypotheses(df).round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
