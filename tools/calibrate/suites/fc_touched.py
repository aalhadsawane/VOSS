"""Share of a function's snapshot that a cold restore and its first invocation read from disk (the ``snapshot_touched``
artifact of the L2 → L3 rung, doc 02 §5; bundle entry ``snapshot_touched_frac``).

Per function and disk tier: a guest of the function boots in ``fn`` mode, imports it and is snapshotted (as the
``sebs`` suite's ``snap_size``). Each repetition evicts the snapshot files from the page cache, restores them in a
new Firecracker process (memory file mapped, pages read on first touch), makes the input (``PREP``) and runs the
handler once (``RUN``) at the function's reference input size. ``/proc/<pid>/io`` ``read_bytes`` of that process
after the run, over the memory file's size, is the touched fraction; it includes the kernel's readahead, which the
disk really reads. The guest root file system stays in the page cache, so its reads are not counted.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from tools.calibrate.common import SuiteSkipped, cache_scope, drop_caches
from tools.calibrate.fc import FcAssets, FcVm, boot_args
from tools.calibrate.suites import Ctx, Suite, sebs

REPS = 10  # restores per function and tier
CATALOG = Path(__file__).resolve().parents[3] / "configs" / "functions.yaml"


def ref_size(fn: str, catalog: str | None = None) -> int:
    """The ``sebs`` size nearest (log scale) to the catalogue's reference input ``in_kb`` (the first size if the
    catalogue does not list the function)."""
    text = catalog if catalog is not None else (CATALOG.read_text() if CATALOG.exists() else "")
    m = re.search(rf"name:\s*{re.escape(fn)}\s*,.*?in_kb:\s*([0-9.]+)", text)
    sizes = [s for s, _ in sebs.SIZES[fn]]
    if not m:
        return sizes[0]
    ref = math.log(max(float(m.group(1)), 1e-9))
    return min(sizes, key=lambda s: (abs(math.log(s) - ref), s))


def snapshot(ctx: Ctx, a: FcAssets, fn: str, d: Path) -> tuple[Path, Path]:
    vm = FcVm(a, ctx.out / "fc", f"touch-{fn}")
    state, mem = d / f"voss-touch-{fn}.state", d / f"voss-touch-{fn}.mem"
    try:
        vm.spawn()
        vm.configure(sebs.MEM_MB.get(fn, 512), 1, boot_args("fn", f"voss.fn={fn}"))
        vm.start()
        vm.wait("MARK", "ready", timeout=120.0)
        vm.pause()
        vm.snapshot(state, mem)
    finally:
        vm.kill()
    return state, mem


def restore_and_run(ctx: Ctx, a: FcAssets, state: Path, mem: Path, size: int, tag: str) -> tuple[int, int, int]:
    """``read_bytes`` after the restore, after making the input, and after the first invocation."""
    vm = FcVm(a, ctx.out / "fc", f"touchr-{tag}")
    try:
        vm.spawn()
        vm.load(state, mem)
        vm.send(f"PING 0 {tag}")
        vm.wait("ACK", tag, timeout=60.0)
        r_restore = vm.read_bytes()
        vm.send(f"PREP {size} {tag}")
        vm.wait("ACK", tag, timeout=600.0)
        r_prep = vm.read_bytes()
        vm.send(f"RUN {size} {tag}")
        vm.wait("EXEC", "", timeout=600.0)
        return r_restore, r_prep, vm.read_bytes()
    finally:
        vm.kill()


def _function(ctx: Ctx, fn: str, tier: str, d: Path) -> None:
    base = sebs.guest_assets(ctx, fn)
    a = FcAssets(base.firecracker, base.kernel, base.rootfs)  # snapshot paths outside a jail
    need = sebs.MEM_MB.get(fn, 512)
    if need > ctx.mem_budget_mb() or not ctx.has_room(d, need + 64):
        ctx.skip(f"fc_touched fn={fn} tier={tier}", need, "guest memory or snapshot over the RAM or disk budget")
        return
    size = ref_size(fn)
    if ctx.sh.dry_run:
        print(f"DRY fc_touched fn={fn} tier={tier} size={size} reps={ctx.reps(REPS)}")
        return
    state, mem = snapshot(ctx, a, fn, d)
    try:
        mem_bytes = mem.stat().st_size
        for rep in range(ctx.reps(REPS)):
            drop_caches(ctx.sh, [state, mem])
            r0, r1, r2 = restore_and_run(ctx, a, state, mem, size, f"{fn}-{tier}-{rep}")
            cfg = {"fn": fn, "tier": tier, "size_kb": size, "cache": "cold", "cache_scope": cache_scope()}
            ctx.rec.add("snapshot_touched_frac", r2 / mem_bytes, unit="frac", rep=rep, mem_bytes=mem_bytes, **cfg)
            ctx.rec.add("snapshot_read_restore", float(r0), unit="B", rep=rep, **cfg)
            ctx.rec.add("snapshot_read_input", float(r1 - r0), unit="B", rep=rep, **cfg)
            ctx.rec.add("snapshot_read_first_run", float(r2 - r1), unit="B", rep=rep, **cfg)
    finally:
        state.unlink(missing_ok=True)
        mem.unlink(missing_ok=True)


def run(ctx: Ctx) -> None:
    dirs = ctx.dirs()
    if not dirs:
        raise SuiteSkipped("pass --set <tier>_dir=<scratch dir> for each disk class (nvme, sata, hdd)")
    fns = [f for f in ctx.opt("functions", ",".join(sebs.SIZES)).split(",") if f]
    for tier, d in sorted(dirs.items()):
        d.mkdir(parents=True, exist_ok=True)
        for fn in fns:
            try:
                _function(ctx, fn, tier, d)
            except SuiteSkipped as e:  # no ML image given: only the functions that need it are left out
                ctx.skip(f"fc_touched fn={fn} tier={tier}", 0, str(e))


SUITE = Suite("fc_touched", run, "share of a snapshot read from disk by a cold restore and the first invocation")
