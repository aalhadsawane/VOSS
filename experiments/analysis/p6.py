"""P6 pilot reports (E08, E14, E15, E16): success, latency, waste, detection and failover per system, mean and 95%
bootstrap CI over seeds (doc 06 §6). Writes ``docs/pilots/<EXP>.md`` and a CSV."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from experiments.analysis.common import bootstrap_ci, fmt, get, latency_metrics, manifest, table

KEYS = {
    "E08": ("label", "scenario.adversary"),
    "E14": ("scenario.regime", "scenario.adversary"),
    "E15": ("label", "scenario.faults"),
    "E16": ("label", "scenario.adversary"),
}
COLS = {
    "E08": ("success", "p99_sync", "met", "waste", "omits", "suspects", "precision", "lost"),
    "E14": ("success", "p50_sync", "p99_sync", "met", "waste", "lost"),
    "E15": ("success", "p99_sync", "p99_fault", "detect_s", "failover_s", "timeouts_fault", "lost"),
    "E16": ("success", "p50_sync", "p99_sync", "met", "waste", "duplicates_k"),
}
NOTES = {
    "waste": "extra accepted attempts per success (retries, hedges, adopted re-dispatches)",
    "omits": "results dropped by adversarial owners (ground truth)",
    "precision": "share of suspected workers that really omitted",
    "lost": "invocations without a terminal outcome by their give-up time",
    "p99_fault": "sync P99 of invocations arriving inside fault windows",
    "detect_s": "fault start → scheduler suspected",
    "failover_s": "fault start → successor active",
    "timeouts_fault": "timeouts among invocations arriving inside fault windows",
    "duplicates_k": "late duplicate results per 1000 invocations (hedge losers that finished)",
}


def _key(name: str, v: Any) -> str:
    if name.endswith("adversary"):
        return f"{v.get('regime', '').removeprefix('adversary_')} α={v.get('alpha', 0)}"
    if name.endswith("faults"):
        return str(v[0]["kind"]) if v else "none"
    return str(v)


def _ev(ev: pd.DataFrame, kind: str) -> pd.DataFrame:
    return ev[ev.kind == kind] if len(ev) else ev


def _faults(inv: pd.DataFrame, ev: pd.DataFrame) -> dict[str, float]:
    starts, out = _ev(ev, "fault_start"), {}
    sus, act = _ev(ev, "scheduler_suspect"), _ev(ev, "scheduler_active")
    det, fo, inside = [], [], np.zeros(len(inv), dtype=bool)
    for f in starts.itertuples():
        s = sus[(sus.worker == f.worker) & (sus.t >= f.t) & (sus.t <= f.t + f.value)]
        det.append(float(s.t.min() - f.t) if len(s) else float(f.value))
        a = act[(act.t >= f.t) & (act.t <= f.t + f.value) & (act.worker != f.worker)]
        fo.append(float(a.t.min() - f.t) if len(a) else float(f.value))
        inside |= ((inv.t_arrive >= f.t) & (inv.t_arrive < f.t + f.value)).to_numpy()
    win = inv[inside]
    sync = win[(win.outcome == "ok") & (win.slo_class == 0)]
    out["detect_s"] = float(np.mean(det)) if det else np.nan
    out["failover_s"] = float(np.mean(fo)) if fo else np.nan
    out["p99_fault"] = float(sync.e2e.quantile(0.99)) if len(sync) else np.nan
    out["timeouts_fault"] = float((win.outcome == "timeout").sum())
    return out


def run_metrics(run: Path) -> dict[str, float]:
    inv, ev = table(run, "invocations"), table(run, "events")
    cfg = manifest(run)["config"]
    m = latency_metrics(inv)
    ok = int((inv.outcome == "ok").sum())
    m["waste"] = (len(_ev(ev, "dispatch_accepted")) - ok) / max(ok, 1)
    omitters = set(_ev(ev, "adv_omit").worker.astype(int)) if len(_ev(ev, "adv_omit")) else set()
    sus = set(_ev(ev, "worker_suspect").worker.astype(int)) if len(_ev(ev, "worker_suspect")) else set()
    m["omits"], m["suspects"] = float(len(_ev(ev, "adv_omit"))), float(len(sus))
    m["precision"] = len(sus & omitters) / len(sus) if sus else np.nan
    m["duplicates_k"] = 1000.0 * len(_ev(ev, "duplicate_result")) / max(len(inv), 1)
    give_up = cfg["voss"]["router"]["give_up_s"]
    lim = inv.slo_class.map({0: give_up["sync"], 1: give_up["async"], 2: give_up["filler"]})
    end = float(cfg["horizon_s"]) + float(cfg["drain_s"])
    m["lost"] = float(((inv.outcome == "unfinished") & (inv.t_arrive + lim < end)).sum())
    return m | _faults(inv, ev)


def collect(exp: str, runs: list[Path]) -> pd.DataFrame:
    rows = []
    for r in runs:
        cfg = manifest(r)["config"]
        rows.append({k: _key(k, get(cfg, k)) for k in KEYS[exp]} | {"seed": cfg["seed"]} | run_metrics(r))
    return pd.DataFrame(rows)


def report(exp: str, df: pd.DataFrame) -> str:
    keys, cols = list(KEYS[exp]), list(COLS[exp])
    notes = "; ".join(f"`{c}` = {NOTES[c]}" for c in cols if c in NOTES)
    lines = [
        f"# {exp} pilot",
        "",
        f"Mean and 95% bootstrap CI over seeds; warm-up (first 60 s) excluded from latency. {notes}.",
        "",
        f"| {' | '.join(keys)} | seeds | {' | '.join(cols)} |",
        "|" + "---|" * (len(keys) + 1 + len(cols)),
    ]
    for raw, g in df.groupby(keys[::-1]):
        key = (raw if isinstance(raw, tuple) else (raw,))[::-1]
        cells = [fmt(*bootstrap_ci(g[c].dropna().to_numpy()), digits=3) for c in cols]
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
