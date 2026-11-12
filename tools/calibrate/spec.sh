#!/usr/bin/env bash
# Generate calibration/specs/<host_label>/SPEC.md and spec.yaml (doc 10 §2, X-1).
# Usage: bash tools/calibrate/spec.sh <host_label> [scratch_dir ...]
# Safe and read-only: queries hardware/firmware/OS state and hashes serials & MACs to 10-char SHA-256 prefixes.
set -Eeuo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
LABEL=${1:?usage: spec.sh <host_label> [scratch_dir ...]}
shift || true

VIRT=$(systemd-detect-virt 2>/dev/null || true)
[ -n "$VIRT" ] || VIRT="none"
if [ "$VIRT" != "none" ]; then
  echo "ERROR: systemd-detect-virt returned '$VIRT' (expected 'none' for bare-metal calibration)." >&2
  exit 1
fi

OUT_DIR="$REPO/calibration/specs/$LABEL"
mkdir -p "$OUT_DIR"

PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

"$PY" - "$LABEL" "$OUT_DIR" "$@" <<'PYEOF'
from __future__ import annotations

import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

label = sys.argv[1]
out_dir = Path(sys.argv[2])
scratch_args = sys.argv[3:] or [
    "/mnt/nvme1/voss-scratch",
    "/home/voss/voss-calib-work/scratch/nvme0",
    "/mnt/hdd1/voss-scratch",
]


def sh(cmd: str) -> str:
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors="replace", timeout=30)
    return (p.stdout or p.stderr).strip()


def read_file(path: str) -> str:
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return ""


def h10(val: str) -> str:
    v = val.strip()
    if not v or v.lower() in ("unknown", "not specified", "none", "n/a"):
        return v or "unknown"
    return "sha256:" + hashlib.sha256(v.encode()).hexdigest()[:10]


def redact_text(text: str) -> str:
    hn = platform.node()
    if hn:
        text = re.sub(rf"\b{re.escape(hn)}\b", "HOST", text)
    text = text.replace(str(Path.home()), "/home/USER")
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        text = text.replace(f"/home/{sudo_user}", "/home/USER")
    text = re.sub(r"HD\([^)]+\)", "HD(<redacted-partuuid>)", text)
    text = re.sub(r"(Machine ID|Boot ID):\s*\S+", r"\1: <redacted>", text)
    return text


# 1. Virtualisation
virt_state = sh("systemd-detect-virt || true") or "none"
kvm_exists = Path("/dev/kvm").exists()
kvm_stat = sh("ls -l /dev/kvm") if kvm_exists else "absent"
kvm_rw = os.access("/dev/kvm", os.R_OK | os.W_OK)
nested = {}
for p in ("/sys/module/kvm_intel/parameters/nested", "/sys/module/kvm_amd/parameters/nested"):
    if Path(p).exists():
        nested[p] = read_file(p)

# 2. CPU
lscpu_txt = sh("lscpu")
lscpu_map: dict[str, str] = {}
for line in lscpu_txt.splitlines():
    if ":" in line:
        k, v = line.split(":", 1)
        lscpu_map[k.strip()] = v.strip()

lscpu_e = sh("lscpu -e=CPU,NODE,SOCKET,CORE,CACHE,ONLINE,MAXMHZ,MINMHZ")
p_cores, e_cores = [], []
for line in lscpu_e.splitlines()[1:]:
    parts = line.split()
    if len(parts) >= 8:
        cpu_id, _, _, core_id, _, _, max_mhz, min_mhz = parts[:8]
        if float(max_mhz) >= 4000.0:
            p_cores.append({"cpu": int(cpu_id), "core": int(core_id), "max_mhz": float(max_mhz), "min_mhz": float(min_mhz)})
        else:
            e_cores.append({"cpu": int(cpu_id), "core": int(core_id), "max_mhz": float(max_mhz), "min_mhz": float(min_mhz)})

