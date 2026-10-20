"""Run one E01 scenario on the emulation testbed (doc 10 §4, P9b), in real time.

``python -m tools.emu.run configs/e01/s1_stable.yaml --out runs-e01/s1_stable-emu-1 --seed 1 \\
    --assets ~/voss-e01/assets --workdir ~/voss-e01/work``

The run directory has the simulator's tables (so the same analysis reads both) plus ``emu.json``: backend counters,
kernel lag, host description and the CPU affinity the run used. Run it pinned to P-cores (``taskset``) on an idle node.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import time
from pathlib import Path
from typing import Any

from voss.core.config import load_config
from voss.metrics.manifest import build_manifest
from voss.world.scenario import generate

from tools.emu.backend import EmuConfig
from tools.emu.system import EmuSystem
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.emu.run", description=__doc__)
    p.add_argument("config")
    p.add_argument("--set", action="append", default=[])
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--assets", type=Path, required=True, help="dir with firecracker, vmlinux, voss-guest-e01.ext4")
    p.add_argument("--workdir", type=Path, required=True, help="scratch dir on the SSD under test (snapshots, sockets)")
    p.add_argument("--rootfs", default="voss-guest-e01.ext4")
    a = p.parse_args(argv)
    sets = [*a.set, f"seed={a.seed}", "decision_clock.mode=measured", "decision_clock.cpu_scale=0.0"]
    cfg = load_config(REPO / a.config if not Path(a.config).is_absolute() else a.config, sets)
    emu = EmuConfig(
        firecracker=str(a.assets / "firecracker"),
        kernel=str(a.assets / "vmlinux"),
        rootfs=str(a.assets / a.rootfs),
        workdir=a.workdir,
    )
    info = host_info()
    scn = generate(cfg)
    system = EmuSystem(cfg, scn, emu, FnVm)
    t0 = time.time()
    result = system.run()
    manifest = build_manifest(cfg, result.scenario_hash, result.recorder.result_hash(), REPO)
    manifest.wall_s = time.time() - t0
    a.out.mkdir(parents=True, exist_ok=True)
    result.recorder.write(a.out)
    manifest.write(a.out / "manifest.json")
    k: Any = system.kernel
    info |= {
        "backend": system.backend.stats,
        "kernel_events": k.events_run,
        "kernel_max_lag_s": k.max_lag_s,
        "kernel_mean_lag_s": k.lag_sum_s / max(1, k.events_run),
        "loadavg_end": os.getloadavg(),
        "failed": repr(system.backend.failed),
    }
    (a.out / "emu.json").write_text(json.dumps(info, indent=2, default=str))
    print(f"run_dir={a.out} scenario={result.scenario_hash} events={result.events_run} lag_max={k.max_lag_s:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
