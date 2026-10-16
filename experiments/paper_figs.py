"""Manuscript figures (IEEE column widths) drawn from the committed per-seed and per-cell tables in ``paper/tables``:
the three E20 viability panels in one row, the E23 Pareto fronts, the E19 ablation tornado and the E18 scalability
curves. ``python -m experiments.paper_figs`` writes ``manuscript/figures/*.pdf`` (deterministic: no creation date).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle

from experiments.analysis import pareto
from experiments.analysis.common import bootstrap_ci
from experiments.analysis.viability import VERDICTS, paired_by_seed
from experiments.figures.p10 import COLORS, _order, short

REPO = Path(__file__).resolve().parents[1]
T = REPO / "paper" / "tables"
COL, TWO = 3.5, 7.16  # IEEE column and page widths in inches
LABELS = {
    "voss_only": "only VOSS viable",
    "voss_better": "both viable, VOSS lower P99",
    "tie": "both viable, tie",
    "baseline_better": "only baseline viable",
    "none": "nobody viable",
}


def style() -> None:
    plt.rcParams.update(
        {
            "font.size": 7,
            "axes.labelsize": 7,
            "axes.titlesize": 7.5,
            "legend.fontsize": 6.5,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "pdf.fonttype": 42,
            "axes.linewidth": 0.6,
            "lines.linewidth": 1.0,
        }
    )


def save(fig: Figure, out: Path, name: str) -> Path:
    path = out / f"{name}.pdf"
    fig.savefig(path, bbox_inches="tight", metadata={"CreationDate": None, "Title": name})
    plt.close(fig)
    return path


def panel(ax: Axes, t: pd.DataFrame, cell: list[str], title: str, xlabel: str, ylabel: str) -> None:
    rows, cols = _order(list(t[cell[0]].astype(str))), _order(list(t[cell[1]].astype(str)))
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            sel = t[(t[cell[0]].astype(str) == r) & (t[cell[1]].astype(str) == c)]
            if not len(sel):
                continue
            x = sel.iloc[0]
            ax.add_patch(Rectangle((j, i), 1, 1, color=COLORS[x.verdict], ec="white", lw=0.8))
            ax.text(j + 0.5, i + 0.5, f"{x.voss_p99:.1f}", ha="center", va="center", fontsize=6)
    ax.set_xlim(0, len(cols))
    ax.set_ylim(len(rows), 0)
    ax.set_xticks(
        np.arange(len(cols)) + 0.5,
        [short(c).replace("/mixed", "").replace("mixed ", "").replace("none α=0", "none") for c in cols],
        rotation=0,
    )
    ax.set_yticks(np.arange(len(rows)) + 0.5, [short(r) for r in rows])
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)


def viability_fig(out: Path) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(TWO, 2.15), gridspec_kw={"width_ratios": [1, 1.25, 1]})
    spec = (
        (
            "E20a",
            ["scenario.adversary", "scenario.regime"],
            "(a) churn regime $\\times$ adversaries",
            "churn regime",
            "adversaries",
        ),
        (
            "E20b",
            ["scenario.substrate_mix", "scenario.load.rate"],
            "(b) substrate $\\times$ load",
            "offered load (inv/s)",
            "substrate",
        ),
        (
            "E20c",
            ["scenario.workers", "scenario.load.rate"],
            "(c) population $\\times$ load",
            "offered load (inv/s)",
            "workers",
        ),
    )
    for ax, (exp, cell, title, xl, yl) in zip(axes, spec, strict=True):
        t = pd.read_csv(T / f"{exp}.csv")
        if exp == "E20a":  # rows are churn regimes, columns adversary cells
            panel(ax, t, ["scenario.regime", "scenario.adversary"], title, "adversaries", "churn regime")
        else:
            panel(ax, t, cell, title, xl, yl)
    fig.legend(
        handles=[Patch(color=COLORS[v], label=LABELS[v]) for v in VERDICTS],
        loc="lower center",
        ncol=5,
        frameon=False,
        bbox_to_anchor=(0.5, -0.07),
    )
    fig.tight_layout()
    return save(fig, out, "fig_viability")


def pareto_fig(out: Path) -> Path:
    res = pareto.analyse(
        pd.read_csv(T / "E23.csv").drop(
            columns=["front3", "front_low", "front_medium", "front_high", "front2", "knee"], errors="ignore"
        )
    )
    fig, axes = plt.subplots(1, 3, figsize=(TWO, 1.9), sharey=True)
    colors = {0.0: "#4f81bd", 0.1: "#9bbb59", 0.2: "#c0504d"}
    for ax, col, ttl in zip(
        axes, ("p99_sync_low", "p99_sync_medium", "p99_sync_high"), ("low", "medium", "high"), strict=True
    ):
        front = pareto.front_mask(res[[col, "exposure"]].to_numpy())
        for _, r in res.iterrows():
            ax.errorbar(
                r[col],
                r.exposure,
                yerr=r.exposure_hw,
                fmt="o",
                ms=3 + 2 * np.log10(10 * r[pareto.KEYS[1]]),
                color=colors[r[pareto.KEYS[0]]],
                alpha=0.85,
                elinewidth=0.6,
            )
        fr = res[front].sort_values(col)
        ax.plot(fr[col], fr.exposure, "k--", lw=0.8)
        ax.set_title(f"{ttl}-sensitivity tenants")
        ax.set_xlabel("sync P99 (s)")
        ax.grid(alpha=0.3, lw=0.4)
    axes[0].set_ylabel("key-holder exposure")
    axes[2].legend(
        handles=[Patch(color=c, label=f"$f={f}$") for f, c in colors.items()], loc="lower right", frameon=False
    )
    fig.tight_layout()
    return save(fig, out, "fig_pareto")


def ablation_fig(out: Path) -> Path:
    d = pd.read_csv(T / "E19.csv")
    full = d[d.label == "voss_full"]
    labs = sorted(set(d.label) - {"voss_full"})
    stats = {lab: paired_by_seed(pd.concat([full, d[d.label == lab]]), lab, "voss_full", "p99_sync") for lab in labs}
    expo = {lab: paired_by_seed(pd.concat([full, d[d.label == lab]]), lab, "voss_full", "exposure") for lab in labs}
    order = sorted(labs, key=lambda k: stats[k][0])
    fig, axes = plt.subplots(1, 2, figsize=(COL, 3.0), sharey=True)
    for ax, s, ttl in zip(axes, (stats, expo), ("$\\Delta$ sync P99 (s)", "$\\Delta$ exposure"), strict=True):
        y = np.arange(len(order))
        m = np.array([s[k][0] for k in order])
        err = np.abs(np.array([[s[k][0] - s[k][1] for k in order], [s[k][2] - s[k][0] for k in order]]))
        ax.barh(y, m, xerr=err, color=np.where(m > 0, "#c0504d", "#4f81bd"), alpha=0.85, error_kw={"elinewidth": 0.6})
        ax.axvline(0, color="k", lw=0.6)
        ax.set_title(ttl)
        ax.set_yticks(y, [k.replace("_", " ") for k in order])
    fig.tight_layout()
    return save(fig, out, "fig_ablation")


def scale_fig(out: Path) -> Path:
    d = pd.read_csv(T / "E18.csv")
    g = d.groupby("workers")
    fig, axes = plt.subplots(1, 2, figsize=(COL, 1.8))
    for ax, m, ttl in zip(axes, ("p99_sync", "success"), ("sync P99 (s)", "success"), strict=True):
        pts = [(w, *bootstrap_ci(x[m].dropna().to_numpy())) for w, x in g]
        xs, mean, lo, hi = (np.array(c, dtype=float) for c in zip(*pts, strict=True))
        ax.errorbar(xs, mean, yerr=[mean - lo, hi - mean], marker="o", ms=3, capsize=2)
        ax.set_xscale("log")
        ax.set_xlabel("workers")
        ax.set_title(ttl)
        ax.grid(alpha=0.3, lw=0.4)
    fig.tight_layout()
    return save(fig, out, "fig_scale")


def cost_fig(out: Path) -> Path:
    """Motivation: time to reach each state on the calibration machine (log scale), from ``cost_ladder.csv``."""
    d = pd.read_csv(REPO / "manuscript" / "generated" / "cost_ladder.csv").sort_values("seconds")
    fig, ax = plt.subplots(figsize=(COL, 2.0))
    colors = np.where(
        d.source == "simulated",
        "#9a9a9a",
        np.where(d.state.str.contains("attested|kernel|quote"), "#c0504d", "#4f81bd"),
    )
    y = np.arange(len(d))
    ax.barh(y, d.seconds, color=colors, height=0.65)
    ax.set_xscale("log")
    ax.set_yticks(y, d.state)
    ax.set_xlabel("time (s, log scale)")
    for yi, v in zip(y, d.seconds, strict=True):
        ax.text(float(v) * 1.15, float(yi), f"{v * 1000:.0f} ms" if v < 1 else f"{v:.1f} s", va="center", fontsize=6)
    ax.set_xlim(1e-3, 3e2)
    ax.grid(axis="x", alpha=0.3, lw=0.4)
    ax.invert_yaxis()
    return save(fig, out, "fig_cost")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=REPO / "manuscript" / "figures")
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    style()
    for f in (viability_fig, pareto_fig, ablation_fig, scale_fig, cost_fig):
        print(f(a.out))


if __name__ == "__main__":
    main()
