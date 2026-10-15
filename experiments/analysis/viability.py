"""E20 viability maps (doc 06 §5, RQ1): for every cell of a regime grid, is each system viable (meets the SLO targets
with confidence over seeds), and how does VOSS compare with the best baseline there? Pure functions of a collected
frame (``experiments.analysis.lib.collect``): columns ``label``, the cell keys, ``seed`` and the run metrics.

A system is *viable* in a cell when the lower 95% bootstrap bound of its mean success is at least ``SUCCESS_MIN`` and
of its mean deadline-met fraction at least ``MET_MIN``. Verdicts (one per cell, VOSS against the best baseline: the
viable baseline with the lowest mean sync P99):

- ``voss_only``       VOSS viable, no baseline is
- ``voss_better``     both viable, VOSS has the lower sync P99 (paired by seed, 95% CI excludes 0)
- ``tie``             both viable, difference within the CI
- ``baseline_better`` both viable and the baseline is lower, or only a baseline is viable
- ``none``            nobody is viable
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from experiments.analysis.common import bootstrap_ci

SUCCESS_MIN = 0.99
MET_MIN = 0.95
SENSITIVITY = (0.90, 0.95, 0.98)
P99_TARGETS = (2.0, 3.0, 5.0)  # absolute sync-P99 SLOs (s) for the alternative viability definition
VERDICTS = ("voss_only", "voss_better", "tie", "baseline_better", "none")


def _lo(x: pd.Series) -> float:
    return bootstrap_ci(x.dropna().to_numpy())[1]


def system_stats(
    df: pd.DataFrame, cell: list[str], met_min: float = MET_MIN, p99_max: float | None = None
) -> pd.DataFrame:
    """Mean, lower CI bound and viability per cell and system."""
    rows = []
    for (*c, label), g in df.groupby([*cell, "label"]):
        row = dict(zip(cell, c, strict=True)) | {"label": label, "n": len(g)}
        for m in ("success", "met", "p50_sync", "p99_sync", "exposure", "waste"):
            if m in g:
                row[m] = float(g[m].mean())
        row["success_lo"], row["met_lo"] = _lo(g.success), _lo(g.met)
        ok = row["met_lo"] >= met_min if p99_max is None else row["p99_sync"] <= p99_max
        row["viable"] = bool(row["success_lo"] >= SUCCESS_MIN and ok)
        rows.append(row)
    return pd.DataFrame(rows)


def paired_by_seed(g: pd.DataFrame, a: str, b: str, m: str) -> tuple[float, float, float]:
    """Mean and 95% CI of ``m(a) - m(b)`` over the seeds both systems ran."""
    pa = g[g.label == a].set_index("seed")[m]
    pb = g[g.label == b].set_index("seed")[m]
    both = pa.index.intersection(pb.index)
    return bootstrap_ci((pa.loc[both] - pb.loc[both]).dropna().to_numpy())


def verdict(df_cell: pd.DataFrame, stats: pd.DataFrame, focal: str) -> tuple[str, str, float, float, float]:
    """(verdict, best baseline, Δ sync P99 = focal - baseline with its CI; informational if only one is viable)."""
    by = stats.set_index("label")
    base = by.drop(index=focal, errors="ignore")
    ok = base[base.viable]
    best = str(ok.p99_sync.idxmin()) if len(ok) else (str(base.met.idxmax()) if len(base) else "")
    f_ok = bool(by.loc[focal].viable) if focal in by.index else False
    d, lo, hi = paired_by_seed(df_cell, focal, best, "p99_sync") if best and focal in by.index else (np.nan,) * 3
    if not f_ok:
        return ("baseline_better" if len(ok) else "none"), best, d, lo, hi
    if not len(ok):
        return "voss_only", best, d, lo, hi
    if hi < 0:
        return "voss_better", best, d, lo, hi
    return ("baseline_better" if lo > 0 else "tie"), best, d, lo, hi


def cells(
    df: pd.DataFrame, cell: list[str], focal: str = "voss", met_min: float = MET_MIN, p99_max: float | None = None
) -> pd.DataFrame:
    """One row per cell: verdict, VOSS and best-baseline statistics (``p99_max``: viable = latency SLO instead)."""
    stats = system_stats(df, cell, met_min, p99_max)
    out = []
    for raw, g in df.groupby(cell):
        key = raw if isinstance(raw, tuple) else (raw,)
        mask = np.logical_and.reduce([stats[c] == v for c, v in zip(cell, key, strict=True)])
        v, best, d, lo, hi = verdict(g, stats[mask], focal)
        f = stats[mask & (stats.label == focal)]
        b = stats[mask & (stats.label == best)]
        out.append(
            dict(zip(cell, key, strict=True))
            | {
                "verdict": v,
                "best_baseline": best,
                "voss_met": float(f.met.iloc[0]) if len(f) else np.nan,
                "voss_success": float(f.success.iloc[0]) if len(f) else np.nan,
                "voss_p99": float(f.p99_sync.iloc[0]) if len(f) else np.nan,
                "base_met": float(b.met.iloc[0]) if len(b) else np.nan,
                "base_p99": float(b.p99_sync.iloc[0]) if len(b) else np.nan,
                "d_p99": d,
                "d_lo": lo,
                "d_hi": hi,
            }
        )
    return pd.DataFrame(out)


def markdown(
    exp: str, cell: list[str], table: pd.DataFrame, stats: pd.DataFrame, df: pd.DataFrame | None = None
) -> str:
    """Per-cell verdict table plus the per-system statistics."""
    n = int(stats.n.max()) if len(stats) else 0
    lines = [
        f"# {exp} viability map",
        "",
        f"Viable = lower 95% bootstrap bound over {n} seeds of mean success ≥ {SUCCESS_MIN} and of deadline-met "
        f"fraction ≥ {MET_MIN}. Δ P99 = VOSS − best viable baseline (sync, s, paired by seed).",
        "",
        f"| {' | '.join(cell)} | verdict | best baseline | VOSS met | VOSS P99 | base met | base P99 | Δ P99 [CI] |",
        "|" + "---|" * (len(cell) + 7),
    ]
    for _, r in table.iterrows():
        d = "" if np.isnan(r.d_p99) else f"{r.d_p99:+.3f} [{r.d_lo:+.3f}, {r.d_hi:+.3f}]"
        cells_ = " | ".join(str(r[c]) for c in cell)
        lines.append(
            f"| {cells_} | {r.verdict} | {r.best_baseline} | {r.voss_met:.3f} | {r.voss_p99:.2f} | "
            f"{r.base_met:.3f} | {r.base_p99:.2f} | {d} |"
        )
    counts = table.verdict.value_counts().reindex(list(VERDICTS), fill_value=0)
    lines += ["", "Cells by verdict: " + ", ".join(f"{k} {v}" for k, v in counts.items()), ""]
    if df is not None:
        lines += [
            "Sensitivity to the deadline-met target (cells by verdict):",
            "",
            "| target | " + " | ".join(VERDICTS) + " |",
        ]
        lines += ["|" + "---|" * (len(VERDICTS) + 1)]
        for target in SENSITIVITY:
            c = cells(df, cell, met_min=target).verdict.value_counts().reindex(list(VERDICTS), fill_value=0)
            lines.append(f"| {target} | " + " | ".join(str(int(c[v])) for v in VERDICTS) + " |")
        lines += [
            "",
            "Alternative definition: success lower bound ≥ 0.99 and mean sync P99 ≤ target (absolute latency SLO):",
            "",
        ]
        lines += ["| P99 target (s) | " + " | ".join(VERDICTS) + " |", "|" + "---|" * (len(VERDICTS) + 1)]
        for target in P99_TARGETS:
            c = cells(df, cell, p99_max=target).verdict.value_counts().reindex(list(VERDICTS), fill_value=0)
            lines.append(f"| {target} | " + " | ".join(str(int(c[v])) for v in VERDICTS) + " |")
        lines += [
            "",
            "`baseline_better` also covers cells where only the baseline reaches the target although VOSS's sync "
            "P99 is lower: the target is deadline hits across all classes, P99 is the sync tail.",
            "",
        ]
    return "\n".join(lines)
