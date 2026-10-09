"""P7 pilot reports (E12 reputation dynamics, E13 accounting cost and completeness): mean and 95% bootstrap CI over
seeds (doc 06 §6), from logs only. Writes ``docs/pilots/<EXP>.md`` and a CSV."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from experiments.analysis.common import get, latency_metrics, manifest, report_table, table

KEYS = {
    "E12": ("label", "voss.reputation.tie_break"),
    "E13": ("label", "scenario.faults"),
}
COLS = {
    "E12": ("success", "p99_sync", "omits_k", "gini", "jain", "top10", "starved", "onoff_rate", "score_gap"),
    "E13": (
        "receipts_s",
        "db_kb_s",
        "verify_ms_s",
        "settle_ms",
        "lat_p50",
        "lat_max",
        "complete",
        "missing",
        "unexplained",
        "p99_sync",
    ),
}
NOTES = {
    "omits_k": "results dropped by on-off owners per 1000 invocations",
    "gini": "Gini of work credits over identities that held a session",
    "jain": "Jain index of the same",
    "top10": "share of work credits earned by the top 10% of identities",
    "starved": "share of benign identities with ≥ 10 min of sessions and no work credit",
    "onoff_rate": "work credit per session-hour of on-off identities ÷ that of benign identities",
    "score_gap": "mean score of benign minus on-off identities over the second half",
    "receipts_s": "receipt rows per second (all statuses)",
    "db_kb_s": "receipt append traffic to the DB",
    "verify_ms_s": "router CPU for receipt signature checks per second",
    "settle_ms": "settlement job CPU per settlement",
    "lat_p50": "median receipt → credit latency",
    "lat_max": "worst receipt → credit latency",
    "complete": "verified receipts ÷ results sent by workers (ground truth)",
    "missing": "results sent before the end without a receipt",
    "unexplained": "missing receipts not accounted for by results lost in the network (owner powered off mid-upload)",
}


def _key(name: str, v: Any) -> str:
    if name.endswith("faults"):
        return "+".join(str(f["kind"]).removeprefix("sched_") for f in v) if v else "none"
    return str(v)


def _ev(ev: pd.DataFrame, kind: str) -> pd.DataFrame:
    return ev[ev.kind == kind] if len(ev) else ev


def gini(x: np.ndarray) -> float:
    x = np.sort(np.asarray(x, dtype=float))
    n, s = len(x), x.sum()
    if n == 0 or s <= 0:
        return np.nan
    return float((2 * np.arange(1, n + 1) - n - 1) @ x / (n * s))


def jain(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    return float(x.sum() ** 2 / (len(x) * (x**2).sum())) if len(x) and (x**2).sum() > 0 else np.nan


def _reputation(run: Path, ev: pd.DataFrame, push_s: float) -> dict[str, float]:
    rep, cr = table(run, "reputation"), table(run, "credits")
    work = cr[cr.kind.isin(["work", "duplicate"])].groupby("worker").amount.sum()
    hours = rep[rep.active.astype(bool)].groupby("worker").size() * push_s / 3600
    ids = hours.index
    earned = work.reindex(ids, fill_value=0.0).to_numpy()
    adv = set(_ev(ev, "adversary").worker.astype(int))
    is_adv = np.array([int(w) in adv for w in ids])
    rate = earned / np.maximum(hours.to_numpy(), 1e-9)
    benign_rate = rate[~is_adv].mean() if (~is_adv).any() else np.nan
    long_benign = (~is_adv) & (hours.to_numpy() >= 10 / 60)
    late = rep[rep.t >= rep.t.max() / 2]
    sc = late.groupby("worker").score.mean()
    sc_adv = sc[sc.index.isin(adv)]
    return {
        "gini": gini(earned),
        "jain": jain(earned),
        "top10": float(np.sort(earned)[::-1][: max(1, len(earned) // 10)].sum() / max(earned.sum(), 1e-9)),
        "starved": float((earned[long_benign] == 0).mean()) if long_benign.any() else np.nan,
        "onoff_rate": float(rate[is_adv].mean() / benign_rate) if is_adv.any() and benign_rate > 0 else np.nan,
        "score_gap": float(sc[~sc.index.isin(adv)].mean() - sc_adv.mean()) if len(sc_adv) else np.nan,
    }


def _accounting(run: Path, ev: pd.DataFrame, horizon: float) -> dict[str, float]:
    rc, msg, sol = table(run, "receipts"), table(run, "messages"), table(run, "solver")
    st, sent = _ev(ev, "settlement"), _ev(ev, "result_sent")
    paid = rc[rc.status.isin(["ok", "duplicate"])]
    db = msg[msg.kind == "DbAppendReceipts"].bytes.sum() if len(msg) else 0.0
    verify = sol[sol.kind == "verify"].charged_s.sum() if len(sol) else 0.0
    return {
        "receipts_s": len(rc) / horizon,
        "db_kb_s": float(db) / 1024 / horizon,
        "verify_ms_s": 1000 * float(verify) / horizon,
        "settle_ms": 1000 * float(st.cpu_s.mean()) if len(st) else np.nan,
        "lat_p50": float(st.lat_p50.mean()) if len(st) else np.nan,
        "lat_max": float(st.lat_max.max()) if len(st) else np.nan,
        "complete": len(paid) / max(len(sent), 1),
        "missing": float(len(miss := _missing(sent, paid, horizon))),
        "unexplained": float(max(0, len(miss) - int(msg[msg.kind == "Result"].drops.sum()))) if len(msg) else np.nan,
    }


def _missing(sent: pd.DataFrame, paid: pd.DataFrame, end: float) -> set[tuple[int, int, int]]:
    got = set(zip(paid.inv.astype(int), paid.attempt.astype(int), paid.worker.astype(int), strict=True))
    early = sent[sent.t < end - 2.0]
    return set(zip(early.inv.astype(int), early.value.astype(int), early.worker.astype(int), strict=True)) - got


def run_metrics(run: Path) -> dict[str, float]:
    inv, ev = table(run, "invocations"), table(run, "events")
    cfg = manifest(run)["config"]
    m = latency_metrics(inv)
    m["omits_k"] = 1000.0 * len(_ev(ev, "adv_omit")) / max(len(inv), 1)
    horizon = float(cfg["horizon_s"]) + float(cfg["drain_s"])
    return m | _reputation(run, ev, float(get(cfg, "voss.reputation.push_s"))) | _accounting(run, ev, horizon)


def collect(exp: str, runs: list[Path]) -> pd.DataFrame:
    rows = []
    for r in runs:
        cfg = manifest(r)["config"]
        rows.append({k: _key(k, get(cfg, k)) for k in KEYS[exp]} | {"seed": cfg["seed"]} | run_metrics(r))
    return pd.DataFrame(rows)


def report(exp: str, df: pd.DataFrame) -> str:
    return report_table(exp, df, list(KEYS[exp]), list(COLS[exp]), NOTES)


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
