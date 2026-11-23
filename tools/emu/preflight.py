"""Preflight of the V13 emulation host (plan V13, handoff Part E step 1): every capability the run needs, with the
command that fixes it.

``tools.emu.run`` calls :func:`check` before it creates anything and refuses to start on a failed check, so a missing
capability is a one-line message instead of a half-started run of microVMs. ``python -m tools.emu.preflight`` prints
the same report for a human (``bash tools/emu/preflight.sh`` is the read-only shell audit and stays the first step).

Each check returns a :class:`Problem`; ``fail`` stops the run, ``warn`` is recorded and printed.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tools.emu import scenario as spec_mod
from tools.emu.isolation import CGROUP_ROOT
from tools.emu.scenario import EmuScenario
from tools.emu.topology import KINDS, read_topology
from tools.emu.topology import plan as host_plan

Level = Literal["fail", "warn"]


@dataclass(frozen=True)
class Problem:
    level: Level
    what: str
    fix: str

    def line(self) -> str:
        return f"[{self.level.upper():4}] {self.what}\n         fix: {self.fix}"


def _run(argv: list[str], timeout: float = 20.0) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, repr(e)
    return p.returncode, (p.stdout or p.stderr).strip()


def _cgroup_ok() -> tuple[bool, str]:
    controllers = Path("/sys/fs/cgroup/cgroup.controllers")
    if not controllers.exists():
        return False, "cgroup v2 is not mounted at /sys/fs/cgroup (no cgroup.controllers)"
    if "memory" not in controllers.read_text().split():
        return False, "the memory controller is not available in /sys/fs/cgroup/cgroup.controllers"
    if not os.access("/sys/fs/cgroup", os.W_OK):
        return False, "the cgroup tree is not writable by this user"
    return True, ""


def check(
    spec: EmuScenario,
    *,
    isolation: bool = True,
    tpm: bool | None = None,
    assets: Path | None = None,
    workdir: Path | None = None,
) -> list[Problem]:
    """Capabilities for one run; ``isolation=False`` checks a smoke run without namespaces or cgroups."""
    out: list[Problem] = []
    want_tpm = spec.emu.tpm if tpm is None else tpm
    if platform.system() != "Linux":
        out.append(Problem("fail", f"this is {platform.system()}, not Linux", "run the emulation on the node02 host"))
        return out
    if platform.machine() not in ("x86_64", "aarch64"):
        out.append(Problem("fail", f"architecture {platform.machine()}", "Firecracker needs x86_64 or aarch64"))
    virt = _run(["systemd-detect-virt"])[1] if shutil.which("systemd-detect-virt") else "none"
    if virt not in ("none", ""):
        out.append(Problem("fail", f"running inside {virt}", "the emulation must run on bare metal (handoff §2)"))
    out += _kvm()
    out += _tools(want_tpm)
    if isolation:
        out += _isolation_caps()
        out += _layout(spec)
    out += _tpm(want_tpm)
    out += _assets(spec, assets)
    out += _disk(workdir or Path(spec.emu.workdir).expanduser())
    load = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    if load > 1.0:
        out.append(Problem("warn", f"load average is {load:.2f}", "stop other work: timings need a quiet machine"))
    return out


def _kvm() -> list[Problem]:
    if not Path("/dev/kvm").exists():
        return [Problem("fail", "/dev/kvm is missing", "enable VT-x/AMD-V in the firmware; a VM host needs nested KVM")]
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        return [Problem("fail", "/dev/kvm is not readable by this user", "run as root or join the kvm group")]
    return []


def _tools(want_tpm: bool) -> list[Problem]:
    need = ["ip", "tc", "taskset", "ping", "modprobe"]
    need += ["tpm2_quote", "tpm2_createek", "tpm2_createak"] if want_tpm else []
    out = [
        Problem("fail", f"{t} is not installed", f"install {t} (iproute2, util-linux, iputils, kmod; tpm2-tools)")
        for t in need
        if not shutil.which(t)
    ]
    if shutil.which("modprobe"):
        rc, _ = _run(["modprobe", "-n", "sch_netem"])
        if rc != 0:
            out.append(Problem("fail", "the sch_netem module is not available", "install linux-modules-extra"))
    return out


def _isolation_caps() -> list[Problem]:
    out = []
    if os.geteuid() != 0:
        out.append(Problem("fail", "not root", "run with sudo: netns, tc and cgroups need it"))
    rc, text = _run(["ip", "netns", "list"])
    if rc != 0:
        out.append(Problem("fail", f"`ip netns list` failed: {text[:200]}", "install iproute2 and run as root"))
    rc, text = _run(["tc", "qdisc", "show", "dev", "lo"])
    if rc != 0:
        out.append(Problem("fail", f"`tc qdisc show` failed: {text[:200]}", "install iproute2 and run as root"))
    ok, why = _cgroup_ok()
    if not ok:
        out.append(
            Problem(
                "fail",
                why,
                f"mount a cgroup v2 hierarchy and make {CGROUP_ROOT.parent} writable (systemd does this on Ubuntu)",
            )
        )
    if not Path("/proc/self/task").is_dir():
        out.append(Problem("fail", "no /proc/self/task", "the coordinator cannot be pinned to the provider cores"))
    return out


def _layout(spec: EmuScenario) -> list[Problem]:
    """Cores of one kind for every worker plus the provider roles, and nothing shared (handoff Part E)."""
    try:
        topo = read_topology()
    except RuntimeError as e:
        return [Problem("fail", str(e), "run on the node02 host")]
    try:
        host_plan(
            topo,
            spec.emu.workers,
            kind=KINDS[spec.emu.kind],
            cores_per_worker=spec.emu.cores_per_worker,
            mem_mb=spec.emu.mem_mb_per_worker,
            infra_cores=spec.emu.infra_cores,
        )
    except ValueError as e:
        return [Problem("fail", str(e), "change emu.workers / emu.cores_per_worker / emu.kind in the scenario")]
    return []


def _tpm(want_tpm: bool) -> list[Problem]:
    if not want_tpm:
        return [Problem("warn", "no real TPM quote (emu.tpm is false)", "a V13 run needs emu.tpm: true")]
    if Path("/dev/tpmrm0").exists() or Path("/dev/tpm0").exists():
        return []
    return [Problem("fail", "no TPM device (/dev/tpmrm0)", "enable the firmware TPM (Intel PTT) in the firmware")]


def _assets(spec: EmuScenario, assets: Path | None) -> list[Problem]:
    root = assets or Path(spec.emu.assets).expanduser()
    out = []
    for name in ("firecracker", spec.emu.rootfs):
        if not (root / name).exists():
            out.append(Problem("fail", f"{root / name} is missing", "run tools/calibrate/guest/fetch_assets.sh"))
    if not os.access(root / "firecracker", os.X_OK) and (root / "firecracker").exists():
        out.append(Problem("fail", f"{root / 'firecracker'} is not executable", "chmod +x it"))
    if not (root / "vmlinux").exists():
        out.append(Problem("fail", f"{root / 'vmlinux'} is missing", "run tools/calibrate/guest/fetch_assets.sh"))
    return out


def _disk(workdir: Path) -> list[Problem]:
    probe = workdir if workdir.exists() else workdir.parent
    try:
        free_gb = shutil.disk_usage(probe).free / 2**30
    except OSError as e:
        return [Problem("fail", f"cannot stat {probe}: {e}", f"mkdir -p {workdir}")]
    if free_gb < 50:
        return [Problem("fail", f"{free_gb:.0f} GB free under {probe}", "free 50 GB: snapshots and VM memory files")]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.emu.preflight", description=__doc__)
    ap.add_argument("scenario", help="configs/emu/<name>.yaml or a scenario name")
    ap.add_argument("--no-isolation", action="store_true", help="skip the netns/tc/cgroup checks (smoke runs)")
    ap.add_argument("--no-tpm", action="store_true", help="skip the TPM checks")
    ap.add_argument("--assets", type=Path, default=None)
    ap.add_argument("--workdir", type=Path, default=None)
    a = ap.parse_args(argv)
    spec = spec_mod.load(a.scenario)
    problems = check(spec, isolation=not a.no_isolation, tpm=not a.no_tpm, assets=a.assets, workdir=a.workdir)
    for p in problems:
        print(p.line())
    fails = sum(p.level == "fail" for p in problems)
    print(f"\n{len(problems)} problem(s), {fails} blocking")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