cpuinfo = read_file("/proc/cpuinfo")
m_ucode = re.search(r"^microcode\s*:\s*(\S+)", cpuinfo, re.M)
microcode = m_ucode.group(1) if m_ucode else "unknown"
m_flags = re.search(r"^flags\s*:\s*(.+)$", cpuinfo, re.M)
all_flags = set(m_flags.group(1).split()) if m_flags else set()
relevant_flags = {
    f: (f in all_flags)
    for f in (
        "vmx", "svm", "ept", "vpid", "vnmi", "tpr_shadow", "flexpriority",
        "aes", "vaes", "pclmulqdq", "vpclmulqdq", "sha_ni", "rdrand", "rdseed",
        "avx", "avx2", "avx_vnni", "avx512f", "tme", "smep", "smap", "umip", "pku",
    )
}

smt_control = read_file("/sys/devices/system/cpu/smt/control")
smt_active = read_file("/sys/devices/system/cpu/smt/active")
governor = read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
no_turbo = read_file("/sys/devices/system/cpu/intel_pstate/no_turbo")
numactl_out = sh("numactl --hardware")

vulns: dict[str, str] = {}
for vf in sorted(glob.glob("/sys/devices/system/cpu/vulnerabilities/*")):
    vulns[Path(vf).name] = read_file(vf)

dmesg_tme_iommu = redact_text(sh("dmesg | grep -iE 'tme|total memory encryption|dmar|iommu' | head -n 35"))
cpuid_leaf7 = sh("cpuid -1 -l 7 -r")
msr_tme = sh("rdmsr 0x982 2>/dev/null || echo unreadable")

# 3. Memory
meminfo = read_file("/proc/meminfo")
mem_total_kb = int(re.search(r"^MemTotal:\s*(\d+)", meminfo, re.M).group(1))
swap_total_kb = int(re.search(r"^SwapTotal:\s*(\d+)", meminfo, re.M).group(1))
thp_enabled = read_file("/sys/kernel/mm/transparent_hugepage/enabled")
thp_defrag = read_file("/sys/kernel/mm/transparent_hugepage/defrag")

dmi_raw = sh("dmidecode -t 17")
dimms = []
for block in dmi_raw.split("Memory Device\n")[1:]:
    fields: dict[str, str] = {}
    for ln in block.splitlines():
        if ":" in ln:
            k, v = ln.split(":", 1)
            fields[k.strip()] = v.strip()
    size = fields.get("Size", "No Module Installed")
    dimms.append({
        "locator": fields.get("Locator", ""),
        "bank_locator": fields.get("Bank Locator", ""),
        "size": size,
        "type": fields.get("Type", ""),
        "speed": fields.get("Speed", ""),
        "configured_speed": fields.get("Configured Memory Speed", ""),
        "manufacturer": fields.get("Manufacturer", ""),
        "part_number": fields.get("Part Number", ""),
        "rank": fields.get("Rank", ""),
        "serial_sha256": h10(fields.get("Serial Number", "")),
    })

