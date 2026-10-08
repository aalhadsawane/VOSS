"""E-CS1, simulated side (doc 06 §5): start-up latency per cache level and trust establishment per substrate.

Each substrate profile is interpreted by the same lifecycle engine as the simulator (doc 02 §5) on an isolated C0
host: local registry (1 Gbps, 1 ms) and verifier/KBS at a fixed RTT. Literature ranges are reported at their low,
mid and high points. The measured side (Firecracker, QEMU, Kata on node C0) arrives with P9.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
from voss.core.config import ScenarioConfig
from voss.core.dist import Dist
from voss.core.kernel import Kernel
from voss.core.rng import stream
from voss.world.hardware import load_hw_class
from voss.world.lifecycle import OpEnv, OpRun, artifact_sizes, ops_of, split_path
from voss.world.resources import Disk, Psp, Tpm
from voss.world.substrate import SUBSTRATES, Op, RpcOp, SubstrateProfile, load_bundle, load_substrate
from voss.world.workload import FunctionSpec, load_catalog

FUNCTIONS = ("dynamic-html", "thumbnailer", "image-recognition", "video-processing")


def _env(
    k: Kernel,
    prof: SubstrateProfile,
    fn: FunctionSpec | None,
    gen: np.random.Generator,
    rtt_s: float,
    bundle: dict[str, Dist],
) -> OpEnv:
    hw = load_hw_class("C0")
    disks = {
        "ssd": Disk(k, "ssd", hw.ssd_read_MBps, hw.ssd_write_MBps),
        "hdd": Disk(k, "hdd", hw.hdd_read_MBps, hw.hdd_write_MBps),
    }
    touched = bundle["snapshot_touched_frac"].mean() if "snapshot_touched_frac" in bundle else 0.3
    env = OpEnv(
        k,
        gen,
        speed=hw.speed,
        tpm=Tpm(k, bundle["tpm2_quote"], gen),
        psp=Psp(k),
        disks=disks,
        sizes=artifact_sizes(fn, touched) if fn is not None else {},
        tiers={"bundle": "ssd", "rootfs": "ssd", "snapshot": "ssd", "snapshot_touched": "ssd"},
        fn=fn,
    )

    def rpc(op: RpcOp, cont: Callable[[], None]) -> None:
        k.after(rtt_s + (op.size + op.reply) * 8 / 1e9, cont)

    def fetch(arts: tuple[str, ...], cont: Callable[[], None]) -> None:
        k.after(0.001 + sum(env.sizes.get(a, 0.0) for a in arts) * 8 / 1e9, cont)

    env.rpc, env.fetch = rpc, fetch
    return env


def _time(ops: tuple[Op, ...], make_env: Callable[[Kernel], OpEnv]) -> float:
    k = Kernel()
    out: list[float] = []
    OpRun(ops, make_env(k), out.append).start()
    k.run(1e7)
    return out[0]


def measure(prof: SubstrateProfile, bundle: dict[str, Dist], n: int, rtt_s: float) -> list[dict[str, object]]:
    cat = load_catalog(ScenarioConfig())
    rows: list[dict[str, object]] = []
    lad = prof.ladder
    g = stream(1, "ecs1", prof.name)
    est = [_time(prof.session.establish, lambda k: _env(k, prof, None, g, rtt_s, bundle)) for _ in range(n)]
    rows.append({"what": "session_establish", "fn": "-", "samples": est})
    trust = (
        [_time(prof.trust, lambda k: _env(k, prof, None, g, rtt_s, bundle)) for _ in range(n)]
        if prof.trust
        else [0.0] * n
    )
    rows.append({"what": "key_release", "fn": "-", "samples": trust})
    busy = f"{lad.ready}->{lad.busy}"
    for f in (x for x in cat.functions if x.name in FUNCTIONS):
        for level in lad.levels[: lad.levels.index(lad.ready) + 1]:
            prep, rest = split_path(lad, level)
            ops = ops_of(lad, prep + rest + ([busy] if busy in lad.transitions else []))
            make: Callable[[Kernel], OpEnv] = partial(_env, prof=prof, fn=f, gen=g, rtt_s=rtt_s, bundle=bundle)
            xs = [_time(ops, make) for _ in range(n)]
            rows.append({"what": f"start_{level}", "fn": f.name, "samples": xs})
    return rows


def run(n: int, rtt_s: float) -> pd.DataFrame:
    bundle = load_bundle("calibration/placeholder/c0")
    out = []
    for name in SUBSTRATES:
        for at in (0.0, 0.5, 1.0):
            prof = load_substrate(name, bundle, range_at=at)
            for r in measure(prof, bundle, n, rtt_s):
                xs = np.asarray(r["samples"], dtype=float)
                out.append(
                    {
                        "substrate": name,
                        "range_at": at,
                        "what": r["what"],
                        "fn": r["fn"],
                        "p50_s": float(np.median(xs)),
                        "p90_s": float(np.quantile(xs, 0.9)),
                    }
                )
    return pd.DataFrame(out)


def report(df: pd.DataFrame) -> str:
    mid = df[df.range_at == 0.5]
    lines = [
        "# E-CS1 (simulated side): start-up and trust establishment per substrate",
        "",
        "Lifecycle engine on an isolated C0 host; values from the **placeholder** calibration bundle (literature/"
        "assumed until P9) and literature ranges at their midpoint; low/high in `ECS1-sim.csv`. "
        "Median seconds (p90 in parentheses).",
        "",
        "| substrate | session establish | key release | function | L0 | L1 | L2 | L3 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name in SUBSTRATES:
        d = mid[mid.substrate == name]
        est = d[d.what == "session_establish"].iloc[0]
        key = d[d.what == "key_release"].iloc[0]
        for f in FUNCTIONS:
            cells = []
            for lv in ("L0", "L1", "L2", "L3"):
                r = d[(d.fn == f) & (d.what == f"start_{lv}")]
                cells.append(f"{r.p50_s.iloc[0]:.3f} ({r.p90_s.iloc[0]:.3f})" if len(r) else "—")
            lines.append(
                f"| {name} | {est.p50_s:.2f} ({est.p90_s:.2f}) | {key.p50_s:.3f} | {f} | {' | '.join(cells)} |"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--rtt", type=float, default=0.05)
    p.add_argument("--out", type=Path, default=Path("docs/pilots/ECS1-sim.md"))
    a = p.parse_args()
    df = run(a.n, a.rtt)
    df.to_csv(a.out.with_suffix(".csv"), index=False)
    a.out.write_text(report(df))
    print(a.out)


if __name__ == "__main__":
    main()
