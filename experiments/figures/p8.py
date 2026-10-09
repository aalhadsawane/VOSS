"""P8 figures: E19 ablations (paired effects, tornado order), E17 commercial comparison, E18 scalability overheads.
Each is a function of the experiment's collected runs (``experiments.analysis.lib``); CIs are 95% bootstrap over
seeds (doc 06 §6)."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from experiments.analysis.common import bootstrap_ci
from experiments.analysis.lib import paired
from experiments.figures import figure


def _ci(g: pd.Series) -> tuple[float, float, float]:
    return bootstrap_ci(g.dropna().to_numpy())


@figure("E19_ablations", "E19", ("p99_sync", "success", "exposure"))
def e19_ablations(df: pd.DataFrame) -> Figure:
    """Tornado: paired change of sync P99 (and success, exposure) when each mechanism is removed."""
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.5), sharey=True)
    d = paired(df, "label", "voss_full", "p99_sync").sort_values("delta")
    order = list(d.label)
    for ax, m, unit in zip(axes, ("p99_sync", "success", "exposure"), ("s", "", ""), strict=True):
        dm = paired(df, "label", "voss_full", m).set_index("label").reindex(order)
        y = np.arange(len(order))
        err = np.abs(np.stack([dm.delta - dm.lo, dm.hi - dm.delta]))
        ax.barh(y, dm.delta, xerr=err, color=np.where(dm.delta > 0, "#c0504d", "#4f81bd"), alpha=0.85)
        ax.axvline(0, color="k", lw=0.8)
        ax.set_title(f"Δ {m}{f' ({unit})' if unit else ''} vs voss_full")
        ax.set_yticks(y, order)
    fig.suptitle("E19 ablations (paired, 95% CI)")
    fig.tight_layout()
    return fig


@figure("E17_commercial", "E17", ("p50_sync", "p99_sync", "success", "cost_per_m"))
def e17_commercial(df: pd.DataFrame) -> Figure:
    """Sync latency and cost per million invocations per system and load."""
    key = next(c for c in df.columns if c.endswith("rate"))
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, m, ttl in zip(
        axes, ("p50_sync", "p99_sync", "cost_per_m"), ("sync P50 (s)", "sync P99 (s)", "USD / M"), strict=True
    ):
        for lab, g in sorted(df.groupby("label")):
            pts = [(float(r), *_ci(gg[m])) for r, gg in g.groupby(key)]
            x, mean, lo, hi = (np.array(v) for v in zip(*sorted(pts), strict=True))
            ax.errorbar(x, mean, yerr=[mean - lo, hi - mean], marker="o", capsize=3, label=lab)
        ax.set_xlabel("load (inv/s)")
        ax.set_title(ttl)
    axes[2].set_yscale("log")
    axes[0].legend()
    fig.suptitle("E17 VOSS vs reference clouds")
    fig.tight_layout()
    return fig


@figure("E18_scalability", "E18", ("workers", "ctrl_msgs_ws", "decide_p99", "orch_cpu_s", "sim_s_per_s", "p99_sync"))
def e18_scalability(df: pd.DataFrame) -> Figure:
    """Overheads against the number of workers (log-log)."""
    cols = (
        ("ctrl_msgs_ws", "control msgs / attested worker / s"),
        ("decide_p99", "placement decide P99 (s)"),
        ("orch_cpu_s", "orchestrator CPU s / s"),
        ("p99_sync", "sync P99 (s)"),
        ("sim_s_per_s", "simulator wall s / simulated s"),
    )
    fig, axes = plt.subplots(1, len(cols), figsize=(18, 3.6))
    for ax, (m, ttl) in zip(axes, cols, strict=True):
        pts = [(n, *_ci(g[m])) for n, g in df.groupby("workers")]
        x, mean, lo, hi = (np.array(v) for v in zip(*sorted(pts), strict=True))
        ax.errorbar(x, mean, yerr=[mean - lo, hi - mean], marker="o", capsize=3)
        ax.set_xscale("log")
        if m in ("orch_cpu_s", "sim_s_per_s"):
            ax.set_yscale("log")
        ax.set_xlabel("workers")
        ax.set_title(ttl, fontsize=9)
    fig.suptitle("E18 scalability")
    fig.tight_layout()
    return fig
