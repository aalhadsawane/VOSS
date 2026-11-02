"""Corrected-placement reruns E10b, E17b, E24b and E20ab (D-77; ``docs/validation/RERUN-results.md``): tables and
macros with the prefix ``Rerun`` so that the frozen E10, E17, E24 and E20a macros coexist. Generated from the committed
per-run CSVs ``paper/tables/<exp>_runs.csv`` (``experiments.analysis.rerun``). Systems are paired by seed (same
scenario); a ratio is the mean of per-seed ratios with a 95% bootstrap CI (``experiments.analysis.round4.paired``)."""

from __future__ import annotations

import pandas as pd

from experiments.analysis.common import bootstrap_ci
from experiments.analysis.round4 import paired
from experiments.analysis.viability import MET_MIN, P99_TARGETS, cells, system_stats
from experiments.paper_tex.core import NUM, Gen, T, expect, ms, rows, tabular

HW = {"homogeneous": "Hom", "mixed": "Mix"}
LOAD = {10: "Ten", 20: "Twenty", 40: "Forty"}
REFS = {"ref_lambda_like": "Lambda", "ref_azure_like": "Azure"}
BUNDLE = {"placeholder": "Plc", "measured": "Meas"}


def _paired(g: Gen, name: str, d: pd.DataFrame, cell: tuple[str, object], num: str, den: str, col: str) -> pd.Series:
    """Macros ``name{Ratio,Lo,Hi}`` of the mean per-seed ratio ``num / den`` of ``col`` in one cell."""
    r = pd.Series(paired(d, cell, num, den, col))
    for suffix, key in (("Ratio", "mean_ratio"), ("Lo", "lo"), ("Hi", "hi")):
        g.mac(name + suffix, f"{r[key]:.2f}")
    return r


def _diff(g: Gen, name: str, d: pd.DataFrame, cell: tuple[str, object], a: str, b: str, col: str) -> tuple[float, ...]:
    """Macros ``name{Diff,Lo,Hi}``: mean per-seed difference ``a - b`` of ``col`` (seconds) with its 95% CI."""
    x = d[d[cell[0]] == cell[1]]
    pa, pb = (x[x.label == k].set_index("seed")[col] for k in (a, b))
    s = pa.index.intersection(pb.index)
    out = bootstrap_ci((pa[s] - pb[s]).to_numpy(), n=10000)
    for suffix, v in zip(("Diff", "Lo", "Hi"), out, strict=True):
        g.mac(name + suffix, f"{v:.3f}")
    return out


def simple(g: Gen) -> None:
    """E10b: VOSS against the simple baseline (homogeneous benign null, doc 06 §5, RQ16)."""
    d = pd.read_csv(T / "E10b_runs.csv")
    body = []
    for hw, short in HW.items():
        for lab, ln in (("simple", "simple baseline"), ("voss", "VOSS")):
            x = d[(d.label == lab) & (d.hw_mix == hw)]
            body.append(rows(hw, ln, ms(x.p99, 2), ms(x.met, 3), ms(x.exposure, 0)))
            g.mac(f"RerunSimpleP99{short}{'Voss' if lab == 'voss' else 'Base'}", f"{x.p99.mean():.2f}")
            g.mac(f"RerunSimpleExp{short}{'Voss' if lab == 'voss' else 'Base'}", f"{x.exposure.mean():.0f}")
        p99 = _paired(g, f"RerunSimpleP99{short}", d, ("hw_mix", hw), "simple", "voss", "p99")
        exp = _paired(g, f"RerunSimpleExp{short}", d, ("hw_mix", hw), "voss", "simple", "exposure")
        g.mac(f"RerunSimplePct{short}", f"{100 * (p99.mean_ratio - 1):.0f}")
        expect(p99.lo > 1.0, f"E10b {hw}: the simple baseline's P99 is higher than VOSS's (paired CI above 1)")
        expect(exp.lo > 1.0, f"E10b {hw}: VOSS holds more keys (exposure) than the simple baseline")
    g.files["tab_rerun_simple.tex"] = tabular("llrrr", ["Hardware", "System", "P99 (s)", "Met", "Exposure"], body)


def commercial(g: Gen) -> None:
    """E17b: VOSS against the reference clouds across load (doc 06 §5, RQ15)."""
    d = pd.read_csv(T / "E17b_runs.csv")
    body = []
    for rate, rn in LOAD.items():
        for lab, name in (("voss", "VOSS"), ("ref_lambda_like", "Lambda-like"), ("ref_azure_like", "Azure-like")):
            x = d[(d.label == lab) & (d.rate == rate)]
            body.append(rows(rate, name, ms(x.p50, 3), ms(x.p99), ms(x.met, 3), ms(x.cost_per_m, 1)))
            if lab == "voss":
                g.mac(f"RerunCommP99{rn}", f"{x.p99.mean():.2f}")
                g.mac(f"RerunCommCost{rn}", f"{x.cost_per_m.mean():.1f}")
        for ref, rname in REFS.items():
            for col in ("p99", "p50"):
                lo = _diff(g, f"RerunComm{col.upper()}{rname}{rn}", d, ("rate", rate), "voss", ref, col)[1]
                if col == "p50" or ref == "ref_lambda_like" or rate >= 20:  # the Azure-like P99 gap at 10 inv/s spans 0
                    expect(lo > 0, f"E17b: VOSS {col} is above {ref} at {rate} inv/s (diff CI above 0)")
    g.files["tab_rerun_commercial.tex"] = tabular(
        "rlrrrr", ["Load (inv/s)", "System", "P50 (s)", "P99 (s)", "Met", "USD/M inv."], body
    )
    for ref, rname in REFS.items():
        g.mac(f"RerunCommCostRef{rname}", f"{d[d.label == ref].cost_per_m.mean():.1f}")
    cost = d[d.label == "voss"].groupby("rate").cost_per_m.mean()
    expect(bool(cost.is_monotonic_decreasing), "E17b: VOSS cost per million invocations falls with load")


