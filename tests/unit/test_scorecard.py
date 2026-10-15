"""Scorecard verdict rules (doc 06 §6) and Pareto utilities (E23), on synthetic frames with known answers."""

from __future__ import annotations

import numpy as np
import pandas as pd
from experiments.analysis import pareto, scorecard
from experiments.analysis.scorecard import Comparison


def _df(base: float, test: float, n: int = 10, cell: str = "a") -> pd.DataFrame:
    rows = []
    for seed in range(n):
        wiggle = 0.01 * (seed - n / 2)
        rows += [
            {"label": "base", "seed": seed, "cell": cell, "m": base + wiggle},
            {"label": "test", "seed": seed, "cell": cell, "m": test + wiggle},
        ]
    return pd.DataFrame(rows)


def _verdict(df: pd.DataFrame, kind: str, margin: float = 0.05) -> str:
    t = Comparison("Hx", "claim", "Exx", "base", "test", "m", kind, margin=margin)
    return str(scorecard.evaluate(df, t)["verdict"])


def test_lower_and_higher_rules() -> None:
    assert _verdict(_df(1.0, 0.8), "lower") == "supported"
    assert _verdict(_df(1.0, 0.98), "lower") == "weak"  # significant but below the 5% margin
    assert _verdict(_df(1.0, 1.0), "lower") == "inconclusive"
    assert _verdict(_df(1.0, 1.2), "lower") == "refuted"
    assert _verdict(_df(1.0, 1.2), "higher") == "supported"


def test_equivalence_rule() -> None:
    assert _verdict(_df(1.0, 1.01), "equivalent", 0.1) == "supported"
    assert _verdict(_df(1.0, 1.5), "equivalent", 0.1) == "refuted"


def test_where_filters_select_one_cell_and_missing_data_is_reported() -> None:
    df = pd.concat([_df(1.0, 0.5, cell="a"), _df(1.0, 2.0, cell="b")])
    t = Comparison("Hx", "c", "Exx", "base", "test", "m", "lower", where={"cell": "==a"})
    assert scorecard.evaluate(df, t)["verdict"] == "supported"
    t_b = Comparison("Hx", "c", "Exx", "base", "test", "m", "lower", where={"cell": "==b"})
    assert scorecard.evaluate(df, t_b)["verdict"] == "refuted"
    assert scorecard.evaluate(pd.DataFrame(columns=["label"]), t)["verdict"] == "no data"


def test_negative_results_lists_only_unsupported_rows() -> None:
    sc = pd.DataFrame(
        [
            {"id": "H1", "claim": "a", "exp": "E", "cmp": "x vs y", "metric": "m", "verdict": "supported",
             "delta": -1.0, "lo": -1.5, "hi": -0.5, "base": 2.0, "n": 10},
            {"id": "H2", "claim": "b", "exp": "E", "cmp": "x vs y", "metric": "m", "verdict": "refuted",
             "delta": 1.0, "lo": 0.5, "hi": 1.5, "base": 2.0, "n": 10},
        ]
    )  # fmt: skip
    out = scorecard.negative_results(sc)
    assert "H2" in out and "H1" not in out


def test_pareto_front_and_knee() -> None:
    pts = np.array([[1.0, 10.0], [1.2, 5.0], [1.3, 4.5], [2.0, 4.0], [1.5, 9.0]])
    mask = pareto.front_mask(pts)
    assert mask.tolist() == [True, True, True, True, False]
    front = pts[mask]
    assert tuple(front[pareto.knee(front)]) == (1.2, 5.0)  # the elbow of the L-shaped front


def test_pareto_analyse_flags_knee_on_the_two_dimensional_front() -> None:
    rows = [
        {"f": 0.0, "w": 1.0, "p99_sync": 1.0, "exposure": 10.0, "success": 0.99, "n": 10},
        {"f": 0.1, "w": 1.0, "p99_sync": 1.2, "exposure": 5.0, "success": 0.995, "n": 10},
        {"f": 0.2, "w": 1.0, "p99_sync": 2.0, "exposure": 4.0, "success": 0.999, "n": 10},
    ]
    res = pareto.analyse(pd.DataFrame(rows).assign(fail=lambda d: 1 - d.success))
    assert res.front2.all() and res.knee.sum() == 1 and res[res.knee].iloc[0].f == 0.1
