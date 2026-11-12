"""Render the host-specific parts of ``calibration/specs/<label>/SPEC.md`` (doc 10 §2, X-1).

``tools/calibrate/spec.sh`` probes the machine and writes a structured ``spec.yaml``; this module turns
that structure into the plain-language summary, the paper table, the CPU topology and the DIMM layout.
Keeping the rendering here (and out of the shell heredoc) means a spec for a new machine cannot silently
inherit the board, disks or TPM of the machine the harness was first written on.
"""

from __future__ import annotations

import os
import re
from typing import Any


def ranges(ids: list[int]) -> str:
    """Compact a sorted id list into ``0-3,8,10-11`` (used for CPU ids and device names)."""
    if not ids:
        return "?"
    parts: list[str] = []
    start = prev = ids[0]
    for value in ids[1:]:
        if value == prev + 1:
            prev = value
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = value
    parts.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(parts)


def _storage_groups(devices: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Group block devices by the class a paper table would name."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for dev in devices:
        interface = str(dev.get("interface", "")).upper()
        rotational = bool(dev.get("rotational"))
        if rotational:
            name = f"{interface} HDD" if interface else "HDD"
        elif interface == "NVME":
            name = "NVMe SSD"
        elif interface:
            name = f"{interface} SSD"
        else:
            name = "SSD"
        groups.setdefault(name, []).append(dev)
    return sorted(groups.items())


def _device_names(devices: list[dict[str, Any]]) -> str:
    """``nvme0n1``+``nvme1n1`` → ``nvme0-1n1`` when the names differ only by one number."""
    names = sorted(str(d.get("device", "")).removeprefix("/dev/") for d in devices)
    if len(names) <= 1:
        return ", ".join(f"`{n}`" for n in names)
    prefix = os.path.commonprefix(names)
    suffix = os.path.commonprefix([name[::-1] for name in names])[::-1]
    numbers: list[int] = []
    for name in names:
        end = len(name) - len(suffix) if suffix else len(name)
        middle = name[len(prefix) : end]
        if not middle.isdigit():
            return ", ".join(f"`{n}`" for n in names)
        numbers.append(int(middle))
    return f"`{prefix}{ranges(sorted(numbers))}{suffix}`"


def _size_phrase(devices: list[dict[str, Any]]) -> str:
    capacities = {float(d.get("capacity_gb") or 0) for d in devices}
    if len(devices) == 1:
        return f"{devices[0].get('capacity_gb')} GB"
    if len(capacities) == 1:
        return f"{len(devices)} × {capacities.pop()} GB"
    total = sum(capacities)
    return f"{total:.1f} GB total"


def _model(devices: list[dict[str, Any]]) -> str:
    models = sorted({str(d.get("model", "")).strip() for d in devices if d.get("model")})
    return " / ".join(models) or "unknown model"


def _plural(count: int, word: str) -> str:
    return word if count == 1 else f"{word}s"


def _storage_summary(devices: list[dict[str, Any]]) -> str:
    groups = _storage_groups(devices)
    if not groups:
        return "no local block devices"
    chunks: list[str] = []
    for name, devs in groups:
        chunks.append(f"{_size_phrase(devs)} {_model(devs)} ({name})")
    return " and ".join(chunks)


def _disk_sentence(spec: dict[str, Any]) -> str:
    devices = spec.get("storage", {}).get("devices", [])
    sentence = f"Its storage subsystem comprises {_storage_summary(devices)}"
    scratch = spec.get("storage", {}).get("scratch_directories", [])
    if scratch:
        first = scratch[0]
        sentence += (
            f"; the calibration scratch directory is on {first.get('source_device')} "
            f"({first.get('fstype')}, mount options `{first.get('mount_options')}`)"
        )
    return sentence + "."


def _cpu_summary(cpu: dict[str, Any]) -> str:
    cores = cpu.get("cores_total", "?")
    threads = cpu.get("threads_total", "?")
    text = f"{cpu.get('model', 'unknown CPU')} processor ({cores} physical cores / {threads} threads"
    hybrid = cpu.get("hybrid_topology") or {}
    if hybrid:
        text += (
            f": {hybrid.get('p_cores')} P-cores / {hybrid.get('p_threads')} threads "
            f"@ {hybrid.get('p_max_mhz')} MHz + {hybrid.get('e_cores')} E-cores / "
            f"{hybrid.get('e_threads')} threads @ {hybrid.get('e_max_mhz')} MHz"
        )
    text += f", {cpu.get('caches', {}).get('l3')} L3 cache, microcode `{cpu.get('microcode')}`)"
    return text


def _dimm_summary(memory: dict[str, Any]) -> str:
    dimms = [d for d in memory.get("dimms", []) if d.get("size") and "No Module" not in str(d.get("size"))]
    if not dimms:
        return "unknown DIMMs"
    sizes = [str(d.get("size")) for d in dimms]
    size_text = f"{len(sizes)} × {sizes[0]}" if len(set(sizes)) == 1 else " + ".join(sizes)
    first = dimms[0]
    detail = " ".join(part for part in (first.get("manufacturer"), first.get("part_number")) if part)
    return f"{size_text} {detail}".strip()


def _tpm_name(tpm: dict[str, Any]) -> str:
    if str(tpm.get("manufacturer", "")).startswith("INTC"):
        return "Intel PTT firmware TPM 2.0"
    return f"TPM {tpm.get('family', '2.0')}"


def _tpm_type(tpm: dict[str, Any]) -> str:
    article = "an" if _tpm_name(tpm)[0].lower() in "aeiou" else "a"
    return f"{article} {_tpm_name(tpm)}"


def _version(text: Any) -> str:
    match = re.search(r"version\s+(\S+)", str(text or ""))
    return match.group(1) if match else str(text or "unknown")


def _guest_assets(software: dict[str, Any]) -> str:
    assets = str(software.get("firecracker_guest_assets") or "")
    return f" (`{assets}`)" if assets else ""


def render_summary(spec: dict[str, Any]) -> str:
    """One paragraph naming this machine's own board, CPU, RAM, TPM and disks."""
    cpu = spec.get("cpu", {})
    memory = spec.get("memory", {})
    tpm = spec.get("tpm", {})
    firmware = spec.get("firmware", {})
    power = spec.get("power", {})
    form = "desktop/workstation" if "desktop" in str(power.get("power_source", "")) else "machine"
    boot = "UEFI" if firmware.get("boot_mode") == "UEFI" else "legacy"
    secure = "disabled" if "disabled" in str(firmware.get("secure_boot", "")).lower() else "enabled"
    vendor = str(firmware.get("board_vendor") or "")
    vendor_article = "an" if vendor[:1].lower() in "aeiou" else "a"
    memory_text = (
        f"{memory.get('nominal_gb', '?')} GB of {memory.get('channels_populated', '?')}-channel "
        f"{memory.get('type', 'unknown')}-{memory.get('speed_mts', '?')} DRAM "
        f"(`{_dimm_summary(memory)}`)"
    )
    tpm_text = (
        f"{_tpm_type(tpm)} (`{tpm.get('manufacturer')}` / `{tpm.get('vendor_string')}`, revision "
        f"`{tpm.get('revision')}`, firmware `{tpm.get('firmware_version')}`, "
        f"{', '.join(tpm.get('active_pcr_banks', []))} PCR bank active)"
    )
    tme = (
        "supports Intel Total Memory Encryption in silicon (CPUID leaf 7 ECX bit 13 set, "
        f"{'enabled' if cpu.get('tme_bios_enabled') else 'disabled in BIOS'} with "
        f"`MSR 0x982 = {cpu.get('tme_msr_0x982', '?')}`)"
        if cpu.get("tme_cpuid_supported")
        else "does not expose Intel Total Memory Encryption"
    )
    return (
        f"**Summary:** `{spec.get('host_label')}` is a bare-metal x86-64 {form} host built on "
        f"{vendor_article} {firmware.get('board_vendor')} {firmware.get('board_model')} "
        f"({firmware.get('board_version')}) motherboard ({firmware.get('bios_vendor')} {boot} BIOS "
        f"`{firmware.get('bios_version')}`, dated `{firmware.get('bios_date')}`, Secure Boot {secure}) "
        f"with a {_cpu_summary(cpu)} and {memory_text}. It has {tpm_text} and {tme}. "
        f"{_disk_sentence(spec)}"
    )


def _core_rows(cpu: dict[str, Any], memory: dict[str, Any]) -> list[str]:
    """CPU, core/thread and RAM rows."""
    hybrid = cpu.get("hybrid_topology") or {}
    if hybrid:
        core_text = (
            f"{cpu.get('cores_total')} cores / {cpu.get('threads_total')} threads "
            f"({hybrid.get('p_cores')} P-cores / {hybrid.get('p_threads')} threads @ "
            f"{cpu.get('base_min_mhz')}-{hybrid.get('p_max_mhz')} MHz + {hybrid.get('e_cores')} "
            f"E-cores / {hybrid.get('e_threads')} threads @ {cpu.get('base_min_mhz')}-"
            f"{hybrid.get('e_max_mhz')} MHz; {cpu.get('caches', {}).get('l3')} L3)"
        )
    else:
        core_text = f"{cpu.get('cores_total')} cores / {cpu.get('threads_total')} threads"
    return [
        f"| **CPU** | {cpu.get('model')} ({cpu.get('microarchitecture')}, microcode `{cpu.get('microcode')}`) |",
        f"| **Cores / Threads** | {core_text} |",
        (
            f"| **RAM** | {memory.get('nominal_gb')} GB ({memory.get('total_gib')} GiB usable) "
            f"{memory.get('type')}-{memory.get('speed_mts')} MT/s "
            f"{memory.get('channels_populated')}-channel (`{_dimm_summary(memory)}`, "
            f"{len(memory.get('dimms', []))} of {memory.get('slots_total')} slots) |"
        ),
    ]


def _storage_rows(spec: dict[str, Any]) -> list[str]:
    """One row per storage class present on the machine."""
    rows = []
    for name, devs in _storage_groups(spec.get("storage", {}).get("devices", [])):
        firmwares = sorted({str(d.get("firmware", "")) for d in devs if d.get("firmware")})
        rows.append(
            f"| **{name} (×{len(devs)})** | {_device_names(devs)}: {_size_phrase(devs)} "
            f"{_model(devs)} (fw `{' / '.join(firmwares) or 'unknown'}`, {name}) |"
        )
    return rows


def _system_rows(tpm: dict[str, Any], firmware: dict[str, Any], software: dict[str, Any]) -> list[str]:
    """TPM, firmware/board and OS rows."""
    secure = "disabled" if "disabled" in str(firmware.get("secure_boot", "")).lower() else "enabled"
    return [
        (
            f"| **TPM** | {_tpm_name(tpm)}: "
            f"(`{tpm.get('manufacturer')}` / `{tpm.get('vendor_string')}`, rev `{tpm.get('revision')}`, "
            f"fw `{tpm.get('firmware_version')}`, active bank `{', '.join(tpm.get('active_pcr_banks', []))}`, "
            f"{tpm.get('pcr_count')} PCRs) |"
        ),
        (
            f"| **Firmware / Board** | {firmware.get('board_vendor')} `{firmware.get('board_model')}` "
            f"({firmware.get('board_version')}), {firmware.get('bios_vendor')} {firmware.get('boot_mode')} "
            f"BIOS `{firmware.get('bios_version')}` (`{firmware.get('bios_date')}`), Secure Boot {secure} |"
        ),
        (
            f"| **OS / Kernel** | {software.get('distro')}, Linux `{software.get('kernel')}` x86_64, "
            f"Firecracker `{software.get('firecracker')}`"
            f"{_guest_assets(software)}, QEMU `{_version(software.get('qemu'))}` |"
        ),
    ]


def render_table(spec: dict[str, Any]) -> str:
    """The specification table used in the paper (one row per storage class)."""
    rows = [
        *_core_rows(spec.get("cpu", {}), spec.get("memory", {})),
        *_storage_rows(spec),
        *_system_rows(spec.get("tpm", {}), spec.get("firmware", {}), spec.get("software", {})),
    ]
    return "\n".join(rows)


def render_topology(cpu: dict[str, Any]) -> str:
    """CPU topology bullet used in section 3."""
    hybrid = cpu.get("hybrid_topology") or {}
    base = (
        f"- **Topology:** {cpu.get('sockets')} socket, {cpu.get('cores_total')} physical cores, "
        f"{cpu.get('threads_total')} hardware threads"
    )
    if not hybrid:
        return base
    return (
        f"{base}\n"
        f"  - **P-cores:** CPUs `{hybrid.get('p_cpus')}` "
        f"({hybrid.get('p_cores')} cores, 2 SMT threads/core, min {cpu.get('base_min_mhz')} MHz, "
        f"max {hybrid.get('p_max_mhz')} MHz)\n"
        f"  - **E-cores:** CPUs `{hybrid.get('e_cpus')}` "
        f"({hybrid.get('e_cores')} cores, 1 thread/core, min {cpu.get('base_min_mhz')} MHz, "
        f"max {hybrid.get('e_max_mhz')} MHz)"
    )


def render_dimms(memory: dict[str, Any]) -> str:
    """DIMM layout line: populated slots first, then the empty ones."""
    populated = [d for d in memory.get("dimms", []) if d.get("size") and "No Module" not in str(d.get("size"))]
    empty = list(memory.get("empty_slots", []))
    if not populated:
        return "unknown"
    parts = []
    for dimm in populated:
        parts.append(
            f"{dimm.get('size')} {dimm.get('type')}-{dimm.get('configured_speed') or dimm.get('speed')} "
            f"({dimm.get('manufacturer')} {dimm.get('part_number')}, {dimm.get('rank')}) in "
            f"`{dimm.get('locator')}` (serial `{dimm.get('serial_sha256')}`)"
        )
    text = "; ".join(parts)
    if empty:
        text += "; " + ", ".join(f"`{slot}`" for slot in empty) + " empty"
    return text
