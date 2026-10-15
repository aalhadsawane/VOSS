"""Capability probe (doc 10 §2): KVM, CPU flags, TPM vendor, TME, Secure Boot, IOMMU, disks.

Every capability is recorded as a 0/1 probe; details go to ``caps.json``. Missing features never fail the suite:
their measurement suites skip and the profile keeps literature values flagged ``assumed``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.calibrate.common import Shell, read_text
from tools.calibrate.suites import Ctx, Suite

FLAGS = ("vmx", "svm", "avx2", "avx512f", "aes", "sha_ni", "tme")


def tpm_manufacturer(getcap: str) -> str:
    """``tpm2_getcap properties-fixed`` → vendor string (``INTC`` = Intel PTT firmware TPM)."""
    m = re.search(r"TPM2_PT_MANUFACTURER:\s*\n(?:\s+raw:.*\n)?\s+value:\s*\"?([A-Za-z0-9 ]+)\"?", getcap)
    return m.group(1).strip() if m else ""


def cpuid_tme(cpuid_raw: str) -> bool | None:
    """CPUID leaf 7 subleaf 0, ECX bit 13 (TME enumeration) from ``cpuid -1 -l 7 -r`` output."""
    m = re.search(r"0x00000007 0x00:.*?ecx=0x([0-9a-f]+)", cpuid_raw)
    return None if m is None else bool(int(m.group(1), 16) >> 13 & 1)


def disks(lsblk_json: str) -> list[dict[str, Any]]:
    """Whole disks from ``lsblk -J -b -o NAME,ROTA,SIZE,TYPE,MODEL``: name, rotational flag, size in GB."""
    out = []
    for d in json.loads(lsblk_json or '{"blockdevices": []}').get("blockdevices", []):
        if d.get("type") != "disk":
            continue
        rota = d.get("rota")
        out.append(
            {
                "name": d.get("name"),
                "rotational": rota in (True, "1", 1),
                "size_gb": round(int(d.get("size") or 0) / 1e9, 1),
                "model": (d.get("model") or "").strip(),
            }
        )
    return out


def _try(sh: Shell, argv: list[str]) -> str:
    if not sh.have(argv[0]):
        return ""
    c = sh.run(argv, check=False, timeout=30)
    return c.out if c.rc == 0 else ""


def probe(sh: Shell) -> dict[str, Any]:
    m = re.search(r"^flags\s*:(.*)$", read_text("/proc/cpuinfo"), re.M)
    flags = set(m.group(1).split()) if m else set()
    getcap = _try(sh, ["tpm2_getcap", "properties-fixed"])
    dmesg = _try(sh, ["dmesg"])
    sb = _try(sh, ["mokutil", "--sb-state"])
    return {
        "kvm": Path("/dev/kvm").exists(),
        "cpu_flags": {f: f in flags for f in FLAGS},
        "tpm_device": Path("/dev/tpmrm0").exists(),
        "tpm_vendor": tpm_manufacturer(getcap),
        "tme_dmesg": bool(re.search(r"\bTME\b|total memory encryption", dmesg, re.I)),
        "tme_cpuid": cpuid_tme(_try(sh, ["cpuid", "-1", "-l", "7", "-r"])),
        "tme_msr_0x982": _try(sh, ["rdmsr", "0x982"]).strip() or None,
        "secure_boot": "enabled" in sb.lower(),
        "iommu": "DMAR" in dmesg or "AMD-Vi" in dmesg,
        "disks": disks(_try(sh, ["lsblk", "-J", "-b", "-o", "NAME,ROTA,SIZE,TYPE,MODEL"])),
        "free": _try(sh, ["df", "-B1", "--output=target,avail"]),
    }


def run(ctx: Ctx) -> None:
    caps = probe(ctx.sh)
    (ctx.out / "caps.json").write_text(json.dumps(caps, indent=2, sort_keys=True))
    for key in ("kvm", "tpm_device", "tme_dmesg", "secure_boot", "iommu"):
        ctx.rec.add(key, float(bool(caps[key])), unit="bool")
    ctx.rec.add("tpm_ptt", float(caps["tpm_vendor"] == "INTC"), unit="bool", vendor=caps["tpm_vendor"])
    ctx.rec.add("tme_cpuid", float(bool(caps["tme_cpuid"])), unit="bool", known=caps["tme_cpuid"] is not None)
    for d in caps["disks"]:
        ctx.rec.add("disk", d["size_gb"], unit="GB", name=d["name"], rotational=d["rotational"], model=d["model"])


SUITE = Suite("caps", run, "capabilities: KVM, TPM vendor, TME, Secure Boot, IOMMU, disks")
