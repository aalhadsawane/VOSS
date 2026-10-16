"""``paper/run-hashes.csv`` is well-formed; the verifier flags a bad hash and table differences (D-67)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from experiments import paper_verify

REPO = Path(__file__).resolve().parents[2]


def test_hashes_cover_manifest_runs() -> None:
    """Every run behind the tables has a recorded hash, except the one E06 run redone after D-64 (hash unrecorded)."""
    ref = pd.read_csv(paper_verify.HASHES, dtype=str)
    manifest = json.loads((REPO / "paper" / "manifest.json").read_text())["runs"]
    counts = ref.groupby("experiment").size().to_dict()
    expected = {e: v["runs"] - (1 if e == "E06" and "E06" not in counts else 0) for e, v in manifest.items()}
    assert set(counts) == set(expected)
    assert all(abs(counts[e] - expected[e]) <= 1 for e in counts)
    assert ref.result_hash.str.fullmatch(r"[0-9a-f]{64}").all()
    assert not ref.duplicated(["experiment", "run_dir"]).any()


def test_verifier_reports_status(tmp_path: Path) -> None:
    ref = pd.read_csv(paper_verify.HASHES, dtype=str)
    exp = ref.experiment.iloc[0]
    rows = ref[ref.experiment == exp].head(3)
    (tmp_path / exp).mkdir()
    pd.DataFrame(
        {
            "run_dir": [f"runs/{exp}/{d}" for d in rows.run_dir],
            "result_hash": [rows.result_hash.iloc[0], "0" * 64, rows.result_hash.iloc[2]],
            "status": ["ok", "ok", "cached"],
        }
    ).to_csv(tmp_path / exp / "index.csv", index=False)
    out = paper_verify.compare(tmp_path, {exp}).head(3)
    assert list(out.status) == ["ok", "mismatch", "ok"]


def test_table_diff_flags_changes_and_ignores_wall_clock() -> None:
    a = pd.DataFrame({"label": ["x", "y"], "seed": [1, 2], "p99": [1.0, 2.0], "solve_s": [0.1, 0.2]})
    same = paper_verify.diff_frames("E", a, a.copy())
    assert same[0].endswith("identical to the committed one (2 rows)")
    b = a.assign(p99=[1.0, 2.5], solve_s=[0.3, 0.4])
    msgs = paper_verify.diff_frames("E", a, b)
    assert any("E.p99" in m and "DIFFERS" in m for m in msgs)
    assert any("E.solve_s" in m and "informational" in m for m in msgs)
    assert "shape differs" in paper_verify.diff_frames("E", a, a.head(1))[0]
