"""Dispatch to a warm sandbox over vsock (contract §4 ``dispatch_warm``; the L3 → L4 rung of doc 02 §5).

One guest of the dispatch function boots in ``fn`` mode with a vsock listener (``guest/fnrunner.py``), imports the
function, and its input is made ahead (``PREP``: the input arrives over the network, which is modelled separately).
Each dispatch then opens a new host-initiated vsock connection (Firecracker's Unix socket, ``CONNECT <port>``), sends
``RUN`` and stops the clock when the guest's ``START`` line arrives; the guest writes it immediately before it calls
the handler. So ``dispatch_warm`` is connect + request + the guest's wake-up until the handler starts, plus one small
guest-to-host message; ``vsock_rtt`` (a ``PING`` on an open connection) measures that message's round trip so the
report can state the bound. Feeds the bundle's ``dispatch``.
"""

from __future__ import annotations

import time
from typing import Any

from tools.calibrate.fc import FcAssets, FcVm, VsockLine, boot_args
from tools.calibrate.suites import Ctx, Suite, sebs

REPS = 200  # contract §4: dispatch_warm n >= 200
PORT = 5005
FN, SIZE = "thumbnailer", 50  # a base-image function with a small input; the handler's own time is not measured


def dispatch_once(uds: str, size: int, tag: str) -> tuple[float, float, float]:
    """(dispatch seconds, handler seconds the guest reports, vsock round trip) of one invocation."""
    t0 = time.monotonic()
    c = VsockLine(uds, PORT)
    try:
        c.send(f"RUN {size} {tag}")
        start = c.line()
        t1 = time.monotonic()
        if start != f"START {tag}":
            raise RuntimeError(f"expected START {tag}, got {start!r}")
        done = c.line().split()
        t2 = time.monotonic()
        c.send(f"PING 0 {tag}")
        c.line()
        rtt = time.monotonic() - t2
        return t1 - t0, float(done[-1]), rtt
    finally:
        c.close()


def run(ctx: Ctx) -> None:
    fn, size = ctx.opt("dispatch_fn", FN), int(ctx.opt("dispatch_size", str(SIZE)))
    base = sebs.guest_assets(ctx, fn)
    a = FcAssets(base.firecracker, base.kernel, base.rootfs)  # the vsock socket lives outside a jail
    mem = sebs.MEM_MB.get(fn, 512)
    if ctx.sh.dry_run:
        print(f"DRY fc_dispatch fn={fn} size={size} mem={mem} reps={ctx.reps(REPS)}")
        return
    vm = FcVm(a, ctx.out / "fc", f"dispatch-{fn}")
    try:
        vm.spawn()
        vm.configure(mem, 1, boot_args("fn", f"voss.fn={fn} voss.vsock={PORT}"))
        uds = vm.vsock()
        vm.start()
        vm.wait("MARK", "ready", timeout=120.0)
        prep = VsockLine(uds, PORT)
        prep.send(f"PREP {size} prep")
        prep.line()
        prep.close()
        for rep in range(ctx.reps(REPS)):
            secs, handler_s, rtt = dispatch_once(uds, size, f"d{rep}")
            cfg: dict[str, Any] = {"fn": fn, "size_kb": size, "mem_mb": mem, "transport": "vsock", "connection": "new"}
            ctx.rec.add("dispatch_warm", secs, rep=rep, **cfg)
            ctx.rec.add("dispatch_handler", handler_s, rep=rep, **cfg)
            ctx.rec.add("vsock_rtt", rtt, rep=rep, **cfg)
    finally:
        vm.kill()


SUITE = Suite("fc_dispatch", run, "dispatch to a warm Firecracker sandbox over vsock until the handler starts")
