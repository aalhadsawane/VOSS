"""E20 viability verdicts (doc 06 §5): synthetic frames with known answers."""

from __future__ import annotations

import pandas as pd
from experiments.analysis import viability


def _frame(spec: dict[tuple[str, str], tuple[float, float, float]], n: int = 10) -> pd.DataFrame:
    """spec: (cell, label) -> (success, met, p99); small seed-to-seed noise, paired across systems."""
    rows = []
    for (cell, label), (s, m, p) in spec.items():
        for seed in range(n):
            noise = 0.001 * (seed - n / 2)
            rows.append(
                {"cell": cell, "label": label, "seed": seed, "success": s + noise / 10, "met": m + noise / 10,
                 "p50_sync": p / 2, "p99_sync": p + noise, "exposure": 1.0, "waste": 0.0}
            )  # fmt: skip
    return pd.DataFrame(rows)


def test_verdicts_cover_every_case() -> None:
    df = _frame(
        {
            ("a", "voss"): (1.0, 0.99, 1.0), ("a", "simple"): (1.0, 0.99, 2.0),  # voss better
            ("b", "voss"): (1.0, 0.99, 1.0), ("b", "simple"): (1.0, 0.99, 1.0),  # tie
            ("c", "voss"): (1.0, 0.99, 3.0), ("c", "simple"): (1.0, 0.99, 1.0),  # baseline better
            ("d", "voss"): (1.0, 0.99, 1.0), ("d", "simple"): (0.5, 0.5, 1.0),  # voss only
            ("e", "voss"): (0.5, 0.5, 1.0), ("e", "simple"): (1.0, 0.99, 1.0),  # only the baseline is viable
            ("f", "voss"): (0.5, 0.5, 1.0), ("f", "simple"): (0.5, 0.5, 1.0),  # none
        }
    )  # fmt: skip
    t = viability.cells(df, ["cell"]).set_index("cell")
    assert t.verdict.to_dict() == {
        "a": "voss_better", "b": "tie", "c": "baseline_better", "d": "voss_only", "e": "baseline_better", "f": "none",
    }  # fmt: skip
    assert t.loc["a", "best_baseline"] == "simple" and t.loc["a", "d_p99"] < 0


def test_best_baseline_is_the_viable_one_with_the_lowest_p99() -> None:
    df = _frame(
        {
            ("x", "voss"): (1.0, 0.99, 2.0), ("x", "simple"): (1.0, 0.99, 1.5),
            ("x", "noattest"): (1.0, 0.99, 1.0), ("y", "voss"): (1.0, 0.99, 2.0),
            ("y", "simple"): (1.0, 0.99, 1.5), ("y", "noattest"): (0.5, 0.5, 0.1),
        }
    )  # fmt: skip
    t = viability.cells(df, ["cell"]).set_index("cell")
    assert t.loc["x", "best_baseline"] == "noattest" and t.loc["y", "best_baseline"] == "simple"
    assert t.loc["x", "verdict"] == "baseline_better"


def test_markdown_lists_every_cell_and_counts_verdicts() -> None:
    df = _frame({("a", "voss"): (1.0, 0.99, 1.0), ("a", "simple"): (1.0, 0.99, 2.0)})
    out = viability.markdown("E20x", ["cell"], viability.cells(df, ["cell"]), viability.system_stats(df, ["cell"]), df)
    assert "voss_better 1" in out and "| a | voss_better | simple |" in out
    assert "Sensitivity to the deadline-met target" in out and "| 0.98 |" in out
