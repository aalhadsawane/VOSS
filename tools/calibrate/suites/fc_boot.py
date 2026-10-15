"""Firecracker cold boot (doc 10 §3 ``fc_boot``): process spawn → API ready, and ``InstanceStart`` → the guest's
first userspace line (``VOSS_MARK init`` from ``/voss-init``), by VM memory, rootfs tier and page-cache state.
Feeds the L1 → L3 start-up rungs.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from tools.calibrate.common import SuiteSkipped, drop_caches, is_root
from tools.calibrate.fc import FcAssets, FcVm, boot_args
from tools.calibrate.suites import Ctx, Suite

MEM_MB = (128, 256, 512, 1024, 2048)


def assets(ctx: Ctx, rootfs_key: str = "rootfs") -> FcAssets:
    need = {
        "firecracker": ctx.opt("firecracker", "firecracker"),
        "kernel": ctx.opt("kernel"),
        "rootfs": ctx.opt(rootfs_key),
    }
    if not need["kernel"] or not need["rootfs"]:
        raise SuiteSkipped(
            f"pass --set kernel=<vmlinux> --set {rootfs_key}=<ext4 image> (see tools/calibrate/README.md)"
        )
    ctx.sh.need(need["firecracker"])
    if not ctx.sh.dry_run and not Path("/dev/kvm").exists():
        raise SuiteSkipped("/dev/kvm missing")
    return FcAssets(need["firecracker"], need["kernel"], need["rootfs"], ctx.opt("jailer") or None)


def rootfs_on(ctx: Ctx, a: FcAssets, tier: str, d: Path) -> str:
    """A copy of the rootfs on the tier under test (boot reads it from there)."""
    dst = d / f"voss-rootfs-{Path(a.rootfs).name}"
    if not ctx.sh.dry_run and not dst.exists():
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(a.rootfs, dst)
    return str(dst)


def boot_once(ctx: Ctx, a: FcAssets, rootfs: str, mem: int, rep: int) -> tuple[float, float]:
    """(spawn → API socket seconds, InstanceStart → ``VOSS_MARK init`` seconds)."""
    vm = FcVm(a, ctx.out / "fc", f"boot-{mem}-{rep}")
    t0 = time.monotonic()
    try:
        vm.spawn()
        spawn_s = time.monotonic() - t0
        vm.configure(mem, 1, boot_args("boot"), rootfs)
        t_start = vm.start()
        t_init = vm.wait("MARK", "init", timeout=30.0)
        vm.wait("MARK", "done", timeout=30.0)
        return spawn_s, t_init - t_start
    finally:
        vm.kill()


def run(ctx: Ctx) -> None:
    a = assets(ctx)
    tiers = ctx.dirs() or {"default": Path(a.rootfs).parent}
    caches = ("warm", "cold") if is_root() or ctx.sh.dry_run else ("warm",)
    for tier, d in sorted(tiers.items()):
        size_mb = Path(a.rootfs).stat().st_size / 2**20 if Path(a.rootfs).exists() else 0.0
        if not ctx.has_room(d, size_mb):
            ctx.skip(f"fc_boot tier={tier}", size_mb, "not enough free disk for a rootfs copy")
            continue
        rootfs = rootfs_on(ctx, a, tier, d)
        for mem in MEM_MB:
            if mem > ctx.mem_budget_mb():
                ctx.skip(f"fc_boot mem={mem}", mem, "guest memory over the RAM budget")
                continue
            for cache in caches:
                for rep in range(ctx.reps(100)):
                    if cache == "cold":
                        drop_caches(ctx.sh)
                    if ctx.sh.dry_run:
                        print(f"DRY firecracker boot mem={mem} tier={tier} cache={cache}")
                        break
                    spawn_s, boot_s = boot_once(ctx, a, rootfs, mem, rep)
                    cfg: dict[str, Any] = {"mem_mb": mem, "tier": tier, "cache": cache, "jailer": bool(a.jailer)}
                    ctx.rec.add("fc_spawn", spawn_s, rep=rep, **cfg)
                    ctx.rec.add("fc_boot", boot_s, rep=rep, **cfg)


SUITE = Suite("fc_boot", run, "Firecracker cold boot to init by memory, rootfs tier, page cache")
