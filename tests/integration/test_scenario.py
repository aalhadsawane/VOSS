"""`voss gen-scenario` produces a hashed, stored, reproducible scenario (roadmap P1 exit)."""

from __future__ import annotations

from pathlib import Path

from voss.cli import main
from voss.core.config import load_config
from voss.world.scenario import generate, store

REPO = Path(__file__).resolve().parents[2]
SMALL = ["scenario.workers=100", "horizon_s=600", "scenario.load.rate=20"]


def test_scenario_hash_is_deterministic(tmp_path: Path) -> None:
    cfg = load_config(REPO / "configs/base.yaml", SMALL)
    a, b = generate(cfg), generate(cfg)
    assert a.hash == b.hash and len(a.hash) == 64
    other = generate(load_config(REPO / "configs/base.yaml", [*SMALL, "seed=2"]))
    assert other.hash != a.hash
    out = store(a, tmp_path)
    assert {p.name for p in out.iterdir()} >= {"meta.json", "workers.parquet", "sessions.parquet", "arrivals.parquet"}


def test_gen_scenario_cli(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["gen-scenario", str(REPO / "configs/base.yaml"), "--set", f"out_dir={tmp_path}", *_sets()]) == 0
    line = capsys.readouterr().out
    h = line.split("scenario=")[1].split()[0]
    assert (tmp_path / "scenarios" / h / "meta.json").exists()


def _sets() -> list[str]:
    out = []
    for s in SMALL:
        out += ["--set", s]
    return out
