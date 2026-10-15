"""E20 viability-map counts and the running-text extras."""

from __future__ import annotations

import re

import pandas as pd

from experiments.paper_tex.core import NUM, Gen, T, expect, rows, tab, tabular


# --- viability maps ------------------------------------------------------------------------------------------------
def sensitivity(exp: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(deadline-met targets, absolute P99 targets) -> verdict counts, parsed from the committed table."""
    txt = (T / f"{exp}.md").read_text()
    out: dict[float, list[int]] = {}
    for m in re.finditer(r"^\| ([0-9.]+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|$", txt, re.M):
        out[float(m.group(1))] = [int(x) for x in m.groups()[1:]]
    cols = ["voss_only", "voss_better", "tie", "baseline_better", "none"]
    df = pd.DataFrame(out, index=cols).T
    return df[df.index < 1.0], df[df.index >= 1.0]


def viability(g: Gen) -> None:
    body, labels = (
        [],
        {
            "E20a": "A: churn $\\times$ $\\alpha$",
            "E20b": "B: substrate $\\times$ load",
            "E20c": "C: $N$ $\\times$ load",
        },
    )
    for exp, label in labels.items():
        met, p99 = sensitivity(exp)
        tag = exp[-1].upper()
        total = int(met.loc[0.95].sum())
        g.mac(f"Viab{tag}Cells", total)
        for t, sub in ((3.0, p99), (5.0, p99)):
            v = int(sub.loc[t, ["voss_only", "voss_better", "tie"]].sum())
            b = int(sub.loc[t, "baseline_better"])
            g.mac(f"Viab{tag}P{NUM[int(t)]}Voss", v)
            g.mac(f"Viab{tag}P{NUM[int(t)]}Base", b)
        g.mac(f"Viab{tag}MetNone", int(met.loc[0.98, "none"]))
        g.mac(f"Viab{tag}MetOnly", int(met.loc[0.95, "voss_only"]))
        g.mac(f"Viab{tag}MetBetter", int(met.loc[0.95, "voss_better"]))
        g.mac(f"Viab{tag}MetBase", int(met.loc[0.95, "baseline_better"]))
        g.mac(f"Viab{tag}MetNoneFive", int(met.loc[0.95, "none"]))
        body.append(
            rows(
                label,
                *[
                    f"{int(met.loc[t].sum() - met.loc[t, 'none'] - met.loc[t, 'baseline_better'])}"
                    for t in (0.9, 0.95, 0.98)
                ],
                *[f"{int(p99.loc[t, ['voss_only', 'voss_better', 'tie']].sum())}" for t in (2.0, 3.0, 5.0)],
                total,
            )
        )
    g.files["tab_viability.tex"] = tabular(
        "lrrrrrrr",
        ["Panel", "0.90", "0.95", "0.98", "2 s", "3 s", "5 s", "Cells"],
        body,
        r"& \multicolumn{3}{c}{deadline-met target} & \multicolumn{3}{c}{sync P99 target} & \\"
        + "\n"
        + r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",
    )
    _, a_p99 = sensitivity("E20a")
    expect(int(a_p99.loc[3.0, "none"]) == 0, "E20a: VOSS viable everywhere at 3 s")
    expect(int(sensitivity("E20b")[0].loc[0.98, "none"]) == 16, "E20b: nobody meets the 0.98 deadline-met target")


def extras(g: Gen) -> None:
    """Numbers used only in running text: baseline viability, routers (E07), the 30k scalability point, hedging."""
    for exp in ("E20a", "E20b", "E20c"):
        met, p99 = sensitivity(exp)
        both = int(p99.loc[3.0, ["voss_better", "tie", "baseline_better"]].sum())
        g.mac(f"Viab{exp[-1].upper()}PThreeBaseAny", both)
        expect(int(met.loc[0.98, "none"]) == int(met.loc[0.95].sum()), f"{exp}: nobody meets deadline-met 0.98")
    expect(
        g.macros["ViabAPThreeBaseAny"] == "0" and g.macros["ViabBPThreeBaseAny"] == "0",
        "baseline never viable at 3 s in panels A and B",
    )
    e7 = tab("E07")
    r = e7[e7["scenario.load.flash_crowds"] == "none"].groupby("label")[["met", "p99_sync"]].mean()
    g.mac("RouteNearMet", f"{r.loc['nearest', 'met']:.3f}")
    g.mac("RouteLeastMet", f"{r.loc['least_loaded', 'met']:.3f}")
    g.mac("RouteNearP99", f"{r.loc['nearest', 'p99_sync']:.2f}")
    g.mac("RouteLeastP99", f"{r.loc['least_loaded', 'p99_sync']:.2f}")
    expect(
        r.loc["nearest", "met"] > r.loc["least_loaded", "met"] + 0.05,
        "nearest routing meets far more deadlines than least-loaded",
    )
    e18 = tab("E18")
    mid = e18[e18.workers == 30000]
    g.mac("ScaleMidSucc", f"{100 * mid.success.mean():.0f}")
    g.mac("ScaleMidP99", f"{mid.p99_sync.mean():.0f}")
    g.mac("ScaleMidDecide", f"{mid.decide_p99.mean():.0f}")
    h10 = g.hyp[g.hyp.id == "H10"]
    g.mac("HTenPct", f"{(100 * (h10.delta / h10.base).abs()).max():.1f}")
    e16 = tab("E16")
    a = e16[(e16["scenario.adversary"].astype(str).str.contains("0.1")) & (e16.label == "hedge_off")]
    g.mac("HedgeOffWastePct", f"{100 * a.waste.mean():.1f}")
