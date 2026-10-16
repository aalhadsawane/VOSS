"""Planner (E04), ablation (E19) and adversary/fault (E08, E15, E16) tables and macros."""

from __future__ import annotations

import pandas as pd

from experiments.analysis.viability import paired_by_seed
from experiments.paper_tex.core import Gen, esc, expect, ms, rows, tab, tabular


# --- planners, ablations, robustness -----------------------------------------------------------------------------
def planners(g: Gen) -> None:
    d = tab("E04")
    body = []
    names = {
        "plan_none": "no planning",
        "keepalive_ttl": "keep-alive TTL",
        "plan_greedy": "greedy planner",
        "plan_milp": "robust MILP",
    }
    for regime in ("churn_med", "churn_high"):
        for lab, name in names.items():
            x = d[(d.label == lab) & (d["scenario.regime"] == regime)]
            body.append(
                rows(
                    esc(regime),
                    name,
                    ms(x.p99_sync),
                    ms(x.met, 3),
                    ms(x.warm_mb / 1024, 0),
                    ms(x.exposure, 1),
                    ms(x.solve_s, 3),
                )
            )
    g.files["tab_planners.tex"] = tabular(
        "llrrrrr", ["Regime", "Planner", "P99 (s)", "Met", "Warm GB", "Exposure", "Solve (s)"], body
    )
    for name, cmp_, cell in (
        ("OnePctNoneMed", "plan_milp vs plan_none", "churn_med"),
        ("OnePctNoneHigh", "plan_milp vs plan_none", "churn_high"),
        ("OnePctKeepMed", "plan_milp vs keepalive_ttl", "churn_med"),
        ("OnePctKeepHigh", "plan_milp vs keepalive_ttl", "churn_high"),
    ):
        expect(g.rel(f"H{name}", "H1", cmp_, cell) < 0, f"H1 {cmp_} {cell}")
    _greedy_macros(g, d)
    mem = g.h("H1", "plan_milp vs keepalive_ttl", "churn_med", "warm_mb")
    g.mac("MilpWarmRatio", f"{1 + mem.delta / mem.base:.1f}")
    v = g.rel("HEightPct", "H8", "plan_milp vs plan_greedy", "", 1)
    expect(g.h("H8", "plan_milp").verdict == "inconclusive", "H8 inconclusive")
    expect(v < 0, "MILP not worse than greedy")
    solve = d[d.label == "plan_milp"].solve_s
    g.mac("MilpSolveS", f"{solve.mean():.1f}")
    g.mac("GreedySolveMs", f"{1000 * d[d.label == 'plan_greedy'].solve_s.mean():.0f}")


def _greedy_macros(g: Gen, d: pd.DataFrame) -> None:
    """Greedy-planner effects and the MILP-over-greedy kill-criterion check (E04)."""
    for tag, regime in (("Med", "churn_med"), ("High", "churn_high")):
        sub = d[d["scenario.regime"] == regime]
        for lab, name in (("plan_none", "None"), ("keepalive_ttl", "Keep")):
            dm, _, _ = paired_by_seed(sub, "plan_greedy", lab, "p99_sync")
            g.mac(f"Greedy{name}{tag}", f"{abs(100 * dm / sub[sub.label == lab].p99_sync.mean()):.0f}")
            expect(dm < 0, f"greedy planner beats {lab} at {regime}")
        dm, _, _ = paired_by_seed(sub, "plan_milp", "plan_greedy", "p99_sync")
        g.mac(f"MilpGreedy{tag}", f"{abs(100 * dm / sub[sub.label == 'plan_greedy'].p99_sync.mean()):.1f}")
        expect(
            abs(dm / sub[sub.label == "plan_greedy"].p99_sync.mean()) < 0.05,
            f"kill criterion: MILP < 5% over greedy ({regime})",
        )


