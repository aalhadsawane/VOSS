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


def main() -> None:
    args = cmdline()
    fn = args["fn"]
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
