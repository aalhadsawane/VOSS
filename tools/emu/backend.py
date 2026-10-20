"""Real-execution backend of the emulation testbed (doc 10 §4, P9b).

The simulator's worker agent drives each invocation through the substrate's start-up ladder (ops) and then a modelled
execution. This backend claims the ops that stand for real work on a Firecracker host and does them for real:

=================  =========================================  ==================================
ladder step        simulated ops (replaced)                   real work
=================  =========================================  ==================================
``L1->L3``         disk_read rootfs, delay fc_boot, cpu init   spawn + boot a microVM, import fn
``L2->L3``         disk_read snapshot_touched, delay restore   load snapshot, answer a ping
``L3->L4``         delay dispatch                              claim an idle or staged microVM
``after_init``     delay snapshot_create, disk_write           pause, full snapshot, resume
execution          true_runtime timer                          run the function in the guest
=================  =========================================  ==================================

Everything else (network, key release, attestation, queueing, the TPM) stays a model on a wall-clock kernel. The cache
and warm pool remain logical (``WorkerCache``); real microVMs are reconciled to them: idle VMs beyond the logical warm
count are killed, a session end kills all VMs of the host. VMs are fungible per (worker, function).
"""

from __future__ import annotations

import shutil
import threading
from collections import deque
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from voss.core.ids import FnId
from voss.metrics.recorder import Recorder
from voss.metrics.schema import Table
from voss.runtime.workerlib.host import HostLocal
from voss.world.lifecycle import artifact_digests
from voss.world.substrate import CpuOp, DelayOp, DiskReadOp, DiskWriteOp, LadderSpec, Op
from voss.world.workload import FunctionSpec

from tools.calibrate.fc import FcAssets
from tools.emu.kernel import RealtimeKernel
from tools.emu.vms import ExecResult, FnVm, evict


@dataclass
class EmuConfig:
    firecracker: str
    kernel: str
    rootfs: str
    workdir: Path  # snapshots and scratch (the SSD tier under test)
    threads: int = 48
    grace_s: float = 2.0  # a freshly booted VM may wait this long for its consumer before it counts as idle
    claimed_ttl_s: float = 60.0  # a claimed VM nobody executes on (cancelled hedge) goes back to the idle pool
    reconcile_s: float = 0.5
    evict_rootfs: bool = True  # a boot reads its rootfs from disk, like the model's ``disk_read rootfs``
    evict_snapshots: bool = True  # a restore reads its snapshot from disk (the model's ``snapshot_touched`` read)
    min_free_gb: float = 20.0  # abort the run below this much free disk under ``workdir``


@dataclass
class Vm:
    vm: FnVm
    worker: int
    fn: str
    session: int
    state: str  # staged | idle | claimed | running | snapshotting
    since: float


NOOP, BOOT, RESTORE, CLAIM, SNAP = "noop", "boot", "restore", "claim", "snapshot"


def op_roles(lad: LadderSpec) -> dict[int, str]:
    """Role of every op object of the appliance ladder (by identity); anything else stays simulated."""
    t, roles = lad.transitions, {}

    def shape(ops: Sequence[Op], kinds: tuple[type, ...]) -> None:
        if len(ops) != len(kinds) or any(not isinstance(o, k) for o, k in zip(ops, kinds, strict=True)):
            raise ValueError(f"emulation supports the appliance ladder only (unexpected ops {ops!r})")

    shape(t["L1->L3"], (DiskReadOp, DelayOp, CpuOp))
    shape(t["L2->L3"], (DiskReadOp, DelayOp))
    shape(t["L3->L4"], (DelayOp,))
    shape(lad.after_init, (DelayOp, DiskWriteOp))
    for o, r in zip(t["L1->L3"], (NOOP, BOOT, NOOP), strict=True):
        roles[id(o)] = r
    for o, r in zip(t["L2->L3"], (NOOP, RESTORE), strict=True):
        roles[id(o)] = r
    roles[id(t["L3->L4"][0])] = CLAIM
    for o, r in zip(lad.after_init, (SNAP, NOOP), strict=True):
        roles[id(o)] = r
    return roles


