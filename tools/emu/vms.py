"""One real Firecracker microVM running one function (doc 10 §4, P9b): boot, snapshot, restore, execute.

Built on ``tools.calibrate.fc.FcVm`` (the harness that measured the calibration bundle), so the emulation and the
calibration use the same code path. Every method blocks and is meant to run on a worker thread.
"""

from __future__ import annotations

import os
import queue
import re
import time
from dataclasses import dataclass
from pathlib import Path

from tools.calibrate.fc import MARK, FcAssets, FcVm, boot_args

EXEC = re.compile(r"(\S+) (\d+) (\S+) ([0-9.eE+-]+) ([0-9.eE+-]+)")


def evict(*paths: Path | str) -> None:
    """Drop these files from the page cache (clean pages only; no root, no effect on other files)."""
    for p in paths:
        try:
            fd = os.open(str(p), os.O_RDONLY)
        except OSError:
            continue
        try:
            getattr(os, "posix_fadvise", lambda *_a: None)(fd, 0, 0, getattr(os, "POSIX_FADV_DONTNEED", 4))
        finally:
            os.close(fd)


@dataclass
class ExecResult:
    ok: bool
    wall_s: float  # host time from sending RUN to the guest's answer
    handler_s: float  # guest-measured handler time
    total_s: float  # guest-measured, including input generation


class FnVm:
    """A microVM whose guest imported one function and waits for ``RUN <size_kb> <tag>`` on its console."""

    def __init__(self, assets: FcAssets, workdir: Path, vm_id: str, fn: str, mem_mb: int) -> None:
        self.fn, self.mem_mb = fn, mem_mb
        self.fc = FcVm(assets, workdir, vm_id)
        self.assets = assets

    # --- life cycle ---------------------------------------------------------------------------------------
    def boot(self, rootfs: str, timeout: float = 120.0) -> float:
        """Spawn, configure, start, wait until the function is imported; returns wall seconds."""
        t0 = time.monotonic()
        self.fc.spawn()
        self.fc.configure(self.mem_mb, 1, boot_args("fn", f"voss.fn={self.fn}"), rootfs)
        self.fc.start()
        self.fc.wait("MARK", "ready", timeout=timeout)
        return time.monotonic() - t0

    def snapshot(self, state: Path, mem: Path) -> float:
        """Pause, write a full snapshot, resume; returns wall seconds (the VM keeps running afterwards)."""
        t0 = time.monotonic()
        try:
            self.fc.send("PING 0 quiesce")  # snapshot only a guest that has answered everything sent to it
            self.fc.wait("ACK", "quiesce", timeout=30.0)
            self.fc.pause()
            self.fc.snapshot(state, mem)
            self.fc.api("PATCH", "/vm", {"state": "Resumed"})
        except (OSError, RuntimeError, TimeoutError):  # killed while snapshotting (session end): no snapshot
            return -1.0
        return time.monotonic() - t0

    def restore(self, state: Path, mem: Path, timeout: float = 60.0) -> float:
        """Spawn a fresh VMM, load the snapshot and wait for the guest to answer a ping (includes first page
        faults, like the ``fc_restore`` calibration probe); returns wall seconds."""
        t0 = time.monotonic()
        self.fc.spawn()
        try:
            self.fc.load(state, mem)
            self.fc.send("PING 0 ping")
            self.fc.wait("ACK", "ping", timeout=timeout)
        except (RuntimeError, TimeoutError, OSError):  # Firecracker rejected or could not resume the snapshot
            self.kill()
            return -1.0
        return time.monotonic() - t0

    def kill(self) -> None:
        self.fc.kill()

    @property
    def alive(self) -> bool:
        return self.fc.proc is not None and self.fc.proc.poll() is None

    # --- execution ----------------------------------------------------------------------------------------
    def prep(self, size_kb: int) -> None:
        """Ask the guest to build the input now (non-blocking); the request that follows then runs on a ready input."""
        try:
            self.fc.send(f"PREP {size_kb} p")
        except OSError:  # the VM was killed meanwhile (session end): the request fails later, as it would on real loss
            pass

    def run(self, size_kb: int, tag: str, timeout_s: float) -> ExecResult:
        """Send one invocation and wait for its ``VOSS_EXEC`` line; a timeout kills the VM."""
        try:
            t0 = self.fc.send(f"RUN {size_kb} {tag}")
        except OSError:
            self.kill()
            return ExecResult(False, 0.0, 0.0, 0.0)
        deadline = t0 + timeout_s
        while True:
            left = deadline - time.monotonic()
            if left <= 0 or not self.alive:
                self.kill()
                return ExecResult(False, time.monotonic() - t0, 0.0, 0.0)
            try:
                t, line = self.fc.lines.get(timeout=min(left, 0.5))
            except queue.Empty:
                continue
            m = MARK.search(line)
            if m is None or m.group(1) != "EXEC":
                if m is not None and m.group(1) == "ERR":
                    self.kill()
                    return ExecResult(False, t - t0, 0.0, 0.0)
                continue
            e = EXEC.match(m.group(2))
            if e is not None and e.group(3) == tag:
                return ExecResult(True, t - t0, float(e.group(4)), float(e.group(5)))
