"""Figure registry (doc 01 §8 item 5, doc 06 §1): figures are registered functions of an experiment's run
directories. ``make figs`` renders every figure whose runs exist to ``figures/<name>.pdf``; the PDF metadata carries a
digest of the runs' result hashes and ``figures/<name>.json`` lists every run with its config, scenario and result
hashes, so a figure names exactly the runs it was drawn from."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure

from experiments.analysis.lib import Run, collect, run_dirs

Draw = Callable[[pd.DataFrame], Figure]


@dataclass(frozen=True)
class FigureSpec:
    name: str
    exp: str
    metrics: tuple[str, ...]
    draw: Draw


FIGURES: dict[str, FigureSpec] = {}


def figure(name: str, exp: str, metrics: tuple[str, ...]) -> Callable[[Draw], Draw]:
    def deco(fn: Draw) -> Draw:
        FIGURES[name] = FigureSpec(name, exp, metrics, fn)
        return fn

    return deco


def provenance(runs: list[Path]) -> list[dict[str, str]]:
    out = []
    for d in runs:
        m = Run(d).manifest
        out.append({k: str(m.get(k, "")) for k in ("config_hash", "scenario_hash", "result_hash", "git_sha")})
        out[-1]["run_dir"] = str(d)
    return out


def render(spec: FigureSpec, root: Path, out_dir: Path) -> Path | None:
    """Draw one figure from its experiment's runs; ``None`` when the experiment has no runs yet."""
    if not (root / spec.exp).exists():
        return None
    runs = run_dirs(spec.exp, root)
    if not runs:
        return None
    df = collect(spec.exp, root, list(spec.metrics))
    fig = spec.draw(df)
    prov = provenance(runs)
    digest = hashlib.sha256("".join(sorted(p["result_hash"] for p in prov)).encode()).hexdigest()[:16]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{spec.name}.pdf"
    meta = {"Title": spec.name, "Subject": spec.exp, "Keywords": f"runs-digest:{digest}", "CreationDate": None}
    fig.savefig(path, metadata=meta, bbox_inches="tight")
    plt.close(fig)
    side = {"figure": spec.name, "experiment": spec.exp, "runs_digest": digest, "runs": prov}
    path.with_suffix(".json").write_text(json.dumps(side, indent=2, sort_keys=True))
    return path


def load_all() -> None:
    """Import the modules whose ``@figure`` decorators register figures."""
    from experiments.figures import p8, p10  # noqa: F401, PLC0415
