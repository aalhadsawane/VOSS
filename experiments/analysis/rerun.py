"""Per-run tables of the corrected-placement reruns E10b, E17b, E20ab, E24b (doc 06 §5, §8; D-77).

Same per-run function as the round-4 analysis (``experiments.analysis.round4.per_run``) with the 60 s warm-up of the
original pilot specs, extended with the grid keys of each spec and, for E17b, USD per million invocations exactly as
E17 computes it (``experiments.analysis.lib`` metric ``cost_per_m``). Usage:
``python -m experiments.analysis.rerun E10b|E17b|E20ab|E24b <runs root> [out.csv]``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

from experiments.analysis.lib import METRICS, Run, key_value
from experiments.analysis.round4 import per_run

WARMUP_S = 60.0  # the E10/E17/E20a/E24 pilot specs (latency_metrics default; horizon 900 s, 600 s for E20)
AMORT = ("sync_served", "key_releases", "sync_per_release", "sync_per_release_all")  # need events.parquet: not read


def keys_e10(run: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    """hw_mix as the E10 table names it: ``homogeneous`` (one class) or ``mixed``."""
    return {"hw_mix": "homogeneous" if len(cfg["scenario"]["hw_mix"]) == 1 else "mixed"}


def keys_e17(run: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    """Load rate and USD per million invocations (E17's ``cost_per_m``)."""
    return {"rate": int(cfg["scenario"]["load"]["rate"]), "cost_per_m": METRICS["cost_per_m"](Run(run))}


def keys_e20(run: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    """Cell key of the viability map: adversary as the E20a table writes it, plus its fraction."""
    adv = cfg["scenario"]["adversary"]
    return {"adversary": key_value(cfg, "scenario.adversary"), "alpha": float(adv.get("alpha", 0.0))}


def keys_e24(run: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    return {"calibration": cfg["calibration"]}


KEYS = {"E10b": keys_e10, "E17b": keys_e17, "E20ab": keys_e20, "E24b": keys_e24}


def runs_table(exp: str, root: Path) -> pd.DataFrame:
    """One row per run of ``exp`` under ``root`` (60 s warm-up, grid keys of the spec)."""
    df = per_run(exp, WARMUP_S, root, KEYS[exp])
    return df.drop(columns=[*AMORT, "churn", "trust_cold"]).sort_values(["label", "seed"], kind="stable")


def main(argv: list[str]) -> int:
    df = runs_table(argv[0], Path(argv[1]))
    out = Path(argv[2]) if len(argv) > 2 else Path("paper/tables") / f"{argv[0]}_runs.csv"
    df.to_csv(out, index=False)
    print(f"{out}: {len(df)} runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
