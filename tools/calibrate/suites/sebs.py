"""SeBS-style functions inside Firecracker (doc 10 §3 ``sebs``): per-function init (cold import) and execution time
versus input size, alone and with 2-8 concurrent guests (interference). Feeds function profiles (``init_s``,
``work_ref_s``, ``size_exp``), predictor priors, C0's ``speed`` and interference.

The guest image (``guest/build_rootfs.sh``) contains ``/voss/fnrunner.py``; the kernel command line selects the
function, input sizes and repetitions, and the guest prints ``VOSS_INIT`` / ``VOSS_EXEC`` lines.
"""

from __future__ import annotations

import concurrent.futures as cf

from tools.calibrate.fc import FcAssets, FcVm, boot_args
from tools.calibrate.suites import Ctx, Suite
from tools.calibrate.suites.fc_boot import assets

# function → input sizes (KiB) around the catalog's reference size (configs/functions.yaml ``in_kb``)
SIZES: dict[str, tuple[int, ...]] = {
    "dynamic-html": (1, 10, 100),
    "uploader": (1, 100, 1000),
    "thumbnailer": (50, 200, 1000),
    "video-processing": (1000, 5000, 20000),
    "compression": (500, 2000, 8000),
    "image-recognition": (50, 100, 400),
    "graph-pagerank": (1,),
    "graph-mst": (1,),
    "graph-bfs": (1,),
    "dna-visualisation": (100, 500, 2000),
}
MEM_MB = {"video-processing": 1024, "image-recognition": 2048, "dna-visualisation": 1024}
CONCURRENCY = (1, 2, 4, 8)


def parse(lines: list[str], kind: str) -> list[tuple[str, int, int, float]]:
    """``VOSS_EXEC <fn> <size_kb> <rep> <seconds>`` (or ``VOSS_INIT <fn> 0 0 <seconds>``) payloads."""
    out = []
    for line in lines:
        parts = line.split()
        if len(parts) == 4:
            out.append((parts[0], int(parts[1]), int(parts[2]), float(parts[3])))
    return out


def one_guest(ctx: Ctx, a: FcAssets, fn: str, reps: int, tag: str) -> tuple[list[str], list[str]]:
    sizes = ",".join(str(s) for s in SIZES[fn])
    vm = FcVm(a, ctx.out / "fc", f"sebs-{tag}")
    try:
        vm.spawn()
        vm.configure(MEM_MB.get(fn, 512), 1, boot_args("sebs", f"voss.fn={fn} voss.sizes={sizes} voss.reps={reps}"))
        vm.start()
        init = vm.collect("INIT", until="imported", timeout=120.0)
        execs = vm.collect("EXEC", until="done", timeout=1800.0)
        return init, execs
    finally:
        vm.kill()


def run(ctx: Ctx) -> None:
    a = assets(ctx, "sebs_rootfs")
    fns = [f for f in ctx.opt("functions", ",".join(SIZES)).split(",") if f]
    reps = ctx.reps(30)
    top = int(ctx.opt("max_concurrency", str(max(CONCURRENCY))))
    for fn in fns:
        for n in (c for c in CONCURRENCY if c <= top):
            need = n * MEM_MB.get(fn, 512)
            if need > ctx.mem_budget_mb():
                ctx.skip(f"sebs fn={fn} concurrency={n}", need, "guests together over the RAM budget")
                continue
            if ctx.sh.dry_run:
                print(f"DRY sebs fn={fn} concurrency={n} reps={reps}")
                continue
            try:
                with cf.ThreadPoolExecutor(max_workers=n) as pool:
                    results = list(pool.map(lambda i, f=fn, k=n: one_guest(ctx, a, f, reps, f"{f}-{k}-{i}"), range(n)))
            except (RuntimeError, TimeoutError) as e:  # e.g. a function whose dependencies are not in the image
                ctx.skip(f"sebs fn={fn} concurrency={n}", 0.0, f"guest failed: {e}")
                break
            for guest, (init, execs) in enumerate(results):
                for name, _, _, secs in parse(init, "INIT"):
                    ctx.rec.add("sebs_init", secs, fn=name, concurrency=n, guest=guest)
                for name, size, rep, secs in parse(execs, "EXEC"):
                    ctx.rec.add("sebs_exec", secs, rep=rep, fn=name, size_kb=size, concurrency=n, guest=guest)


SUITE = Suite("sebs", run, "SeBS-style functions in Firecracker: init and exec vs input size and concurrency")
