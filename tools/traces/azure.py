"""Azure Functions 2019 trace → sampled functions and per-minute arrivals (docs/REVISION_PLAN.md V9.1, D-89).

    uv run python -m tools.traces.azure --out data/traces/azure2019 [--archive <tar.xz>] [--n 200] [--seed 1]

For each split (development = days 1-4, held-out = days 8-11; functions are sampled separately per split):
- tenant = owner hash; a function is synchronous if its trigger is ``http``, else asynchronous;
- functions with at least one invocation in the split are ranked by total invocations and cut into 10 rate deciles;
  ``n / 10`` functions are sampled from each decile with ``core.rng.stream`` (deterministic);
- ``functions_<split>.parquet``: one row per sampled function (short hashes, trigger, sync, decile, rate, duration
  percentiles in ms from the trace, for the mapping onto measured profiles only, never as run times);
- ``arrivals_<split>.parquet``: non-zero per-minute counts ``(fn, minute, count)``, minute 0 = 00:00 of the split's
  first day. Within a minute the simulator draws a Poisson process with that count.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from voss.core.rng import stream

from tools.traces.common import download, write_provenance

URL = (
    "https://github.com/Azure/AzurePublicDataset/releases/download/dataset-functions-2019/"
    "azurefunctions_dataset2019_azurefunctions-dataset2019.tar.xz"
)
SOURCE = {
    "name": "Azure Functions trace 2019 (Shahrad et al., USENIX ATC 2020)",
    "url": URL,
    "description": "https://github.com/Azure/AzurePublicDataset/blob/master/AzureFunctionsDataset2019.md",
    "licence": "CC-BY 4.0 (AzurePublicDataset LICENSE)",
}
SPLITS = {"dev": (1, 2, 3, 4), "heldout": (8, 9, 10, 11)}
KEYS = ["HashOwner", "HashApp", "HashFunction"]
MINUTES = [str(m) for m in range(1, 1441)]


def extract(archive: Path, work: Path, days: tuple[int, ...]) -> Path:
    """Extract the invocation and duration files of ``days`` (one pass of ``tar``; xz has no random access)."""
    names = [
        f"{kind}.anon.d{d:02d}.csv"
        for d in days
        for kind in ("invocations_per_function_md", "function_durations_percentiles")
    ]
    missing = [n for n in names if not (work / n).exists()]
    if missing:
        work.mkdir(parents=True, exist_ok=True)
        subprocess.run(["tar", "-xJf", str(archive), "-C", str(work), *missing], check=True)
    return work


def read_day(work: Path, day: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(per-minute counts with keys and trigger, duration percentiles) of one day."""
    inv = pd.read_csv(work / f"invocations_per_function_md.anon.d{day:02d}.csv")
    inv[MINUTES] = inv[MINUTES].astype(np.int32)
    dur = pd.read_csv(work / f"function_durations_percentiles.anon.d{day:02d}.csv")
    return inv, dur


def short(h: pd.Series) -> pd.Series:
    """First 12 hex digits of a trace hash: enough to stay unique, short in files."""
    out: pd.Series = h.str.slice(0, 12)
    return out