def ablations(g: Gen) -> None:
    d = tab("E19")
    full = d[d.label == "voss_full"]
    rows_ = []
    for lab in sorted(set(d.label) - {"voss_full"}):
        x = d[d.label == lab]
        cells = [
            paired_by_seed(pd.concat([full, x]), lab, "voss_full", m)
            for m in ("p99_sync", "success", "exposure", "waste")
        ]
        rows_.append((cells[0][0], lab, cells))
    body = []
    for _, lab, c in sorted(rows_, reverse=True):
        body.append(
            rows(
                esc(lab.replace("no_", "$-$ ")), *[f"{m:+.3g}{{\\scriptsize[{lo:+.2g}, {hi:+.2g}]}}" for m, lo, hi in c]
            )
        )
    g.files["tab_ablation.tex"] = tabular(
        "lrrrr", ["Removed", r"$\Delta$ P99 (s)", r"$\Delta$ success", r"$\Delta$ exposure", r"$\Delta$ waste"], body
    )
    delta = {lab: c for _, lab, c in rows_}
    g.mac("AblLifecycleP", f"{delta['no_lifecycle'][0][0]:.1f}")
    g.mac("AblPlanningP", f"{delta['no_planning'][0][0]:.1f}")
    g.mac("AblPlanningExp", f"{-delta['no_planning'][2][0]:.0f}")
    g.mac("AblRobustP", f"{delta['no_robustness'][0][0]:.1f}")
    g.mac("AblRobustExp", f"{-delta['no_robustness'][2][0]:.0f}")
    g.mac("AblHedgeP", f"{delta['no_hedging'][0][0]:.1f}")
    g.mac("AblGeoExp", f"{-delta['no_geo'][2][0]:.0f}")
    g.mac("AblGeoP", f"{-delta['no_geo'][0][0]:.2f}")
    g.mac("AblRepExp", f"{delta['reputation_in_cost'][2][0]:.0f}")
    g.mac("AblNoProgSucc", f"{-100 * delta['no_progress'][1][0]:.1f}")
    expect(delta["no_geo"][0][2] < 0.0, "removing geo clusters lowers P99 (hi < 0)")
    top2 = sorted(delta, key=lambda k: -delta[k][0][0])[:2]
    expect(set(top2) == {"no_lifecycle", "no_planning"}, "lifecycle and planning are the two largest P99 contributors")


def adversaries(g: Gen) -> None:
    d = tab("E08")
    body = []
    names = {"voss": "VOSS", "f0": "VOSS, $f{=}0$", "heartbeat_only": "heartbeat-only"}
    for adv in ("none α=0", "mixed α=0.1", "mixed α=0.2", "all α=0.2"):
        for lab, name in names.items():
            x = d[(d.label == lab) & (d["scenario.adversary"] == adv)]
            body.append(
                rows(
                    esc(adv).replace("α", r"$\alpha$"),
                    name,
                    ms(100 * x.success, 2),
                    ms(x.p99_sync),
                    ms(x.waste * 100, 1),
                    ms(x.omits, 0),
                )
            )
    g.files["tab_adversary.tex"] = tabular(
        "llrrrr", ["Adversaries", "System", "Success (\\%)", "P99 (s)", "Waste (\\%)", "Omissions"], body
    )
    a = d[d["scenario.adversary"] == "mixed α=0.2"]
    g.mac("HbSuccAlpha", f"{100 * a[a.label == 'heartbeat_only'].success.mean():.1f}")
    g.mac("VossSuccAlpha", f"{100 * a[a.label == 'voss'].success.mean():.2f}")
    g.mac("HbOmitRatio", f"{a[a.label == 'heartbeat_only'].omits.mean() / a[a.label == 'voss'].omits.mean():.0f}")
    g.mac("FzeroSuccDelta", f"{abs(g.h('H2', 'f0 vs voss', '', 'success').delta) * 100:.2f}")
    g.mac("PrecisionMixed", f"{100 * a[a.label == 'voss'].precision.mean():.0f}")
    expect(g.h("H2", "f0 vs voss", "", "success").verdict == "inconclusive", "H2 inconclusive")
    expect(g.h("H4", "heartbeat_only vs voss", "", "success").verdict == "supported", "H4 supported")


