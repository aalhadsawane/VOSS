"""Node-side plumbing of the calibration harness (doc 10 §1): raw records, timed commands, host metadata.

Runs on the calibration node with the Python standard library only (the node does not need the project's venv).
Every suite writes JSON lines ``{suite, probe, rep, value, unit, config}`` plus a ``meta.json`` describing the host,
so ``ingest.py`` can fit distributions later without re-running anything.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import queue
import re
import shlex
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HARNESS_VERSION = "0.1.0"


class SuiteSkipped(Exception):
    """A required feature or tool is missing: the suite records why and the profile keeps literature values."""


@dataclass
class Cmd:
    """Result of one command: stdout/stderr text, exit code and wall seconds (monotonic clock)."""

    argv: list[str]
    rc: int
    out: str
    err: str
    seconds: float


@dataclass
class Shell:
    """Runs commands, or only prints them in ``dry_run`` mode (returning empty successful results)."""

    dry_run: bool = False
    log: list[str] = field(default_factory=list)

    def run(self, argv: list[str], check: bool = True, timeout: float | None = 600.0, stdin: str | None = None) -> Cmd:
        self.log.append(shlex.join(argv))
        if self.dry_run:
            print("DRY", shlex.join(argv))
            return Cmd(argv, 0, "", "", 0.0)
        t0 = time.monotonic()
        p = subprocess.run(
            argv, capture_output=True, text=True, errors="replace", timeout=timeout, input=stdin, check=False
        )
        dt = time.monotonic() - t0
        if check and p.returncode != 0:
            raise RuntimeError(f"{shlex.join(argv)} failed ({p.returncode}): {p.stderr.strip()[:400]}")
        return Cmd(argv, p.returncode, p.stdout, p.stderr, dt)

    def have(self, tool: str) -> bool:
        return self.dry_run or shutil.which(tool) is not None

    def need(self, *tools: str) -> None:
        missing = [t for t in tools if not self.have(t)]
        if missing:
            raise SuiteSkipped(f"missing tools: {', '.join(missing)}")


class Records:
    """Append-only JSON-lines writer for one suite run."""

    def __init__(self, path: Path, suite: str) -> None:
        self.path, self.suite = path, suite
        path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, probe: str, value: float, unit: str = "s", rep: int = 0, **config: Any) -> None:
        row = {"suite": self.suite, "probe": probe, "rep": rep, "value": value, "unit": unit, "config": config}
        with self.path.open("a") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def read_text(path: str) -> str:
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return ""


def _version(sh: Shell, argv: list[str]) -> str:
    if not shutil.which(argv[0]):
        return "absent"
    try:
        c = sh.run(argv, check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return "error"
    return (c.out or c.err).strip().splitlines()[0] if (c.out or c.err).strip() else "unknown"


def _microcode() -> str:
    m = re.search(r"^microcode\s*:\s*(\S+)", read_text("/proc/cpuinfo"), re.M)
    return m.group(1) if m else "unknown"


def _cpu_model() -> str:
    m = re.search(r"^model name\s*:\s*(.+)$", read_text("/proc/cpuinfo"), re.M)
    return m.group(1).strip() if m else platform.processor()


def _dmesg(sh: Shell) -> str:
    if not shutil.which("dmesg"):
        return ""
    try:
        return sh.run(["dmesg"], check=False, timeout=20).out
    except (OSError, subprocess.TimeoutExpired):
        return ""


def host_meta(sh: Shell) -> dict[str, Any]:
    """Doc 10 §1: harness, kernel, VMM versions, BIOS, microcode, and whether TME, Secure Boot and IOMMU are on."""
    quiet = Shell(dry_run=False)
    dmesg = _dmesg(quiet)
    sb = _version(quiet, ["mokutil", "--sb-state"])
    return {
        "harness_version": HARNESS_VERSION,
        "hostname": platform.node(),
        "kernel": platform.release(),
        "cpu_model": _cpu_model(),
        "microcode": _microcode(),
        "bios_version": read_text("/sys/class/dmi/id/bios_version") or "unknown",
        "board": read_text("/sys/class/dmi/id/board_name") or "unknown",
        "mem_kb": _mem_kb(),
        "firecracker": _version(quiet, ["firecracker", "--version"]),
        "qemu": _version(quiet, ["qemu-system-x86_64", "--version"]),
        "tpm2_tools": _version(quiet, ["tpm2_quote", "--version"]),
        "fio": _version(quiet, ["fio", "--version"]),
        "tme": bool(re.search(r"\bTME\b|total memory encryption", dmesg, re.I)),
        "secure_boot": "enabled" in sb.lower(),
        "iommu": "DMAR" in dmesg or "AMD-Vi" in dmesg,
        "dry_run": sh.dry_run,
        "t_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _mem_kb() -> int:
    m = re.search(r"^MemTotal:\s*(\d+)", read_text("/proc/meminfo"), re.M)
    return int(m.group(1)) if m else 0


def fingerprint(meta: dict[str, Any]) -> str:
    """Stable host id for ``configs/calibration/measured/<fingerprint>/``: hardware and firmware, not software."""
    key = "|".join(str(meta.get(k, "")) for k in ("cpu_model", "board", "bios_version", "mem_kb"))
    return "c0-" + hashlib.sha256(key.encode()).hexdigest()[:10]


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def drop_caches(sh: Shell) -> None:
    """Cold page cache (root only); callers record whether it happened."""
    sh.run(["sync"])
    if sh.dry_run:
        print("DRY echo 3 > /proc/sys/vm/drop_caches")
        return
    Path("/proc/sys/vm/drop_caches").write_text("3\n")


def time_to_marker(argv: list[str], marker: str, timeout: float = 60.0) -> float:
    """Spawn a VMM whose serial console is stdout; seconds from spawn until a line containing ``marker``."""
    lines: queue.Queue[tuple[float, str]] = queue.Queue()
    t0 = time.monotonic()
    p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def read() -> None:
        assert p.stdout is not None
        for line in p.stdout:
            lines.put((time.monotonic(), line))

    threading.Thread(target=read, daemon=True).start()
    try:
        while (left := t0 + timeout - time.monotonic()) > 0:
            try:
                t, line = lines.get(timeout=left)
            except queue.Empty:
                break
            if marker in line:
                return t - t0
        raise TimeoutError(f"{argv[0]}: no {marker!r} within {timeout} s")
    finally:
        p.kill()
        p.wait(timeout=10)
