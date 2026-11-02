"""Round-4 numbers (doc 06 §8; ``docs/validation/ROUND4-results.md``): the E04b front table, verdicts H12-H15, the E25
(H16) table, the decomposition of the planner's gain and the key-release amortisation, all computed from the committed
per-run CSVs ``paper/tables/E04b_runs.csv`` and ``E25_runs.csv`` with the same functions as
``experiments.analysis.round4`` (no second implementation). Macro names carry no digits (``Htwelve``, ``Kone``)."""

from __future__ import annotations

import pandas as pd

from experiments.analysis.common import bootstrap_ci
from experiments.analysis.round4 import (
    best_single,
    e25_advantage,
    e25_blind,
    e25_cells,
    e25_differences,
    h13_resources,
    hypotheses,
    ratios,
)
from experiments.paper_tex.core import Gen, T, esc, expect, ms

REGIMES = {"churn_med": "Med", "churn_high": "High"}
SYSTEMS = {  # E04b rows in table order -> macro stem
    "plan_none": "PlanNone",
    "keepalive_ttl": "KeepaliveTtl",
    "keepalive_inf": "KeepaliveInf",
    "hist_prewarm": "HistPrewarm",
    "provisioned_keys": "ProvisionedKeys",
    "plan_greedy": "PlanGreedy",
    "plan_milp": "PlanMilp",
    "erlang_greedy": "ErlangGreedy",
    "erlang_dpp": "ErlangDpp",
    "plan_greedy_oldwait": "PlanGreedyOldwait",
}
HYP = {"H12": "Htwelve", "H13": "Hthirteen", "H14b": "HfourteenB", "H15": "Hfifteen"}
SHAPE = {0.6: "Ksix", 1.0: "Kone"}
MULT = {0.25: "Mquarter", 1.0: "Mone", 4.0: "Mfour"}
AMORT = ("plan_greedy", "keepalive_ttl", "keepalive_inf", "provisioned_keys")


def per_system(g: Gen, d: pd.DataFrame) -> None:
    """Mean P99 (s), warm memory (GB), exposure and seed count per system and regime."""
    for reg, r in REGIMES.items():
        for lab, stem in SYSTEMS.items():
            x = d[(d.regime == reg) & (d.label == lab)]
            g.mac(f"RfourP{stem}{r}", f"{x.p99.mean():.3f}")
            g.mac(f"RfourWarm{stem}{r}", f"{x.warm_mb.mean() / 1e3:.1f}")
            g.mac(f"RfourExp{stem}{r}", f"{x.exposure.mean():.1f}")
            g.mac(f"RfourN{stem}{r}", len(x))


def front_table(g: Gen, d: pd.DataFrame) -> None:
    """``tab_round4_front.tex``: P99 (mean and 95% CI half-width over seeds), warm GB and exposure, nine systems."""
    body = []
    for lab in list(SYSTEMS)[:-1]:  # plan_greedy_oldwait is the E04 continuity row, not in the front
        cells: list[str] = []
        for reg in REGIMES:
            x = d[(d.regime == reg) & (d.label == lab)]
            cells += [ms(x.p99, 3), f"{x.warm_mb.mean() / 1e3:.1f}", f"{x.exposure.mean():.1f}"]
        body.append(" & ".join([f"\\texttt{{{esc(lab)}}}", *cells]) + r" \\")
    sub = ["P99 (s)", "Warm (GB)", "Exposure"] * 2
    head = [
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r" & \multicolumn{3}{c}{medium churn} & \multicolumn{3}{c}{high churn} \\",
        r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",
        " & ".join(f"\\textbf{{{h}}}" for h in ["System", *sub]) + r" \\",
        r"\midrule",
    ]
    g.files["tab_round4_front.tex"] = "\n".join([*head, *body, r"\bottomrule", r"\end{tabular}", ""])


def verdicts(g: Gen, d: pd.DataFrame) -> pd.DataFrame:
    """Macros of the H12-H15 verdict table (``hypotheses`` as the analysis computes it) and the H13 resource ratios."""
    h = hypotheses(d)
    for reg, r in REGIMES.items():
        for hid, stem in HYP.items():
            row = h[h.test.str.startswith(f"{hid} {reg}:")].iloc[0]
            p = f"Rfour{stem}{r}"
            g.mac(p + "Ratio", f"{row.mean_ratio:.3f}")
            g.mac(p + "Lo", f"{row.ci_lo:.3f}")
            g.mac(p + "Hi", f"{row.ci_hi:.3f}")
            g.mac(p + "Below", int(row.seeds_below_1))
            g.mac(p + "Seeds", int(row.n))
            g.mac(p + "Bound", f"{row.bound:.2f}")
        g.mac(f"RfourHtwelve{r}Ref", esc(best_single(d, reg)))
    for (reg, col), v in h13_resources(d).items():
        g.mac(f"RfourHthirteen{REGIMES[reg]}{'Warm' if col == 'warm_mb' else 'Exp'}", f"{v:.3f}")
    return h


def row_of(h: pd.DataFrame, hid: str, reg: str) -> pd.Series:
    return h[h.test.str.startswith(f"{hid} {reg}:")].iloc[0]