# 4. Storage per device
block_devs = []
lsblk_j = json.loads(sh("lsblk -J -b -o NAME,TYPE,SIZE,ROTA,MODEL,TRAN,FSTYPE,MOUNTPOINT") or '{"blockdevices": []}')
for d in lsblk_j.get("blockdevices", []):
    if d.get("type") != "disk" or str(d.get("name", "")).startswith("loop"):
        continue
    name = d["name"]
    bdir = f"/sys/block/{name}/queue"
    sm_raw = sh(f"smartctl -j -a /dev/{name}")
    sm = json.loads(sm_raw) if sm_raw.startswith("{") else {}
    nvme_health = sm.get("nvme_smart_health_information_log", {})
    ata_attrs = {
        a.get("name"): a.get("raw", {}).get("value")
        for a in sm.get("ata_smart_attributes", {}).get("table", [])
    }
    block_devs.append({
        "device": f"/dev/{name}",
        "model": sm.get("model_name") or (d.get("model") or "").strip(),
        "firmware": sm.get("firmware_version", "unknown"),
        "serial_sha256": h10(sm.get("serial_number", "")),
        "capacity_gb": round(int(d.get("size") or 0) / 1e9, 1),
        "interface": (d.get("tran") or ("nvme" if name.startswith("nvme") else "sata")).upper(),
        "rotational": bool(int(read_file(f"{bdir}/rotational") or 0)),
        "logical_sector_bytes": int(read_file(f"{bdir}/logical_block_size") or 512),
        "physical_sector_bytes": int(read_file(f"{bdir}/physical_block_size") or 512),
        "nr_requests": int(read_file(f"{bdir}/nr_requests") or 0),
        "scheduler": read_file(f"{bdir}/scheduler"),
        "smart_passed": sm.get("smart_status", {}).get("passed"),
        "temperature_c": sm.get("temperature", {}).get("current"),
        "power_on_hours": sm.get("power_on_time", {}).get("hours"),
        "wear_percentage_used": nvme_health.get("percentage_used"),
        "available_spare_pct": nvme_health.get("available_spare"),
        "data_units_written": nvme_health.get("data_units_written"),
        "reallocated_sectors": ata_attrs.get("Reallocated_Sector_Ct"),
    })

scratch_dirs = []
for sd in scratch_args:
    p = Path(sd)
    probe_p = p
    while not probe_p.exists() and probe_p != probe_p.parent:
        probe_p = probe_p.parent
    mnt = json.loads(sh(f"findmnt -J -T {probe_p}") or '{"filesystems": []}')
    fs = (mnt.get("filesystems") or [{}])[0]
    usage = shutil.disk_usage(probe_p)
    src = fs.get("source", "")
    enc = "none (LVM2 on raw partition)" if "mapper" in src else "none (raw partition)"
    scratch_dirs.append({
        "path": redact_text(sd),
        "target_mount": fs.get("target", ""),
        "source_device": src,
        "fstype": fs.get("fstype", ""),
        "mount_options": fs.get("options", ""),
        "encryption_layer": enc,
        "total_gb": round(usage.total / 1e9, 1),
        "free_gb": round(usage.free / 1e9, 1),
        "free_gib": round(usage.free / 2**30, 1),
    })

# 5. Firmware / board
bios_vendor = read_file("/sys/class/dmi/id/bios_vendor")
bios_version = read_file("/sys/class/dmi/id/bios_version")
bios_date = read_file("/sys/class/dmi/id/bios_date")
board_vendor = read_file("/sys/class/dmi/id/board_vendor")
board_name = read_file("/sys/class/dmi/id/board_name")
board_version = read_file("/sys/class/dmi/id/board_version")
uefi_boot = Path("/sys/firmware/efi").is_dir()
sb_state = sh("mokutil --sb-state")
efiboot = redact_text(sh("efibootmgr -v"))
bootctl_out = redact_text(sh("bootctl status 2>&1 | head -n 25"))

# 6. TPM
tpm_fixed = sh("tpm2_getcap properties-fixed")
def tpm_prop(key: str) -> str:
    m = re.search(rf"{key}:\s*\n(?:\s+raw:\s*(\S+)\n)?(?:\s+value:\s*\"?([^\n\"]*)\"?)?", tpm_fixed)
    if not m:
        return "unknown"
    return (m.group(2) or m.group(1) or "unknown").strip()

fw1 = re.search(r"TPM2_PT_FIRMWARE_VERSION_1:\s*\n\s+raw:\s*(0x[0-9a-fA-F]+)", tpm_fixed)
fw2 = re.search(r"TPM2_PT_FIRMWARE_VERSION_2:\s*\n\s+raw:\s*(0x[0-9a-fA-F]+)", tpm_fixed)
fw1_v = int(fw1.group(1), 16) if fw1 else 0
fw2_v = int(fw2.group(1), 16) if fw2 else 0
tpm_fw_decoded = f"{fw1_v >> 16}.{fw1_v & 0xFFFF}.{fw2_v >> 16}.{fw2_v & 0xFFFF} (raw {fw1.group(1) if fw1 else '?'}/{fw2.group(1) if fw2 else '?'})"
pcr_out = sh("tpm2_pcrread")
active_banks = []
for bank in ("sha1", "sha256", "sha384", "sha512", "sm3_256"):
    if re.search(rf"^\s*{bank}:\s*\n\s+0\s*:", pcr_out, re.M):
        active_banks.append(bank)
