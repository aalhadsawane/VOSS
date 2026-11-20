"""Machine specification from probes only (tools/calibrate/spec.py, CALIBRATION_DATA_CONTRACT.md §1): run against canned
outputs of a machine unlike the one spec.sh was first written on, and check nothing of that machine leaks in."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from tools.calibrate import nodes, spec
from tools.calibrate.check_bundle import check_spec
from tools.calibrate.scrub import scrub
from tools.calibrate.spec_parts import Probe

FORBIDDEN = ("MSI", "MS-7E07", "HGST", "Z790", "PTT", "i7-12700")
MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b|MAC\([0-9A-Fa-f]{12}")

LSCPU = """Architecture: x86_64
CPU(s): 16
Vendor ID: AuthenticAMD
Model name: AMD Ryzen 7 5800U with Radeon Graphics
CPU family: 25
Model: 80
Thread(s) per core: 2
Core(s) per socket: 8
Socket(s): 1
Stepping: 0
CPU max MHz: 4507.0000
CPU min MHz: 400.0000
L1d cache: 256 KiB (8 instances)
L1i cache: 256 KiB (8 instances)
L2 cache: 4 MiB (8 instances)
L3 cache: 16 MiB (1 instance)"""
LSCPU_E = "CPU NODE SOCKET CORE L1d:L1i:L2:L3 ONLINE MAXMHZ MINMHZ\n" + "\n".join(
    f"{i} 0 0 {i // 2} {i // 2}:{i // 2}:{i // 2}:0 yes 4507.0000 400.0000" for i in range(16)
)
CPUINFO = "processor\t: 0\nmicrocode\t: 0xa50000c\nflags\t\t: fpu sse2 svm npt aes avx2 sme sev rdrand smep smap\n"
DMI17 = """Memory Device
\tSize: 8 GB
\tLocator: DIMM 0
\tType: LPDDR4
\tSpeed: 4266 MT/s
\tConfigured Memory Speed: 4266 MT/s
\tManufacturer: Samsung
\tSerial Number: 12345678
\tPart Number: K4UBE3D4AB-MGCL
Memory Device
\tSize: 8 GB
\tLocator: DIMM 1
\tType: LPDDR4
\tConfigured Memory Speed: 4266 MT/s
\tManufacturer: Samsung
\tSerial Number: 87654321
\tPart Number: K4UBE3D4AB-MGCL
"""
SMART = {
    "model_name": "SAMSUNG MZVL2512HCJQ-00BL7",
    "firmware_version": "GXA7401Q",
    "serial_number": "S64KNX0R123456",
    "smart_status": {"passed": True},
    "power_on_time": {"hours": 1234},
    "nvme_smart_health_information_log": {"percentage_used": 3},
}
LSBLK = {"blockdevices": [{"name": "nvme0n1", "type": "disk", "size": 512110190592, "rota": False,
                           "model": "SAMSUNG MZVL2512HCJQ-00BL7", "tran": "nvme"}]}  # fmt: skip
EFIBOOT = (
    "BootCurrent: 0001\n"
    "Boot0001* ubuntu HD(1,GPT,0f4c2a1e-1b2c-4d5e-8f90-a1b2c3d4e5f6,0x800,0x100000)/File(\\shimx64.efi)\n"
    "Boot0002* IPv4 PXE PciRoot(0x0)/Pci(0x2,0x2)/MAC(8c8caa112233,0)/IPv4(0.0.0.0,0,DHCP)"
)
RUNS = {
    "lscpu": LSCPU,
    "lscpu -e=CPU,NODE,SOCKET,CORE,CACHE,ONLINE,MAXMHZ,MINMHZ": LSCPU_E,
    "dmesg": "AMD Memory Encryption Features active: SME\nAMD-Vi: IOMMU performance counters supported",
    "dmidecode -t 17": DMI17,
    "lsblk -J -b -o NAME,TYPE,SIZE,ROTA,MODEL,TRAN": json.dumps(LSBLK),
    "smartctl -j -a /dev/nvme0n1": json.dumps(SMART),
    "findmnt -J -T /home/u/scratch": json.dumps(
        {"filesystems": [{"target": "/", "source": "/dev/nvme0n1p2", "fstype": "ext4"}]}
    ),
    "lsblk -s -n -o TYPE /dev/nvme0n1p2": "part\ndisk",
    "mokutil --sb-state": "SecureBoot enabled",
    "efibootmgr -v": EFIBOOT,
    "lspci -s 0000:01:00.0": "01:00.0 Network controller: MEDIATEK Corp. MT7921 802.11ax wireless network adapter",
    "timedatectl status": "System clock synchronized: yes\nNTP service: active",
    '. /etc/os-release && echo "$PRETTY_NAME"': "Fedora Linux 40 (Workstation Edition)",
    "uname -v": "#1 SMP PREEMPT_DYNAMIC",
    "python3 --version": "Python 3.12.4",
}
FILES = {
    "/proc/cpuinfo": CPUINFO,
    "/proc/meminfo": "MemTotal:       15728640 kB\nSwapTotal:       8388608 kB",
    "/proc/cmdline": "BOOT_IMAGE=/vmlinuz root=UUID=0f4c2a1e-1b2c-4d5e-8f90-a1b2c3d4e5f7 amd_iommu=on ip=192.168.0.2",
    "/sys/class/dmi/id/bios_vendor": "LENOVO",
    "/sys/class/dmi/id/bios_version": "R1MET43W (1.13 )",
    "/sys/class/dmi/id/bios_date": "08/10/2023",
    "/sys/class/dmi/id/board_vendor": "LENOVO",
    "/sys/class/dmi/id/board_name": "20YN0001US",
    "/sys/class/dmi/id/board_version": "SDK0J40697 WIN",
    "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor": "performance",
    "/sys/devices/system/cpu/cpufreq/boost": "1",
    "/sys/block/nvme0n1/queue/rotational": "0",
    "/sys/block/nvme0n1/queue/scheduler": "[none] mq-deadline",
    "/sys/class/net/wlp1s0/address": "8c:8c:aa:11:22:33",
    "/sys/class/net/wlp1s0/operstate": "up",
    "/sys/class/net/wlp1s0/speed": "",
    "/sys/class/power_supply/BAT0/type": "Battery",
    "/sys/class/power_supply/AC/type": "Mains",
    "/sys/class/power_supply/AC/online": "1",
}
DIRS = {"/sys/class/net": ["lo", "wlp1s0"], "/sys/class/power_supply": ["AC", "BAT0"]}
LINKS = {"/sys/class/net/wlp1s0/device": "../../../0000:01:00.0",
         "/sys/class/net/wlp1s0/device/driver": "../../../bus/pci/drivers/mt7921e"}  # fmt: skip


class Laptop(Probe):
    """An AMD laptop with one NVMe disk and no TPM, from canned outputs."""

    def run(self, cmd: str) -> str:
        return RUNS.get(cmd, "")

    def read(self, path: str) -> str:
        return FILES.get(path, "")

    def exists(self, path: str) -> bool:
        return path in FILES or path in ("/dev/kvm", "/sys/firmware/efi", "/home/u/scratch")

    def listdir(self, path: str) -> list[str]:
        return DIRS.get(path, [])

    def readlink(self, path: str) -> str:
        return LINKS.get(path, "")

    def disk_usage(self, path: str) -> tuple[int, int]:
        return 512 * 10**9, 200 * 10**9

    def kernel(self) -> str:
        return "6.9.7-200.fc40.x86_64"


def test_spec_of_another_machine_has_only_its_own_values(tmp_path: Path) -> None:
    s = spec.collect(Laptop(), "node09-r7-5800u-16g-nvme", ["/home/u/scratch"], "/opt/assets")
    spec.write(s, tmp_path)
    text = (tmp_path / "SPEC.md").read_text() + (tmp_path / "spec.yaml").read_text()
    leaked = [w for w in FORBIDDEN if w in text]
    assert leaked == [], leaked
    assert not MAC.search(text), MAC.search(text)
    assert "192.168.0.2" not in text and "0f4c2a1e" not in text  # private IP and UUIDs scrubbed
    assert "S64KNX0R123456" not in text and "12345678" not in text  # serials hashed
    for probed in ("AMD Ryzen 7 5800U", "SAMSUNG MZVL2512HCJQ-00BL7", "LENOVO", "LPDDR4", "Fedora Linux 40"):
        assert probed in text
    y = yaml.safe_load((tmp_path / "spec.yaml").read_text())
    assert y["tpm"]["type"] == "none" and y["tpm"]["present"] is False
    assert "TPM 2.0" not in (tmp_path / "SPEC.md").read_text()
    assert y["cpu"]["cores_total"] == 8 and y["cpu"]["threads_total"] == 16
    assert y["cpu"]["sme_enabled"] is True and y["cpu"]["tme_cpuid_supported"] is False
    assert y["memory"]["nominal_gb"] == 16.0 and y["memory"]["speed_mts"] == 4266
    assert y["storage"]["devices"][0]["interface"] == "NVME" and not y["storage"]["devices"][0]["rotational"]
    assert y["power"]["power_source"].startswith("battery present")
    assert check_spec(tmp_path) == []  # every contract §1 field is present
    c = nodes.node_class(y)
    assert c.tpm == "none" and c.mem_encryption


def _getcap(maker: str, vendor: tuple[str, str], fw: tuple[str, str], rev: str) -> str:
    return (
        'TPM2_PT_FAMILY_INDICATOR:\n  raw: 0x322E3000\n  value: "2.0"\n'
        f"TPM2_PT_REVISION:\n  raw: 0x9F\n  value: {rev}\n"
        f'TPM2_PT_MANUFACTURER:\n  raw: 0x0\n  value: "{maker}"\nTPM2_PT_VENDOR_STRING_1:\n  raw: 0x0\n'
        f'  value: "{vendor[0]}"\nTPM2_PT_VENDOR_STRING_2:\n  raw: 0x0\n  value: "{vendor[1]}"\n'
        f"TPM2_PT_FIRMWARE_VERSION_1:\n  raw: {fw[0]}\nTPM2_PT_FIRMWARE_VERSION_2:\n  raw: {fw[1]}\n"
        "TPM2_PT_PCR_COUNT:\n  raw: 0x18\n"
    )


TPMS = {  # a discrete Infineon chip, and the AMD firmware TPM of a Ryzen laptop (node05-like)
    "discrete": (_getcap("IFX", ("SLB9", "670"), ("0x7003F", "0xAE100"), "1.59"), "Infineon SLB 9670 TPM 2.0"),
    "amd_ftpm": (_getcap("AMD", ("AMD", ""), ("0x3005E", "0x0"), "1.38"), "AMD fTPM 2.0 Device"),
}


@pytest.mark.parametrize("which", sorted(TPMS))
def test_a_tpm_is_described_from_its_own_probes(which: str, tmp_path: Path) -> None:
    """Type, manufacturer, vendor string, firmware and the ACPI description come from tpm2_getcap and sysfs."""
    cap, desc = TPMS[which]

    class WithTpm(Laptop):
        def run(self, cmd: str) -> str:
            if cmd == "tpm2_getcap properties-fixed":
                return cap
            if cmd == "tpm2_pcrread":
                return "  sha256:\n    0 : 0x00\n"
            return super().run(cmd)

        def read(self, path: str) -> str:
            return desc if path == "/sys/class/tpm/tpm0/device/description" else super().read(path)

        def exists(self, path: str) -> bool:
            return path == "/dev/tpmrm0" or super().exists(path)

    s = spec.collect(WithTpm(), "node09-r7-5800u-16g-nvme", ["/home/u/scratch"], "/opt/assets")
    spec.write(s, tmp_path)
    text = (tmp_path / "SPEC.md").read_text() + (tmp_path / "spec.yaml").read_text()
    assert [w for w in FORBIDDEN if w in text] == [] and not MAC.search(text)
    t = yaml.safe_load((tmp_path / "spec.yaml").read_text())["tpm"]
    assert t["sysfs_description"] == desc and desc in text and t["active_pcr_banks"] == ["sha256"]
    assert t["pcr_count"] == 24 and t["family"] == "2.0"
    if which == "discrete":
        assert (t["type"], t["manufacturer"], t["vendor_string"]) == ("discrete", "IFX", "SLB9670")
        assert t["firmware_version"] == "7.63.10.57600" and t["revision"] == "1.59"
    else:
        assert (t["type"], t["manufacturer"], t["vendor_string"]) == ("firmware (AMD fTPM)", "AMD", "AMD")
        assert t["firmware_version"] == "3.94.0.0" and t["revision"] == "1.38"
    assert nodes.node_class(yaml.safe_load((tmp_path / "spec.yaml").read_text())).tpm == (
        "discrete" if which == "discrete" else "firmware"
    )
    assert check_spec(tmp_path) == []


def test_scrub_hashes_identifiers_and_drops_private_addresses() -> None:
    text = "logged in: alice pts/1 (192.168.0.2) MAC 8c:8c:aa:11:22:33 wwn-0x5000c500a1b2c3d4 on box7 10.0.0.5 1.2.3"
    out = scrub(text, names=["alice", "box7"])
    assert "192.168.0.2" not in out and "10.0.0.5" not in out and "8c:8c" not in out and "5000c500" not in out
    assert "alice" not in out and "box7" not in out and "1.2.3" in out  # a version number stays
    assert scrub("8c:8c:aa:11:22:33", names=[]) == scrub("8C-8C-AA-11-22-33", names=[])  # one hash per identifier
