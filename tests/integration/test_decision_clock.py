"""Decision clock modes (doc 01 §7, D-21): ``replay`` reproduces a ``measured`` run bit for bit."""

from __future__ import annotations

import json
from pathlib import Path

from voss.cli import main

REPO = Path(__file__).resolve().parents[2]
SMALL = ["horizon_s=90", "drain_s=5", "scenario.workers=60", "scenario.load.rate=4"]


def _sets(extra: list[str]) -> list[str]:
    out: list[str] = []
    for s in [*SMALL, *extra]:
        out += ["--set", s]
    return out


def test_replay_reproduces_measured(tmp_path: Path) -> None:
    measured = tmp_path / "measured"
    main(["run", str(REPO / "configs/smoke.yaml"), "--out", str(measured), *_sets(["decision_clock.mode=measured"])])
    replay = tmp_path / "replay"
    sets = _sets(["decision_clock.mode=replay", f"decision_clock.replay_log={measured}"])
    main(["run", str(REPO / "configs/smoke.yaml"), "--out", str(replay), *sets])
    a = json.loads((measured / "manifest.json").read_text())["result_hash"]
    b = json.loads((replay / "manifest.json").read_text())["result_hash"]
    assert a == b
