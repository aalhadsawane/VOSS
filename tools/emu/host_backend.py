"""One emulated worker's real work (plan V13, handoff Part E; doc 10 §4).

``HostBackend`` is the ``RealBackend`` a worker host points to: it claims the start-up ladder's ops and performs them
on real Firecracker sandboxes placed in that worker's namespace, cores and memory cgroup, and it runs the
invocations. It never calls another worker: everything it shares with the rest of the host (the VM pool, the counters,
the kernel) is passed in by :class:`~tools.emu.backend.FcBackend`.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from voss.runtime.workerlib.host import HostLocal
from voss.world.workload import FunctionSpec

from tools.emu.backend import FcBackend, Vm
from tools.emu.roles import BOOT, CLAIM, NOOP, RESTORE, op_roles
from tools.emu.vms import ExecResult, FnVm, evict


class HostBackend:
    """``RealBackend`` for one worker host (what ``HostLocal.emu`` points to)."""

    def __init__(self, shared: FcBackend, host: HostLocal) -> None:
        self.s, self.host, self.w = shared, host, int(host.worker)
        shared.register(host, self)
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
                if self.s.cfg.isolation is not None:
                    self.s.cfg.isolation.setup(self.w)
                fv = self.s.new_vm(
                    self.s.assets_for(self.w),
                    self.s.cfg.workdir / "fc",
                    self.s.next_id(self.w, fn.name),
                    fn.name,
                    int(fn.mem_mb),
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

        def job() -> tuple[FnVm | None, float]:
            if self.s.cfg.evict_rootfs:
                evict(self.s.cfg.rootfs)
            for attempt in (1, 2):  # a VMM that dies while being configured is retried once, like a supervisor would
                wd = self.s.cfg.workdir / "fc"
                vm = self.s.new_vm(
                    self.s.assets_for(self.w),
                    wd,
                    f"{self.s.next_id(self.w, fn.name)}-{attempt}",
                    fn.name,
                    int(fn.mem_mb),
                )
                try:
                    if self.s.cfg.isolation is not None:  # the namespace may have gone with the last session
                        self.s.cfg.isolation.setup(self.w)
                    return vm, vm.boot(self.s.cfg.rootfs)
                except (OSError, RuntimeError, TimeoutError):
                    vm.kill()
                    self.s.count("boot_retry")
                    if self.host.session != session or not self.host.up:
                        return None, -1.0  # the session ended under the boot: nobody waits for this VM
                    if attempt == 2:
                        raise
            raise AssertionError("unreachable")

        self.s.submit(job, lambda res: self._staged(res, fn, session, "emu_boot", cont))

    def _staged(
        self, res: tuple[FnVm | None, float], fn: FunctionSpec, session: int, kind: str, cont: Callable[[], None]
    ) -> None:
        vm, secs = res
        if vm is None:  # the boot was lost with its session
            return
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

        def job() -> tuple[FnVm | None, float]:
            if self.s.cfg.evict_snapshots:
                evict(state, mem)
            try:
                if self.s.cfg.isolation is not None:
                    self.s.cfg.isolation.setup(self.w)
                vm = self.s.new_vm(self.s.assets_for(self.w), self.s.cfg.workdir / "fc", vid, fn.name, int(fn.mem_mb))
                return vm, vm.restore(state, mem)
            except (OSError, RuntimeError) as e:
                if self.host.session != session or not self.host.up:
                    return None, -1.0  # the session ended under the restore
                raise RuntimeError(f"restore of {fn.name} on worker {self.w} failed: {e!r}") from e

        def then(res: tuple[FnVm | None, float]) -> None:
            if res[0] is None:
                return  # lost with its session
            if res[1] >= 0:
                self._staged(res, fn, session, "emu_restore", cont)
                return
            self.s.count("restore_failed")  # a real system would discard the snapshot and boot
            self.s.snaps.pop((self.w, fn.name), None)
            state.unlink(missing_ok=True)
            mem.unlink(missing_ok=True)
            self._boot(fn, cont)

        self.s.submit(job, then)

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
            if secs < 0:  # the VM died under the snapshot
                self.s.count("snapshot_lost")
                state.unlink(missing_ok=True)
                mem.unlink(missing_ok=True)
                cont()
                return
            self.s.log("emu_snapshot", self.w, secs, fn.name)
            if v in self.s.vms.get((self.w, fn.name), []):
                v.state = "idle"
                self.s.snaps[(self.w, fn.name)] = (state, mem, self.k.now)
            cont()

        self.s.submit(job, then)
