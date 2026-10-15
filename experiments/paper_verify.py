"""Verify a (re)run of the paper sweeps against the committed result hashes (doc 01 §8, D-66).

``paper/run-hashes.csv`` records, for every run behind the paper tables, the run directory (its config hash) and the
result hash of the original sweep. ``python -m experiments.paper_verify`` compares each
``runs/<EXP>/index.csv`` with it: identical hashes mean the rerun reproduced the logs the tables were drawn from, bit for bit.

Usage: ``python -m experiments.paper_verify [--runs runs] [--only E04,E19]``; exits 1 on any mismatch or missing run.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
HASHES = REPO / "paper" / "run-hashes.csv"


def compare(runs: Path, only: set[str] | None = None) -> pd.DataFrame:
    """One row per reference run with ``status`` in ``ok``, ``mismatch`` or ``missing``."""
    ref = pd.read_csv(HASHES, dtype=str)
    if only:
        ref = ref[ref.experiment.isin(only)]
    got: dict[tuple[str, str], str] = {}
    for exp in sorted(ref.experiment.unique()):
        idx = runs / exp / "index.csv"
        if idx.exists():
            df = pd.read_csv(idx, dtype=str).fillna("")
            got.update(
                {(exp, Path(r.run_dir).name): r.result_hash for r in df.itertuples() if r.status in ("ok", "cached")}
            )
    out = ref.copy()
    out["got"] = [got.get((r.experiment, r.run_dir), "") for r in ref.itertuples()]
    out["status"] = [
        "missing" if not g else ("ok" if g == h else "mismatch") for g, h in zip(out.got, out.result_hash, strict=True)
    ]
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs", type=Path, default=REPO / "runs")
    p.add_argument("--only", default="")
    a = p.parse_args(argv)
    df = compare(a.runs, set(filter(None, a.only.split(","))) or None)
    print(df.groupby(["experiment", "status"]).size().unstack(fill_value=0).to_string())
    bad = int((df.status != "ok").sum())
    print(f"{len(df) - bad}/{len(df)} runs reproduce their recorded result hash")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
