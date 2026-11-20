"""Identifiers out of committed calibration output (CALIBRATION_HANDOFF.md §1: no serials, MAC or IP addresses, real
hostnames or user names in the repository).

``scrub(text)`` hashes MAC addresses (also Firecracker/UEFI ``MAC(001122334455,...)`` device paths), UUIDs and disk
WWNs to 10-character SHA-256 prefixes, so the same identifier stays recognisable within one file, and replaces
private, loopback-free IPv4 addresses (RFC 1918, carrier-grade NAT, link-local), the hostname and user names.
``python -m tools.calibrate.scrub`` filters standard input to standard output, line by line (``node_run.sh`` logs).
Standard library only: it runs on the node before the project environment exists.
"""

from __future__ import annotations

import contextlib
import getpass
import hashlib
import os
import platform
import re
import sys
from collections.abc import Iterable

MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
UEFI_MAC = re.compile(r"MAC\(([0-9A-Fa-f]{12})")
UUID = re.compile(r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b")
WWN = re.compile(r"\b(?:wwn-0x|naa\.|eui\.|nvme-eui\.)[0-9A-Fa-f]{8,32}\b")
PRIVATE_IP = re.compile(
    r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01])|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])|169\.254)"
    r"\.\d{1,3}\.\d{1,3}\b"
)


def h10(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()[:10]


def local_names() -> list[str]:
    """This machine's hostname and the user names a session runs as (longest first, at least 3 characters)."""
    names = {platform.node(), os.environ.get("SUDO_USER", ""), os.environ.get("USER", "")}
    with contextlib.suppress(KeyError, OSError):
        names.add(getpass.getuser())
    return sorted((n for n in names if len(n) >= 3 and n != "root"), key=len, reverse=True)


def scrub(text: str, names: Iterable[str] | None = None) -> str:
    text = UEFI_MAC.sub(lambda m: f"MAC(<mac:{h10(m.group(1))}>", text)
    text = MAC.sub(lambda m: f"<mac:{h10(m.group(0).replace('-', ':'))}>", text)
    text = UUID.sub(lambda m: f"<uuid:{h10(m.group(0))}>", text)
    text = WWN.sub(lambda m: f"<wwn:{h10(m.group(0))}>", text)
    text = PRIVATE_IP.sub("<private-ip>", text)
    for n in local_names() if names is None else names:
        text = re.sub(rf"(?<![\w.-]){re.escape(n)}(?![\w-])", "HOST" if n == platform.node() else "USER", text)
    return text


def main() -> None:
    names = local_names()
    for line in sys.stdin:
        sys.stdout.write(scrub(line, names))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