def faults(g: Gen) -> None:
    e = tab("E15")
    body = []
    for kind in ("sched_crash", "sched_partition", "sched_blackhole", "sched_slow"):
        for lab in ("progress", "heartbeat_only"):
            x = e[(e.label == lab) & (e["scenario.faults"] == kind)]
            body.append(
                rows(
                    esc(kind.replace("sched_", "")),
                    esc(lab),
                    ms(x.detect_s, 1),
                    ms(x.failover_s, 1),
                    ms(100 * x.success, 2),
                    ms(x.p99_fault),
                )
            )
    g.files["tab_faults.tex"] = tabular(
        "llrrrr", ["Fault", "Detector", "Detect (s)", "Failover (s)", "Success (\\%)", "P99 in window (s)"], body
    )
    bh = e[e["scenario.faults"] == "sched_blackhole"]
    g.mac("BhDetectProg", f"{bh[bh.label == 'progress'].detect_s.mean():.1f}")
    g.mac("BhDetectHb", f"{bh[bh.label == 'heartbeat_only'].detect_s.mean():.0f}")
    g.mac("BhTimeoutsHb", f"{bh[bh.label == 'heartbeat_only'].timeouts_fault.mean():.0f}")
    g.mac("BhTimeoutsProg", f"{bh[bh.label == 'progress'].timeouts_fault.mean():.1f}")
    cr = e[e["scenario.faults"] == "sched_crash"]
    g.mac("CrashDetectProg", f"{cr[cr.label == 'progress'].detect_s.mean():.1f}")
    g.mac("CrashFailover", f"{cr[cr.label == 'progress'].failover_s.mean():.1f}")
    sl = e[e["scenario.faults"] == "sched_slow"]
    g.mac("SlowFailover", f"{sl[sl.label == 'progress'].failover_s.mean():.0f}")
    g.rel("HFTOnePct", "H-FT1", "progress vs heartbeat_only", "", 1, "success")
    g.mac("HFTOneSuccHb", f"{100 * bh[bh.label == 'heartbeat_only'].success.mean():.1f}")


def hedging(g: Gen) -> None:
    h = tab("E16")
    body = []
    names = {
        "hedge_off": "off",
        "hedge_always": "always",
        "rp_t01_b005": r"$\theta{=}0.1$, 5\%",
        "rp_t01_b02": r"$\theta{=}0.1$, 20\%",
        "rp_t03_b005": r"$\theta{=}0.3$, 5\%",
        "rp_t03_b02": r"$\theta{=}0.3$, 20\%",
    }
    for adv in ("none α=0", "mixed α=0.1"):
        for lab, name in names.items():
            x = h[(h.label == lab) & (h["scenario.adversary"] == adv)]
            body.append(
                rows(
                    esc(adv).replace("α", r"$\alpha$"),
                    name,
                    ms(x.p99_sync),
                    ms(100 * x.waste, 1),
                    ms(x.duplicates_k, 1),
                )
            )
    g.files["tab_hedging.tex"] = tabular(
        "llrrr", ["Adversaries", "Hedging", "P99 (s)", "Waste (\\%)", "Late dup./1000"], body
    )
    r = g.h("H-FT3", "rp_t03_b005 vs hedge_off")
    g.mac("HedgeP99Pct", f"{abs(100 * r.delta / r.base):.0f}")
    g.mac("HedgeP99Lo", f"{100 * r.lo / r.base:.0f}")
    g.mac("HedgeP99Hi", f"{100 * r.hi / r.base:.0f}")
    x = h[(h.label == "hedge_always") & (h["scenario.adversary"] == "mixed α=0.1")]
    g.mac("AlwaysWastePct", f"{100 * x.waste.mean():.1f}")
    y = h[(h.label == "rp_t03_b005") & (h["scenario.adversary"] == "mixed α=0.1")]
    g.mac("RpWastePct", f"{100 * y.waste.mean():.1f}")