def check_verdicts(h: pd.DataFrame, d: pd.DataFrame) -> None:
    """The sentences of ROUND4-results.md that the verdict table backs."""
    res = h13_resources(d)
    for reg in REGIMES:
        h12, h14, h15 = (row_of(h, x, reg) for x in ("H12", "H14b", "H15"))
        expect(h12.ci_hi < 0.95 and bool(h12.holm_supported), f"H12 supported at {reg}")
        expect(h14.ci_hi < 1.05, f"H14b erlang_dpp within 5% of erlang_greedy at {reg}")
        expect(res[(reg, "warm_mb")] > 1.05, f"H13 fails on warm memory at {reg}")
        expect(res[(reg, "exposure")] <= 1.05, f"H13 exposure no higher at {reg}")
        expect(0.95 <= h15.ci_hi < 1.0, f"H15 weak at {reg}: CI below 1 but not below the 0.95 bound")
        expect(not bool(h15.holm_supported), f"H15 not Holm-supported at {reg}")
    med, high = row_of(h, "H13", "churn_med"), row_of(h, "H13", "churn_high")
    expect(med.ci_hi >= 1.05, "H13 P99 part not supported at churn_med (CI crosses the bound)")
    expect(high.ci_hi < 1.10 and high.ci_lo > 1.0, "H13 P99 part supported at churn_high, above plan_greedy")


def decomposition(g: Gen, d: pd.DataFrame) -> None:
    """Percentage P99 reduction against the best single loop (paired, mean of per-seed ratios) and the share of the
    greedy gain that holding keys early (``provisioned_keys``) captures."""
    for reg, r in REGIMES.items():
        best = best_single(d, reg)
        pk = 100 * (1 - ratios(d, reg, "provisioned_keys", best).mean())
        gr = 100 * (1 - ratios(d, reg, "plan_greedy", best).mean())
        g.mac(f"RfourDecompPk{r}", f"{pk:.0f}")
        g.mac(f"RfourDecompGreedy{r}", f"{gr:.0f}")
        g.mac(f"RfourDecompShare{r}", f"{100 * pk / gr:.0f}")
        g.mac(f"RfourDecompRest{r}", f"{100 * (1 - pk / gr):.0f}")
        expect(gr > pk > 0, f"plan_greedy gains more than provisioned_keys at {reg}")
        expect(0.6 < pk / gr < 0.95, f"holding keys early captures most of the greedy gain at {reg}: {pk / gr:.2f}")


def e25(g: Gen, d: pd.DataFrame) -> None:
    """H16 table cells (A and B with 95% CI) and the two A differences at shape 1.0."""
    for k, ks in SHAPE.items():
        for m, mm in MULT.items():
            p = f"RfourEtwentyfive{ks}{mm}"
            for name, x in (("A", e25_advantage(d, m, k)), ("B", e25_blind(d, m, k))):
                mean, lo, hi = bootstrap_ci(x, n=10000)
                g.mac(f"{p}{name}", f"{mean:.3f}")
                g.mac(f"{p}{name}Lo", f"{lo:.3f}")
                g.mac(f"{p}{name}Hi", f"{hi:.3f}")
                if name == "A":
                    expect(lo > 0, f"H16: the planner beats the best single loop at k={k}, M={m}")
                else:
                    expect(abs(mean) < 0.05, f"H16b: B is within 5% of zero at k={k}, M={m}")
    diff = e25_differences(d, 1.0)
    for m, (mean, lo, hi) in diff.items():
        p = f"RfourEtwentyfiveKoneAdiff{'Quarter' if m == 0.25 else 'Four'}"
        g.mac(p, f"{mean:.3f}")
        g.mac(p + "Lo", f"{lo:.3f}")
        g.mac(p + "Hi", f"{hi:.3f}")
    expect(diff[4.0][1] > 0, "H16a: A(1) - A(4) at shape 1.0 excludes zero")
    expect(diff[0.25][1] < 0 < diff[0.25][2], "H16a: A(1) - A(0.25) at shape 1.0 includes zero")
    b_one, b_four = (bootstrap_ci(e25_blind(d, m, 1.0), n=10000) for m in (1.0, 4.0))
    expect(b_one[1] > 0 and b_four[2] < 0, "H16b: B excludes zero only at (1.0, 1) upward and (1.0, 4) downward")


def amortisation(g: Gen, d: pd.DataFrame) -> None:
    """Synchronous requests served per key release: pooled over seeds after the warm-up, median per run after the
    warm-up and over the whole run, and the mean number of releases after the warm-up."""
    pooled: dict[tuple[str, str], float] = {}
    for reg, r in REGIMES.items():
        for lab in AMORT:
            x = d[(d.regime == reg) & (d.label == lab)]
            stem = SYSTEMS[lab]
            pooled[(reg, lab)] = x.sync_served.sum() / x.key_releases.sum()
            g.mac(f"RfourAmort{stem}{r}", f"{pooled[(reg, lab)]:.0f}")
            g.mac(f"RfourAmortMed{stem}{r}", f"{x.sync_per_release.median():.0f}")
            g.mac(f"RfourAmortRun{stem}{r}", f"{x.sync_per_release_all.median():.0f}")
            g.mac(f"RfourRel{stem}{r}", f"{x.key_releases.mean():.0f}")
    for reg in REGIMES:
        order = pooled[(reg, "keepalive_ttl")] > pooled[(reg, "provisioned_keys")] > pooled[(reg, "plan_greedy")]
        expect(order, f"key-release amortisation order keepalive > provisioned_keys > plan_greedy at {reg}")


def round4(g: Gen) -> None:
    d4 = pd.read_csv(T / "E04b_runs.csv")
    d25 = e25_cells(pd.read_csv(T / "E25_runs.csv"))
    per_system(g, d4)
    front_table(g, d4)
    check_verdicts(verdicts(g, d4), d4)
    decomposition(g, d4)
    e25(g, d25)
    amortisation(g, d4)
