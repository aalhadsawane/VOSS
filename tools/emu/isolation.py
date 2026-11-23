"""Multi-worker isolation layer of the emulation testbed (plan V13, handoff Part E).

One emulated worker is a set of processes (its Firecracker sandboxes) that (a) may run only on its own physical core
or cores, (b) lives under its own cgroup v2 memory limit, and (c) lives in its own network namespace, where the
scenario worker's own access link is injected with ``tc netem``: the one-way last-mile delay and the up/down
bandwidth of ``voss.world.network``. No physical core is shared between workers, and only cores of one kind are used
on a hybrid CPU (the handoff's rule).

Everything that needs root is expressed as an argv list first (:func:`setup_commands`, :func:`teardown_commands`), so
the plan and the exact commands are unit-testable without root, ``ip``, ``tc`` or cgroups; :class:`Isolation` runs
them through the calibration harness's :class:`~tools.calibrate.common.Shell`, which logs every command and supports
``dry_run``.

What the namespace does and does not do: the emulation keeps the simulator's network model for every actor message
(the same code path, so the two sides are comparable), so the injected link shapes traffic that the worker's own
processes generate and is verified by :meth:`Isolation.self_check`; it is not added on top of the modelled delays,
which would double-count them. ``docs/validation/emulation-runbook.md`` states this to the reader.
"""

from __future__ import annotations

import contextlib
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.calibrate.common import Shell
from tools.calibrate.fc import FcAssets
from tools.emu.topology import NS_PREFIX, Layout, Slot

CGROUP_ROOT = Path("/sys/fs/cgroup/voss-emu")


# --- commands ---------------------------------------------------------------------------------------------------
def netem_argv(dev: str, delay_ms: float, rate_mbps: float) -> list[str]:
    """One ``tc`` command that injects ``delay_ms`` one way and a ``rate_mbps`` ceiling on ``dev``'s egress."""
    return [
        "tc",
        "qdisc",
        "add",
        "dev",
        dev,
        "root",
        "netem",
        "delay",
        f"{delay_ms:.3f}ms",
        "rate",
        f"{rate_mbps:.3f}mbit",
        "limit",
        "10000",
    ]


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def _sh(text: str) -> list[str]:
    return ["sh", "-c", text]


def setup_commands(s: Slot, cgroup_root: Path = CGROUP_ROOT) -> list[list[str]]:
    """Every command that creates one worker's namespace, link and memory limit."""
    dev, peer = f"{s.ns}-v", f"{s.ns}-r"
    return [
        ["mkdir", "-p", str(cgroup_root)],
        _sh(f"echo '+memory' > {cgroup_root}/cgroup.subtree_control"),
        ["mkdir", "-p", str(cgroup_root / s.ns)],
        _sh(f"echo {s.mem_bytes} > {cgroup_root / s.ns}/memory.max"),
        _sh(f"echo 0 > {cgroup_root / s.ns}/memory.swap.max"),
        _sh(f"echo 1 > {cgroup_root / s.ns}/memory.oom.group"),
        ["ip", "netns", "add", s.ns],
        ["ip", "link", "add", dev, "type", "veth", "peer", "name", peer],
        ["ip", "link", "set", dev, "netns", s.ns],
        ["ip", "addr", "add", f"{s.peer}/30", "dev", peer],
        ["ip", "link", "set", peer, "up"],
        ["ip", "netns", "exec", s.ns, "ip", "addr", "add", f"{s.addr}/30", "dev", dev],
        ["ip", "netns", "exec", s.ns, "ip", "link", "set", dev, "up"],
        ["ip", "netns", "exec", s.ns, "ip", "link", "set", "lo", "up"],
        netem_argv(peer, s.delay_ms, s.down_mbps),  # what arrives at the worker
        ["ip", "netns", "exec", s.ns, *netem_argv(dev, s.delay_ms, s.up_mbps)],  # what leaves the worker
    ]


def teardown_commands(s: Slot, cgroup_root: Path = CGROUP_ROOT) -> list[list[str]]:
    """Kill the worker's process tree (cgroup v2 ``cgroup.kill``) and remove its namespace and link."""
    kill = cgroup_root / s.ns / "cgroup.kill"
    return [
        _sh(f"test -e {kill} && echo 1 > {kill} || true"),
        ["ip", "netns", "del", s.ns],
        ["ip", "link", "del", f"{s.ns}-r"],
    ]


