"""P4 pilot reports (E02, E04, E09, E23): latency, success, donor state, exposure and solver time per system,
mean and 95% bootstrap CI over seeds (doc 06 §6). Writes ``docs/pilots/<EXP>.md`` and a CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.analysis.common import bootstrap_ci, fmt, get, latency_metrics, manifest, table

KEYS = {
    "E02": ("voss.planner.max_plan_workers", "voss.planner.T_plan"),
    "E04": ("label", "scenario.regime"),
    "E09": ("label",),
    "E23": ("voss.planner.params.exposure_weight", "voss.planner.f_from_alpha"),
}
COLS = ("p50_sync", "p99_sync", "met", "warm_mb", "exposure", "solve_s", "l3_share", "p2p_mb")


def run_metrics(run: Path) -> dict[str, float]:
    inv, cache, plans = table(run, "invocations"), table(run, "cache"), table(run, "plans")
    m = latency_metrics(inv)
    ok = inv[(inv.outcome == "ok") & (inv.t_arrive >= 60)]
    late = cache[cache.t >= 60] if len(cache) else cache
    m["l3_share"] = float((ok.start_level == "L3").mean()) if len(ok) else np.nan
    m["trust_cold"] = float(ok.trust_cold.mean()) if len(ok) else np.nan
    m["warm_mb"] = float(late.warm_mb.mean()) if len(late) else np.nan
    m["exposure"] = float(late.exposure.mean()) if len(late) else np.nan
    m["p2p_mb"] = float(cache.p2p_mb.iloc[-1]) if len(cache) else np.nan
    solved = plans[plans.status != "reused"] if len(plans) else plans
    m["solve_s"] = float(solved.solve_wall_s.mean()) if len(solved) else 0.0
    return m


def collect(exp: str, runs: list[Path]) -> pd.DataFrame:
    rows = []
    for r in runs:
        cfg = manifest(r)["config"]
        rows.append({k: get(cfg, k) for k in KEYS[exp]} | {"seed": cfg["seed"]} | run_metrics(r))
    return pd.DataFrame(rows)


def report(exp: str, df: pd.DataFrame) -> str:
    keys = list(KEYS[exp])
    head = " | ".join(keys) + " | seeds | " + " | ".join(COLS)
    lines = [
        f"# {exp} pilot",
        "",
        "Mean and 95% bootstrap CI over seeds; warm-up (first 60 s) excluded. `exposure` = "
        "Σ over attested workers of keys held × (1 − assurance) (doc 04 §8); `warm_mb` = idle warm-VM memory "
        "(donor cost); `solve_s` = planner wall time per solve.",
        "",
        f"| {head} |",
        "|" + "---|" * (len(keys) + 1 + len(COLS)),
    ]
    for raw, g in df.groupby(keys):
        key = raw if isinstance(raw, tuple) else (raw,)
        cells = [fmt(*bootstrap_ci(g[c].to_numpy()), digits=3) for c in COLS]
        lines.append(f"| {' | '.join(map(str, key))} | {len(g)} | {' | '.join(cells)} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("exp", choices=sorted(KEYS))
    p.add_argument("root", type=Path)
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args()
    runs = sorted(d for d in a.root.iterdir() if (d / "manifest.json").exists())
    df = collect(a.exp, runs)
    out = a.out or Path(f"docs/pilots/{a.exp}.md")
    out.write_text(report(a.exp, df))
    df.to_csv(out.with_suffix(".csv"), index=False)
    print(out)


if __name__ == "__main__":
    main()
