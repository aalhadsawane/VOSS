"""Emulation CLI (plan V13): argument parsing and the dry run, which works anywhere.

The real run needs Linux, root, /dev/kvm and a TPM; ``--dry-run`` resolves the scenario, generates it and prints the
plan without creating anything, so the builder can check a scenario before the node visit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.emu.run import main


def test_the_run_cli_needs_a_system_and_a_repetition(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["configs/emu/s1_central.yaml", "--rep", "1", "--out", str(tmp_path)])
    with pytest.raises(SystemExit):
        main(["configs/emu/s1_central.yaml", "--system", "voss", "--out", str(tmp_path)])


def test_an_unknown_system_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="not in s1_central"):
        main(["configs/emu/s1_central.yaml", "--system", "kpa", "--rep", "1", "--out", str(tmp_path), "--dry-run"])


def test_dry_run_prints_the_plan_without_touching_anything(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "runs-emu"
    assert (
        main(
            ["configs/emu/s1_central.yaml", "--system", "fixed_keepalive", "--rep", "2", "--out", str(out), "--dry-run"]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "system=fixed_keepalive seed=2 workers=6" in text
    assert "horizon_s=7200" in text
    assert not out.exists()  # nothing was created


def test_emit_sim_spec_writes_the_matching_runner_spec(tmp_path: Path) -> None:
    import yaml

    path = tmp_path / "spec.yaml"
    assert (
        main(
            [
                "configs/emu/s1_central.yaml",
                "--system",
                "voss",
                "--rep",
                "1",
                "--out",
                str(tmp_path),
                "--emit-sim-spec",
                str(path),
            ]
        )
        == 0
    )
    spec = yaml.safe_load(path.read_text())
    assert spec["experiment"] == "emu-s1_central"
    assert spec["seeds"] == [1, 2, 3]
    assert "decision_clock.mode=modeled" in spec["overrides"]