def calibsens(g: Gen) -> None:
    """E24b: VOSS and the simple baseline under the placeholder and the measured bundle (doc 10 §2)."""
    d = pd.read_csv(T / "E24b_runs.csv")
    body = []
    for b, short in BUNDLE.items():
        x = d[d.calibration.str.contains(b)].assign(bundle=b)
        for lab, ln in (("voss", "VOSS"), ("simple", "simple baseline")):
            y = x[x.label == lab]
            body.append(rows(b, ln, ms(y.p50, 3), ms(y.p99), ms(y.met, 3), ms(y.exposure, 0)))
            g.mac(f"RerunCalSens{ln.split()[0].capitalize()}P99{short}", f"{y.p99.mean():.2f}")
        r = _paired(g, f"RerunCalSensRatio{short}", x, ("bundle", b), "simple", "voss", "p99")
        expect(r.lo > 1.0, f"E24b {b}: the simple baseline's P99 is higher than VOSS's (paired CI above 1)")
    g.files["tab_rerun_calibsens.tex"] = tabular(
        "llrrrr", ["Bundle", "System", "P50 (s)", "P99 (s)", "Met", "Exposure"], body
    )


def feasible(df: pd.DataFrame, label: str, **kw: float | None) -> int:
    """Cells in which ``label`` is viable (``viability.system_stats``; ``kw``: ``met_min`` or ``p99_max``)."""
    s = system_stats(df, ["regime", "adversary"], **kw)  # type: ignore[arg-type]
    return int(s[(s.label == label)].viable.sum())


def viability(g: Gen) -> None:
    """E20ab: feasible cells for VOSS and the simple baseline, same targets as the E20a viability map."""
    path = T / "E20ab_runs.csv"
    if not path.exists():  # the sweep may still be running: the macros appear once the CSV is committed
        return
    d = pd.read_csv(path).rename(columns={"p99": "p99_sync", "p50": "p50_sync"})
    cell = ["regime", "adversary"]
    g.mac("RerunViabCells", len(d.groupby(cell)))
    for label, stem in (("voss", "Voss"), ("simple", "Simple")):
        g.mac(f"RerunViabMet{stem}", feasible(d, label, met_min=MET_MIN))
        for t in P99_TARGETS:
            g.mac(f"RerunViabP{NUM[int(t)]}{stem}", feasible(d, label, p99_max=t))
    for t in P99_TARGETS:
        v = cells(d, cell, p99_max=t).verdict.value_counts()
        g.mac(f"RerunViabP{NUM[int(t)]}VossOnly", int(v.get("voss_only", 0)))
        g.mac(f"RerunViabP{NUM[int(t)]}BaseBetter", int(v.get("baseline_better", 0)))
    cm = d.groupby([*cell, "label"])[["p99_sync", "success"]].mean().reset_index()
    for label, stem in (("voss", "Voss"), ("simple", "Simple"), ("noattest", "Noattest")):
        c = cm[cm.label == label]
        g.mac(f"RerunViabP99Lo{stem}", f"{c.p99_sync.min():.1f}")
        g.mac(f"RerunViabP99Hi{stem}", f"{c.p99_sync.max():.1f}")
    nc = cm[cm.label == "noattest"]
    g.mac("RerunViabSuccLoNoattest", f"{100 * nc.success.min():.0f}")
    g.mac("RerunViabSuccHiNoattest", f"{100 * nc.success.max():.0f}")
    g.mac("RerunViabSuccLoSimple", f"{100 * cm[cm.label == 'simple'].success.min():.1f}")
    n = len(d.groupby(cell))
    for t in P99_TARGETS:
        expect(feasible(d, "voss", p99_max=t) == n, f"VOSS is feasible in every E20ab cell at P99 {t:g} s")
    expect(feasible(d, "simple", p99_max=max(P99_TARGETS)) == 0, "the simple baseline is feasible in no E20ab cell")
    body = []
    for tgt in (None, *P99_TARGETS):
        kw: dict[str, float | None] = {"met_min": MET_MIN} if tgt is None else {"p99_max": tgt}
        name = f"deadlines met, lower bound $\\geq$ {MET_MIN:g}" if tgt is None else f"P99 $\\leq$ {tgt:g} s"
        body.append(rows(name, *(feasible(d, lab, **kw) for lab in ("voss", "simple"))))
    g.files["tab_rerun_viability.tex"] = tabular("lrr", ["Target", "VOSS", "Simple"], body)


def rerun(g: Gen) -> None:
    for step in (simple, commercial, calibsens, viability):
        step(g)