# --- execution --------------------------------------------------------------------------------------------------
@dataclass
class Isolation:
    """Runs the plan's commands and hands out per-worker :class:`FcAssets` (namespace, cores, memory cgroup)."""

    layout: Layout
    sh: Shell = field(default_factory=Shell)
    cgroup_root: Path = CGROUP_ROOT
    state: dict[int, tuple[bool, int]] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    _locks: dict[int, threading.Lock] = field(default_factory=dict)
    _up: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        self._locks = {s.index: threading.Lock() for s in self.layout.slots}

    # --- life cycle --------------------------------------------------------------------------------------------
    def setup(self, w: int) -> None:
        """Create worker ``w``'s namespace, link and memory limit (no-op when already up)."""
        with self._locks[w]:
            if w in self._up:
                return
            for argv in setup_commands(self.layout.slot(w), self.cgroup_root):
                self._run(argv)
            self._up.add(w)

    def teardown(self, w: int) -> None:
        """Kill worker ``w``'s process tree and remove its namespace (session end, handoff Part E)."""
        with self._locks[w]:
            if w not in self._up:
                return
            for argv in teardown_commands(self.layout.slot(w), self.cgroup_root):
                self._run(argv, check=False)
            self._up.discard(w)

    def session(self, w: int, up: bool, session: int) -> None:
        """Follow a worker's session: a new session starts from a clean namespace, an end removes it."""
        prev = self.state.get(w)
        if prev == (up, session):
            return
        self.state[w] = (up, session)
        if prev is not None and (prev[1] != session or not up):
            self.teardown(w)
        if up:
            self.setup(w)

    def close(self) -> None:
        """Remove every worker namespace and the cgroup tree (end of run)."""
        for s in self.layout.slots:
            self.teardown(s.index)
        if self.sh.dry_run:
            return
        for path in sorted(self.cgroup_root.glob(f"{NS_PREFIX}*")):
            with contextlib.suppress(OSError):
                path.rmdir()
        with contextlib.suppress(OSError):
            self.cgroup_root.rmdir()

    # --- placement ---------------------------------------------------------------------------------------------
    def assets(self, w: int, base: FcAssets) -> FcAssets:
        """``base`` with the worker's namespace and core pinning in front of the VMM and its memory cgroup."""
        s = self.layout.slot(w)
        return FcAssets(
            firecracker=base.firecracker,
            kernel=base.kernel,
            rootfs=base.rootfs,
            jailer=base.jailer,
            chroot_base=base.chroot_base,
            prefix=("ip", "netns", "exec", s.ns, "taskset", "-c", s.cpus_arg),
            cgroup_procs=str(self.cgroup_root / s.ns / "cgroup.procs"),
        )

    def pin_infra(self) -> None:
        """Pin every thread of the coordinator (provider roles and thread pool) to the provider cores."""
        set_affinity = getattr(os, "sched_setaffinity", None)
        if self.sh.dry_run or not self.layout.infra_cpus or set_affinity is None:
            return
        for task in Path("/proc/self/task").iterdir():
            try:
                set_affinity(int(task.name), set(self.layout.infra_cpus))
            except OSError:  # a thread that just exited
                continue

    # --- observations ------------------------------------------------------------------------------------------
    def self_check(self, w: int) -> float:
        """Round-trip time in ms inside the worker's namespace (about twice ``delay_ms`` when the link is injected)."""
        s = self.layout.slot(w)
        argv = ["ip", "netns", "exec", s.ns, "ping", "-c", "3", "-i", "0.2", "-W", "2", s.peer]
        c = self.sh.run(argv, check=False)
        m = re.search(r"= [\d.]+/([\d.]+)/", c.out or "")
        return float(m.group(1)) if m else float("nan")

    def oom(self, w: int) -> tuple[int, int]:
        """``(oom, oom_kill)`` events of the worker's cgroup; a non-zero ``oom_kill`` means it hit its limit."""
        path = self.cgroup_root / self.layout.slot(w).ns / "memory.events"
        vals = {}
        for line in _read(path).splitlines():
            parts = line.split()
            if len(parts) == 2:
                vals[parts[0]] = int(parts[1])
        return vals.get("oom", 0), vals.get("oom_kill", 0)

    def snapshot_stats(self) -> dict[str, Any]:
        """Per-worker self-check and memory-limit counters, read while the namespaces still exist (``emu.json``)."""
        return {
            "self_check_ms": {str(s.index): self.self_check(s.index) for s in self.layout.slots},
            "oom": {str(s.index): list(self.oom(s.index)) for s in self.layout.slots},
        }

    def _run(self, argv: list[str], check: bool = True) -> None:
        self.log.append(" ".join(argv))
        self.sh.run(argv, check=check, timeout=120.0)
