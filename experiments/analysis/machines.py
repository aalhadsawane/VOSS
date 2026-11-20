"""Two measurements of the calibration data that motivate the run-time model (design.tex, "Machines differ per
function, and history predicts"; docs/REVISION_PLAN.md V9.4):

(i) how repeatable a function's execution time is on one machine: the coefficient of variation of the handler times of
    each (function, input size) at concurrency 1, from the raw records of the reference machine;
(ii) how much the speed ratio between two machine classes depends on the function: for each function, the geometric
    mean over its input sizes of the ratio of median handler times between a second calibrated machine and the
    reference machine.

Both are read from merged bundles and their raw records only (analysis reads logs only, AGENTS.md rule 10).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from voss.core.paths import REPO_ROOT

MEASURED = REPO_ROOT / "configs" / "calibration" / "measured"
RAW = REPO_ROOT / "calibration" / "raw"
REFERENCE = "node02-i7-12700-64g-nvme_nvme"  # calibration/REFERENCE (node02), its main tier
OTHER = "node04-i7-4790s-8g-hdd_hdd"  # the calibrated machine of another processor generation


def _yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    return data


def repeat_cov(bundle: str) -> np.ndarray:
    """Coefficient of variation of the concurrency-1 handler times per (function, size) in the bundle's raw host."""
    host = _yaml(MEASURED / bundle / "meta.yaml")["raw_host"]
    runs: dict[tuple[str, int], list[float]] = defaultdict(list)
    for path in sorted((RAW / host / "sebs").glob("*/records.jsonl")):
        for line in path.read_text().splitlines():
            r = json.loads(line)
            c = r.get("config", {})
            if r.get("probe") == "sebs_exec" and c.get("concurrency") == 1:
                runs[(str(c["fn"]), int(c["size_kb"]))].append(float(r["value"]))
    return np.array([np.std(v, ddof=1) / np.mean(v) for _, v in sorted(runs.items()) if len(v) >= 5])


def class_ratios(other: str, ref: str) -> dict[str, list[float]]:
    """Ratio of median handler times other / reference per function, over the input sizes both measured."""
    a = _yaml(MEASURED / ref / "functions.yaml")["functions"]
    b = _yaml(MEASURED / other / "functions.yaml")["functions"]
    out = {}
    for fn in sorted(set(a) & set(b)):
        ea, eb = a[fn]["exec_by_size"], b[fn]["exec_by_size"]
        out[fn] = [float(eb[s]["median_s"]) / float(ea[s]["median_s"]) for s in sorted(set(ea) & set(eb))]
    return out


def machines(values: dict[str, float | int | str]) -> None:
    """Macros ``Mach*`` for design.tex (T11)."""
    cov = repeat_cov(REFERENCE)
    values["MachCovPairs"] = len(cov)
    values["MachCovMedianPct"] = float(np.median(cov) * 100)
    values["MachCovUnderTenPct"] = round(float(np.mean(cov < 0.1) * 100))
    values["MachCovMaxPct"] = round(float(cov.max() * 100))
    ratios = class_ratios(OTHER, REFERENCE)
    gm = {fn: float(np.exp(np.mean(np.log(r)))) for fn, r in ratios.items()}
    lo, hi = min(gm, key=gm.__getitem__), max(gm, key=gm.__getitem__)
    every = [x for r in ratios.values() for x in r]
    values["MachRatioFns"] = len(gm)
    values["MachRatioLo"], values["MachRatioLoFn"] = gm[lo], lo
    values["MachRatioHi"], values["MachRatioHiFn"] = gm[hi], hi
    values["MachRatioSpread"] = gm[hi] / gm[lo]
    values["MachRatioPairLo"], values["MachRatioPairHi"] = min(every), max(every)
