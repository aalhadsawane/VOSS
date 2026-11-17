"""Input generation time per function and input size (contract §5 ``fn_input_gen``; reported, never part of
``fn_exec``).

One guest per function, alone on the machine, at the ``sebs`` suite's sizes and guest memory: the guest builds each
input ``REPS`` times and times every build (``VOSS_GEN`` lines of ``guest/fnrunner.py``); no handler runs
(``voss.reps=0``). The ``sebs`` suite's handler times are unaffected: there ``make_input`` still runs once per size,
before the timer starts.
"""

from __future__ import annotations

from tools.calibrate.common import SuiteSkipped
from tools.calibrate.fc import FcAssets, FcVm, boot_args
from tools.calibrate.suites import Ctx, Suite, sebs

REPS = 30  # contract §5: fn_input_gen n >= 30 per size


def one_guest(ctx: Ctx, a: FcAssets, fn: str, reps: int) -> list[str]:
    sizes = ",".join(str(s) for s, _ in sebs.SIZES[fn])
    vm = FcVm(a, ctx.out / "fc", f"gen-{fn}")
    try:
        vm.spawn()
        args = f"voss.fn={fn} voss.sizes={sizes} voss.reps=0 voss.gen_reps={reps}"
        vm.configure(sebs.MEM_MB.get(fn, 512), 1, boot_args("sebs", args))
        vm.start()
        vm.wait("MARK", "imported", timeout=120.0)
        return vm.collect("GEN", until="done", timeout=3600.0)
    finally:
        vm.kill()


def run(ctx: Ctx) -> None:
    reps = ctx.reps(REPS)
    for fn in [f for f in ctx.opt("functions", ",".join(sebs.SIZES)).split(",") if f]:
        try:
            a = sebs.guest_assets(ctx, fn)
        except SuiteSkipped as e:
            ctx.skip(f"fn_inputs fn={fn}", 0, str(e))
            continue
        if ctx.sh.dry_run:
            print(f"DRY fn_inputs fn={fn} reps={reps}")
            continue
        for name, size, rep, secs in sebs.parse(one_guest(ctx, a, fn, reps), "GEN"):
            ctx.rec.add("fn_input_gen", secs, rep=rep, fn=name, size_kb=size)


SUITE = Suite("fn_inputs", run, "input generation time per function and input size, one guest alone")
