"""Per-shard result merge (plan V6; experiment.yml publish job)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from experiments.merge_results import merge


def _part(root: Path, name: str, runs: list[str]) -> Path:
    p = root / name
    p.mkdir()
    pd.DataFrame({"run": runs, "deadline_met": [0.9] * len(runs)}).to_parquet(p / "summary.parquet")
    pd.DataFrame({"run": runs, "result_hash": ["h"] * len(runs)}).to_csv(p / "hashes.csv", index=False)
    return p


def test_merge_concatenates_and_sorts(tmp_path: Path) -> None:
    parts = [_part(tmp_path, "0", ["b", "d"]), _part(tmp_path, "1", ["a", "c"])]
    out = tmp_path / "results"
    df = merge(parts, out)
    assert df.run.tolist() == ["a", "b", "c", "d"]
    assert pd.read_csv(out / "hashes.csv").run.tolist() == ["a", "b", "c", "d"]


def test_merge_refuses_a_run_in_two_parts(tmp_path: Path) -> None:
    parts = [_part(tmp_path, "0", ["a"]), _part(tmp_path, "1", ["a"])]
    with pytest.raises(ValueError, match="more than one part"):
        merge(parts, tmp_path / "results")


def test_merge_needs_at_least_one_part(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="no result parts"):
        merge([tmp_path / "empty"], tmp_path / "results")