class FcBackend:
    """Shared state of all emulated hosts: the thread pool, the real VMs and their reconciliation."""

    def __init__(
        self,
        k: RealtimeKernel,
        cfg: EmuConfig,
        rec: Recorder,
        catalog: dict[FnId, FunctionSpec],
        vm_factory: Callable[..., FnVm] = FnVm,
    ) -> None:
        self.k, self.cfg, self.rec, self.catalog = k, cfg, rec, catalog
        self.new_vm = vm_factory  # tests substitute a fake that sleeps instead of booting Firecracker
        self.assets = FcAssets(cfg.firecracker, cfg.kernel, cfg.rootfs)
        self.pool = ThreadPoolExecutor(max_workers=cfg.threads, thread_name_prefix="emu")
        self.vms: dict[tuple[int, str], list[Vm]] = {}
        self.claimed: dict[tuple[int, str], deque[Vm]] = {}
        self.snaps: dict[tuple[int, str], tuple[Path, Path, float]] = {}
        self.hosts: dict[int, HostLocal] = {}
        self.seq = 0
        self.lock = threading.Lock()
        self.stats: dict[str, int] = {}
        self.failed: Exception | None = None
        cfg.workdir.mkdir(parents=True, exist_ok=True)

    # --- registration -----------------------------------------------------------------------------------------
    def attach(self, host: HostLocal) -> HostBackend:
        self.hosts[int(host.worker)] = host
        hb = HostBackend(self, host)
        host.emu = hb
        return hb

    def start(self) -> None:
        self.k.after(self.cfg.reconcile_s, self._tick)

    # --- bookkeeping ------------------------------------------------------------------------------------------
    def count(self, what: str) -> None:
        self.stats[what] = self.stats.get(what, 0) + 1

    def log(self, kind: str, worker: int, value: float, fn: str, **extra: Any) -> None:
        self.rec.log(Table.EVENTS, t=self.k.now, kind=kind, worker=worker, value=value, reason=fn, **extra)

    def next_id(self, worker: int, fn: str) -> str:
        with self.lock:
            self.seq += 1
            return f"e01-w{worker}-{fn}-{self.seq}"[-90:]

    def submit(self, job: Callable[[], Any], then: Callable[[Any], None]) -> None:
        """Run ``job`` on a pool thread; ``then(result)`` runs on the kernel thread."""

        def runner() -> None:
            try:
                res = job()
            except Exception as e:  # a failed real action invalidates the run: stop it loudly
                self.failed = e
                self.k.post(self._raise, e)
                return
            self.k.post(then, res)

        self.pool.submit(runner)

    @staticmethod
    def _raise(e: Exception) -> None:
        raise RuntimeError(f"emulation backend failure: {e!r}") from e

    # --- reconciliation with the logical cache -----------------------------------------------------------------
    def _tick(self) -> None:
        self.reconcile()
        free_gb = shutil.disk_usage(self.cfg.workdir).free / 2**30
        if free_gb < self.cfg.min_free_gb:
            raise RuntimeError(f"free disk under {self.cfg.workdir} is {free_gb:.1f} GB: aborting (guard)")
        self.k.after(self.cfg.reconcile_s, self._tick)

    def reconcile(self) -> None:
        now = self.k.now
        for w, fn in list(self.vms):
            host = self.hosts[w]
            if not host.up:
                self._kill_where(w, fn, lambda _v: True)
                continue
            self._kill_stale(w, fn, host.session)
            idle = [
                v
                for v in self.vms.get((w, fn), [])
                if v.state == "idle" or (v.state == "staged" and now - v.since > self.cfg.grace_s)
            ]
            excess = len(idle) - host.cache.warm_count(fn)
            for v in sorted(idle, key=lambda v: v.since)[: max(0, excess)]:
                self._drop(v)
        for key, dq in list(self.claimed.items()):
            for v in [v for v in dq if now - v.since > self.cfg.claimed_ttl_s]:
                dq.remove(v)
                v.state, v.since = "idle", now
                self.vms.setdefault(key, []).append(v)
        self._prune_snapshots()

    def _kill_stale(self, w: int, fn: str, session: int) -> None:
        """Kill the VMs of an earlier session of ``w`` (a session end lost all RAM state)."""
        self._kill_where(w, fn, lambda v: v.session != session)

    def _kill_where(self, w: int, fn: str, pred: Callable[[Vm], bool]) -> None:
        for v in [v for v in self.vms.get((w, fn), []) if pred(v)]:
            self._drop(v)
        for v in [v for v in self.claimed.get((w, fn), deque()) if pred(v)]:
            self.claimed[(w, fn)].remove(v)
            v.vm.kill()

    def _drop(self, v: Vm) -> None:
        lst = self.vms.get((v.worker, v.fn), [])
        if v in lst:
            lst.remove(v)
        self.count("vm_killed")
        self.pool.submit(v.vm.kill)  # killing blocks briefly; keep the loop free

    def _prune_snapshots(self) -> None:
        for (w, fn), (state, mem, born) in list(self.snaps.items()):
            host, spec = self.hosts[w], self.catalog[FnId(fn)]
            dig = artifact_digests(spec, host.snapshot_class)["snapshot"]
            if host.cache.tier_of(dig) is None and self.k.now - born > 5.0:
                self.snaps.pop((w, fn))
                state.unlink(missing_ok=True)
                mem.unlink(missing_ok=True)

    def shutdown(self) -> None:
        for vs in list(self.vms.values()) + [list(d) for d in self.claimed.values()]:
            for v in list(vs):
                v.vm.kill()
        self.pool.shutdown(wait=True, cancel_futures=True)
        shutil.rmtree(self.cfg.workdir / "snap", ignore_errors=True)


