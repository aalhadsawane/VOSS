"""Merge per-shard result parts into one ``results/<spec>-<run id>`` directory (plan V6).

The experiment workflow collects summaries and hashes in each shard, where the raw logs are, and uploads only those
small files. The publish job concatenates the parts here instead of downloading every run's raw tables: a held-out
sweep has thousands of runs and their raw logs do not fit one runner's disk or a GitHub release's asset limit.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _read(parts: list[Path], name: str) -> pd.DataFrame:
    frames = []
    for p in sorted(parts):
        path = p / name
        if path.exists():
            frames.append(pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, dtype=str))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def merge(parts: list[Path], dst: Path) -> pd.DataFrame:
    """Concatenate ``summary.parquet`` and ``hashes.csv`` of every part, sorted by run; writes ``dst``."""
    summary = _read(parts, "summary.parquet")
    hashes = _read(parts, "hashes.csv")
    if summary.empty or hashes.empty:
        raise ValueError(f"no result parts under {parts}")
    summary = summary.sort_values("run").reset_index(drop=True)
    hashes = hashes.sort_values("run").reset_index(drop=True)
    dup = summary[summary.run.duplicated()].run.tolist()
    if dup:
        raise ValueError(f"run appears in more than one part: {dup[:5]}")
    dst.mkdir(parents=True, exist_ok=True)
    summary.to_parquet(dst / "summary.parquet", index=False)
    hashes.to_csv(dst / "hashes.csv", index=False)
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="experiments.merge_results", description=__doc__)
    p.add_argument("--parts", type=Path, nargs="+", required=True)
    p.add_argument("--dst", type=Path, required=True)
    a = p.parse_args(argv)
    df = merge(a.parts, a.dst)
    print(f"merged {len(df)} runs into {a.dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
