"""Verify a (re)run of the paper sweeps against the committed result hashes (doc 01 §8, D-66).

``paper/run-hashes.csv`` records, for every run behind the paper tables, the run directory (its config hash) and the
result hash of the original sweep. ``python -m experiments.paper_verify`` compares each
``runs/<EXP>/index.csv`` with it: identical hashes mean the rerun reproduced the logs the tables were drawn from,
bit for bit.

Usage: ``python -m experiments.paper_verify [--runs runs] [--only E04,E19]``; exits 1 on any mismatch or missing run.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from experiments.analysis import paper as tables

REPO = Path(__file__).resolve().parents[1]
HASHES = REPO / "paper" / "run-hashes.csv"
WALL_CLOCK = {"solve_s", "sim_s_per_s", "build_s", "solve_wall_s", "wall_s"}  # measured, not simulated: may differ


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


def regenerate(exp: str, runs: Path, out: Path) -> Path | None:
    """Re-draw ``exp``'s table from the run logs into ``out`` (the same functions ``make paper`` uses)."""
    if exp in tables.LEGACY:
        tables.legacy_table(exp, runs, out)
    elif exp in tables.GENERIC:
        tables.generic_table(exp, runs, out)
    elif exp == "E03":
        tables.e03_table(runs, out)
    elif exp in ("E20a", "E20b", "E20c"):
        tables.viability_table(exp, runs, out)
    elif exp == "E23":
        tables.pareto_table(runs, out)
    path = out / f"{exp}.csv"
    return path if path.exists() else None


def table_diff(exp: str, runs: Path) -> list[str]:
    """Lines describing how the regenerated per-seed table differs from the committed ``paper/tables/<exp>.csv``."""
    with tempfile.TemporaryDirectory() as tmp:
        fresh = regenerate(exp, runs, Path(tmp))
        committed = REPO / "paper" / "tables" / f"{exp}.csv"
        if fresh is None or not committed.exists():
            return [f"{exp}: table missing (fresh={fresh is not None}, committed={committed.exists()})"]
        a, b = pd.read_csv(committed), pd.read_csv(fresh)
    return diff_frames(exp, a, b)


def diff_frames(exp: str, a: pd.DataFrame, b: pd.DataFrame) -> list[str]:
    """Column-wise comparison of a committed table ``a`` with its regeneration ``b`` (wall-clock: informational)."""
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return [f"{exp}: shape differs, committed {a.shape} vs rerun {b.shape}"]
    keys = [c for c in a.columns if not is_numeric_dtype(a[c])] + (["seed"] if "seed" in a.columns else [])
    a, b = a.sort_values(keys).reset_index(drop=True), b.sort_values(keys).reset_index(drop=True)
    out: list[str] = []
    for c in a.columns:
        if not is_numeric_dtype(a[c]):
            same = bool((a[c].fillna("") == b[c].fillna("")).all())
            worst = 0.0 if same else float("inf")
        else:
            x, y = a[c].to_numpy(float), b[c].to_numpy(float)
            worst = float(np.nanmax(np.abs(x - y) / np.maximum(np.abs(x), 1e-12))) if len(x) else 0.0
        if worst > 1e-9:
            tag = "wall-clock (informational)" if c in WALL_CLOCK else "DIFFERS"
            out.append(f"{exp}.{c}: max relative difference {worst:.3g} [{tag}]")
    return out or [f"{exp}: table identical to the committed one ({len(a)} rows)"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs", type=Path, default=REPO / "runs")
    p.add_argument("--only", default="")
    p.add_argument(
        "--tables", action="store_true", help="also re-draw each experiment's table and diff it against paper/"
    )
    a = p.parse_args(argv)
    only = set(filter(None, a.only.split(",")))
    df = compare(a.runs, only or None)
    print(df.groupby(["experiment", "status"]).size().unstack(fill_value=0).to_string())
    bad = int((df.status != "ok").sum())
    print(f"{len(df) - bad}/{len(df)} runs reproduce their recorded result hash")
    worse = 0
    if a.tables:
        for exp in sorted(only or df.experiment.unique()):
            lines = table_diff(exp, a.runs)
            print("\n".join(lines))
            worse += sum("DIFFERS" in x or "shape" in x or "missing" in x for x in lines)
    return 1 if bad or worse else 0


if __name__ == "__main__":
    raise SystemExit(main())
