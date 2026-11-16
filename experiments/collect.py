"""Collect a finished sweep (docs/REVISION_PLAN.md V6): one metric row per run into ``summary.parquet``
and the hashes of every run into ``hashes.csv`` (the file ``experiments.verify`` checks against), both in ``--dst``
(``results/<spec>-<run id>`` on GitHub Actions). A summary row carries the run's value of every ``grid`` axis of
the spec.

``python -m experiments.collect <spec> --runs runs --dst results/<spec>``. Analysis reads these logs only (AGENTS.md
rule 10).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from experiments.analysis.summary import summarize

HASH_COLS = ["run", "label", "seed", "config_hash", "scenario_hash", "calibration_hash", "result_hash", "git_sha"]


def reader(run_dir: Path) -> Callable[[str], pd.DataFrame]:
    """``frame(table)`` over a run directory's Parquet files; a table the run never logged is empty."""

    def frame(table: str) -> pd.DataFrame:
        p = run_dir / f"{table}.parquet"
        return pd.read_parquet(p) if p.exists() else pd.DataFrame()

    return frame


def grid_keys(spec: str) -> list[str]:
    """Sorted grid axes of ``configs/experiments/<spec>.yaml`` (none when the spec has no grid or is not found)."""
    path = Path(__file__).resolve().parents[1] / "configs" / "experiments" / f"{spec}.yaml"
    return sorted((yaml.safe_load(path.read_text()) or {}).get("grid") or {}) if path.exists() else []


def lookup(cfg: dict[str, Any], key: str) -> Any:
    """Value at dotted ``key`` of a resolved config (None when absent): a grid coordinate of the run."""
    node: Any = cfg
    for part in key.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node


def one(run_dir: Path, axes: list[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """(hash row, summary row) of one run; the summary row carries the run's value of every grid axis in ``axes``."""
    man = json.loads((run_dir / "manifest.json").read_text())
    cfg = man["config"]
    head = {
        "run": run_dir.name,
        "label": cfg.get("label") or "",
        "seed": cfg["seed"],
        **{k: man.get(k) or "" for k in HASH_COLS[3:]},
    }
    coords = {k: lookup(cfg, k) for k in axes or []}
    warm, end = float(cfg["scenario"]["warmup_s"]), float(cfg["horizon_s"])
    cost = {
        "wall_s": float(man.get("wall_s", 0.0)),
        "peak_rss_mb": float(man.get("peak_rss_mb", 0.0)),
        "events": int(man.get("events", 0)),
    }
    return head, {"run": run_dir.name, "label": head["label"], "seed": head["seed"]} | coords | cost | summarize(
        reader(run_dir), warm, end
    )


def collect(spec: str, runs: Path, dst: Path) -> pd.DataFrame:
    """Summaries of every run under ``runs/<spec>`` in sorted order; writes the two result files."""
    dirs = sorted(d for d in (runs / spec).iterdir() if (d / "manifest.json").exists())
    axes = grid_keys(spec)
    pairs = [one(d, axes) for d in dirs]
    dst.mkdir(parents=True, exist_ok=True)
    hashes = pd.DataFrame([h for h, _ in pairs], columns=HASH_COLS)
    hashes.to_csv(dst / "hashes.csv", index=False)
    summary = pd.DataFrame([s for _, s in pairs])
    summary.to_parquet(dst / "summary.parquet", index=False)
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("spec")
    p.add_argument("--runs", type=Path, default=Path("runs"))
    p.add_argument("--dst", type=Path, default=None)
    a = p.parse_args()
    df = collect(a.spec, a.runs, a.dst or Path("results") / a.spec)
    by = ["label", *(k for k in grid_keys(a.spec) if k in df)]
    print(df.groupby(by, dropna=False)[["deadline_met", "p99_s", "holders_mean"]].mean().to_string())


if __name__ == "__main__":
    main()