def split_frames(work: Path, days: tuple[int, ...]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(function table with totals, long per-minute counts, duration medians) over the split's days."""
    meta, longs, durs = [], [], []
    for k, day in enumerate(days):
        inv, dur = read_day(work, day)
        inv = inv.assign(fid=short(inv.HashOwner) + short(inv.HashApp) + short(inv.HashFunction)).copy()
        meta.append(inv[["fid", "HashOwner", "HashApp", "Trigger"]])
        m = inv.set_index("fid")[MINUTES].stack()
        m = m[m > 0].reset_index()
        m.columns = ["fid", "minute", "count"]
        m["minute"] = m.minute.astype(np.int32) - 1 + k * 1440
        longs.append(m)
        dur["fid"] = short(dur.HashOwner) + short(dur.HashApp) + short(dur.HashFunction)
        durs.append(dur[["fid", "Count", "percentile_Average_50", "percentile_Average_99"]])
    fns = pd.concat(meta).drop_duplicates("fid").set_index("fid")
    counts = pd.concat(longs, ignore_index=True)
    d = pd.concat(durs)
    w = d.Count.clip(lower=1)
    med = (
        d.assign(w=w, p50=d.percentile_Average_50 * w, p99=d.percentile_Average_99 * w)
        .groupby("fid")[["w", "p50", "p99"]]
        .sum()
    )
    dur_ms = pd.DataFrame({"dur_p50_ms": med.p50 / med.w, "dur_p99_ms": med.p99 / med.w})
    return fns, counts, dur_ms


def sample(fns: pd.DataFrame, totals: pd.Series, n: int, seed: int, split: str) -> list[str]:
    """``n / 10`` functions from each invocation-rate decile (sorted ids first, so the draw is deterministic)."""
    t = totals[totals > 0].sort_index()
    dec = pd.qcut(t.rank(method="first"), 10, labels=False)
    gen = stream(seed, "traces.azure.sample", split)
    out: list[str] = []
    for d in range(10):
        ids = sorted(t.index[dec == d])
        k = min(len(ids), n // 10)
        out += [ids[i] for i in sorted(gen.choice(len(ids), size=k, replace=False))]
    return sorted(out)


def derive(work: Path, out: Path, split: str, n: int, seed: int) -> pd.DataFrame:
    """Write ``functions_<split>.parquet`` and ``arrivals_<split>.parquet``; return the function table."""
    days = SPLITS[split]
    fns, counts, dur = split_frames(work, days)
    totals = counts.groupby("fid")["count"].sum()
    chosen = sample(fns, totals, n, seed, split)
    t = totals.reindex(chosen)
    dec = pd.qcut(totals[totals > 0].rank(method="first"), 10, labels=False).reindex(chosen)
    table = pd.DataFrame(
        {
            "fn": range(len(chosen)),
            "fid": chosen,
            "owner": short(fns.loc[chosen, "HashOwner"]).to_numpy(),
            "app": short(fns.loc[chosen, "HashApp"]).to_numpy(),
            "trigger": fns.loc[chosen, "Trigger"].to_numpy(),
            "sync": (fns.loc[chosen, "Trigger"] == "http").to_numpy(),
            "decile": dec.to_numpy().astype(int),
            "rate_per_s": (t / (len(days) * 86400)).to_numpy(),
            "dur_p50_ms": dur.reindex(chosen).dur_p50_ms.to_numpy(),
            "dur_p99_ms": dur.reindex(chosen).dur_p99_ms.to_numpy(),
        }
    )
    idx = dict(zip(chosen, range(len(chosen)), strict=True))
    arr = counts[counts.fid.isin(idx)].assign(fn=lambda x: x.fid.map(idx).astype(np.int32))
    arr = arr[["fn", "minute", "count"]].sort_values(["fn", "minute"]).reset_index(drop=True)
    out.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out / f"functions_{split}.parquet", index=False)
    arr.to_parquet(out / f"arrivals_{split}.parquet", index=False)
    return table


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.traces.azure")
    p.add_argument("--out", type=Path, default=Path("data/traces/azure2019"))
    p.add_argument("--archive", type=Path, default=None, help="local copy of the trace archive (else downloaded)")
    p.add_argument("--work", type=Path, default=Path("data/raw/azure2019"))
    p.add_argument("--n", type=int, default=200, help="sampled functions per split (V9.5 sets the final value)")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args(argv)
    archive = a.archive or download(URL, a.work / "azurefunctions-dataset2019.tar.xz")
    days = tuple(sorted({d for ds in SPLITS.values() for d in ds}))
    work = extract(archive, a.work, days)
    for split in SPLITS:
        t = derive(work, a.out, split, a.n, a.seed)
        print(f"{split}: {len(t)} functions, {int(t.sync.sum())} synchronous, rate {t.rate_per_s.sum():.1f}/s")
    params = {
        "splits": {k: list(v) for k, v in SPLITS.items()},
        "n_per_split": a.n,
        "seed": a.seed,
        "sampling": "10 invocation-rate deciles, n/10 each",
        "sync": "trigger == http",
        "duration": "count-weighted mean of daily median and p99 (ms); mapping only",
    }
    write_provenance(a.out, SOURCE, [archive], params)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
