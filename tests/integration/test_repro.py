"""`voss run` writes a manifest and `voss repro` reproduces its result hash (doc 01 §8)."""

from __future__ import annotations

import json
from pathlib import Path

from voss.cli import main

REPO = Path(__file__).resolve().parents[2]


def test_run_then_repro(tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert main(["run", str(REPO / "configs/toy.yaml"), "--out", str(out), "--set", "horizon_s=50"]) == 0
    manifest = out / "manifest.json"
    data = json.loads(manifest.read_text())
    assert data["result_hash"] and data["config"]["horizon_s"] == 50
    assert (out / "events.parquet").exists()
    assert main(["repro", str(manifest)]) == 0


def test_repro_detects_mismatch(tmp_path: Path) -> None:
    out = tmp_path / "run"
    main(["run", str(REPO / "configs/toy.yaml"), "--out", str(out), "--set", "horizon_s=20"])
    manifest = out / "manifest.json"
    data = json.loads(manifest.read_text())
    data["result_hash"] = "0" * 64
    manifest.write_text(json.dumps(data))
    assert main(["repro", str(manifest)]) == 1


def test_seed_changes_hash(tmp_path: Path) -> None:
    hashes = set()
    for seed in (1, 2):
        out = tmp_path / f"s{seed}"
        main(["run", str(REPO / "configs/toy.yaml"), "--out", str(out), "--set", f"seed={seed}"])
        hashes.add(json.loads((out / "manifest.json").read_text())["result_hash"])
    assert len(hashes) == 2