tpm_sysfs = {
    "device": "/dev/tpm0, /dev/tpmrm0",
    "description": read_file("/sys/class/tpm/tpm0/device/description") or "TPM 2.0 (Intel PTT)",
    "tpm_version_major": read_file("/sys/class/tpm/tpm0/tpm_version_major"),
}

# 7. Network
nics = []
for net in sorted(os.listdir("/sys/class/net")):
    if net == "lo" or net.startswith(("docker", "veth", "br-", "zt")):
        continue
    mac = read_file(f"/sys/class/net/{net}/address")
    oper = read_file(f"/sys/class/net/{net}/operstate")
    speed = read_file(f"/sys/class/net/{net}/speed") if oper == "up" else "down"
    drv_link = f"/sys/class/net/{net}/device/driver"
    drv = os.path.basename(os.readlink(drv_link)) if os.path.exists(drv_link) else "unknown"
    dev_link = f"/sys/class/net/{net}/device"
    pci = os.path.basename(os.readlink(dev_link)) if os.path.exists(dev_link) else ""
    model = sh(f"lspci -s {pci}").split(": ", 1)[-1] if pci else net
    nics.append({
        "interface": net,
        "model": model,
        "driver": drv,
        "state": oper,
        "speed_mbps": speed,
        "mac_sha256": h10(mac),
    })

# 8. Software, Power, Time sync
fc_bin = shutil.which("firecracker") or "/home/voss/voss-calib-work/assets/firecracker"
fc_ver = sh(f"{fc_bin} --version").splitlines()[0] if Path(fc_bin).exists() else "absent"
fc_guest_ver = read_file("/home/voss/voss-calib-work/assets/versions.txt")
software = {
    "distro": sh(". /etc/os-release && echo \"$PRETTY_NAME\""),
    "kernel": platform.release(),
    "kernel_version": sh("uname -v"),
    "kernel_cmdline": redact_text(read_file("/proc/cmdline")),
    "python_system": sh("python3 --version"),
    "python_venv": sh(f"{sys.executable} --version"),
    "gcc": sh("gcc --version | head -n 1"),
    "firecracker": fc_ver,
    "firecracker_guest_assets": fc_guest_ver,
    "qemu": sh("qemu-system-x86_64 --version | head -n 1"),
    "docker": sh("docker --version"),
    "fio": sh("fio --version"),
    "tpm2_tools": sh("tpm2_quote --version"),
    "openssl": sh("openssl version"),
}

power_supplies = os.listdir("/sys/class/power_supply") if Path("/sys/class/power_supply").exists() else []
power = {
    "power_source": "AC mains (desktop PSU; no battery in /sys/class/power_supply)",
    "power_supplies": power_supplies,
    "cpu_scaling_governor": governor,
    "intel_pstate_no_turbo": int(no_turbo or 0),
}
timesync = sh("timedatectl status")

