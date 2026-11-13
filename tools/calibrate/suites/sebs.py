"""SeBS-style functions inside Firecracker (doc 10 §3 ``sebs``; docs/handoff/CALIBRATION_DATA_CONTRACT.md §5).

Per function: initialisation (cold import), handler time at every input size of ``SIZES`` (SeBS's test, small and
large input classes where the guest's size parameter can express them, and larger sizes so that handler times span
under 1 ms to over 10 s, plan V1 step 1), co-run slowdown with 1..physical cores and the thread count of guests
running together (``sebs_exec`` with ``concurrency``), resident memory of the Firecracker process (``fn_rss``) and the
snapshot size of a started sandbox (``snap_size``). The guest image (``guest/build_rootfs.sh``) contains
``/voss/fnrunner.py``; the kernel command line selects the function, input sizes and repetitions, and the guest prints
``VOSS_INIT`` / ``VOSS_EXEC`` lines.
"""

from __future__ import annotations

import concurrent.futures as cf
import os
from pathlib import Path

from tools.calibrate.common import _cores
from tools.calibrate.fc import FcAssets, FcVm, boot_args
from tools.calibrate.suites import Ctx, Suite
from tools.calibrate.suites.fc_boot import assets

# function → ((size, SeBS class or "-"), ...). ``size`` is the guest function's ``make_input`` argument; each guest
# module's docstring says what it means for that function. SeBS classes from spcl/serverless-benchmarks
# ``benchmarks/*/input.py`` (dynamic-html: 10/1,000/100,000 random numbers; graph-*: 10/10,000/100,000 nodes).
SIZES: dict[str, tuple[tuple[int, str], ...]] = {
    "dynamic-html": ((1, "-"), (10, "small"), (1000, "large"), (10000, "-"), (100000, "-")),
    "uploader": ((256, "test"), (1000, "-"), (6700, "small"), (25000, "-"), (100000, "large")),
    "thumbnailer": ((50, "-"), (200, "-"), (1000, "-"), (4000, "-"), (16000, "-")),
    "video-processing": ((1000, "-"), (5000, "-"), (20000, "-"), (80000, "-")),
    "compression": ((500, "-"), (2000, "-"), (8000, "-"), (32000, "-"), (128000, "-")),
    "image-recognition": ((50, "-"), (100, "-"), (400, "-")),
    "graph-pagerank": ((1, "small"), (10, "large"), (30, "-"), (100, "-")),
    "graph-mst": ((1, "small"), (10, "large"), (30, "-"), (100, "-")),
    "graph-bfs": ((1, "small"), (10, "large"), (30, "-"), (100, "-")),
    "dna-visualisation": ((100, "-"), (500, "-"), (2000, "-"), (8000, "-")),
}
# guest memory (MB); the larger input sizes need more than the 512 MB default
MEM_MB = {
    "video-processing": 1024,
    "image-recognition": 2048,
    "dna-visualisation": 1024,
    "uploader": 1024,
    "compression": 1024,
    "graph-pagerank": 2048,
    "graph-mst": 2048,
    "graph-bfs": 2048,
}


def concurrencies(ctx: Ctx) -> list[int]:
    """Co-run levels: explicit ``concurrencies``, else 1, 2, 4, ... up to the physical cores, plus the physical-core
    count and the hardware-thread count (contract §5 ``fn_corun``), capped by ``max_concurrency`` if given."""
    raw = ctx.opt("concurrencies")
    if raw:
        return [int(x) for x in raw.split(",") if x]
    cores, threads = int(ctx.opt("physical_cores", str(_cores()))), os.cpu_count() or 1
    levels, n = {cores, threads}, 1
    while n < cores:
        levels.add(n)
        n *= 2
    top = int(ctx.opt("max_concurrency", "0"))  # a small machine's helper script caps the levels
    return sorted(x for x in levels if not top or x <= top)


def parse(lines: list[str], kind: str) -> list[tuple[str, int, int, float]]:
    """``VOSS_EXEC <fn> <size_kb> <rep> <seconds>`` (or ``VOSS_INIT <fn> 0 0 <seconds>``) payloads."""
    out = []
    for line in lines:
        parts = line.split()
        if len(parts) == 4:
            out.append((parts[0], int(parts[1]), int(parts[2]), float(parts[3])))
    return out


