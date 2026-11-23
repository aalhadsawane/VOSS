"""Real-execution backend of the emulation testbed (doc 10 §4, plan V13).

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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from voss.core.ids import FnId
from voss.metrics.recorder import Recorder
from voss.metrics.schema import Table
from voss.runtime.workerlib.host import HostLocal
from voss.world.lifecycle import artifact_digests
from voss.world.workload import FunctionSpec

from tools.calibrate.fc import FcAssets
from tools.emu.isolation import Isolation
from tools.emu.kernel import RealtimeKernel
from tools.emu.tpm import Quoter
from tools.emu.vms import FnVm


@dataclass
class EmuConfig:
    firecracker: str
    kernel: str
    rootfs: str
    workdir: Path  # snapshots and scratch (the SSD tier under test)
    threads: int = 48
    grace_s: float = 2.0  # a freshly booted VM may wait this long for its consumer before it counts as idle
    claimed_ttl_s: float = 60.0  # a claimed VM nobody executes on (cancelled backup attempt) goes back to the idle pool
    reconcile_s: float = 0.5
    evict_rootfs: bool = True  # a boot reads its rootfs from disk, like the model's ``disk_read rootfs``
    evict_snapshots: bool = True  # a restore reads its snapshot from disk (the model's ``snapshot_touched`` read)
    min_free_gb: float = 20.0  # abort the run below this much free disk under ``workdir``
    isolation: Isolation | None = None  # per-worker cores, memory cgroup and network namespace (plan V13)
    tpm: Quoter | None = None  # real quotes at session start; None keeps the calibrated model


@dataclass
class Vm:
    vm: FnVm
    worker: int
    fn: str
    session: int
    state: str  # staged | idle | claimed | running | snapshotting
    since: float


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
        self.base_assets = FcAssets(cfg.firecracker, cfg.kernel, cfg.rootfs)
        self.pool = ThreadPoolExecutor(max_workers=cfg.threads, thread_name_prefix="emu")
        self.vms: dict[tuple[int, str], list[Vm]] = {}
        self.claimed: dict[tuple[int, str], deque[Vm]] = {}
        self.snaps: dict[tuple[int, str], tuple[Path, Path, float]] = {}
        self.hosts: dict[int, HostLocal] = {}
        self.seq = 0
        self.lock = threading.Lock()
        self.stats: dict[str, int] = {}
        self.failed: Exception | None = None
        self._seen: dict[int, tuple[bool, int]] = {}  # last (up, session) per worker, for the isolation layer
        cfg.workdir.mkdir(parents=True, exist_ok=True)

    # --- placement --------------------------------------------------------------------------------------------
    def assets_for(self, w: int) -> FcAssets:
        """The VMM command for worker ``w``: its network namespace and cores, and its memory cgroup (plan V13)."""
        if self.cfg.isolation is None:
            return self.base_assets
        return self.cfg.isolation.assets(w, self.base_assets)

    # --- registration -----------------------------------------------------------------------------------------
    def register(self, host: HostLocal, hb: Any) -> None:
        """Register one worker's host and its :class:`~tools.emu.host_backend.HostBackend`."""
        self.hosts[int(host.worker)] = host
        host.emu = hb

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
            return f"emu-w{worker}-{fn}-{self.seq}"[-90:]

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
        for w in sorted(self.hosts):
            host = self.hosts[w]
            state = (host.up, host.session)
            if self._seen.get(w) != state:
                self._seen[w] = state
                if self.cfg.isolation is not None:  # a session end kills the tree and removes the namespace
                    iso = self.cfg.isolation
                    self.pool.submit(iso.session, w, host.up, host.session)
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