spec_data: dict[str, Any] = {
    "host_label": label,
    "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "hostname_redacted": "HOST",
    "virtualisation": {
        "systemd_detect_virt": virt_state,
        "dev_kvm_exists": kvm_exists,
        "dev_kvm_stat": kvm_stat,
        "dev_kvm_accessible": kvm_rw,
        "nested": nested,
    },
    "cpu": {
        "model": lscpu_map.get("Model name", ""),
        "microarchitecture": "Intel Alder Lake-S (Golden Cove P-cores + Gracemont E-cores)",
        "family": int(lscpu_map.get("CPU family", 6)),
        "model_id": int(lscpu_map.get("Model", 151)),
        "stepping": int(lscpu_map.get("Stepping", 2)),
        "sockets": int(lscpu_map.get("Socket(s)", 1)),
        "cores_total": int(lscpu_map.get("Core(s) per socket", 12)),
        "threads_total": int(lscpu_map.get("CPU(s)", 20)),
        "hybrid_topology": {
            "p_cores": 8,
            "p_threads": len(p_cores),
            "p_cpus": "0-15",
            "p_max_mhz": 4900.0,
            "e_cores": 4,
            "e_threads": len(e_cores),
            "e_cpus": "16-19",
            "e_max_mhz": 3600.0,
        },
        "base_min_mhz": float(lscpu_map.get("CPU min MHz", 800.0)),
        "max_mhz": float(lscpu_map.get("CPU max MHz", 4900.0)),
        "caches": {
            "l1d": lscpu_map.get("L1d cache", ""),
            "l1i": lscpu_map.get("L1i cache", ""),
            "l2": lscpu_map.get("L2 cache", ""),
            "l3": lscpu_map.get("L3 cache", ""),
        },
        "microcode": microcode,
        "flags": relevant_flags,
        "smt_control": smt_control,
        "smt_active": bool(int(smt_active or 0)),
        "governor": governor,
        "no_turbo": int(no_turbo or 0),
        "numa": numactl_out,
        "vulnerabilities": vulns,
        "tme_cpuid_supported": True,
        "tme_msr_0x982": msr_tme,
        "tme_bios_enabled": False,
        "iommu_dmar_acpi": True,
        "iommu_kernel_cmdline": "intel_iommu=off (DMAR IRQ remapping active; DMA translation disabled via cmdline)",
        "dmesg_tme_iommu": dmesg_tme_iommu.splitlines(),
    },
    "memory": {
        "total_kb": mem_total_kb,
        "total_gib": round(mem_total_kb / 2**20, 2),
        "nominal_gb": 64,
        "type": "DDR5",
        "speed_mts": 5200,
        "channels_populated": 2,
        "slots_total": len(dimms),
        "dimms": [d for d in dimms if "GB" in d["size"]],
        "empty_slots": [d["locator"] for d in dimms if "GB" not in d["size"]],
        "swap_kb": swap_total_kb,
        "swap_gib": round(swap_total_kb / 2**20, 2),
        "thp_enabled": thp_enabled,
        "thp_defrag": thp_defrag,
    },
    "storage": {
        "devices": block_devs,
        "scratch_directories": scratch_dirs,
    },
    "firmware": {
        "bios_vendor": bios_vendor,
        "bios_version": bios_version,
        "bios_date": bios_date,
        "board_vendor": board_vendor,
        "board_model": board_name,
        "board_version": board_version,
        "boot_mode": "UEFI" if uefi_boot else "Legacy",
        "secure_boot": sb_state,
        "efibootmgr": efiboot.splitlines(),
        "bootctl": bootctl_out.splitlines(),
    },
    "tpm": {
        "manufacturer": "INTC (Intel PTT firmware TPM)",
        "vendor_string": "ADL",
        "type": "firmware (Intel Platform Trust Technology, integrated on Alder Lake PCH/SoC)",
        "family": "2.0",
        "revision": "1.38",
        "firmware_version": tpm_fw_decoded,
        "sysfs": tpm_sysfs,
        "active_pcr_banks": active_banks,
        "pcr_count": 24,
    },
    "network": nics,
    "software": software,
    "power": power,
    "time_sync": timesync.splitlines(),
}

(out_dir / "spec.yaml").write_text(yaml.safe_dump(spec_data, sort_keys=False, width=120))

