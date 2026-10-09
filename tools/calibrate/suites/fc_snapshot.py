"""Firecracker snapshots (doc 10 §3 ``fc_snapshot``): create (pause + full snapshot write) and restore by memory
size, snapshot tier and page-cache state. Restore is measured to the guest's echo of a console probe, so it includes
the page faults of the first request. Feeds the L2 → L3 rung and snapshot sizes. Runs without the jailer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.calibrate.common import drop_caches, is_root
from tools.calibrate.fc import FcAssets, FcVm, boot_args
from tools.calibrate.suites import Ctx, Suite
from tools.calibrate.suites.fc_boot import assets

MEM_MB = (128, 512, 2048)


def create(ctx: Ctx, a: FcAssets, d: Path, mem: int) -> tuple[Path, Path, float]:
    """Boot a guest that echoes its console, pause it and write a full snapshot to ``d``."""
    vm = FcVm(a, ctx.out / "fc", f"snapc-{mem}")
    state, memf = d / f"voss-snap-{mem}.state", d / f"voss-snap-{mem}.mem"
    try:
        vm.spawn()
        vm.configure(mem, 1, boot_args("serve"))
        vm.start()
        vm.wait("MARK", "ready", timeout=30.0)
        vm.pause()
        secs = vm.snapshot(state, memf)
    finally:
        vm.kill()
    return state, memf, secs


def restore(ctx: Ctx, a: FcAssets, state: Path, memf: Path, tag: str) -> tuple[float, float]:
    """(``/snapshot/load`` API seconds, load start → echo of a console probe)."""
    vm = FcVm(a, ctx.out / "fc", f"snapr-{tag}")
    try:
        vm.spawn()
        t0, api_s = vm.load(state, memf)
        vm.send("ping")
        t_ack = vm.wait("ACK", "ping", timeout=30.0)
        return api_s, t_ack - t0
    finally:
        vm.kill()


def run(ctx: Ctx) -> None:
    base = assets(ctx)
    a = FcAssets(base.firecracker, base.kernel, base.rootfs)  # snapshots use paths outside a jail
    tiers = ctx.dirs() or {"default": ctx.out}
    caches = ("warm", "cold") if is_root() or ctx.sh.dry_run else ("warm",)
    for tier, d in sorted(tiers.items()):
        d.mkdir(parents=True, exist_ok=True)
        for mem in MEM_MB:
            if ctx.sh.dry_run:
                print(f"DRY firecracker snapshot create/restore mem={mem} tier={tier} caches={caches}")
                continue
            state, memf, secs = create(ctx, a, d, mem)
            size_mb = memf.stat().st_size / 2**20
            ctx.rec.add("fc_snapshot_create", secs, mem_mb=mem, tier=tier, size_mb=size_mb)
            ctx.rec.add("fc_snapshot_mb", size_mb, unit="MB", mem_mb=mem, tier=tier)
            for cache in caches:
                for rep in range(ctx.reps(50)):
                    if cache == "cold":
                        drop_caches(ctx.sh)
                    api_s, ack_s = restore(ctx, a, state, memf, f"{mem}-{tier}-{cache}-{rep}")
                    cfg: dict[str, Any] = {"mem_mb": mem, "tier": tier, "cache": cache}
                    ctx.rec.add("fc_restore_api", api_s, rep=rep, **cfg)
                    ctx.rec.add("fc_restore", ack_s, rep=rep, **cfg)
            state.unlink(missing_ok=True)
            memf.unlink(missing_ok=True)


SUITE = Suite("fc_snapshot", run, "Firecracker snapshot create/restore by memory, tier, page cache")