def one_guest(ctx: Ctx, a: FcAssets, fn: str, reps: int, tag: str) -> tuple[list[str], list[str], float]:
    """Run ``fn`` on every size in one guest; returns INIT lines, EXEC lines and the Firecracker process RSS (MB)."""
    sizes = ",".join(str(s) for s, _ in SIZES[fn])
    vm = FcVm(a, ctx.out / "fc", f"sebs-{tag}")
    try:
        vm.spawn()
        vm.configure(MEM_MB.get(fn, 512), 1, boot_args("sebs", f"voss.fn={fn} voss.sizes={sizes} voss.reps={reps}"))
        vm.start()
        init = vm.collect("INIT", until="imported", timeout=120.0)
        execs = vm.collect("EXEC", until="done", timeout=3600.0)
        return init, execs, vm.rss_mb()
    finally:
        vm.kill()


def snapshot_size(ctx: Ctx, a: FcAssets, fn: str, scratch: Path) -> float:
    """MB of the memory file of a snapshot taken once ``fn`` is imported and idle (``serve`` mode)."""
    vm = FcVm(a, ctx.out / "fc", f"snap-{fn}")
    state, mem = scratch / f"{fn}.state", scratch / f"{fn}.mem"
    try:
        vm.spawn()
        vm.configure(MEM_MB.get(fn, 512), 1, boot_args("fn", f"voss.fn={fn}"))
        vm.start()
        vm.wait("MARK", "ready", timeout=120.0)
        vm.pause()
        vm.snapshot(state, mem)
        return (state.stat().st_size + mem.stat().st_size) / 2**20
    finally:
        vm.kill()
        state.unlink(missing_ok=True)
        mem.unlink(missing_ok=True)


def _level(ctx: Ctx, a: FcAssets, fn: str, n: int, reps: int) -> bool:
    """One co-run level of ``fn``; False when a guest failed (the function is then skipped at higher levels)."""
    try:
        with cf.ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(lambda i: one_guest(ctx, a, fn, reps, f"{fn}-{n}-{i}"), range(n)))
    except (RuntimeError, TimeoutError) as e:  # e.g. a function whose dependencies are not in the image
        ctx.skip(f"sebs fn={fn} concurrency={n}", 0.0, f"guest failed: {e}")
        return False
    classes = dict(SIZES[fn])
    for guest, (init, execs, rss) in enumerate(results):
        for name, _, _, secs in parse(init, "INIT"):
            ctx.rec.add("sebs_init", secs, fn=name, concurrency=n, guest=guest)
        for name, size, rep, secs in parse(execs, "EXEC"):
            cls = classes.get(size, "-")
            ctx.rec.add("sebs_exec", secs, rep=rep, fn=name, size_kb=size, sebs_class=cls, concurrency=n, guest=guest)
        if n == 1:
            ctx.rec.add("fn_rss", rss, unit="MB", fn=fn)
    return True


def run(ctx: Ctx) -> None:
    a = assets(ctx, "sebs_rootfs")
    fns = [f for f in ctx.opt("functions", ",".join(SIZES)).split(",") if f]
    reps, levels = ctx.reps(30), concurrencies(ctx)
    scratch = ctx.dirs().get("ssd")
    for fn in fns:
        for n in levels:
            need = n * MEM_MB.get(fn, 512)
            if need > ctx.mem_budget_mb():
                ctx.skip(f"sebs fn={fn} concurrency={n}", need, "guests together over the RAM budget")
                continue
            if ctx.sh.dry_run:
                print(f"DRY sebs fn={fn} concurrency={n} reps={reps}")
                continue
            if not _level(ctx, a, fn, n, reps):
                break
        if scratch is not None and not ctx.sh.dry_run:
            scratch.mkdir(parents=True, exist_ok=True)
            ctx.rec.add("snap_size", snapshot_size(ctx, a, fn, scratch), unit="MB", fn=fn)


SUITE = Suite("sebs", run, "SeBS-style functions in Firecracker: init, exec by input size, co-run, memory, snapshot")
