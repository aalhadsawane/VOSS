"""Pareto, geo, caching, simple-baseline, commercial, scalability, accounting and scorecard tables and macros."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from experiments.paper_tex.core import Gen, T, esc, expect, ms, rows, tab, tabular


def pareto_and_rest(g: Gen) -> None:
    p = pd.read_csv(T / "E23.csv")
    knee = p[p.knee].iloc[0]
    fr = p[p.front2]
    g.mac("ParetoFrontN", len(fr))
    g.mac("ParetoKneeF", f"{knee['voss.planner.f_from_alpha']:.1f}")
    g.mac("ParetoExpMin", f"{p.exposure.min():.0f}")
    g.mac("ParetoExpMax", f"{p.exposure.max():.0f}")
    g.mac("ParetoP99Lo", f"{p.p99_sync.min():.2f}")
    g.mac("ParetoP99Hi", f"{p.p99_sync.max():.2f}")
    g.mac("ParetoKneeExpSaved", f"{100 * (1 - knee.exposure / fr.exposure.max()):.0f}")
    g.mac("ParetoKneeP99Loss", f"{100 * (knee.p99_sync / fr.p99_sync.min() - 1):.1f}")
    fs = p.groupby("voss.planner.f_from_alpha").exposure.mean()
    g.mac("ExpF0", f"{fs.loc[0.0]:.0f}")
    g.mac("ExpFOne", f"{fs.loc[0.1]:.0f}")
    g.mac("ExpFTwo", f"{fs.loc[0.2]:.0f}")
    g.mac("ParetoHighMax", f"{p.p99_sync_high.max():.1f}")
    g.mac("ParetoLowMax", f"{p.p99_sync_low.max():.1f}")


def geo_and_null(g: Gen) -> None:
    """Geo clustering (E05), the simple baseline (E10) and caching (H6)."""
    e5 = tab("E05")
    body = []
    for reg, name in (("eu", "Europe"), ("eu+na", "EU + NA"), ("world", "world")):
        for lab, ln in (
            ("none_global", "one global scheduler"),
            ("static_regions", "static regions"),
            ("static_kmeans", "static $k$-means"),
            ("dynamic", "dynamic"),
        ):
            x = e5[(e5.label == lab) & (e5["scenario.geo.regions"] == reg)]
            body.append(rows(name, ln, ms(x.p99_sync), ms(x.net_s, 3), ms(x.clusters, 1), ms(x.exposure, 0)))
    g.files["tab_geo.tex"] = tabular(
        "llrrrr", ["Population", "Clustering", "P99 (s)", "Network (s)", "Clusters", "Exposure"], body
    )
    for name, cell in (("Eu", "regions=[eu]"), ("EuNa", "regions=[eu, na]"), ("World", "regions=[]")):
        expect(g.rel(f"HSeven{name}", "H7", "dynamic vs none_global", cell) > 0, f"H7 {cell}: geo is slower")
    g.mac("GeoClusters", f"{e5[(e5.label == 'dynamic') & (e5['scenario.geo.regions'] == 'eu')].clusters.mean():.0f}")
    eu = e5[e5["scenario.geo.regions"] == "eu"]
    g.mac(
        "GeoExpRatio",
        f"{eu[eu.label == 'dynamic'].exposure.mean() / eu[eu.label == 'none_global'].exposure.mean():.1f}",
    )
    e10 = tab("E10")
    body = []
    for hw, name in (("homogeneous", "homogeneous"), ("mixed", "mixed")):
        for lab, ln in (("simple", "simple baseline"), ("voss", "VOSS")):
            x = e10[(e10.label == lab) & (e10["scenario.hw_mix"] == hw)]
            body.append(rows(name, ln, ms(x.p99_sync), ms(x.met, 3), ms(x.exposure, 0)))
    g.files["tab_simple.tex"] = tabular("llrrr", ["Hardware", "System", "P99 (s)", "Met", "Exposure"], body)
    g.rel("HElevenPct", "H11", "simple vs voss", "", 0)
    s = e10[(e10.label == "simple") & (e10["scenario.hw_mix"] == "homogeneous")].exposure.mean()
    v = e10[(e10.label == "voss") & (e10["scenario.hw_mix"] == "homogeneous")].exposure.mean()
    g.mac("SimpleExpRatio", f"{v / s:.1f}")
    r = g.hyp[g.hyp.id == "H6"]
    g.mac("HSixPct", f"{abs(100 * r.iloc[0].delta / r.iloc[0].base):.0f}")
    expect(set(r.verdict) == {"inconclusive"}, "H6 inconclusive")


def commercial(g: Gen) -> None:
    c = tab("E17")
    body = []
    for rate in (10, 20, 40):
        for lab, name in (("voss", "VOSS"), ("ref_lambda_like", "Lambda-like"), ("ref_azure_like", "Azure-like")):
            x = c[(c.label == lab) & (c["scenario.load.rate"] == rate)]
            body.append(rows(rate, name, ms(x.p50_sync, 3), ms(x.p99_sync), ms(x.met, 3), ms(x.cost_per_m, 1)))
    g.files["tab_commercial.tex"] = tabular(
        "rlrrrr", ["Load (inv/s)", "System", "P50 (s)", "P99 (s)", "Met", "USD/M inv."], body
    )
    r = g.h("RQ15", "voss vs ref_lambda_like")
    g.mac("CommP99Pct", f"{100 * r.delta / r.base:.0f}")
    p50 = (
        c[(c.label == "voss") & (c["scenario.load.rate"] == 20)].p50_sync.mean()
        / c[(c.label == "ref_lambda_like") & (c["scenario.load.rate"] == 20)].p50_sync.mean()
        - 1
    )
    g.mac("CommP50Pct", f"{100 * p50:.0f}")
    for rate in (10, 20, 40):
        g.mac(
            f"CommCost{['Ten', 'Twenty', 'Forty'][[10, 20, 40].index(rate)]}",
            f"{c[(c.label == 'voss') & (c['scenario.load.rate'] == rate)].cost_per_m.mean():.0f}",
        )
    g.mac("CommCostRef", f"{c[c.label == 'ref_lambda_like'].cost_per_m.mean():.0f}")


def scalability(g: Gen) -> None:
    s = tab("E18")
    body = []
    for lab in ("n100", "n1k", "n10k", "n30k", "n100k"):
        x = s[s.label == lab]
        body.append(
            rows(
                f"{int(x.workers.iloc[0]):,}".replace(",", r"\,"),
                len(x),
                ms(100 * x.success, 1),
                ms(x.p99_sync, 1),
                ms(x.decide_p99, 2),
                ms(x.ctrl_msgs_ws, 2),
                ms(x.orch_cpu_s, 3),
            )
        )
    g.files["tab_scale.tex"] = tabular(
        "rrrrrrr",
        ["Workers", "Seeds", "Success (\\%)", "P99 (s)", "Decide P99 (s)", "Msg/s/worker", "Orch. CPU (s/s)"],
        body,
    )
    big = s[s.label == "n100k"]
    g.mac("ScaleBigSucc", f"{100 * big.success.mean():.0f}")
    g.mac("ScaleBigP99", f"{big.p99_sync.mean():.0f}")
    g.mac("ScaleBigDecide", f"{big.decide_p99.mean():.0f}")
    g.mac("ScaleMsgLo", f"{s.ctrl_msgs_ws.min():.2f}")
    g.mac("ScaleMsgHi", f"{s.ctrl_msgs_ws.max():.2f}")
    g.mac("ScaleTenKSucc", f"{100 * s[s.label == 'n10k'].success.mean():.1f}")


def cell_text(cell: object) -> str:
    """Readable scenario cell for the scorecard (``adversary={alpha: 0.2, ...}`` -> ``mixed α=0.2``)."""
    c = cell if isinstance(cell, str) else ""
    c = re.sub(r"adversary=\{alpha: ([0-9.]+), regime: adversary_mixed\}", r"mixed α=\1", c)
    c = re.sub(r"hw_mix=\{(\w+): 1\.0\}", r"hw=\1", c)
    return c.replace("regime=", "")


def scorecard(g: Gen) -> None:
    body = []
    sym = {
        "supported": r"\textbf{supported}",
        "refuted": r"\textbf{refuted}",
        "weak": "weak",
        "inconclusive": "inconclusive",
        "info": "--",
    }
    for r in g.hyp.itertuples():
        if r.verdict == "no data":
            continue
        rel = f"{100 * r.delta / r.base:+.1f}\\%" if r.base else ""
        ci = "" if np.isnan(r.lo) else f"{{\\scriptsize[{100 * r.lo / r.base:+.1f}, {100 * r.hi / r.base:+.1f}]}}"
        body.append(
            rows(
                esc(r.id),
                esc(str(r.claim)[:78]),
                esc(r.exp),
                esc(cell_text(r.cell)),
                f"{rel} {ci}",
                sym.get(r.verdict, r.verdict),
            )
        )
    g.files["tab_scorecard.tex"] = tabular(
        "lp{5.6cm}lp{2.2cm}rl", ["H", "Claim", "Exp.", "Cell", "$\\Delta$ rel. [95\\% CI]", "Verdict"], body
    )
    n = g.hyp.verdict.value_counts()
    for v in ("supported", "refuted", "weak", "inconclusive"):
        g.mac(f"Score{v.capitalize()}", int(n.get(v, 0)))
