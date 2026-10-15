"""Firecracker driver for the ``fc_boot``, ``fc_snapshot`` and ``sebs`` suites (doc 10 §3), standard library only.

One ``FcVm`` is one Firecracker process (optionally under the jailer). The guest serial console is the process's
stdin/stdout; a reader thread timestamps every line with the host monotonic clock, so boot time is measured from the
``InstanceStart`` call to the guest's first ``VOSS_MARK`` line, and restore time from ``/snapshot/load`` to the
guest's echo of a probe written to its console.
"""

from __future__ import annotations

import http.client
import json
import queue
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MARK = re.compile(r"VOSS_(MARK|ACK|EXEC|INIT|ERR)\s+(.*)")


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float = 30.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self.unix_path = path

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self.unix_path)
        self.sock = s


@dataclass
class FcAssets:
    """Binaries and guest images on the node (paths given on the command line, see README)."""

    firecracker: str
    kernel: str
    rootfs: str
    jailer: str | None = None
    chroot_base: str = "/srv/jailer"


@dataclass
class FcVm:
    assets: FcAssets
    workdir: Path
    vm_id: str
    proc: subprocess.Popen[str] | None = None
    lines: queue.Queue[tuple[float, str]] = field(default_factory=queue.Queue)
    sock: str = ""

    # --- process --------------------------------------------------------------------------------------------
    def spawn(self) -> None:
        self.workdir.mkdir(parents=True, exist_ok=True)
        if self.assets.jailer:
            argv, self.sock = self._jailed()
        else:
            # AF_UNIX paths are limited to 107 bytes: a deep results directory would silently break (seen at rep 10)
            sock_dir = Path(tempfile.gettempdir()) / "voss-fc"
            sock_dir.mkdir(parents=True, exist_ok=True)
            self.sock = str(sock_dir / f"{self.vm_id[-60:]}.sock")
            Path(self.sock).unlink(missing_ok=True)
            argv = [self.assets.firecracker, "--api-sock", self.sock, "--level", "Warning"]
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        threading.Thread(target=self._read, daemon=True).start()
        deadline = time.monotonic() + 5.0
        while not Path(self.sock).exists():
            if time.monotonic() > deadline or self.proc.poll() is not None:
                raise RuntimeError(f"firecracker did not create {self.sock}")
            time.sleep(0.002)

    def _jailed(self) -> tuple[list[str], str]:
        """Jailer layout: files hard-linked into ``<base>/firecracker/<id>/root``; API paths are chroot-relative."""
        root = Path(self.assets.chroot_base) / "firecracker" / self.vm_id / "root"
        root.mkdir(parents=True, exist_ok=True)
        for src in (self.assets.kernel, self.assets.rootfs):
            dst = root / Path(src).name
            if not dst.exists():
                shutil.copy2(src, dst)
        argv = [
            str(self.assets.jailer),
            "--id",
            self.vm_id,
            "--exec-file",
            self.assets.firecracker,
            "--uid",
            "0",
            "--gid",
            "0",
            "--chroot-base-dir",
            self.assets.chroot_base,
            "--",
            "--api-sock",
            "/run/fc.sock",
        ]
        return argv, str(root / "run" / "fc.sock")

    def _read(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.put((time.monotonic(), line.rstrip("\n")))

    def kill(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)
        Path(self.sock).unlink(missing_ok=True)

    # --- API ------------------------------------------------------------------------------------------------
    def api(self, method: str, path: str, body: dict[str, Any] | None = None) -> float:
        """One API call; returns its wall seconds. Raises on a non-2xx status."""
        conn = UnixHTTPConnection(self.sock)
        t0 = time.monotonic()
        payload = json.dumps(body) if body is not None else None
        conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
        r = conn.getresponse()
        data = r.read().decode(errors="replace")
        dt = time.monotonic() - t0
        conn.close()
        if r.status >= 300:
            raise RuntimeError(f"{method} {path} -> {r.status}: {data[:300]}")
        return dt

    def _p(self, path: str) -> str:
        return Path(path).name if self.assets.jailer else path

    def configure(self, mem_mb: int, vcpus: int, boot_args: str, rootfs: str | None = None) -> None:
        self.api("PUT", "/machine-config", {"vcpu_count": vcpus, "mem_size_mib": mem_mb, "smt": False})
        self.api("PUT", "/boot-source", {"kernel_image_path": self._p(self.assets.kernel), "boot_args": boot_args})
        drive = {
            "drive_id": "rootfs",
            "path_on_host": self._p(rootfs or self.assets.rootfs),
            "is_root_device": True,
            "is_read_only": True,
        }
        self.api("PUT", "/drives/rootfs", drive)

    def start(self) -> float:
        """``InstanceStart``; returns the host monotonic time just before the call."""
        t0 = time.monotonic()
        self.api("PUT", "/actions", {"action_type": "InstanceStart"})
        return t0

    def pause(self) -> None:
        self.api("PATCH", "/vm", {"state": "Paused"})

    def snapshot(self, state: Path, mem: Path) -> float:
        return self.api(
            "PUT", "/snapshot/create", {"snapshot_type": "Full", "snapshot_path": str(state), "mem_file_path": str(mem)}
        )

    def load(self, state: Path, mem: Path) -> tuple[float, float]:
        """Restore and resume; returns (time before the call, API seconds)."""
        t0 = time.monotonic()
        body = {"snapshot_path": str(state), "mem_backend": {"backend_type": "File", "backend_path": str(mem)}}
        dt = self.api("PUT", "/snapshot/load", body | {"resume_vm": True})
        return t0, dt

    # --- serial ---------------------------------------------------------------------------------------------
    def wait(self, kind: str, text: str = "", timeout: float = 60.0) -> float:
        """Host time at which the guest printed ``VOSS_<kind> <text...>``."""
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"no VOSS_{kind} {text!r} within {timeout} s")
            try:
                t, line = self.lines.get(timeout=left)
            except queue.Empty:
                continue
            m = MARK.search(line)
            if m and m.group(1) == kind and m.group(2).startswith(text):
                return t
            if m and m.group(1) == "ERR":
                raise RuntimeError(f"guest error: {m.group(2)}")

    def collect(self, kind: str, until: str, timeout: float) -> list[str]:
        """Payloads of every ``VOSS_<kind>`` line until ``VOSS_MARK <until>``."""
        out: list[str] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                _, line = self.lines.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                break
            m = MARK.search(line)
            if m and m.group(1) == kind:
                out.append(m.group(2))
            elif m and m.group(1) == "MARK" and m.group(2).startswith(until):
                return out
            elif m and m.group(1) == "ERR":
                raise RuntimeError(f"guest error: {m.group(2)}")
        raise TimeoutError(f"no VOSS_MARK {until!r} within {timeout} s")

    def send(self, text: str) -> float:
        assert self.proc is not None and self.proc.stdin is not None
        t0 = time.monotonic()
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()
        return t0


def boot_args(mode: str, extra: str = "") -> str:
    """Kernel command line: serial console, exit on reboot, our init and its mode (see ``guest/voss-init``)."""
    return f"console=ttyS0 reboot=k panic=1 pci=off quiet init=/voss-init voss.mode={mode} {extra}".strip()
