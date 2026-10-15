"""Paper pipeline (ROADMAP P10, doc 06 §1): ``make paper`` runs every frozen experiment spec (10 seeds, idempotent),
then regenerates every table, figure and the hypothesis scorecard under ``paper/`` from the run logs only.

    python -m experiments.paper sweep [--jobs 3] [--only E20a,E20b] [--seeds 1,2]
    python -m experiments.paper analyze [--only ...]
    python -m experiments.paper all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from experiments.analysis import paper as tables
from experiments.figures import FIGURES, load_all, render
from experiments.sweep import spec_path, sweep

REPO = Path(__file__).resolve().parents[1]
# Cheap and decisive first; E18 (memory) and E02 (measured decision clock: must run alone) last with one job.
ORDER = (
    "E20a", "E20b", "E20c", "E24", "E23", "E04", "E19", "E17", "E08", "E16", "E15", "E05", "E07", "E10", "E06",
    "E13", "E14", "E09", "E03", "E12", "E18", "E02",
)  # fmt: skip
ALONE = {"E18": 1, "E02": 1}
MEASURED_HOST = "laptop-b9212a4528"


def spec_hashes() -> dict[str, str]:
    return {e: hashlib.sha256(spec_path(e).read_bytes()).hexdigest()[:16] for e in ORDER}


def run_sweeps(jobs: int, only: list[str] | None, seeds: list[int] | None, runs: Path) -> None:
    for exp in ORDER:
        if only and exp not in only:
            continue
        t0 = time.time()
        df = sweep(exp, ALONE.get(exp, jobs), runs, seeds)
        n_bad = int((df.status == "failed").sum())
        print(f"{exp}: {len(df)} runs, {n_bad} failed, {time.time() - t0:.0f} s", flush=True)


def git_sha() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False)
    return r.stdout.strip() or "unknown"


def run_counts(runs: Path) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for exp in ORDER:
        idx = runs / exp / "index.csv"
        if idx.exists():
            df = pd.read_csv(idx)
            out[exp] = {"runs": len(df), "failed": int((df.status == "failed").sum())}
    return out


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO))
    except ValueError:
        return str(p)


def analyze(runs: Path, out: Path) -> list[str]:
    """Write every table, figure and the scorecard from the run logs; return the artifact paths."""
    tab, figs = out / "tables", out / "figures"
    tab.mkdir(parents=True, exist_ok=True)
    made: list[Path | None] = []
    made += [tables.legacy_table(e, runs, tab) for e in tables.LEGACY]
    made += [tables.generic_table(e, runs, tab) for e in tables.GENERIC]
    made += [tables.e03_table(runs, tab)]
    made += [tables.viability_table(e, runs, tab) for e in ("E20a", "E20b", "E20c")]
    pareto_path, res = tables.pareto_table(runs, tab)
    made.append(pareto_path)
    measured = ["--raw", "calibration/raw", "--host", MEASURED_HOST, "--out", str(tab / "ECS1-measured.md")]
    for mod, args in (
        ("experiments.ecs1", ["--n", "200", "--out", str(tab / "ECS1-sim.md")]),
        ("experiments.ecs1_measured", measured),
    ):
        subprocess.run([sys.executable, "-m", mod, *args], check=True, cwd=REPO, capture_output=True)
        made.append(Path(args[-1]))
    made += tables.scorecard_files(runs, tab / "ECS1-sim.csv", res, tab)
    load_all()
    made += [render(f, runs, figs) for _, f in sorted(FIGURES.items())]
    return sorted(_rel(p) for p in made if p is not None)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("stage", choices=("sweep", "analyze", "all"))
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--only", type=lambda s: s.split(","), default=None)
    p.add_argument("--seeds", type=lambda s: [int(x) for x in s.split(",")], default=None)
    p.add_argument("--runs", type=Path, default=Path("runs"))
    p.add_argument("--out", type=Path, default=REPO / "paper", help="where tables, figures and the scorecard go")
    a = p.parse_args(argv)
    if a.stage in ("sweep", "all"):
        run_sweeps(a.jobs, a.only, a.seeds, a.runs)
    out = a.out
    out.mkdir(exist_ok=True)
    if a.stage in ("analyze", "all"):
        files = analyze(a.runs, out)
        info = {"git_sha": git_sha(), "specs": spec_hashes(), "runs": run_counts(a.runs), "artifacts": files}
        (out / "manifest.json").write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
        print(f"{len(files)} artifacts under {out}")


if __name__ == "__main__":
    main()
