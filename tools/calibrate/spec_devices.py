"""Probes of the TPM, network interfaces and software versions for the machine specification (``spec.py``;
CALIBRATION_DATA_CONTRACT.md §1). A machine without ``/dev/tpm0`` or ``/dev/tpmrm0`` gets ``tpm: {type: none}``.
"""

from __future__ import annotations

import os
import re
from typing import Any

from tools.calibrate.scrub import h10
from tools.calibrate.spec_parts import Probe, unknown


def _getcap(text: str, key: str) -> tuple[str, str]:
    m = re.search(rf"{key}:\s*\n\s+raw:\s*(\S+)(?:\n\s+value:\s*\"?([^\n\"]*)\"?)?", text)
    return (m.group(1), (m.group(2) or "").strip()) if m else ("", "")


def _pcr_count(cap: str) -> Any:
    raw, value = _getcap(cap, "TPM2_PT_PCR_COUNT")
    try:
        return int(value or raw, 0)
    except ValueError:
        return unknown("TPM2_PT_PCR_COUNT")


def tpm_kind(manufacturer: str) -> str:
    """Firmware TPMs are those of the CPU vendors (Intel PTT ``INTC``, AMD fTPM ``AMD``); others are chips."""
    return {"INTC": "firmware (Intel PTT)", "AMD": "firmware (AMD fTPM)"}.get(manufacturer.strip(), "discrete")


def tpm(pr: Probe) -> dict[str, Any]:
    if not (pr.exists("/dev/tpmrm0") or pr.exists("/dev/tpm0")):
        none = "none (no /dev/tpm0 or /dev/tpmrm0)"
        return {"type": "none", "present": False, "manufacturer": none, "family": "none", "firmware_version": "none"}
    cap = pr.run("tpm2_getcap properties-fixed")
    if not cap:
        why = unknown("tpm2_getcap gave no output")
        return {"type": why, "present": True, "manufacturer": why, "family": why, "firmware_version": why}
    maker = _getcap(cap, "TPM2_PT_MANUFACTURER")[1] or unknown("TPM2_PT_MANUFACTURER")
    vendor = "".join(_getcap(cap, f"TPM2_PT_VENDOR_STRING_{i}")[1] for i in (1, 2, 3, 4)).strip()
    fw = [int(_getcap(cap, f"TPM2_PT_FIRMWARE_VERSION_{i}")[0] or "0", 16) for i in (1, 2)]
    rev = _getcap(cap, "TPM2_PT_REVISION")[1]
    pcrs = pr.run("tpm2_pcrread")
    return {
        "type": tpm_kind(maker),
        "present": True,
        "manufacturer": maker,
        "vendor_string": vendor or unknown("TPM2_PT_VENDOR_STRING"),
        "family": _getcap(cap, "TPM2_PT_FAMILY_INDICATOR")[1] or unknown("TPM2_PT_FAMILY_INDICATOR"),
        "revision": rev or unknown("TPM2_PT_REVISION"),
        "firmware_version": f"{fw[0] >> 16}.{fw[0] & 0xFFFF}.{fw[1] >> 16}.{fw[1] & 0xFFFF}",
        "pcr_count": _pcr_count(cap),
        "active_pcr_banks": [
            b
            for b in ("sha1", "sha256", "sha384", "sha512", "sm3_256")
            if re.search(rf"^\s*{b}:\s*\n\s+0\s*:", pcrs, re.M)
        ],
        "sysfs_description": pr.read("/sys/class/tpm/tpm0/device/description") or unknown("no ACPI description"),
    }


def network(pr: Probe) -> list[dict[str, Any]]:
    out = []
    for net in pr.listdir("/sys/class/net"):
        if net == "lo" or net.startswith(("docker", "veth", "br-", "zt", "virbr", "tap", "fc")):
            continue
        base = f"/sys/class/net/{net}"
        pci = os.path.basename(pr.readlink(f"{base}/device"))
        model = pr.run(f"lspci -s {pci}").split(": ", 1)[-1] if pci else unknown("no PCI device")
        state = pr.read(f"{base}/operstate")
        mac = pr.read(f"{base}/address")
        out.append(
            {
                "interface": net,
                "model": model or unknown("lspci"),
                "driver": os.path.basename(pr.readlink(f"{base}/device/driver")) or unknown("no driver link"),
                "state": state,
                "speed_mbps": pr.read(f"{base}/speed") if state == "up" else "down",
                "mac_sha256": h10(mac) if mac else "none",
            }
        )
    return out


def software(pr: Probe, assets: str) -> dict[str, Any]:
    fc = f"{assets}/firecracker"

    def first(cmd: str) -> str:
        return (pr.run(cmd).splitlines() or [unknown(f"{cmd.split(maxsplit=1)[0]} absent")])[0]

    return {
        "distro": pr.run('. /etc/os-release && echo "$PRETTY_NAME"') or unknown("/etc/os-release"),
        "kernel": pr.kernel(),
        "kernel_version": pr.run("uname -v"),
        "kernel_cmdline": pr.read("/proc/cmdline"),
        "firecracker": first(f"{fc} --version") if pr.exists(fc) else unknown(f"no {fc} yet (setup comes later)"),
        "firecracker_guest_assets": pr.read(f"{assets}/versions.txt") or unknown("no versions.txt yet"),
        "python_system": first("python3 --version"),
        "gcc": first("gcc --version"),
        "qemu": first("qemu-system-x86_64 --version"),
        "docker": first("docker --version"),
        "fio": first("fio --version"),
        "tpm2_tools": first("tpm2_quote --version"),
        "openssl": first("openssl version"),
    }
