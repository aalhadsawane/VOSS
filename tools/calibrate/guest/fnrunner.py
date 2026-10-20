"""Guest function runner for the ``sebs`` suite (doc 10 §3): import one function (cold init), then run it on each
input size ``reps`` times, printing ``VOSS_INIT``/``VOSS_EXEC`` lines on the serial console."""

from __future__ import annotations

import importlib
import re
import sys
import time
import traceback


def cmdline() -> dict[str, str]:
    with open("/proc/cmdline") as f:
        text = f.read()
    return dict(re.findall(r"voss\.(\w+)=(\S+)", text))


def serve(fn: str) -> None:
    """Emulation testbed (doc 10 §4): import ``fn`` once, then run it on demand.

    Protocol on the serial console: ``RUN <size_kb> <tag>`` -> ``VOSS_EXEC <fn> <size_kb> <tag> <handler_s> <total_s>``
    (handler time and time including input generation); ``VOSS_MARK ready`` after the import. A snapshot taken while
    blocked on the read resumes into the same loop."""
    sys.path.insert(0, "/voss")
    t0 = time.perf_counter()
    mod = importlib.import_module("functions." + fn.replace("-", "_"))
    print(f"VOSS_INIT {fn} 0 0 {time.perf_counter() - t0:.6f}", flush=True)
    print("VOSS_MARK ready", flush=True)
    for line in sys.stdin:
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "PING":
            print(f"VOSS_ACK {parts[2]}", flush=True)
        elif len(parts) >= 3 and parts[0] == "RUN":
            t_all = time.perf_counter()
            inp = mod.make_input(int(parts[1]))
            t = time.perf_counter()
            mod.handler(inp)
            end = time.perf_counter()
            print(f"VOSS_EXEC {fn} {parts[1]} {parts[2]} {end - t:.6f} {end - t_all:.6f}", flush=True)


def main() -> None:
    args = cmdline()
    fn = args["fn"]
    if args.get("mode") == "fn":
        serve(fn)
        return
    sizes = [int(s) for s in args.get("sizes", "1").split(",")]
    reps = int(args.get("reps", "10"))
    sys.path.insert(0, "/voss")
    t0 = time.perf_counter()
    mod = importlib.import_module("functions." + fn.replace("-", "_"))
    print(f"VOSS_INIT {fn} 0 0 {time.perf_counter() - t0:.6f}", flush=True)
    print("VOSS_MARK imported", flush=True)
    for size in sizes:
        inp = mod.make_input(size)
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
