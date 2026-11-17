"""TME on vs off (doc 10 §3 ``tme``, manual): STREAM-style memory bandwidth and a SeBS subset at concurrency 1, run
once per BIOS setting with ``--phase on`` / ``--phase off``. Toggling TME is a BIOS change done by the owner of the
machine with the human's approval, never by the harness; ``ingest`` turns the two phases into the ``tme_cpu_factor``
/ ``tme_mem_factor`` slowdowns only when both were measured on the same node (otherwise they stay missing).

Every run first records the firmware's TME state (``tme_state``: CPUID enumeration, and whether the firmware enabled
it, from the kernel log or MSR ``IA32_TME_ACTIVATE``) and refuses a ``--phase`` that contradicts it.
``python -m tools.calibrate.suites.tme state`` prints ``on``, ``off`` or ``unknown`` (``node_run.sh`` uses it).
"""

from __future__ import annotations

import re
import struct
import sys
import time
from pathlib import Path

from tools.calibrate.common import Shell, SuiteSkipped, read_text
from tools.calibrate.suites import Ctx, Suite, sebs

STREAM_C = Path(__file__).resolve().parents[1] / "bench" / "stream.c"
SUBSET = "dynamic-html,thumbnailer,compression,graph-pagerank"
MSR_TME_ACTIVATE = 0x982  # bit 0 lock, bit 1 enable


def triad_MBps(stream_out: str) -> float:
    """``Triad:  <best MB/s> ...`` from STREAM's report."""
    m = re.search(r"^Triad:\s+([0-9.]+)", stream_out, re.M)
    if not m:
        raise RuntimeError("no Triad line in STREAM output")
    return float(m.group(1))


def bios_enabled(dmesg: str, msr: int | None) -> bool | None:
    """Whether the firmware turned TME on: the kernel's ``x86/tme`` line, else the MSR's enable bit."""
    if re.search(r"x86/tme: not enabled by BIOS", dmesg):
        return False
    if re.search(r"x86/tme: enabled by BIOS", dmesg):
        return True
    return None if msr is None else bool(msr & 0b10)


def _msr() -> int | None:
    try:
        with open("/dev/cpu/0/msr", "rb") as f:
            f.seek(MSR_TME_ACTIVATE)
            return int(struct.unpack("<Q", f.read(8))[0])
    except OSError:  # not root, or the msr module is not loaded
        return None


def state(sh: Shell) -> dict[str, object]:
    """``phase`` is ``on``/``off`` when the firmware state is known, else ``unknown``."""
    flags = re.search(r"^flags\s*:(.*)$", read_text("/proc/cpuinfo"), re.M)
    cpuid = bool(flags) and "tme" in flags.group(1).split()  # type: ignore[union-attr]
    dmesg = sh.run(["dmesg"], check=False).out if sh.have("dmesg") else ""
    msr = _msr()
    on = bios_enabled(dmesg, msr) if cpuid else False
    phase = "unknown" if on is None else ("on" if on else "off")
    return {"phase": phase, "cpuid": cpuid, "msr": msr, "dmesg": "x86/tme" in dmesg}


def _stream(ctx: Ctx) -> str:
    exe = ctx.out / "stream"
    ctx.sh.need("gcc")
    ctx.sh.run(
        ["gcc", "-O3", "-march=native", "-fopenmp", "-DSTREAM_ARRAY_SIZE=80000000", str(STREAM_C), "-o", str(exe)]
    )
    return str(exe)


def run(ctx: Ctx) -> None:
    if ctx.phase not in ("on", "off"):
        raise SuiteSkipped("manual suite: set TME in the BIOS, boot, then run with --phase on|off (doc 10 §3)")
    st = state(Shell()) if not ctx.sh.dry_run else {"phase": ctx.phase, "cpuid": None, "msr": None, "dmesg": False}
    ctx.rec.add("tme_state", float(st["phase"] == "on"), unit="bool", **st)
    if st["phase"] != ctx.phase:
        raise RuntimeError(f"--phase {ctx.phase} but the firmware's TME state is {st['phase']}: nothing measured")
    exe = _stream(ctx)
    for rep in range(ctx.reps(10)):
        c = ctx.sh.run([exe])
        if not ctx.sh.dry_run:
            ctx.rec.add("stream_triad", triad_MBps(c.out), unit="MBps", rep=rep, phase=ctx.phase)
    t0 = time.monotonic()
    opts = dict(ctx.opts) | {"concurrencies": "1", "snapshots": "0"}  # factor = handler time alone, on vs off
    opts.setdefault("functions", SUBSET)
    sebs.run(Ctx(ctx.sh, ctx.rec, ctx.out, opts, ctx.reps_scale, phase=ctx.phase))
    ctx.rec.add("tme_phase_wall", time.monotonic() - t0, phase=ctx.phase)


SUITE = Suite("tme", run, "TME on/off: STREAM triad and a SeBS subset (BIOS toggle by the owner)", manual="bios")


if __name__ == "__main__":
    if sys.argv[1:] == ["state"]:
        print(state(Shell())["phase"])
    else:
        print("usage: python -m tools.calibrate.suites.tme state", file=sys.stderr)
        raise SystemExit(2)
