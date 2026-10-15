"""Experiment runner (doc 06 §1): a base config × a grid of overrides × seeds, one run per point, idempotent.

``python -m experiments.runner configs/experiments/E03.yaml`` runs every point not already present under
``runs/<experiment>/<config_hash>/`` and prints the run directories. ``experiments.sweep`` adds failure capture
and a run index on top (``make sweep EXP=...``).
"""

from __future__ import annotations

import argparse
import itertools
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import yaml
from voss.cli import cmd_run
from voss.core.config import RunConfig, apply_overrides, load_yaml_tree

ABLATIONS = Path(__file__).resolve().parents[1] / "configs" / "ablations.yaml"


def systems(spec: dict[str, Any]) -> dict[str, list[str]]:
    """``systems`` plus the switches named by ``ablations`` (``all`` or a list) from ``configs/ablations.yaml``."""
    out: dict[str, list[str]] = dict(spec.get("systems", {"": []}))
    names = spec.get("ablations")
    if names:
        table: dict[str, list[str]] = yaml.safe_load(ABLATIONS.read_text())
        out |= {n: list(table[n]) for n in (sorted(table) if names == "all" else names)}
    return out


def points(spec: dict[str, Any]) -> list[list[str]]:
    """Override lists for every system × grid point × seed (keys sorted for stable order).

    ``systems`` maps a label to its own overrides: compared systems run paired on the same scenario (doc 06 §4).
    ``seeds_by_system`` gives a system fewer seeds when its runs are too expensive for the full protocol (D-63).
    """
    grid = spec.get("grid", {})
    keys = sorted(grid)
    systems_ = systems(spec)
    seeds_by = spec.get("seeds_by_system", {})
    out = []
    for label in sorted(systems_):
        for values in itertools.product(*(grid[k] for k in keys)):
            gv = [f"{k}={json.dumps(v)}" for k, v in zip(keys, values, strict=True)]
            for seed in seeds_by.get(label, spec.get("seeds", [1])):
                tag = [f"label={label}"] if label else []
                out.append([*spec.get("overrides", []), *systems_[label], *gv, f"seed={seed}", *tag])
    return out


def _one(cfg: RunConfig, run_dir: Path) -> Path:
    if not (run_dir / "manifest.json").exists():
        cmd_run(cfg, run_dir)
    return run_dir


def run_experiment(path: Path, out_root: Path = Path("runs"), jobs: int = 1) -> list[Path]:
    """Run every point (in ``jobs`` processes); runs are independent and deterministic."""
    spec = yaml.safe_load(path.read_text())
    base = (path.parent / spec["base"]).resolve()
    work = []
    for ov in points(spec):
        cfg = RunConfig.model_validate(apply_overrides(load_yaml_tree(base), ov))
        work.append((cfg, out_root / spec["experiment"] / cfg.config_hash()[:16]))
    if jobs <= 1:
        return [_one(c, d) for c, d in work]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(_one, *zip(*work, strict=True)))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("spec", type=Path)
    p.add_argument("--out", type=Path, default=Path("runs"))
    p.add_argument("--jobs", type=int, default=1)
    a = p.parse_args()
    for d in run_experiment(a.spec, a.out, a.jobs):
        print(d)


if __name__ == "__main__":
    main()
