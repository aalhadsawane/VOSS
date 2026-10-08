"""E03 pilot report: predictor accuracy/calibration (online, time-ordered) and P99 by predictor × scalarizer ×
churn (doc 06 §5). Writes ``docs/pilots/E03.md``."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.analysis.common import bootstrap_ci, fmt, get, latency_metrics, manifest, table

KEYS = ("voss.predictor.name", "voss.cost.scalarizer", "scenario.regime")


def prediction_metrics(pred: pd.DataFrame) -> dict[str, float]:
    """MAE of log runtime and 90% interval coverage from logged (mean, var) of the chosen worker."""
    p = pred[(pred.pred_mean > 0) & (pred.actual > 0)]
    if p.empty:
        return {"mae_log": np.nan, "cov90": np.nan, "mae_log_late": np.nan}
    s2 = np.log1p(p.pred_var / p.pred_mean**2)
    mu = np.log(p.pred_mean) - s2 / 2
    z = (np.log(p.actual) - mu) / np.sqrt(np.maximum(s2, 1e-12))
    err = np.abs(np.log(p.actual) - mu)
    late = err[len(err) // 2 :]
    return {
        "mae_log": float(err.mean()),
        "cov90": float((np.abs(z) <= 1.645).mean()),
        "mae_log_late": float(late.mean()),
    }


def online_curve(pred: pd.DataFrame, bins: int = 4) -> list[float]:
    """Time-ordered evaluation: MAE of log runtime in consecutive quarters of the run (doc 03 §6.1)."""
    p = pred[(pred.pred_mean > 0) & (pred.actual > 0)].sort_values("t")
    if len(p) < bins:
        return [np.nan] * bins
    s2 = np.log1p(p.pred_var / p.pred_mean**2)
    err = np.abs(np.log(p.actual) - (np.log(p.pred_mean) - s2 / 2)).to_numpy()
    return [float(x.mean()) for x in np.array_split(err, bins)]


def collect(runs: list[Path]) -> pd.DataFrame:
    rows = []
    for r in runs:
        cfg = manifest(r)["config"]
        row = {k: get(cfg, k) for k in KEYS} | {"seed": cfg["seed"]}
        pred = table(r, "predictions")
        row |= latency_metrics(table(r, "invocations")) | prediction_metrics(pred)
        row |= {f"mae_q{i + 1}": v for i, v in enumerate(online_curve(pred))}
        rows.append(row)
    return pd.DataFrame(rows)


def report(df: pd.DataFrame) -> str:
    lines = [
        "# E03 pilot: predictors × scalarizations",
        "",
        "Pilot (doc 06 §5); mean and 95% bootstrap CI over seeds; per-run metrics first (doc 06 §6).",
        "",
        "| predictor | scalarizer | regime | seeds | MAE log (late half) | 90% coverage | P99 sync (s) | met |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, g in df.groupby(list(KEYS)):
        cells = [fmt(*bootstrap_ci(g[c].to_numpy())) for c in ("mae_log_late", "cov90", "p99_sync", "met")]
        lines.append(f"| {' | '.join(map(str, key))} | {len(g)} | {' | '.join(cells)} |")
    lines += [
        "",
        "## Online predictor evaluation (time-ordered)",
        "",
        "MAE of log execution time per quarter of the run, all scalarizers and regimes pooled per predictor "
        "(mean over runs). Decreasing values show online learning from the profile prior.",
        "",
        "| predictor | Q1 | Q2 | Q3 | Q4 | 90% coverage |",
        "|---|---|---|---|---|---|",
    ]
    for name, g in df.groupby(KEYS[0]):
        qs = " | ".join(f"{g[f'mae_q{i}'].mean():.3f}" for i in range(1, 5))
        lines.append(f"| {name} | {qs} | {g.cov90.mean():.3f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("runs", type=Path, nargs="+")
    p.add_argument("--out", type=Path, default=Path("docs/pilots/E03.md"))
    a = p.parse_args()
    df = collect(sorted(d for r in a.runs for d in ([r] if (r / "manifest.json").exists() else r.iterdir())))
    a.out.write_text(report(df))
    df.to_csv(a.out.with_suffix(".csv"), index=False)
    print(a.out)


if __name__ == "__main__":
    main()