class HostBackend:
    """``RealBackend`` for one worker host (what ``HostLocal.emu`` points to)."""

    def __init__(self, shared: FcBackend, host: HostLocal) -> None:
        self.s, self.host, self.w = shared, host, int(host.worker)
        self.roles = op_roles(host.profile.ladder)
        self.k = shared.k

    # --- RealBackend --------------------------------------------------------------------------------------------
    def handle_op(self, op: Any, env: Any, cont: Callable[[], None]) -> bool:
        role = self.roles.get(id(op))
        if role is None:
            return False
        if role == NOOP:
            self.k.after(0.0, cont)
        elif role == CLAIM:
            self._claim(env.fn, env.in_bytes, cont)
        elif role == BOOT:
            self._boot(env.fn, cont)
        elif role == RESTORE:
            self._restore(env.fn, cont)
        else:
            self._snapshot(env.fn, cont)
        return True

    def execute(
        self, worker: int, fn: FunctionSpec, in_bytes: int, timeout_s: float, done: Callable[[bool], None]
    ) -> None:
        vm = self._take_claimed(fn.name)
        session = self.host.session
        tag = f"{self.s.next_id(self.w, fn.name)}"
        size_kb = max(1, round(in_bytes / 1024))
        if vm is None:  # the model's dispatch step reserved nothing (should not happen): run on a fresh VM
            self.s.count("exec_without_claim")
        vm_ref: list[Vm | None] = [vm]

        def job() -> tuple[ExecResult, bool]:
            v = vm_ref[0]
            created = False
            if v is None:
                fv = self.s.new_vm(
                    self.s.assets, self.s.cfg.workdir / "fc", self.s.next_id(self.w, fn.name), fn.name, int(fn.mem_mb)
                )
                fv.boot(self.s.cfg.rootfs)
                v, created = Vm(fv, self.w, fn.name, session, "running", 0.0), True
                vm_ref[0] = v
            return v.vm.run(size_kb, tag, timeout_s), created

        def then(res: tuple[ExecResult, bool]) -> None:
            r, _created = res
            v = vm_ref[0]
            assert v is not None
            self.s.log("emu_exec", self.w, r.wall_s, fn.name, detail=f"handler={r.handler_s:.6f} total={r.total_s:.6f}")
            lost = self.host.session != session or not self.host.up
            if r.ok and not lost:
                v.state, v.since = "idle", self.k.now
                self.s.vms.setdefault((self.w, fn.name), []).append(v)
            else:
                self.s._drop(v) if v in self.s.vms.get((self.w, fn.name), []) else v.vm.kill()
            if not lost:
                done(r.ok)

        if vm is not None:
            vm.state = "running"
        self.s.submit(job, then)

    # --- actions ------------------------------------------------------------------------------------------------
    def _take_claimed(self, fn: str) -> Vm | None:
        dq = self.s.claimed.get((self.w, fn))
        return dq.popleft() if dq else None

    def _claim(self, fn: FunctionSpec, in_bytes: int, cont: Callable[[], None]) -> None:
        vs = self.s.vms.get((self.w, fn.name), [])
        pool = [v for v in vs if v.state == "staged"] or [v for v in vs if v.state == "idle"]
        if pool:
            v = max(pool, key=lambda v: v.since)
            vs.remove(v)
            v.state, v.since = "claimed", self.k.now
            self.s.claimed.setdefault((self.w, fn.name), deque()).append(v)
            v.vm.prep(max(1, round(in_bytes / 1024)))  # build the input while the request's data is still on its way
            self.k.after(0.0, cont)
            return
        self.s.count("claim_without_vm")

        def after_boot() -> None:
            self._claim(fn, in_bytes, cont)

        self._boot(fn, after_boot)

    def _boot(self, fn: FunctionSpec, cont: Callable[[], None]) -> None:
        session = self.host.session
        vid = self.s.next_id(self.w, fn.name)

        def job() -> tuple[FnVm, float]:
            if self.s.cfg.evict_rootfs:
                evict(self.s.cfg.rootfs)
            vm = self.s.new_vm(self.s.assets, self.s.cfg.workdir / "fc", vid, fn.name, int(fn.mem_mb))
            return vm, vm.boot(self.s.cfg.rootfs)

        self.s.submit(job, lambda res: self._staged(res, fn, session, "emu_boot", cont))

    def _staged(
        self, res: tuple[FnVm, float], fn: FunctionSpec, session: int, kind: str, cont: Callable[[], None]
    ) -> None:
        vm, secs = res
        self.s.log(kind, self.w, secs, fn.name)
        if self.host.session != session or not self.host.up:
            self.s.pool.submit(vm.kill)
            return  # the host lost its session meanwhile: nobody waits for this VM
        self.s.vms.setdefault((self.w, fn.name), []).append(Vm(vm, self.w, fn.name, session, "staged", self.k.now))
        cont()

    def _restore(self, fn: FunctionSpec, cont: Callable[[], None]) -> None:
        snap = self.s.snaps.get((self.w, fn.name))
        if snap is None:  # the cache says L2 but no real snapshot exists (create failed or pruned): boot instead
            self.s.count("restore_without_snapshot")
            self._boot(fn, cont)
            return
        state, mem, _ = snap
        session = self.host.session
        vid = self.s.next_id(self.w, fn.name)

        def job() -> tuple[FnVm, float]:
            if self.s.cfg.evict_snapshots:
                evict(state, mem)
            vm = self.s.new_vm(self.s.assets, self.s.cfg.workdir / "fc", vid, fn.name, int(fn.mem_mb))
            return vm, vm.restore(state, mem)

        self.s.submit(job, lambda res: self._staged(res, fn, session, "emu_restore", cont))

    def _snapshot(self, fn: FunctionSpec, cont: Callable[[], None]) -> None:
        vs = self.s.vms.get((self.w, fn.name), [])
        pool = [v for v in vs if v.state in ("idle", "staged")]
        if not pool or (self.w, fn.name) in self.s.snaps:
            self.s.count("snapshot_skipped")
            self.k.after(0.0, cont)
            return
        v = max(pool, key=lambda v: v.since)
        v.state = "snapshotting"
        d = self.s.cfg.workdir / "snap" / f"w{self.w}"
        state, mem = d / f"{fn.name}.state", d / f"{fn.name}.mem"

        def job() -> float:
            d.mkdir(parents=True, exist_ok=True)
            secs = v.vm.snapshot(state, mem)
            if self.s.cfg.evict_snapshots:
                evict(state, mem)
            return secs

        def then(secs: float) -> None:
            self.s.log("emu_snapshot", self.w, secs, fn.name)
            if v in self.s.vms.get((self.w, fn.name), []):
                v.state = "idle"
                self.s.snaps[(self.w, fn.name)] = (state, mem, self.k.now)
            cont()

        self.s.submit(job, then)
