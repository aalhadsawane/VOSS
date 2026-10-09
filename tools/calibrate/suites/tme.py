"""TME on vs off (doc 10 §3 ``tme``, manual): STREAM-style memory bandwidth and a SeBS subset, run once per BIOS
setting with ``--phase on`` / ``--phase off``. Toggling TME is a BIOS change done by the owner of the machine, never by
the harness; ``ingest`` turns the two phases into the ``tme_cpu_factor`` / ``tme_mem_factor`` slowdowns.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from tools.calibrate.common import SuiteSkipped
from tools.calibrate.suites import Ctx, Suite, sebs

STREAM_C = Path(__file__).resolve().parents[1] / "bench" / "stream.c"


def triad_MBps(stream_out: str) -> float:
    """``Triad:  <best MB/s> ...`` from STREAM's report."""
    m = re.search(r"^Triad:\s+([0-9.]+)", stream_out, re.M)
    if not m:
        raise RuntimeError("no Triad line in STREAM output")
    return float(m.group(1))


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
    exe = _stream(ctx)
    for rep in range(ctx.reps(10)):
        c = ctx.sh.run([exe])
        if not ctx.sh.dry_run:
            ctx.rec.add("stream_triad", triad_MBps(c.out), unit="MBps", rep=rep, phase=ctx.phase)
    t0 = time.monotonic()
    ctx.opts.setdefault("functions", "dynamic-html,thumbnailer,compression,graph-pagerank")
    sub = Ctx(ctx.sh, ctx.rec, ctx.out, ctx.opts, ctx.reps_scale * 0.34, phase=ctx.phase)
    sebs.run(sub)
    ctx.rec.add("tme_phase_wall", time.monotonic() - t0, phase=ctx.phase)


SUITE = Suite("tme", run, "TME on/off: STREAM triad and a SeBS subset (BIOS toggle by the owner)", manual="bios")