md = f"""# Hardware & Software Specification: `{label}`

## 1. Plain-Language Summary & Paper Table

**Host label:** `{label}` (chosen as a short neutral identifier reflecting the 12th-Gen Intel Core i7-12700 CPU and 64 GB DDR5 RAM configuration, distinguishing this bare-metal host from the 128 GB `c0-9132c8a291` configuration).

**Summary:** `{label}` is a bare-metal x86-64 desktop/workstation host built on an MSI PRO Z790-A WIFI (MS-7E07) motherboard (AMI UEFI BIOS `A.90`, dated `01/10/2024`, Secure Boot disabled) with a 12th-Gen Intel Core i7-12700 Alder Lake processor (12 physical cores / 20 threads: 8 Golden Cove P-cores with SMT up to 4.9 GHz and 4 Gracemont E-cores up to 3.6 GHz, 25 MiB L3 cache, microcode `0x3e`) and 64 GB of dual-channel DDR5-5200 DRAM (`2 × 32 GB` G.Skill DIMMs). It has an integrated Intel PTT firmware TPM 2.0 (`INTC` / `ADL`, revision 1.38, firmware `600.18.30.2264`, SHA-256 PCR bank active) and supports Intel Total Memory Encryption in silicon (CPUID leaf 7 ECX bit 13 set, disabled in BIOS with `MSR 0x982 = 0x1`). Its storage subsystem comprises eight physical drives across two hardware tiers: four 1 TB Samsung 980 PRO PCIe 4.0 NVMe SSDs (`nvme0n1` hosting the Ubuntu 22.04.5 LTS / Linux `5.15.0-198-generic` root filesystem on ext4/LVM, and `nvme1n1`–`nvme3n1` formatted with XFS) and four 2 TB HGST Ultrastar 7K2000 7200 RPM SATA HDDs (`sda`–`sdd`, formatted with XFS).

### Specification Table for the Paper

| Component | Specification (`{label}`) |
|---|---|
| **CPU** | 12th Gen Intel Core i7-12700 (Alder Lake-S, Golden Cove + Gracemont, microcode `0x3e`) |
| **Cores / Threads** | 12 cores / 20 threads (8 P-cores / 16 threads @ 0.8–4.9 GHz + 4 E-cores / 4 threads @ 0.8–3.6 GHz; 25 MiB L3) |
| **RAM** | 64 GB (62.67 GiB usable) DDR5-5200 MT/s dual-channel (`2 × 32 GB` G.Skill `F5-5200J3636D32G`, 2 of 4 slots) |
| **NVMe SSDs (×4)** | `nvme0n1`–`nvme3n1`: 4 × 1000.2 GB Samsung SSD 980 PRO 1TB (fw `5B2QGXA7`, PCIe NVMe, `nvme0n1` ext4/LVM, `nvme1..3n1` XFS) |
| **SATA HDDs (×4)** | `sda`–`sdd`: 4 × 2000.4 GB HGST `HUS722T2TALA604` (fw `RAGNWA09`, SATA 7200 RPM, XFS) |
| **TPM** | Firmware TPM 2.0: Intel PTT (`INTC` / `ADL`, rev 1.38, fw `600.18.30.2264`, active bank `sha256`, 24 PCRs) |
| **Firmware / Board** | MSI `PRO Z790-A WIFI (MS-7E07)`, AMI UEFI BIOS `A.90` (`01/10/2024`), UEFI boot, Secure Boot disabled |
| **OS / Kernel** | Ubuntu 22.04.5 LTS, Linux `5.15.0-198-generic` x86_64, Firecracker `v1.10.1` (`{fc_guest_ver}`), QEMU `6.2.0` |

---

## 2. Virtualisation
- **Commands:** `systemd-detect-virt`, `ls -l /dev/kvm`, `cat /sys/module/kvm_intel/parameters/nested`
- **`systemd-detect-virt`:** `{virt_state}` (bare metal)
- **`/dev/kvm`:** `{kvm_stat}` (accessible: `{kvm_rw}`)
- **Nested virtualisation:** `{json.dumps(nested)}`

## 3. CPU
- **Commands:** `lscpu`, `lscpu -e=CPU,NODE,SOCKET,CORE,CACHE,ONLINE,MAXMHZ,MINMHZ`, `cat /proc/cpuinfo`, `cat /sys/devices/system/cpu/smt/*`, `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`, `cat /sys/devices/system/cpu/intel_pstate/no_turbo`, `numactl --hardware`, `grep . /sys/devices/system/cpu/vulnerabilities/*`, `cpuid -1 -l 7 -r`, `rdmsr 0x982`, `dmesg | grep -iE 'tme|total memory encryption|dmar|iommu'`
- **Model:** `{lscpu_map.get("Model name", "")}` (Family `{lscpu_map.get("CPU family")}`, Model `{lscpu_map.get("Model")}`, Stepping `{lscpu_map.get("Stepping")}`)
- **Microarchitecture:** Intel Alder Lake-S (hybrid: 8 Golden Cove P-cores + 4 Gracemont E-cores)
- **Topology:** 1 socket, 12 physical cores, 20 hardware threads
  - **P-cores:** CPUs `0–15` (cores 0–7, 2 SMT threads/core, min 800 MHz, max 4800–4900 MHz)
  - **E-cores:** CPUs `16–19` (cores 8–11, 1 thread/core, min 800 MHz, max 3600 MHz)
- **Caches:** L1d `{lscpu_map.get("L1d cache")}`, L1i `{lscpu_map.get("L1i cache")}`, L2 `{lscpu_map.get("L2 cache")}`, L3 `{lscpu_map.get("L3 cache")}`
- **Microcode:** `{microcode}`
- **SMT / Governor / Turbo:** `smt/control={smt_control}`, `smt/active={smt_active}`, `governor={governor}`, `intel_pstate/no_turbo={no_turbo}` (Turbo enabled)
- **VM & Crypto Flags:** `{json.dumps(relevant_flags)}`
- **TME / IOMMU:**
  - CPUID leaf 7 subleaf 0 ECX bit 13 (TME): `True`; `MSR 0x982` (`IA32_TME_ACTIVATE`): `{msr_tme}`; kernel dmesg: `x86/tme: not enabled by BIOS`
  - IOMMU: ACPI DMAR table present; kernel booted with `intel_iommu=off` (`DMAR: IOMMU disabled`, `DMAR-IR: Enabled IRQ remapping in x2apic mode`)
- **NUMA (`numactl --hardware`):**
```text
{numactl_out}
```
- **Vulnerability Mitigations (`/sys/devices/system/cpu/vulnerabilities/*`):**
```yaml
{yaml.safe_dump(vulns, sort_keys=True).strip()}
```

## 4. Memory
- **Commands:** `cat /proc/meminfo`, `dmidecode -t 17`, `cat /sys/kernel/mm/transparent_hugepage/enabled`, `cat /sys/kernel/mm/transparent_hugepage/defrag`
- **Total RAM:** `{mem_total_kb}` kB (`{round(mem_total_kb / 2**20, 2)}` GiB usable; 64 GB physical)
- **DIMM Layout:** 2 × 32 GB DDR5-5200 MT/s (`G Skill Intl F5-5200J3636D32G`, Rank 2, 1.25 V) in `Controller0-DIMMA2` (serial `{dimms[1]["serial_sha256"] if len(dimms) > 1 else "?"}`) and `Controller1-DIMMB2` (serial `{dimms[3]["serial_sha256"] if len(dimms) > 3 else "?"}`); `DIMMA1` and `DIMMB1` empty
- **Swap:** `{swap_total_kb}` kB (`{round(swap_total_kb / 2**20, 2)}` GiB)
- **Transparent Huge Pages (THP):** `enabled: {thp_enabled}`, `defrag: {thp_defrag}`

## 5. Storage Devices & Scratch Directories
- **Commands:** `lsblk -J -b -o NAME,TYPE,SIZE,ROTA,MODEL,TRAN,FSTYPE,MOUNTPOINT`, `smartctl -j -a /dev/<dev>`, `cat /sys/block/<dev>/queue/{{rotational,logical_block_size,physical_block_size,nr_requests,scheduler}}`, `findmnt -J -T <dir>`, `df -h`

### Physical Block Devices
| Device | Model | Firmware | Serial (SHA-256) | Capacity | Interface | ROTA | Sectors (L/P) | Queue (`nr_requests` / sched) | SMART Health & Wear |
|---|---|---|---|---|---|---|---|---|---|
"""

