"""Sweep runner (doc 06 §1, doc 05 §2): every point of ``configs/experiments/<EXP>.yaml`` (systems and ablations ×
grid × seeds) in parallel processes, idempotent, with failures recorded instead of aborting the sweep, and an index
``runs/<EXP>/index.csv`` (label, seed, run directory, config / scenario / result hashes, status) for analysis and
figures.

``make sweep EXP=E19 JOBS=4`` or ``python -m experiments.sweep E19 --jobs 4 [--seeds 1,2]``.
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from voss.cli import cmd_run
from voss.core.config import RunConfig, apply_overrides, load_yaml_tree

from experiments.runner import points

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Point:
    label: str
    seed: int
    overrides: tuple[str, ...]
    run_dir: str
    config_hash: str


@dataclass(frozen=True)
class Outcome:
    run_dir: str
    status: str  # ok | cached | failed
    wall_s: float
    scenario_hash: str = ""
    result_hash: str = ""
    error: str = ""


def spec_path(exp: str) -> Path:
    return REPO / "configs" / "experiments" / f"{exp}.yaml"


def plan(exp: str, out_root: Path, seeds: list[int] | None = None) -> tuple[list[Point], list[RunConfig]]:
    """All points of the experiment (optionally restricted to ``seeds``), in the spec's stable order."""
    path = spec_path(exp)
    spec: dict[str, Any] = yaml.safe_load(path.read_text())
    if seeds is not None:
        spec["seeds"], spec["seeds_by_system"] = seeds, {}
    base = load_yaml_tree((path.parent / spec["base"]).resolve())
    pts, cfgs = [], []
    for ov in points(spec):
        cfg = RunConfig.model_validate(apply_overrides(base, ov))
        run_dir = out_root / spec["experiment"] / cfg.config_hash()[:16]
        pts.append(Point(cfg.label, cfg.seed, tuple(ov), str(run_dir), cfg.config_hash()))
        cfgs.append(cfg)
    return pts, cfgs


def _one(cfg: RunConfig, run_dir: str) -> Outcome:
    d = Path(run_dir)
    if (d / "manifest.json").exists():
        m = json.loads((d / "manifest.json").read_text())
        return Outcome(run_dir, "cached", 0.0, m.get("scenario_hash", ""), m.get("result_hash", ""))
    t0 = time.perf_counter()
    try:
        man = cmd_run(cfg, d)
    except Exception:
        return Outcome(run_dir, "failed", time.perf_counter() - t0, error=traceback.format_exc(limit=5))
    return Outcome(run_dir, "ok", time.perf_counter() - t0, man.scenario_hash or "", man.result_hash)


def sweep(exp: str, jobs: int = 1, out_root: Path = Path("runs"), seeds: list[int] | None = None) -> pd.DataFrame:
    pts, cfgs = plan(exp, out_root, seeds)
    dirs = [p.run_dir for p in pts]
    if jobs <= 1:
        outs = [_one(c, d) for c, d in zip(cfgs, dirs, strict=True)]
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            outs = list(pool.map(_one, cfgs, dirs))
    rows = [asdict(p) | asdict(o) for p, o in zip(pts, outs, strict=True)]
    df = pd.DataFrame(rows).drop(columns=["overrides"]).assign(overrides=[" ".join(p.overrides) for p in pts])
    index = out_root / exp / "index.csv"
    index.parent.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["wall_s"]).to_csv(index, index=False)
    return df


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("exp")
    p.add_argument("--jobs", type=int, default=1)
    p.add_argument("--out", type=Path, default=Path("runs"))
    p.add_argument("--seeds", type=lambda s: [int(x) for x in s.split(",")], default=None)
    a = p.parse_args()
    df = sweep(a.exp, a.jobs, a.out, a.seeds)
    counts = df.status.value_counts().to_dict()
    print(f"{a.exp}: {len(df)} points {counts} → {a.out / a.exp / 'index.csv'}")
    for r in df[df.status == "failed"].itertuples():
        print(f"FAILED {r.label} seed={r.seed} {r.run_dir}\n{r.error}")
    if "failed" in counts:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
