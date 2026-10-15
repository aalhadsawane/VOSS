"""P10 figures: the E20 viability maps (three panels), the E23 latency-exposure-robustness Pareto fronts and the E24
calibration-sensitivity bars. Each is a function of the experiment's collected runs; verdicts and fronts come from
``experiments.analysis.viability`` / ``pareto`` (doc 06 §3, §6)."""

from __future__ import annotations

import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle

from experiments.analysis import pareto, viability
from experiments.analysis.common import bootstrap_ci
from experiments.analysis.lib import spec
from experiments.figures import figure

COLORS = {
    "voss_only": "#2c7fb8",
    "voss_better": "#7fcdbb",
    "tie": "#ffffbf",
    "baseline_better": "#fc8d59",
    "none": "#bdbdbd",
}
LEGEND = {
    "voss_only": "only VOSS viable",
    "voss_better": "both viable, VOSS faster",
    "tie": "both viable, tie",
    "baseline_better": "baseline better / only baseline viable",
    "none": "nobody viable",
}


def short(v: object) -> str:
    """Compact axis label for a stringified config value."""
    s = str(v)
    for a, b in (("regime: ", ""), ("adversary_", ""), ("alpha: ", "α="), ("churn_", ""), ("{", ""), ("}", "")):
        s = s.replace(a, b)
    return s.replace(": 1.0", "").replace(", ", "/")


RANK = {"churn_low": 0, "churn_med": 1, "churn_high": 2, "churn_burst": 3, "churn_correlated": 4}
RANK |= {"appliance_tpm": 0, "drtm_hv": 1, "cvm_snp": 2, "coco_pool": 3, "none": 4}


def _sort_key(v: str) -> tuple[float, str]:
    """Semantic order: churn regimes by severity, adversary cells by α, substrates by cost, numbers by value."""
    if v in RANK:
        return (float(RANK[v]), v)
    m = re.search(r"alpha: ([0-9.]+)", v)
    if m:
        return (float(m.group(1)), v)
    if "adversary_none" in v:
        return (0.0, v)
    for name, r in RANK.items():  # a substrate mix like "{cvm_snp: 1.0}"
        if v.startswith("{" + name):
            return (float(r), v)
    try:
        return (float(v), v)
    except ValueError:
        return (0.0, v)


def _order(vals: list[str]) -> list[str]:
    return sorted(set(vals), key=_sort_key)


def viability_map(df: pd.DataFrame, exp: str) -> Figure:
    cell = [k for k in spec(exp)["report"]["keys"] if k != "label"]
    t = viability.cells(df, cell)
    rows, cols = _order(list(t[cell[0]])), _order(list(t[cell[1]]))
    fig, ax = plt.subplots(figsize=(1.6 * len(cols) + 3, 0.9 * len(rows) + 2))
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            sel = t[(t[cell[0]] == r) & (t[cell[1]] == c)]
            if not len(sel):
                continue
            x = sel.iloc[0]
            ax.add_patch(Rectangle((j, i), 1, 1, color=COLORS[x.verdict], ec="white"))
            d = "" if np.isnan(x.d_p99) else f"\nΔP99 {x.d_p99:+.2f}s"
            ax.text(j + 0.5, i + 0.5, f"met {x.voss_met:.2f}{d}", ha="center", va="center", fontsize=8)
    ax.set_xlim(0, len(cols))
    ax.set_ylim(len(rows), 0)
    ax.set_xticks(np.arange(len(cols)) + 0.5, [short(c) for c in cols])
    ax.set_yticks(np.arange(len(rows)) + 0.5, [short(r) for r in rows])
    ax.set_xlabel(cell[1])
    ax.set_ylabel(cell[0])
    ax.legend(handles=[Patch(color=COLORS[k], label=LEGEND[k]) for k in viability.VERDICTS], loc="upper left",
              bbox_to_anchor=(1.01, 1), fontsize=8)  # fmt: skip
    ax.set_title(f"{exp}: VOSS vs best baseline (cell text: VOSS deadline-met fraction)")
    fig.tight_layout()
    return fig


METRICS = ("success", "met", "p50_sync", "p99_sync", "exposure", "waste")


@figure("E20a_map", "E20a", METRICS)
def e20a(df: pd.DataFrame) -> Figure:
    return viability_map(df, "E20a")


@figure("E20b_map", "E20b", METRICS)
def e20b(df: pd.DataFrame) -> Figure:
    return viability_map(df, "E20b")


@figure("E20c_map", "E20c", METRICS)
def e20c(df: pd.DataFrame) -> Figure:
    return viability_map(df, "E20c")


@figure("E23_pareto", "E23", ("success", "p99_sync", "p99_sync_low", "p99_sync_medium", "p99_sync_high", "exposure"))
def e23_pareto(df: pd.DataFrame) -> Figure:
    res = pareto.analyse(pareto.config_means(df))
    fig, axes = plt.subplots(1, 4, figsize=(17, 4), sharey=True)
    fs = sorted(set(res[pareto.KEYS[0]]))
    cmap = dict(zip(fs, ["#4f81bd", "#9bbb59", "#c0504d", "#8064a2"], strict=False))
    for ax, col, ttl in zip(
        axes, ("p99_sync", "p99_sync_low", "p99_sync_medium", "p99_sync_high"), ("all", "low", "medium", "high"),
        strict=True,
    ):  # fmt: skip
        front = pareto.front_mask(res[[col, "exposure"]].to_numpy())
        for _, r in res.iterrows():
            ax.errorbar(r[col], r.exposure, yerr=r.exposure_hw, fmt="o", color=cmap[r[pareto.KEYS[0]]],
                        ms=4 + 3 * np.log10(10 * r[pareto.KEYS[1]]), alpha=0.85)  # fmt: skip
        fr = res[front].sort_values(col)
        ax.plot(fr[col], fr.exposure, "k--", lw=1)
        ax.set_title(f"sync P99, {ttl} sensitivity")
        ax.set_xlabel("P99 (s)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("key-holder exposure")
    axes[0].legend(
        handles=[Patch(color=cmap[f], label=f"f = {f}") for f in fs], fontsize=8, title="marker size ~ λ_exp"
    )
    fig.suptitle("E23 Pareto fronts (dashed), means over seeds with 95% CI on exposure")
    fig.tight_layout()
    return fig


@figure("E24_calibration", "E24", ("success", "met", "p50_sync", "p99_sync"))
def e24_calibration(df: pd.DataFrame) -> Figure:
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    bundles = sorted(set(df.calibration))
    for ax, m in zip(axes, ("p50_sync", "p99_sync", "met"), strict=True):
        for k, lab in enumerate(sorted(set(df.label))):
            for j, b in enumerate(bundles):
                mean, lo, hi = bootstrap_ci(df[(df.label == lab) & (df.calibration == b)][m].dropna().to_numpy())
                ax.bar(
                    k + 0.38 * (j - 0.5), mean, 0.36, yerr=[[mean - lo], [hi - mean]], color=["#4f81bd", "#c0504d"][j]
                )
        ax.set_xticks(range(len(set(df.label))), sorted(set(df.label)))
        ax.set_title(m)
    palette = ["#4f81bd", "#c0504d"]
    axes[0].legend(
        handles=[Patch(color=c, label=b.split("/")[-1]) for c, b in zip(palette, bundles, strict=False)], fontsize=8
    )
    fig.suptitle("E24: placeholder (C0 design values) vs measured stand-in laptop bundle")
    fig.tight_layout()
    return fig
