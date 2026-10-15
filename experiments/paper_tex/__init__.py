"""Manuscript numbers: every number and table in ``manuscript/`` is generated here from the committed artifacts under
``paper/`` (per-seed CSVs, viability tables, scorecard) and ``configs/calibration/`` (the measured bundle), so the text
cannot drift from the results. ``python -m experiments.paper_tex`` rewrites ``manuscript/generated/``; a test fails when
the committed files are stale. ``expect`` raises when a result no longer supports a sentence of the draft.

Usage: ``python -m experiments.paper_tex [--out manuscript/generated]``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from experiments.paper_tex.core import REPO, Gen, write
from experiments.paper_tex.measured import calibration, calibration_sensitivity, ecs1_sim
from experiments.paper_tex.planning import ablations, adversaries, faults, hedging, planners
from experiments.paper_tex.results import commercial, geo_and_null, pareto_and_rest, scalability, scorecard
from experiments.paper_tex.viab import extras, viability


def build() -> Gen:
    g = Gen()
    for step in (
        calibration,
        ecs1_sim,
        viability,
        planners,
        ablations,
        faults,
        adversaries,
        hedging,
        pareto_and_rest,
        geo_and_null,
        commercial,
        scalability,
        calibration_sensitivity,
        extras,
        scorecard,
    ):
        step(g)
    return g


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=REPO / "manuscript" / "generated")
    a = p.parse_args(argv)
    g = build()
    write(a.out, g)
    print(f"{len(g.macros)} macros, {len(g.files)} tables -> {a.out}")


if __name__ == "__main__":
    main()
