"""P9/X-1 hosts: the generated SPEC.md must describe the probed machine, not the first host it ran on."""

from __future__ import annotations

from typing import Any

from tools.calibrate.spec_md import ranges, render_dimms, render_summary, render_table, render_topology


def _cpu(model: str = "12th Gen Intel(R) Core(TM) i7-12700") -> dict[str, Any]:
    return {
        "model": model,
        "microarchitecture": "Intel Alder Lake-S (hybrid: Golden Cove P-cores + Gracemont E-cores)",
        "cores_total": 12,
        "threads_total": 20,
        "base_min_mhz": 800.0,
        "microcode": "0x3e",
        "caches": {"l3": "25 MiB"},
        "hybrid_topology": {
            "p_cores": 8,
            "p_threads": 16,
            "p_cpus": "0-15",
            "p_max_mhz": 4900.0,
            "e_cores": 4,
            "e_threads": 4,
            "e_cpus": "16-19",
            "e_max_mhz": 3600.0,
        },
        "tme_cpuid_supported": True,
        "tme_bios_enabled": False,
        "tme_msr_0x982": "1",
    }


def _memory() -> dict[str, Any]:
    dimm = {
        "size": "32 GB",
        "type": "DDR5",
        "speed": "5200 MT/s",
        "configured_speed": "5200 MT/s",
        "manufacturer": "G Skill Intl",
        "part_number": "F5-5200J3636D32G",
        "rank": "2",
        "locator": "Controller0-DIMMA2",
        "serial_sha256": "sha256:1111111111",
    }
    return {
        "nominal_gb": 64,
        "total_gib": 62.45,
        "type": "DDR5",
        "speed_mts": 5200,
        "channels_populated": 2,
        "slots_total": 4,
        "dimms": [dimm, dimm | {"locator": "Controller1-DIMMB2", "serial_sha256": "sha256:2222222222"}],
        "empty_slots": ["DIMMA1", "DIMMB1"],
    }


def _spec(*, board: str, vendor: str, bios: str, devices: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "host_label": "test-host",
        "cpu": _cpu(),
        "memory": _memory(),
        "storage": {
            "devices": devices,
            "scratch_directories": [
                {
                    "path": "/home/USER/scratch",
                    "source_device": "/dev/mapper/vg-lv",
                    "fstype": "ext4",
                    "mount_options": "rw,relatime",
                }
            ],
        },
        "tpm": {
            "manufacturer": "INTC",
            "vendor_string": "ADL",
            "type": "Firmware TPM 2.0 (Intel PTT)",
            "family": "2.0",
            "revision": "1.38",
            "firmware_version": "600.18.30.2307 (raw 0x2580012/0x1E0903)",
            "active_pcr_banks": ["sha256"],
            "pcr_count": 24,
        },
        "firmware": {
            "board_vendor": vendor,
            "board_model": board,
            "board_version": "Rev 1.xx",
            "bios_vendor": "American Megatrends Inc.",
            "bios_version": bios,
            "bios_date": "03/15/2024",
            "boot_mode": "UEFI",
            "secure_boot": "SecureBoot disabled",
        },
        "software": {
            "distro": "Ubuntu 22.04.5 LTS",
            "kernel": "5.15.0-198-generic",
            "firecracker": "Firecracker v1.10.1",
            "firecracker_guest_assets": "vmlinux-6.1.102",
            "qemu": "QEMU emulator version 6.2.0",
        },
        "power": {"power_source": "AC mains (desktop PSU; no battery in /sys/class/power_supply)"},
    }


def _nvme(name: str) -> dict[str, Any]:
    return {
        "device": f"/dev/{name}",
        "model": "Samsung SSD 980 PRO 1TB",
        "capacity_gb": 1000.2,
        "interface": "NVME",
        "rotational": False,
        "firmware": "5B2QGXA7",
    }


def _hdd(name: str) -> dict[str, Any]:
    return {
        "device": f"/dev/{name}",
        "model": "HGST HUS722T2TAL",
        "capacity_gb": 2000.4,
        "interface": "SATA",
        "rotational": True,
        "firmware": "RAGNWA09",
    }


def test_summary_uses_the_probed_board_and_storage() -> None:
    spec = _spec(
        board="PRIME Z790-P WIFI",
        vendor="ASUSTeK COMPUTER INC.",
        bios="1645",
        devices=[_nvme("nvme0n1"), _nvme("nvme1n1")],
    )
    summary = render_summary(spec)
    assert "ASUSTeK COMPUTER INC." in summary
    assert "PRIME Z790-P WIFI" in summary
    assert "2 × 1000.2 GB Samsung SSD 980 PRO 1TB" in summary
    assert "MSI" not in summary
    assert "HGST" not in summary
    assert "four 1 TB" not in summary


def test_table_lists_one_row_per_storage_class() -> None:
    spec = _spec(
        board="PRO Z790-A WIFI (MS-7E07)",
        vendor="Micro-Star International Co., Ltd.",
        bios="A.90",
        devices=[_nvme("nvme0n1"), _nvme("nvme1n1"), _nvme("nvme2n1"), _nvme("nvme3n1"), _hdd("sda"), _hdd("sdb")],
    )
    table = render_table(spec)
    assert "**NVMe SSD (×4)**" in table
    assert "**SATA HDD (×2)**" in table
    assert "`nvme0-3n1`" in table
    assert "`sda`, `sdb`" in table  # no numeric suffix: list them
    assert "PRO Z790-A WIFI" in table
    assert "Firecracker `Firecracker v1.10.1`" in table


def test_storage_classes_are_ordered_and_singular() -> None:
    spec = _spec(board="B", vendor="V", bios="1", devices=[_hdd("sda")])
    summary = render_summary(spec)
    assert "2000.4 GB HGST HUS722T2TAL (SATA HDD)" in summary
    assert "SATA HDDs" not in summary


def test_topology_and_dimms_are_derived() -> None:
    topology = render_topology(_cpu())
    assert "CPUs `0-15`" in topology
    assert "CPUs `16-19`" in topology
    dimms = render_dimms(_memory())
    assert "Controller0-DIMMA2" in dimms
    assert "DIMMA1" in dimms
    assert "empty" in dimms


def test_ranges_compacts_ids() -> None:
    assert ranges([0, 1, 2, 3, 8, 10, 11]) == "0-3,8,10-11"
    assert ranges([5]) == "5"
    assert ranges([]) == "?"


def test_non_intel_tpm_is_not_called_intel_ptt() -> None:
    spec = _spec(board="B", vendor="V", bios="1", devices=[_nvme("nvme0n1")])
    spec["tpm"] = spec["tpm"] | {"manufacturer": "IFX", "vendor_string": "SLB9670"}
    summary = render_summary(spec)
    assert "Intel PTT" not in summary
    assert "TPM 2.0" in summary
