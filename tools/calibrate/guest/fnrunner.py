"""Guest function runner for the ``sebs``, ``fn_inputs``, ``fc_dispatch`` and ``fc_touched`` suites (doc 10 §3):
import one function (cold init), then run it on each input size ``reps`` times, printing ``VOSS_INIT``/``VOSS_EXEC``
lines on the serial console. ``make_input`` always runs before the handler's timer starts."""

from __future__ import annotations

import importlib
import os
import re
import socket
import sys
import threading
import time
import traceback
from typing import Any


def cmdline() -> dict[str, str]:
    with open("/proc/cmdline") as f:
        text = f.read()
    return dict(re.findall(r"voss\.(\w+)=(\S+)", text))


def _input(mod: Any, cache: dict[int, object], size: int) -> object:
    inp = cache.get(size)
    if inp is None:
        inp = cache[size] = mod.make_input(size)
    return inp


def vsock_listen(port: int) -> socket.socket:
    """Bound and listening before ``VOSS_MARK ready``, so the host's first connection never races the bind."""
    ls = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
    ls.bind((socket.VMADDR_CID_ANY, port))
    ls.listen(8)
    return ls


def vsock_serve(fn: str, mod: Any, cache: dict[int, object], ls: socket.socket) -> None:
    """Dispatch over vsock (contract §4 ``dispatch_warm``): the host's agent connects through Firecracker's vsock
    device. Per connection, one command per line: ``PREP <size_kb> <tag>`` answers ``ACK <tag>``; ``RUN <size_kb>
    <tag>`` answers ``START <tag>`` immediately before the handler is called and ``EXEC <fn> <size_kb> <tag>
    <handler_s>`` after it; ``PING 0 <tag>`` answers ``ACK <tag>``."""
    while True:
        conn, _ = ls.accept()
        with conn, conn.makefile("rwb", buffering=0) as f:
            for line in f:
                parts = line.decode().split()
                if len(parts) < 3:
                    continue
                if parts[0] in ("PING", "PREP"):
                    if parts[0] == "PREP":
                        _input(mod, cache, int(parts[1]))
                    f.write(f"ACK {parts[2]}\n".encode())
                elif parts[0] == "RUN":
                    inp = _input(mod, cache, int(parts[1]))
                    f.write(f"START {parts[2]}\n".encode())
                    t = time.perf_counter()
                    mod.handler(inp)
                    f.write(f"EXEC {fn} {parts[1]} {parts[2]} {time.perf_counter() - t:.6f}\n".encode())


def serve(fn: str, vsock_port: int = 0) -> None:
    """Emulation testbed (doc 10 §4) and snapshot suites: import ``fn`` once, then run it on demand.

    Serial-console protocol, one command per line:
    ``PREP <size_kb> <tag>``  make and cache the input, answer ``VOSS_ACK <tag>``;
    ``RUN <size_kb> <tag>``   run the handler, answer ``VOSS_EXEC <fn> <size_kb> <tag> <handler_s> <total_s>``;
    ``PING 0 <tag>``          answer ``VOSS_ACK <tag>``.
    ``VOSS_MARK ready`` follows the import. A snapshot taken while blocked on the read resumes into the same loop.
    With ``voss.vsock=<port>`` the same function also listens on vsock (``vsock_serve``)."""
    sys.path.insert(0, "/voss")
    t0 = time.perf_counter()
    mod = importlib.import_module("functions." + fn.replace("-", "_"))
    print(f"VOSS_INIT {fn} 0 0 {time.perf_counter() - t0:.6f}", flush=True)
    cache: dict[int, object] = {}
    if vsock_port:
        ls = vsock_listen(vsock_port)
        threading.Thread(target=vsock_serve, args=(fn, mod, cache, ls), daemon=True).start()
    print("VOSS_MARK ready", flush=True)
    # commands come from the console; give children (ffmpeg reads stdin!) /dev/null so they cannot eat a request
    cmds = os.fdopen(os.dup(0), "r")
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
    for line in cmds:
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "PING":
            print(f"VOSS_ACK {parts[2]}", flush=True)
        elif (
            len(parts) >= 3 and parts[0] == "PREP"
        ):  # make the input ahead of the request (it arrives over the network)
            _input(mod, cache, int(parts[1]))
            print(f"VOSS_ACK {parts[2]}", flush=True)
        elif len(parts) >= 3 and parts[0] == "RUN":
            t_all = time.perf_counter()
            inp = _input(mod, cache, int(parts[1]))
            t = time.perf_counter()
            mod.handler(inp)
            end = time.perf_counter()
            print(f"VOSS_EXEC {fn} {parts[1]} {parts[2]} {end - t:.6f} {end - t_all:.6f}", flush=True)


def make_inputs(mod: Any, fn: str, size: int, gen_reps: int) -> object:
    """The input of ``size``; with ``gen_reps`` > 0 it is built that many times, each timed (``VOSS_GEN`` lines,
    contract §5 ``fn_input_gen``). Without, it is built once and not reported (the ``sebs`` suite)."""
    if gen_reps <= 0:
        return mod.make_input(size)
    inp: object = None
    for rep in range(gen_reps):
        inp = None  # the previous input is freed first, so two never sit in guest memory together
        t = time.perf_counter()
        inp = mod.make_input(size)
        print(f"VOSS_GEN {fn} {size} {rep} {time.perf_counter() - t:.6f}", flush=True)
    return inp


def main() -> None:
    args = cmdline()
    fn = args["fn"]
    if args.get("mode") == "fn":
        serve(fn, int(args.get("vsock", "0")))
        return
    sizes = [int(s) for s in args.get("sizes", "1").split(",")]
    reps, gen_reps = int(args.get("reps", "10")), int(args.get("gen_reps", "0"))
    sys.path.insert(0, "/voss")
    t0 = time.perf_counter()
    mod = importlib.import_module("functions." + fn.replace("-", "_"))
    print(f"VOSS_INIT {fn} 0 0 {time.perf_counter() - t0:.6f}", flush=True)
    print("VOSS_MARK imported", flush=True)
    for size in sizes:
        inp = make_inputs(mod, fn, size, gen_reps)
        for rep in range(reps):
            t = time.perf_counter()
            mod.handler(inp)
            print(f"VOSS_EXEC {fn} {size} {rep} {time.perf_counter() - t:.6f}", flush=True)
    print("VOSS_MARK done", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # report to the host instead of hanging the VM
        print(f"VOSS_ERR {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
