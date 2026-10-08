"""Command-line entrypoints: ``voss run`` and ``voss repro`` (doc 01 §8)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from voss.core.config import RunConfig, load_config
from voss.metrics.manifest import Manifest, build_manifest
from voss.runtime.system import run_system
from voss.world.scenario import generate, store

REPO = Path(__file__).resolve().parent.parent


def cmd_run(cfg: RunConfig, out: Path | None) -> Manifest:
    """Run one config, write its logs and manifest under ``runs/<config_hash>`` (or ``out``)."""
    result = run_system(cfg)
    manifest = build_manifest(cfg, result.scenario_hash, result.recorder.result_hash(), REPO)
    run_dir = out or Path(cfg.out_dir) / cfg.config_hash()[:16]
    result.recorder.write(run_dir)
    manifest.write(run_dir / "manifest.json")
    print(f"run_dir={run_dir} events={result.events_run} result_hash={manifest.result_hash}")
    return manifest


def cmd_repro(path: Path) -> bool:
    """Re-run a manifest's resolved config and compare result hashes."""
    old = Manifest.read(path)
    cfg = RunConfig.model_validate(old.config)
    result = run_system(cfg)
    new_hash = result.recorder.result_hash()
    ok = new_hash == old.result_hash and result.scenario_hash == old.scenario_hash
    print(f"expected={old.result_hash} got={new_hash} {'OK' if ok else 'MISMATCH'}")
    return ok


def cmd_gen_scenario(cfg: RunConfig) -> str:
    """Generate the scenario for ``cfg`` and store it under ``<out_dir>/scenarios/<hash>``."""
    scn = generate(cfg)
    path = store(scn, Path(cfg.out_dir) / "scenarios")
    print(
        f"scenario={scn.hash} path={path} workers={len(scn.workers)} "
        f"sessions={len(scn.sessions.sessions)} arrivals={len(scn.arrivals)}"
    )
    return scn.hash


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="voss")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a config")
    r.add_argument("config")
    r.add_argument("--set", action="append", default=[], help="override key.path=value")
    r.add_argument("--out", type=Path, default=None)
    g = sub.add_parser("gen-scenario", help="generate, hash and store a scenario")
    g.add_argument("config")
    g.add_argument("--set", action="append", default=[], help="override key.path=value")
    rp = sub.add_parser("repro", help="re-run a manifest and assert its result hash")
    rp.add_argument("manifest", type=Path)
    a = p.parse_args(argv)
    if a.cmd == "run":
        cmd_run(load_config(a.config, a.set), a.out)
        return 0
    if a.cmd == "gen-scenario":
        cmd_gen_scenario(load_config(a.config, a.set))
        return 0
    return 0 if cmd_repro(a.manifest) else 1


if __name__ == "__main__":
    sys.exit(main())