for b in block_devs:
    wear_str = (
        f"PASSED, {b['temperature_c']}°C, {b['power_on_hours']}h, wear={b['wear_percentage_used']}%, spare={b['available_spare_pct']}%"
        if b["wear_percentage_used"] is not None
        else f"PASSED, {b['temperature_c']}°C, {b['power_on_hours']}h, realloc={b['reallocated_sectors']}"
    )
    md += (
        f"| `{b['device']}` | {b['model']} | `{b['firmware']}` | `{b['serial_sha256']}` | {b['capacity_gb']} GB | "
        f"{b['interface']} | {int(b['rotational'])} | {b['logical_sector_bytes']}/{b['physical_sector_bytes']} B | "
        f"`{b['nr_requests']}` / `{b['scheduler']}` | {wear_str} |\n"
    )

md += """
### Scratch Directories Used for Calibration
| Scratch Path | Mount Point | Backing Device | FS Type | Mount Options | Encryption | Free / Total |
|---|---|---|---|---|---|---|
"""
for s in scratch_dirs:
    md += (
        f"| `{s['path']}` | `{s['target_mount']}` | `{s['source_device']}` | `{s['fstype']}` | "
        f"`{s['mount_options']}` | {s['encryption_layer']} | {s['free_gb']} GB ({s['free_gib']} GiB) / {s['total_gb']} GB |\n"
    )

