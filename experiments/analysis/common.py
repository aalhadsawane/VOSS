"""Shared analysis helpers: load runs, per-run metrics, bootstrap CIs over seeds (doc 06 §6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from voss.core.rng import stream


def manifest(run: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((run / "manifest.json").read_text())
    return data


def table(run: Path, name: str) -> pd.DataFrame:
    p = run / f"{name}.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def get(cfg: dict[str, Any], dotted: str) -> Any:
    node: Any = cfg
    for part in dotted.split("."):
        node = node[part]
    return node


def bootstrap_ci(x: np.ndarray, n: int = 2000, alpha: float = 0.05) -> tuple[float, float, float]:
    """Mean and percentile bootstrap CI (seeded: analysis is reproducible too)."""
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return (np.nan, np.nan, np.nan)
    g = stream(0, "analysis.bootstrap", len(x))
    means = x[g.integers(0, len(x), (n, len(x)))].mean(axis=1)
    return float(x.mean()), float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def latency_metrics(inv: pd.DataFrame, warmup_s: float = 60.0) -> dict[str, float]:
    """Per-run percentiles first (doc 06 §6), over invocations arriving after the warm-up window."""
    d = inv[inv.t_arrive >= warmup_s]
    ok = d[d.outcome == "ok"]
    sync = ok[ok.slo_class == 0]
    return {
        "n": float(len(d)),
        "success": float((d.outcome == "ok").mean()) if len(d) else np.nan,
        "met": float(d.met.fillna(False).astype(bool).mean()) if len(d) else np.nan,
        "p50_sync": float(sync.e2e.quantile(0.5)) if len(sync) else np.nan,
        "p99_sync": float(sync.e2e.quantile(0.99)) if len(sync) else np.nan,
        "p99_all": float(ok.e2e.quantile(0.99)) if len(ok) else np.nan,
    }


def fmt(m: float, lo: float, hi: float, digits: int = 3) -> str:
    return f"{m:.{digits}f} [{lo:.{digits}f}, {hi:.{digits}f}]"


def report_table(exp: str, df: pd.DataFrame, keys: list[str], cols: list[str], notes: dict[str, str]) -> str:
    """Markdown table: one row per key combination, mean and 95% bootstrap CI over seeds per column."""
    note = "; ".join(f"`{c}` = {notes[c]}" for c in cols if c in notes)
    lines = [
        f"# {exp}",
        "",
        "Mean and 95% bootstrap CI over seeds; warm-up (first 60 s) excluded from latency."
        + (f" {note}." if note else ""),
        "",
        f"| {' | '.join(keys)} | seeds | {' | '.join(cols)} |",
        "|" + "---|" * (len(keys) + 1 + len(cols)),
    ]
    for raw, g in df.groupby(keys[::-1]):
        key = (raw if isinstance(raw, tuple) else (raw,))[::-1]
        cells = [fmt(*bootstrap_ci(g[c].dropna().to_numpy()), digits=3) for c in cols]
        lines.append(f"| {' | '.join(map(str, key))} | {len(g)} | {' | '.join(cells)} |")
    return "\n".join(lines) + "\n"
