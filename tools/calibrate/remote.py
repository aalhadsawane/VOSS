"""Run calibration suites on the remote node over SSH (ROADMAP P9 access note): copy ``tools/calibrate`` to the node,
run ``tools.calibrate.run`` there, and copy the raw logs back for ``ingest.py``.

    python -m tools.calibrate.remote --host user@c0 --suite caps --suite tpm --set ssd_dir=/mnt/nvme/voss

Reboot/BIOS suites are refused unless ``--allow-reboot`` (appliance) or ``--phase`` (tme) is given, and those flags
may only be used with the user's explicit approval (AGENTS.md rule 14). ``--boots N`` repeats the appliance's single
reboot ``N`` times, waiting for SSH to come back in between; it never installs a reboot loop on the node.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REMOTE_DIR = "voss-calib"


def ssh_base(a: argparse.Namespace) -> list[str]:
    base = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-p", str(a.port)]
    return base + (["-i", a.identity] if a.identity else [])


def remote_cmd(a: argparse.Namespace) -> str:
    args = ["python3", "-m", "tools.calibrate.run", "--out", "raw"]
    for s in a.suite:
        args += ["--suite", s]
    for kv in a.set:
        args += ["--set", kv]
    args += ["--quick"] * a.quick + ["--dry-run"] * a.dry_run + ["--allow-reboot"] * a.allow_reboot
    args += ["--phase", a.phase] if a.phase else []
    cmd = f"cd ~/{REMOTE_DIR} && " + shlex.join(args)
    return f"sudo -n sh -c {shlex.quote(cmd)}" if a.sudo else cmd


def rsync(a: argparse.Namespace, src: str, dst: str) -> list[str]:
    ssh = " ".join(shlex.quote(x) for x in ssh_base(a))
    return ["rsync", "-az", "--exclude", "__pycache__", "-e", ssh, src, dst]


def push(a: argparse.Namespace) -> list[list[str]]:
    dst = f"{a.host}:{REMOTE_DIR}/tools/"
    return [
        [*ssh_base(a), a.host, f"mkdir -p ~/{REMOTE_DIR}/tools"],
        rsync(a, str(REPO / "tools" / "__init__.py"), dst),
        rsync(a, str(REPO / "tools" / "calibrate"), dst),
    ]


def pull(a: argparse.Namespace) -> list[str]:
    a.raw.mkdir(parents=True, exist_ok=True)
    return rsync(a, f"{a.host}:{REMOTE_DIR}/raw/", str(a.raw) + "/")


def wait_ssh(a: argparse.Namespace, down_first: bool, timeout_s: float = 900.0) -> None:
    """After a reboot: wait for SSH to go away (if ``down_first``) and come back."""
    deadline = time.monotonic() + timeout_s
    probe = [*ssh_base(a), a.host, "true"]
    while down_first and subprocess.run(probe, capture_output=True, check=False).returncode == 0:
        if time.monotonic() > deadline:
            raise TimeoutError("node did not go down")
        time.sleep(5)
    while subprocess.run(probe, capture_output=True, check=False).returncode != 0:
        if time.monotonic() > deadline:
            raise TimeoutError("node did not come back over SSH")
        time.sleep(10)


def run(argv: list[str], dry: bool) -> int:
    print("$", shlex.join(argv))
    return 0 if dry else subprocess.run(argv, check=False).returncode


def parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tools.calibrate.remote", description=__doc__.splitlines()[0])
    p.add_argument("--host", required=True, help="user@host of the calibration node")
    p.add_argument("--port", type=int, default=22)
    p.add_argument("--identity", default=None, help="SSH private key")
    p.add_argument("--suite", action="append", required=True)
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("--raw", type=Path, default=REPO / "calibration" / "raw", help="local copy of raw logs")
    p.add_argument("--sudo", action="store_true", help="run suites as root (cold page cache, dm-crypt)")
    p.add_argument("--quick", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="dry-run the suites on the node")
    p.add_argument("--print-only", action="store_true", help="print the local ssh/rsync commands, run nothing")
    p.add_argument("--allow-reboot", action="store_true", help="appliance only, with the user's explicit approval")
    p.add_argument("--boots", type=int, default=1, help="appliance arm: reboots, one at a time")
    p.add_argument("--phase", choices=("on", "off"))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    a = parse(sys.argv[1:] if argv is None else argv)
    rebooting = a.allow_reboot and "appliance" in a.suite and "step=arm" in a.set
    for cmd in push(a):
        if run(cmd, a.print_only):
            return 1
    rc = 0
    for i in range(a.boots if rebooting else 1):
        r = run([*ssh_base(a), a.host, remote_cmd(a)], a.print_only)
        rc |= 0 if rebooting else r  # the session dies with the reboot
        if rebooting and not a.print_only:
            print(f"boot {i + 1}/{a.boots}: waiting for the node to reboot and return")
            wait_ssh(a, down_first=True)
    return rc | run(pull(a), a.print_only)


if __name__ == "__main__":
    raise SystemExit(main())
