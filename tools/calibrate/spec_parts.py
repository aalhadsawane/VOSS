"""Probes behind the machine specification (``spec.py``; CALIBRATION_DATA_CONTRACT.md §1), one function per section.

Each function reads only through ``Probe`` and returns plain data; a value no probe gives is ``unknown (<reason>)``.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from tools.calibrate.scrub import h10

FLAGS = (
    "vmx",
    "svm",
    "ept",
    "vpid",
    "npt",
    "aes",
    "vaes",
    "pclmulqdq",
    "vpclmulqdq",
    "sha_ni",
    "rdrand",
    "rdseed",
    "avx",
    "avx2",
    "avx_vnni",
    "avx512f",
    "tme",
    "sme",
    "sev",
    "sev_es",
    "smep",
    "smap",
    "umip",
    "pku",
)


class Probe:
    """Commands and files of the machine being described (a test replaces it with canned outputs)."""

    def run(self, cmd: str) -> str:
        try:
            p = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, errors="replace", timeout=30, check=False
            )
        except subprocess.TimeoutExpired:
            return ""
        return (p.stdout or "").strip()

    def read(self, path: str) -> str:
        try:
            return Path(path).read_text(errors="replace").strip()
        except OSError:
            return ""

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def listdir(self, path: str) -> list[str]:
        try:
            return sorted(os.listdir(path))
        except OSError:
            return []

    def readlink(self, path: str) -> str:
        try:
            return os.readlink(path)
        except OSError:
            return ""

    def disk_usage(self, path: str) -> tuple[int, int]:
        p = Path(path)
        while not p.exists() and p != p.parent:
            p = p.parent
        u = shutil.disk_usage(p)
        return u.total, u.free

    def kernel(self) -> str:
        return platform.release()


def unknown(why: str) -> str:
    return f"unknown ({why})"


def kv(text: str, sep: str = ":") -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if sep in line:
            k, v = line.split(sep, 1)
            out.setdefault(k.strip(), v.strip())
    return out


def _num(v: str, cast: type = int) -> Any:
    try:
        return cast(v)
    except (TypeError, ValueError):
        return unknown(f"not a number: {v!r}")


def virtualisation(pr: Probe) -> dict[str, Any]:
    nested = {
        p: pr.read(p)
        for p in ("/sys/module/kvm_intel/parameters/nested", "/sys/module/kvm_amd/parameters/nested")
        if pr.exists(p)
    }
    return {
        "systemd_detect_virt": pr.run("systemd-detect-virt") or "none",
        "dev_kvm_exists": pr.exists("/dev/kvm"),
        "dev_kvm_accessible": pr.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK),
        "nested": nested,
    }


def core_kinds(lscpu_e: str) -> list[dict[str, Any]]:
    """Physical cores grouped by their maximum frequency (performance and efficiency cores differ there)."""
    cores: dict[tuple[str, str], list[float]] = {}
    for line in lscpu_e.splitlines()[1:]:
        p = line.split()
        if len(p) >= 8:
            mhz = _num(p[6], float)
            cores.setdefault((p[2], p[3]), []).append(mhz if isinstance(mhz, float) else 0.0)
    by_mhz: dict[float, list[int]] = {}
    for threads in cores.values():
        by_mhz.setdefault(max(threads), []).append(len(threads))
    return [
        {"max_mhz": mhz or unknown("lscpu -e gives no MAXMHZ"), "cores": len(t), "threads": sum(t)}
        for mhz, t in sorted(by_mhz.items(), reverse=True)
    ]


def _tme_enabled(dmesg: str, has_tme: bool) -> Any:
    if not has_tme:
        return False
    if "x86/tme: not enabled by BIOS" in dmesg:
        return False
    if "x86/tme: enabled by BIOS" in dmesg:
        return True
    return unknown("no x86/tme line in dmesg")


def cpu(pr: Probe) -> dict[str, Any]:
    lc = kv(pr.run("lscpu"))
    info = pr.read("/proc/cpuinfo")
    fl = re.search(r"^flags\s*:\s*(.+)$", info, re.M)
    flags = set(fl.group(1).split()) if fl else set()
    ucode = re.search(r"^microcode\s*:\s*(\S+)", info, re.M)
    dmesg = pr.run("dmesg")
    sockets, per = _num(lc.get("Socket(s)", "")), _num(lc.get("Core(s) per socket", ""))
    no_turbo = pr.read("/sys/devices/system/cpu/intel_pstate/no_turbo")
    boost = pr.read("/sys/devices/system/cpu/cpufreq/boost")
    return {
        "vendor": lc.get("Vendor ID", unknown("lscpu has no Vendor ID")),
        "model": lc.get("Model name", unknown("lscpu has no Model name")),
        "family": _num(lc.get("CPU family", "")),
        "model_id": _num(lc.get("Model", "")),
        "stepping": _num(lc.get("Stepping", "")),
        "sockets": sockets,
        "cores_total": sockets * per if isinstance(sockets, int) and isinstance(per, int) else unknown("lscpu"),
        "threads_total": _num(lc.get("CPU(s)", "")),
        "core_kinds": core_kinds(pr.run("lscpu -e=CPU,NODE,SOCKET,CORE,CACHE,ONLINE,MAXMHZ,MINMHZ")),
        "min_mhz": _num(lc.get("CPU min MHz", ""), float),
        "max_mhz": _num(lc.get("CPU max MHz", ""), float),
        "caches": {k: lc.get(f"{k.upper()[:2]}{k[2:]} cache", unknown("lscpu")) for k in ("l1d", "l1i", "l2", "l3")},
        "microcode": ucode.group(1) if ucode else unknown("no microcode line in /proc/cpuinfo"),
        "flags": {f: f in flags for f in FLAGS},
        "smt_control": pr.read("/sys/devices/system/cpu/smt/control") or unknown("no smt/control"),
        "governor": pr.read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") or unknown("no cpufreq"),
        "no_turbo": int(no_turbo) if no_turbo else (1 - int(boost) if boost in ("0", "1") else unknown("no knob")),
        "vulnerabilities": {
            Path(f).name: pr.read(f"/sys/devices/system/cpu/vulnerabilities/{f}")
            for f in pr.listdir("/sys/devices/system/cpu/vulnerabilities")
        },
        "tme_cpuid_supported": "tme" in flags,
        "tme_bios_enabled": _tme_enabled(dmesg, "tme" in flags),
        "sme_cpuid_supported": "sme" in flags,
        "sme_enabled": bool(re.search(r"Memory Encryption Features active:.*SME", dmesg)),
        "iommu_acpi": "DMAR" in dmesg or "AMD-Vi" in dmesg or "IVRS" in dmesg,
        "iommu_cmdline": re.findall(r"\b(?:intel|amd)_iommu=\S+|\biommu=\S+", pr.read("/proc/cmdline")),
        "dmesg_tme_iommu": [
            ln for ln in dmesg.splitlines() if re.search(r"tme|memory encryption|dmar|iommu|amd-vi", ln, re.I)
        ][:35],
    }


def _dimms(dmi: str) -> list[dict[str, str]]:
    out = []
    for block in dmi.split("Memory Device\n")[1:]:
        f = kv(block)
        out.append(
            {
                "locator": f.get("Locator", ""),
                "size": f.get("Size", ""),
                "type": f.get("Type", ""),
                "speed": f.get("Configured Memory Speed", f.get("Speed", "")),
                "manufacturer": f.get("Manufacturer", ""),
                "part_number": f.get("Part Number", ""),
                "serial_sha256": h10(f.get("Serial Number", "")) if f.get("Serial Number") else "none",
            }
        )
    return out


def _size_gb(size: str) -> float:
    m = re.match(r"(\d+)\s*(GB|MB|TB)", size)
    return 0.0 if not m else int(m.group(1)) * {"MB": 1 / 1024, "GB": 1, "TB": 1024}[m.group(2)]


def memory(pr: Probe) -> dict[str, Any]:
    mi = kv(pr.read("/proc/meminfo"))
    total_kb = _num(mi.get("MemTotal", "").split(" ")[0])
    dimms = _dimms(pr.run("dmidecode -t 17"))
    used = [d for d in dimms if _size_gb(d["size"]) > 0]

    def mode(key: str) -> str:
        return Counter(d[key] for d in used).most_common(1)[0][0] if used else unknown("dmidecode -t 17")

    speed = mode("speed")
    return {
        "total_kb": total_kb,
        "total_gib": round(total_kb / 2**20, 2) if isinstance(total_kb, int) else total_kb,
        "nominal_gb": round(sum(_size_gb(d["size"]) for d in used), 1) if used else unknown("dmidecode -t 17"),
        "type": mode("type"),
        "speed_mts": _num(speed.split()[0]) if used and speed.split() else speed,
        "dimms_populated": len(used),
        "slots_total": len(dimms) if dimms else unknown("dmidecode -t 17"),
        "dimms": used,
        "swap_kb": _num(mi.get("SwapTotal", "").split(" ")[0]),
        "thp_enabled": pr.read("/sys/kernel/mm/transparent_hugepage/enabled"),
    }


def _disk(pr: Probe, d: dict[str, Any]) -> dict[str, Any]:
    name = d["name"]
    q = f"/sys/block/{name}/queue"
    raw = pr.run(f"smartctl -j -a /dev/{name}")
    sm = json.loads(raw) if raw.startswith("{") else {}
    nv = sm.get("nvme_smart_health_information_log", {})
    rot = pr.read(f"{q}/rotational")
    return {
        "device": f"/dev/{name}",
        "model": sm.get("model_name") or (d.get("model") or "").strip() or unknown("smartctl and lsblk"),
        "firmware": sm.get("firmware_version") or unknown("smartctl"),
        "serial_sha256": h10(sm["serial_number"]) if sm.get("serial_number") else unknown("smartctl"),
        "capacity_gb": round(int(d.get("size") or 0) / 1e9, 1),
        "interface": (d.get("tran") or ("nvme" if name.startswith("nvme") else unknown("lsblk TRAN"))).upper(),
        "rotational": bool(int(rot)) if rot in ("0", "1") else bool(d.get("rota")),
        "scheduler": pr.read(f"{q}/scheduler"),
        "smart_passed": sm.get("smart_status", {}).get("passed"),
        "power_on_hours": sm.get("power_on_time", {}).get("hours"),
        "wear_percentage_used": nv.get("percentage_used"),
    }


def _scratch(pr: Probe, path: str) -> dict[str, Any]:
    p = Path(path)
    while not pr.exists(str(p)) and p != p.parent:
        p = p.parent
    mnt = json.loads(pr.run(f"findmnt -J -T {p}") or '{"filesystems": []}')
    fs = (mnt.get("filesystems") or [{}])[0]
    stack = pr.run(f"lsblk -s -n -o TYPE {fs.get('source', '')}").split() if fs.get("source") else []
    total, free = pr.disk_usage(str(p))
    return {
        "path": path,
        "mount": fs.get("target", ""),
        "source": fs.get("source", ""),
        "fstype": fs.get("fstype", ""),
        "layers": sorted(set(stack) - {"disk", "part"}) or ["none"],
        "total_gb": round(total / 1e9, 1),
        "free_gb": round(free / 1e9, 1),
    }


def storage(pr: Probe, scratch: list[str]) -> dict[str, Any]:
    blk = json.loads(pr.run("lsblk -J -b -o NAME,TYPE,SIZE,ROTA,MODEL,TRAN") or '{"blockdevices": []}')
    disks = [
        d
        for d in blk.get("blockdevices", [])
        if d.get("type") == "disk" and not d["name"].startswith(("loop", "zram", "ram"))
    ]
    return {"devices": [_disk(pr, d) for d in disks], "scratch_directories": [_scratch(pr, s) for s in scratch]}


def firmware(pr: Probe) -> dict[str, Any]:
    dmi = {
        k: pr.read(f"/sys/class/dmi/id/{k}") or unknown(f"/sys/class/dmi/id/{k}")
        for k in ("bios_vendor", "bios_version", "bios_date", "board_vendor", "board_name", "board_version")
    }
    sb = pr.run("mokutil --sb-state")
    return {
        "bios_vendor": dmi["bios_vendor"],
        "bios_version": dmi["bios_version"],
        "bios_date": dmi["bios_date"],
        "board_vendor": dmi["board_vendor"],
        "board_model": dmi["board_name"],
        "board_version": dmi["board_version"],
        "boot_mode": "UEFI" if pr.exists("/sys/firmware/efi") else "legacy BIOS",
        "secure_boot": "enabled"
        if "enabled" in sb.lower()
        else "disabled"
        if "disabled" in sb.lower()
        else unknown("mokutil --sb-state gave no answer"),
        "efibootmgr": pr.run("efibootmgr -v").splitlines(),
        "bootctl": pr.run("bootctl status 2>/dev/null | head -n 25").splitlines(),
    }