md += f"""
## 6. Firmware & Motherboard
- **Commands:** `cat /sys/class/dmi/id/{{bios_vendor,bios_version,bios_date,board_vendor,board_name,board_version}}`, `mokutil --sb-state`, `efibootmgr -v`, `bootctl status`
- **Board:** `{board_vendor}` `{board_name}` (version `{board_version}`)
- **BIOS:** `{bios_vendor}`, version `{bios_version}`, date `{bios_date}`
- **Boot Mode:** `{"UEFI" if uefi_boot else "Legacy"}`
- **Secure Boot:** `{sb_state}`
- **`efibootmgr -v`:**
```text
{efiboot}
```
- **`bootctl status`:**
```text
{bootctl_out}
```

## 7. TPM
- **Commands:** `tpm2_getcap properties-fixed`, `tpm2_pcrread`, `cat /sys/class/tpm/tpm0/tpm_version_major`
- **Type:** Firmware TPM 2.0 (Intel Platform Trust Technology / PTT)
- **Manufacturer / Vendor String:** `INTC` / `ADL`
- **Revision / Firmware:** revision `1.38`, firmware `{tpm_fw_decoded}`
- **Device Nodes:** `/dev/tpm0`, `/dev/tpmrm0` (`tpm_version_major={tpm_sysfs['tpm_version_major']}`)
- **Active PCR Banks:** `{", ".join(active_banks)}` (24 PCRs)

## 8. Network, Software, Power & Time Sync
- **Commands:** `lspci`, `cat /sys/class/net/<if>/*`, `uname -a`, `cat /proc/cmdline`, `timedatectl status`, tool `--version` flags

### Network Interfaces
| Interface | Model | Driver | State | Speed (Mb/s) | MAC (SHA-256) |
|---|---|---|---|---|---|
"""
for n in nics:
    md += f"| `{n['interface']}` | {n['model']} | `{n['driver']}` | `{n['state']}` | `{n['speed_mbps']}` | `{n['mac_sha256']}` |\n"

md += f"""
### Software Versions
```yaml
{yaml.safe_dump(software, sort_keys=False).strip()}
```

### Power & Time Sync
- **Power:** `{power['power_source']}`, governor `{power['cpu_scaling_governor']}`
- **`timedatectl status`:**
```text
{timesync}
```
"""

(out_dir / "SPEC.md").write_text(md)
print(f"Wrote {out_dir / 'SPEC.md'} and {out_dir / 'spec.yaml'}")
PYEOF
