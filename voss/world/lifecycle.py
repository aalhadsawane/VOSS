"""Generic lifecycle engine (doc 02 §5, doc 05 §5): interprets substrate op lists; no per-substrate code.

``OpRun`` executes ops sequentially on the worker's simulated resources. Ops that are protocol exchanges
(``rpc``, ``fetch``) are delegated to hooks supplied by the worker agent, which sends the real messages and resumes
the run when the reply arrives. Every run can be aborted (host died); late callbacks are then ignored.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from voss.core.dist import Dist
from voss.core.kernel import Kernel
from voss.world.cache import WorkerCache, digest
from voss.world.resources import Disk, Psp, Tpm
from voss.world.substrate import (
    CpuOp,
    DelayOp,
    DiskReadOp,
    DiskWriteOp,
    FetchOp,
    LadderSpec,
    Op,
    PspOp,
    RpcOp,
    TpmQuoteOp,
)
from voss.world.workload import FunctionSpec

Done = Callable[[], None]
RpcHook = Callable[[RpcOp, Done], None]
FetchHook = Callable[[tuple[str, ...], Done], None]
MB = 1024 * 1024


@dataclass
class OpEnv:
    """What an op list may touch: the worker's own resources plus protocol hooks."""

    kernel: Kernel
    gen: np.random.Generator
    speed: float = 1.0
    io_slowdown: float = 1.0
    tpm: Tpm | None = None
    psp: Psp | None = None
    disks: dict[str, Disk] = field(default_factory=dict)
    sizes: dict[str, float] = field(default_factory=dict)  # artifact → bytes
    tiers: dict[str, str] = field(default_factory=dict)  # artifact → disk tier holding it
    fn: FunctionSpec | None = None
    rpc: RpcHook | None = None
    fetch: FetchHook | None = None


def value(ref: Dist | str | float, env: OpEnv) -> float:
    """Sample a distribution reference: a dist, a constant or ``fn.<attr>``."""
    if isinstance(ref, str):
        if env.fn is None:
            raise ValueError(f"'{ref}' needs a function")
        return float(getattr(env.fn, ref.removeprefix("fn.")))
    if isinstance(ref, int | float):
        return float(ref)
    return float(ref.sample(env.gen))


class OpRun:
    """Sequential execution of ``ops``; ``done(elapsed_s)`` fires at the end unless aborted."""

    def __init__(self, ops: tuple[Op, ...], env: OpEnv, done: Callable[[float], None]) -> None:
        self.ops, self.env, self.done = ops, env, done
        self.i = 0
        self.t0 = env.kernel.now
        self.aborted = False

    def start(self) -> OpRun:
        self._next()
        return self

    def abort(self) -> None:
        self.aborted = True

    def _next(self) -> None:
        if self.aborted:
            return
        if self.i >= len(self.ops):
            self.done(self.env.kernel.now - self.t0)
            return
        op = self.ops[self.i]
        self.i += 1
        _dispatch(op, self.env, self._next)


def _dispatch(op: Op, env: OpEnv, cont: Done) -> None:
    k = env.kernel
    if isinstance(op, DelayOp):
        k.after(value(op.dist, env), cont)
    elif isinstance(op, CpuOp):
        work = value(op.work, env) * (sum(env.sizes.get(a, 0.0) for a in op.per_mb) / MB if op.per_mb else 1.0)
        k.after(work / env.speed, cont)
    elif isinstance(op, TpmQuoteOp):
        if env.tpm is None:
            raise RuntimeError("tpm_quote on a host without a TPM")
        env.tpm.quote(cont)
    elif isinstance(op, PspOp):
        if env.psp is None:
            raise RuntimeError("psp op on a host without a PSP")
        env.psp.submit(value(op.dist, env), cont)
    elif isinstance(op, RpcOp):
        if env.rpc is None:
            raise RuntimeError("rpc op without an rpc hook")
        env.rpc(op, cont)
    elif isinstance(op, FetchOp):
        if env.fetch is None:
            raise RuntimeError("fetch op without a fetch hook")
        env.fetch(op.artifacts, cont)
    elif isinstance(op, DiskReadOp | DiskWriteOp):
        _disk(op, env, cont)
    else:  # pragma: no cover - the Op union is closed
        raise TypeError(f"unknown op {op!r}")


def _disk(op: DiskReadOp | DiskWriteOp, env: OpEnv, cont: Done) -> None:
    tier = env.tiers.get(op.what, "ssd")
    disk = env.disks.get(tier) or env.disks.get("ssd")
    nbytes = env.sizes.get(op.what, 0.0) * env.io_slowdown
    if disk is None or nbytes <= 0:
        env.kernel.after(0.0, cont)
    elif isinstance(op, DiskReadOp):
        disk.read(nbytes, cont)
    else:
        disk.write(nbytes, cont)


def split_path(ladder: LadderSpec, start: str) -> tuple[list[str], list[str]]:
    """Path from ``start`` to ready, split into a *prep* prefix (transitions that fetch artifacts; they overlap
    waiting for a slot, doc 08 §5) and the remainder that needs a slot."""
    keys = ladder.path(start)
    prep: list[str] = []
    for key in keys:
        if any(isinstance(op, FetchOp) for op in ladder.transitions[key]):
            prep.append(key)
        else:
            break
    return prep, keys[len(prep) :]


def ops_of(ladder: LadderSpec, keys: list[str]) -> tuple[Op, ...]:
    return tuple(op for key in keys for op in ladder.transitions[key])


def artifact_digests(fn: FunctionSpec, snapshot_class: str) -> dict[str, str]:
    """Content addresses (doc 02 §6): rootfs is shared per runtime; snapshots are per snapshot class."""
    return {
        "bundle": digest(fn.name, fn.version, "bundle"),
        "rootfs": digest(fn.runtime, "rootfs"),
        "snapshot": digest(fn.name, fn.version, "snapshot", snapshot_class),
    }


def artifact_sizes(fn: FunctionSpec, touched_frac: float) -> dict[str, float]:
    """Bytes per artifact; ``snapshot_touched`` is what a lazy restore reads."""
    return {
        "bundle": fn.bundle_mb * MB,
        "rootfs": fn.rootfs_mb * MB,
        "snapshot": fn.snapshot_mb * MB,
        "snapshot_touched": fn.snapshot_mb * touched_frac * MB,
    }


def cache_level(
    cache: WorkerCache, fn: FunctionSpec, ladder: LadderSpec, snapshot_class: str, digests: dict[str, str] | None = None
) -> tuple[str, str]:
    """``(level, tier)`` of ``fn`` on a worker: warm VM (ready level, ram) ▸ snapshot (L2) ▸ artifacts (L1) ▸ L0."""
    if cache.warm_count(fn.name) > 0:
        return ladder.ready, "ram"
    d = digests if digests is not None else artifact_digests(fn, snapshot_class)
    snap = cache.tier_of(d["snapshot"])
    if snap is not None and "L2" in ladder.persistent:
        return "L2", snap
    b, r = cache.tier_of(d["bundle"]), cache.tier_of(d["rootfs"])
    if b is not None and r is not None and "L1" in ladder.persistent:
        return "L1", "hdd" if "hdd" in (b, r) else "ssd"
    return ladder.levels[0], ""
