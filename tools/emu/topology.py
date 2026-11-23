"""CPU topology and the worker layout of the emulation testbed (plan V13, handoff Part E).

One emulated worker gets its own physical core or cores, never shared with another worker, and only cores of one kind
are used on a hybrid CPU. The layout also carries what the isolation layer needs: the worker's memory limit, its
namespace name and its injected link, taken from the scenario's worker table so that the emulator and the simulator
give a worker the same access link. Everything here is pure: :class:`~tools.emu.isolation.Isolation` runs the commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

KIND_PERFORMANCE, KIND_EFFICIENCY, KIND_ANY = "P", "E", "any"
CORE_TYPE = {"1": KIND_PERFORMANCE, "2": KIND_EFFICIENCY}  # sysfs topology/core_type (Linux >= 5.16)
NS_PREFIX = "voss-emu-w"
SUBNET = "10.213"  # per-worker /30 in the root namespace: 10.213.0.(4w+1) worker, .(4w+2) root side
KINDS = {"P": KIND_PERFORMANCE, "E": KIND_EFFICIENCY, "any": KIND_ANY}


@dataclass(frozen=True)
class Cpu:
    """One hardware thread."""

    cpu: int
    core: int
    package: int
    kind: str


@dataclass(frozen=True)
class Core:
    """One physical core and the hardware threads it exposes."""

    package: int
    core: int
    cpus: tuple[int, ...]
    kind: str

    @property
    def label(self) -> str:
        return f"{self.kind}{self.package}.{self.core}"


@dataclass(frozen=True)
class Topology:
    cpus: tuple[Cpu, ...]

    def cores(self, kind: str = KIND_ANY) -> tuple[Core, ...]:
        """Physical cores of one kind, sorted by (package, core); ``any`` means every core."""
        groups: dict[tuple[int, int], list[Cpu]] = {}
        for c in self.cpus:
            groups.setdefault((c.package, c.core), []).append(c)
        return tuple(
            Core(pkg, core, tuple(sorted(c.cpu for c in cs)), cs[0].kind)
            for (pkg, core), cs in sorted(groups.items())
            if kind == KIND_ANY or cs[0].kind == kind
        )

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted({c.kind for c in self.cpus}))


def cpulist(text: str) -> set[int]:
    """Parse a kernel cpu list ("0-3,8,10-11") into cpu numbers."""
    out: set[int] = set()
    for part in text.strip().split(","):
        if not part:
            continue
        lo, _, hi = part.partition("-")
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def read_topology(root: Path = Path("/sys/devices/system/cpu")) -> Topology:
    """Cores and their kind from sysfs.

    The kind comes from ``topology/core_type`` (1 = performance, 2 = efficiency) and, when the kernel does not expose
    it, from the hybrid PMU cpumasks ``/sys/devices/cpu_core/cpus`` and ``cpu_atom/cpus``. A machine where neither
    exists is treated as homogeneous (kind ``any``), which is what it is as far as the kernel reports.
    """
    perf = cpulist(_read(Path("/sys/devices/cpu_core/cpus")))
    eff = cpulist(_read(Path("/sys/devices/cpu_atom/cpus")))
    cpus = []
    for d in sorted(root.glob("cpu[0-9]*"), key=lambda p: int(p.name[3:])):
        n = int(d.name[3:])
        core = int(_read(d / "topology" / "core_id") or n)
        pkg = int(_read(d / "topology" / "physical_package_id") or 0)
        kind = CORE_TYPE.get(_read(d / "topology" / "core_type"), "")
        if not kind:
            kind = KIND_PERFORMANCE if n in perf else KIND_EFFICIENCY if n in eff else KIND_ANY
        cpus.append(Cpu(n, core, pkg, kind))
    if not cpus:
        raise RuntimeError(f"{root}: no cpu[0-9]* directories; not a Linux sysfs CPU tree")
    return Topology(tuple(cpus))


@dataclass(frozen=True)
class Slot:
    """One emulated worker: its cores, its memory limit, its namespace and its injected link."""

    index: int
    cores: tuple[Core, ...]
    mem_mb: int
    delay_ms: float
    up_mbps: float
    down_mbps: float
    ns: str = ""

    @property
    def cpus(self) -> tuple[int, ...]:
        return tuple(sorted(c for core in self.cores for c in core.cpus))

    @property
    def cpus_arg(self) -> str:
        return ",".join(str(c) for c in self.cpus)

    @property
    def mem_bytes(self) -> int:
        return self.mem_mb * 2**20

    @property
    def addr(self) -> str:
        """Worker side of the /30 pair."""
        return f"{SUBNET}.{self.index // 64}.{(self.index % 64) * 4 + 1}"

    @property
    def peer(self) -> str:
        """Root side of the /30 pair (the address the self-check pings)."""
        return f"{SUBNET}.{self.index // 64}.{(self.index % 64) * 4 + 2}"


@dataclass(frozen=True)
class Layout:
    """Where every emulated worker and the provider-side processes run."""

    kind: str
    slots: tuple[Slot, ...]
    infra: tuple[Core, ...]

    @property
    def infra_cpus(self) -> tuple[int, ...]:
        return tuple(sorted(c for core in self.infra for c in core.cpus))

    def slot(self, w: int) -> Slot:
        return self.slots[w]

    def summary(self) -> list[dict[str, Any]]:
        """JSON-able description of the layout (written to ``emu.json`` and printed by ``--dry-run``)."""
        return [
            {
                "worker": s.index,
                "kind": self.kind,
                "cores": [c.label for c in s.cores],
                "cpus": list(s.cpus),
                "mem_mb": s.mem_mb,
                "netns": s.ns,
                "netem": {"delay_ms": s.delay_ms, "up_mbps": s.up_mbps, "down_mbps": s.down_mbps},
            }
            for s in self.slots
        ]


def plan(
    topo: Topology,
    workers: int,
    *,
    kind: str = KIND_PERFORMANCE,
    cores_per_worker: int = 1,
    mem_mb: int = 4096,
    infra_cores: int = 2,
    last_mile_s: list[float] | tuple[float, ...] | None = None,
    up_bps: list[float] | tuple[float, ...] | None = None,
    down_bps: list[float] | tuple[float, ...] | None = None,
) -> Layout:
    """Assign cores, memory limits and link parameters to ``workers`` workers and to the provider roles.

    Cores of one kind only, never shared: worker ``i`` gets ``cores_per_worker`` whole physical cores and the
    provider roles (scheduler, routers, verifier, key services, the coordinator) get the next ``infra_cores``. The
    link parameters come from the scenario's worker table, so the injected delay and bandwidth are the ones the
    simulator gives that worker; omitted, a typical residential link is used.
    """
    if kind not in KINDS.values():
        raise ValueError(f"unknown core kind {kind!r}")
    cores = list(topo.cores(kind))
    need = workers * cores_per_worker + infra_cores
    if need > len(cores):
        raise ValueError(
            f"{workers} workers x {cores_per_worker} core(s) + {infra_cores} provider core(s) need {need} {kind} "
            f"core(s); this machine has {len(cores)} {kind} core(s) of kinds {topo.kinds()}. Lower emu.workers or "
            f"emu.cores_per_worker, or set emu.kind."
        )
    lm = list(last_mile_s if last_mile_s is not None else [0.010] * workers)
    up = list(up_bps if up_bps is not None else [30e6] * workers)
    down = list(down_bps if down_bps is not None else [100e6] * workers)
    if not len(lm) == len(up) == len(down) == workers:
        raise ValueError(f"link tables must have {workers} entries, got {len(lm)}/{len(up)}/{len(down)}")
    slots = tuple(
        Slot(
            index=i,
            cores=tuple(cores[i * cores_per_worker : (i + 1) * cores_per_worker]),
            mem_mb=mem_mb,
            delay_ms=1000.0 * lm[i],
            up_mbps=up[i] / 1e6,
            down_mbps=down[i] / 1e6,
            ns=f"{NS_PREFIX}{i}",
        )
        for i in range(workers)
    )
    return Layout(kind=kind, slots=slots, infra=tuple(cores[workers * cores_per_worker : need]))
