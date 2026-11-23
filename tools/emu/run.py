"""Run one V13 emulation scenario on the node (plan V13, handoff Part E), in real time.

    uv run python -m tools.emu.run configs/emu/s1_central.yaml --system voss --rep 1 \\
        --out runs-emu/node02-i7-12700-64g-nvme/

One emulated worker per scenario worker: its own physical core(s), its own cgroup memory limit and its own network
namespace with the scenario worker's access link injected (``tools/emu/isolation.py``). Sandboxes are real Firecracker
microVMs (``tools/emu/vms.py`` over ``tools/calibrate/fc.py``) and every session start performs a real TPM quote
(``tools/emu/tpm.py``). The provider roles and the coordinator run on the cores reserved for them.

The run directory is ``<out>/<system>/rep<i>/``: the simulator's own tables plus ``manifest.json`` (scenario hash, code
commit) and ``emu.json`` (layout, isolation commands, TPM and kernel statistics). ``tools.emu.compare`` reads the
simulator's tables on both sides, so the comparison is like for like.

``--dry-run`` prints the resolved config, the core allocation and the injected links without touching anything.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from voss.core.config import RunConfig
from voss.metrics.manifest import build_manifest
from voss.world.scenario import generate

from tools.emu import preflight as preflight_mod
from tools.emu import scenario as spec_mod
from tools.emu.backend import EmuConfig
from tools.emu.isolation import CGROUP_ROOT, Isolation
from tools.emu.system import EmuSystem
from tools.emu.topology import KINDS, read_topology
from tools.emu.topology import plan as host_plan
from tools.emu.tpm import Quoter
from tools.emu.vms import FnVm

REPO = Path(__file__).resolve().parents[2]


def host_info() -> dict[str, Any]:
    gov = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    lines = Path("/proc/cpuinfo").read_text().splitlines() if Path("/proc/cpuinfo").exists() else []
    cpu = next((ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("model name")), "?")
    return {
        "host": platform.node(),
        "kernel": platform.release(),
        "cpu": cpu,
        "governor": gov.read_text().strip() if gov.exists() else "?",
        "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else [],
        "loadavg_start": os.getloadavg(),
    }


def layout_for(spec: spec_mod.EmuScenario, cfg: RunConfig, scn: Any) -> Any:
    """Cores, memory limits and injected links for the scenario's workers (handoff Part E)."""
    wt = scn.workers
    return host_plan(
        read_topology(),
        spec.emu.workers,
        kind=KINDS[spec.emu.kind],
        cores_per_worker=spec.emu.cores_per_worker,
        mem_mb=spec.emu.mem_mb_per_worker,
        infra_cores=spec.emu.infra_cores,
        last_mile_s=list(wt.last_mile_s),
        up_bps=list(wt.up_bps),
        down_bps=list(wt.down_bps),
    )


def _print_plan(spec: spec_mod.EmuScenario, cfg: RunConfig, layout: Any | None) -> None:
    print(f"scenario={spec.name} system={cfg.label} seed={cfg.seed} workers={cfg.scenario.workers}")
    print(f"horizon_s={cfg.horizon_s:.0f} drain_s={cfg.drain_s:.0f} warmup_s={cfg.scenario.warmup_s:.0f}")
    print(f"calibration={cfg.calibration} config_hash={cfg.config_hash()[:16]}")
    if layout is None:
        print("cores: not planned here (no Linux sysfs CPU tree); run --dry-run on the node to see the allocation")
        return
    print(f"cores: workers {spec.emu.cores_per_worker}x {layout.kind} each, provider roles on {layout.infra_cpus}")
    for row in layout.summary():
        n = row["netem"]
        print(
            f"  worker {row['worker']}: cpus={row['cpus']} mem={row['mem_mb']} MB ns={row['netns']} "
            f"delay={n['delay_ms']:.2f} ms up={n['up_mbps']:.1f} Mbit/s down={n['down_mbps']:.1f} Mbit/s"
        )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tools.emu.run", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("scenario", help="configs/emu/<name>.yaml or a scenario name")
    p.add_argument("--system", required=True, help="a system of the scenario's `systems:` list (voss, fixed_keepalive)")
    p.add_argument("--rep", type=int, required=True, help="repetition 1..len(seeds); its seed comes from the scenario")
    p.add_argument("--out", type=Path, default=None, help="output root, e.g. runs-emu/<host_label>/")
    p.add_argument("--assets", type=Path, default=None, help="dir with firecracker, vmlinux and the guest rootfs")
    p.add_argument("--workdir", type=Path, default=None, help="scratch dir on the SSD under test (snapshots, sockets)")
    p.add_argument("--set", action="append", default=[], help="extra config override, applied last")
    p.add_argument("--no-isolation", action="store_true", help="no netns/tc/cgroup (smoke runs only, not a V13 run)")
    p.add_argument("--no-tpm", action="store_true", help="calibrated quote instead of a real one (not a V13 run)")
    p.add_argument("--dry-run", action="store_true", help="print the resolved config and the host plan, do nothing")
    p.add_argument("--force", action="store_true", help="overwrite an existing run directory")
    p.add_argument("--emit-sim-spec", type=Path, default=None, help="write the matching experiments.runner spec")
    return p


def _info(spec: spec_mod.EmuScenario, a: argparse.Namespace, layout: Any) -> dict[str, Any]:
    """What the run was, before it started: host, scenario, layout and where the isolation lives."""
    info = host_info()
    info |= {"scenario": spec.name, "scenario_file": spec.source, "system": a.system, "rep": a.rep}
    info |= {"layout": layout.summary(), "provider_cpus": list(layout.infra_cpus), "cgroup_root": str(CGROUP_ROOT)}
    return info


