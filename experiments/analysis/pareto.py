"""E23 latency × exposure × robustness Pareto fronts (doc 06 §5, RQ3/RQ4, H3). Each configuration (exposure weight ×
robustness level f) is a point with three outcomes, all to be minimised: sync P99, key-holder exposure and the
failure rate ``1 - success`` under attack. Fronts are computed on the per-configuration means over seeds, overall
and per tenant sensitivity class (latency of that class's tenants); the knee of the latency-exposure front is the point
farthest from the chord between its extremes after min-max scaling.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from experiments.analysis.common import bootstrap_ci

KEYS = ["voss.planner.f_from_alpha", "voss.planner.params.exposure_weight"]
CLASSES = ("low", "medium", "high")


def config_means(df: pd.DataFrame, keys: list[str] = KEYS) -> pd.DataFrame:
    """Mean and CI half-width per configuration for the outcome metrics."""
    df = df.assign(**{k: pd.to_numeric(df[k]) for k in keys})  # collect() returns config values as strings
    rows = []
    for raw, g in df.groupby(keys):
        key = raw if isinstance(raw, tuple) else (raw,)
        row: dict[str, object] = dict(zip(keys, key, strict=True)) | {"n": len(g)}
        for m in ("p99_sync", "p99_sync_low", "p99_sync_medium", "p99_sync_high", "exposure", "success", "waste"):
            if m in g:
                mean, lo, hi = bootstrap_ci(g[m].dropna().to_numpy())
                row[m], row[f"{m}_hw"] = mean, (hi - lo) / 2
        row["fail"] = 1.0 - float(row["success"])  # type: ignore[arg-type]
        rows.append(row)
    return pd.DataFrame(rows)


def front_mask(points: np.ndarray) -> np.ndarray:
    """True for rows not dominated by another row (all columns minimised; ties do not dominate)."""
    n = len(points)
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        dom = np.all(points <= points[i], axis=1) & np.any(points < points[i], axis=1)
        keep[i] = not dom.any()
    return keep


def knee(points: np.ndarray) -> int:
    """Index (into ``points``, a 2-column latency-exposure front) farthest from the chord between its extremes."""
    if len(points) < 3:
        return 0
    span = points.max(axis=0) - points.min(axis=0)
    p = (points - points.min(axis=0)) / np.where(span > 0, span, 1.0)
    order = np.argsort(p[:, 0])
    a, b = p[order[0]], p[order[-1]]
    chord = b - a
    norm = float(np.hypot(*chord)) or 1.0
    dist = np.abs(chord[0] * (p[:, 1] - a[1]) - chord[1] * (p[:, 0] - a[0])) / norm
    return int(np.argmax(dist))


def analyse(means: pd.DataFrame) -> pd.DataFrame:
    """Add front membership (3-D and per class) and the knee flag of the overall latency-exposure front."""
    out = means.copy()
    out["front3"] = front_mask(out[["p99_sync", "exposure", "fail"]].to_numpy())
    for c in CLASSES:
        col = f"p99_sync_{c}"
        if col in out and out[col].notna().all():
            out[f"front_{c}"] = front_mask(out[[col, "exposure"]].to_numpy())
    f2 = front_mask(out[["p99_sync", "exposure"]].to_numpy())
    out["front2"], out["knee"] = f2, False
    idx = np.flatnonzero(f2)
    if len(idx):
        out.loc[out.index[idx[knee(out.iloc[idx][["p99_sync", "exposure"]].to_numpy())]], "knee"] = True
    return out


def markdown(res: pd.DataFrame, keys: list[str] = KEYS) -> str:
    lines = [
        "# E23 latency × exposure × robustness",
        "",
        "Means over seeds (± 95% CI half-width); `front` = not dominated in (sync P99, exposure, 1 − success); "
        "`front2` = latency-exposure front; `knee` = farthest from its chord. Per-class columns are the sync P99 "
        "of that sensitivity class's tenants.",
        "",
        "| f | exposure weight | P99 | P99 low | P99 med | P99 high | exposure | success | front | front2 | knee |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in res.sort_values(keys).iterrows():
        lines.append(
            f"| {r[keys[0]]} | {r[keys[1]]} | {r.p99_sync:.3f} ± {r.p99_sync_hw:.3f} | {r.p99_sync_low:.2f} | "
            f"{r.p99_sync_medium:.2f} | {r.p99_sync_high:.2f} | {r.exposure:.1f} ± {r.exposure_hw:.1f} | "
            f"{r.success:.4f} | {'yes' if r.front3 else ''} | {'yes' if r.front2 else ''} | "
            f"{'knee' if r.knee else ''} |"
        )
    return "\n".join(lines) + "\n"
