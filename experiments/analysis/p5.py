"""P5 pilot reports (E05, E06, E07, E10): latency, network share, migrations, spillover and exposure per system,
mean and 95% bootstrap CI over seeds (doc 06 §6), plus the paired P99 gap to a reference system. Writes
``docs/pilots/<EXP>.md`` and a CSV."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from experiments.analysis.common import bootstrap_ci, fmt, get, latency_metrics, manifest, table

KEYS = {
    "E05": ("label", "scenario.geo.regions"),
    "E06": ("label", "scenario.regime"),
    "E07": ("label", "scenario.load.flash_crowds"),
    "E10": ("label", "scenario.hw_mix"),
}
REFERENCE = {"E05": "none_global", "E06": "static_kmeans", "E07": "nearest", "E10": "simple"}
COLS = ("p50_sync", "p99_sync", "met", "net_s", "clusters", "moves_wh", "max_moves_h", "spills_k", "exposure")
FLASH = (300.0, 600.0)


def _key(name: str, v: Any) -> str:
    if name.endswith("regions"):
        return "+".join(v) if v else "world"
    if name.endswith("flash_crowds"):
        return "flash" if v else "none"
    if name.endswith("hw_mix"):
        return "homogeneous" if len(v) == 1 else "mixed"
    return str(v)


def _moves(ev: pd.DataFrame, samples: pd.DataFrame, horizon: float) -> tuple[float, float]:
    """Moves per attested worker-hour, and the most moves of any worker inside any one-hour window."""
    mv = ev[ev.kind == "move"] if len(ev) else ev
    if not len(mv):
        return 0.0, 0.0
    worker_h = float(samples.attested.mean()) * horizon / 3600.0 if len(samples) else np.nan
    worst = 0
    for _, g in mv.groupby("worker"):
        t = np.sort(g.t.to_numpy())
        worst = max(worst, int(max(((t >= a) & (t < a + 3600.0)).sum() for a in t)))
    return len(mv) / worker_h, float(worst)


def run_metrics(run: Path) -> dict[str, float]:
    inv, ev, cache, samples = (table(run, n) for n in ("invocations", "events", "cache", "samples"))
    horizon = float(manifest(run)["config"]["horizon_s"])
    m = latency_metrics(inv)
    ok = inv[(inv.outcome == "ok") & (inv.t_arrive >= 60)]
    share = ok.cluster.value_counts(normalize=True) if len(ok) else pd.Series(dtype=float)
    m["clusters"] = float((share >= 0.01).sum())
    m["net_s"] = float((ok.net_in + ok.net_out).mean()) if len(ok) else np.nan
    m["moves_wh"], m["max_moves_h"] = _moves(ev, samples, horizon)
    spills = int((ev.kind == "spillover").sum()) if len(ev) else 0
    m["spills_k"] = 1000.0 * spills / max(1.0, m["n"])
    late = cache[cache.t >= 60] if len(cache) else cache
    m["exposure"] = float(late.exposure.mean()) if len(late) else np.nan
    sync = ok[(ok.slo_class == 0) & (ok.t_arrive >= FLASH[0]) & (ok.t_arrive < FLASH[1])]
    m["p99_window"] = float(sync.e2e.quantile(0.99)) if len(sync) else np.nan
    return m


def collect(exp: str, runs: list[Path]) -> pd.DataFrame:
    rows = []
    for r in runs:
        cfg = manifest(r)["config"]
        rows.append({k: _key(k, get(cfg, k)) for k in KEYS[exp]} | {"seed": cfg["seed"]} | run_metrics(r))
    df = pd.DataFrame(rows)
    return _gap(exp, df)


def _gap(exp: str, df: pd.DataFrame) -> pd.DataFrame:
    """Paired relative P99 difference to the reference system on the same scenario (grid point and seed)."""
    grid = [k for k in KEYS[exp] if k != "label"]
    ref = df[df.label == REFERENCE[exp]].set_index([*grid, "seed"]).p99_sync
    idx = pd.MultiIndex.from_frame(df[[*grid, "seed"]])
    df["p99_gap"] = df.p99_sync.to_numpy() / ref.reindex(idx).to_numpy() - 1.0
    return df


def report(exp: str, df: pd.DataFrame) -> str:
    keys = list(KEYS[exp])
    cols = [*COLS, "p99_gap"] + (["p99_window"] if exp == "E07" else [])
    lines = [
        f"# {exp} pilot",
        "",
        "Mean and 95% bootstrap CI over seeds; warm-up (first 60 s) excluded. `net_s` = network share of a successful "
        "invocation (input + output legs); `clusters` = clusters serving ≥ 1% of traffic; `moves_wh` = orchestrator "
        "moves per attested worker-hour; `max_moves_h` = most moves of one worker in any hour (bound: "
        "`max_moves_per_h`); `spills_k` = spillovers per 1000 invocations; `exposure` = Σ keys held × (1 − assurance); "
        f"`p99_gap` = paired P99 (sync) relative to `{REFERENCE[exp]}` on the same scenario"
        + ("; `p99_window` = sync P99 during t ∈ [300, 600) s (the flash crowd)." if exp == "E07" else "."),
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