def _start(spec: spec_mod.EmuScenario, a: argparse.Namespace, layout: Any, workdir: Path) -> tuple[Any, Any, float]:
    """Create the worker isolation and the TPM quoter; returns ``(isolation, quoter, ak_create_s)``."""
    iso = None
    if not a.no_isolation:
        iso = Isolation(layout)
        iso.pin_infra()
        for s in layout.slots:
            iso.setup(s.index)
    quoter = None if a.no_tpm else Quoter(workdir / "tpm")
    return iso, quoter, (quoter.prepare() if quoter is not None else 0.0)


def _write(cfg: RunConfig, run_dir: Path, system: EmuSystem, info: dict[str, Any], result: Any, t0: float) -> None:
    """Write the simulator's tables, the manifest and ``emu.json`` into ``run_dir``."""
    manifest = build_manifest(cfg, result.scenario_hash, result.recorder.result_hash(), REPO)
    manifest.wall_s = time.time() - t0
    manifest.events = int(result.events_run)
    result.recorder.write(run_dir)
    manifest.write(run_dir / "manifest.json")
    (run_dir / "emu.json").write_text(json.dumps(info, indent=2, default=str))


def _prepare(a: argparse.Namespace, spec: spec_mod.EmuScenario, workdir: Path) -> int | Path:
    """The run directory, or the exit code of refusing to overwrite one; prepares the scratch directory."""
    run_dir = Path(a.out) / spec.run_dir(a.system, a.rep)
    if (run_dir / "manifest.json").exists() and not a.force:
        print(f"{run_dir} already has a manifest; pass --force to overwrite it", file=sys.stderr)
        return 3
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(workdir / "fc", ignore_errors=True)
    return run_dir


def _run(spec: spec_mod.EmuScenario, a: argparse.Namespace, cfg: RunConfig, scn: Any, layout: Any) -> int:
    assets = (a.assets or Path(spec.emu.assets)).expanduser()
    workdir = (a.workdir or Path(spec.emu.workdir)).expanduser()
    problems = preflight_mod.check(
        spec, cfg, isolation=not a.no_isolation, tpm=not a.no_tpm, assets=assets, workdir=workdir
    )
    for pr in problems:
        print(pr.line())
    if any(pr.level == "fail" for pr in problems):
        print("\npreflight failed: fix the lines above, then run again (nothing was started)", file=sys.stderr)
        return 2
    run_dir = _prepare(a, spec, workdir)
    if isinstance(run_dir, int):
        return run_dir
    iso, quoter, ak_s = _start(spec, a, layout, workdir)
    info = _info(spec, a, layout)
    emu = EmuConfig(
        firecracker=str(assets / "firecracker"),
        kernel=str(assets / "vmlinux"),
        rootfs=str(assets / spec.emu.rootfs),
        workdir=workdir,
        isolation=iso,
        tpm=quoter,
    )
    system = EmuSystem(cfg, scn, emu, FnVm)
    t0 = time.time()
    try:
        result = system.run()
        iso_stats = iso.snapshot_stats() if iso is not None else None
    finally:  # never leave a namespace or a pinned process behind, even on a crash
        if iso is not None:
            iso.close()
    k: Any = system.kernel
    info |= {
        "backend": system.backend.stats,
        "kernel_events": k.events_run,
        "kernel_max_lag_s": k.max_lag_s,
        "kernel_mean_lag_s": k.lag_sum_s / max(1, k.events_run),
        "loadavg_end": os.getloadavg(),
        "failed": repr(system.backend.failed),
        "tpm": quoter.stats() if quoter is not None else {"n": 0, "ak_create_s": ak_s},
        "isolation": {"enabled": iso is not None, "stats": iso_stats, "commands": len(iso.log) if iso else 0},
        "scenario_hash": result.scenario_hash,
        "events": result.events_run,
    }
    _write(cfg, run_dir, system, info, result, t0)
    print(f"run_dir={run_dir} scenario={result.scenario_hash} events={result.events_run} lag_max={k.max_lag_s:.3f}s")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    a = parser.parse_args(argv)
    if a.out is None and a.emit_sim_spec is None:
        parser.error("--out is required for a run")
    spec = spec_mod.load(a.scenario)
    if a.emit_sim_spec is not None:
        import yaml  # noqa: PLC0415

        a.emit_sim_spec.parent.mkdir(parents=True, exist_ok=True)
        a.emit_sim_spec.write_text(yaml.safe_dump(spec.sim_spec(), sort_keys=False))
        print(f"wrote {a.emit_sim_spec}")
        return 0
    cfg = spec.run_config(a.system, a.rep, a.set)
    spec.check_workers(cfg)
    try:
        scn = generate(cfg)
    except FileNotFoundError as e:  # a traced input the scenario names is not on the node
        print(f"{e}\nfetch or build the trace release into data/traces (tools/traces, docs/handoff)", file=sys.stderr)
        return 2
    try:
        layout = layout_for(spec, cfg, scn)
    except (RuntimeError, ValueError) as e:  # not Linux, or too few cores: a dry run still shows the config
        if not a.dry_run:
            raise
        print(f"cores: no usable plan here: {e}")
        layout = None
    if a.dry_run:
        _print_plan(spec, cfg, layout)
        return 0
    return _run(spec, a, cfg, scn, layout)


if __name__ == "__main__":
    raise SystemExit(main())
