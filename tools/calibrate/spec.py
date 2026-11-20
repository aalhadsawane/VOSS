"""Machine specification of a calibration node (CALIBRATION_DATA_CONTRACT.md §1; NODE_PLAN.md §5 step 2):
``calibration/specs/<label>/spec.yaml`` and ``SPEC.md``, written by ``spec.sh``.

Every field comes from a probe of this machine (``lscpu``, ``/proc``, ``/sys``, ``dmidecode``, ``smartctl``,
``lsblk``, ``findmnt``, ``dmesg``, ``tpm2_getcap``, ``/dev/tpm*``); a value no probe gives is written as
``unknown (<reason>)``, never as text from another machine. Serial numbers and MAC addresses are hashed, and the
whole output goes through ``scrub.scrub`` (MAC, UUID, WWN, private IP, hostname, user names). All probing goes through
``Probe``, so ``tests/unit/test_spec.py`` can run this against canned outputs of another machine.
Read-only and standard library plus PyYAML.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from tools.calibrate.scrub import scrub
from tools.calibrate.spec_devices import network, software, tpm
from tools.calibrate.spec_parts import Probe, cpu, firmware, memory, storage, virtualisation


def collect(pr: Probe, label: str, scratch: list[str], assets: str) -> dict[str, Any]:
    """The specification as data: every field from ``pr``."""
    c = cpu(pr)
    return {
        "host_label": label,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hostname_redacted": "HOST",
        "virtualisation": virtualisation(pr),
        "cpu": c,
        "memory": memory(pr),
        "storage": storage(pr, scratch),
        "firmware": firmware(pr),
        "tpm": tpm(pr),
        "network": network(pr),
        "software": software(pr, assets),
        "power": power(pr, c),
        "time_sync": pr.run("timedatectl status").splitlines(),
    }


def power(pr: Probe, c: dict[str, Any]) -> dict[str, Any]:
    supplies = pr.listdir("/sys/class/power_supply")
    kinds = {s: pr.read(f"/sys/class/power_supply/{s}/type") or "unknown" for s in supplies}
    online = [pr.read(f"/sys/class/power_supply/{s}/online") for s, k in kinds.items() if k == "Mains"]
    if "Battery" in kinds.values():
        source = "battery present; mains online" if "1" in online else "battery present; mains not reported online"
    else:
        source = "no battery in /sys/class/power_supply (mains)"
    return {"power_source": source, "power_supplies": kinds, "cpu_scaling_governor": c["governor"]}


def _hz(mhz: Any) -> str:
    return f"{float(mhz) / 1000:.1f} GHz" if isinstance(mhz, int | float) else str(mhz)


def summary(s: dict[str, Any]) -> str:
    """One paragraph, built only from the fields of ``s``."""
    c, m, f, t = s["cpu"], s["memory"], s["firmware"], s["tpm"]
    kinds = "; ".join(f"{k['cores']} cores / {k['threads']} threads up to {_hz(k['max_mhz'])}" for k in c["core_kinds"])
    disks = Counter(f"{d['model']} ({d['interface']}, {d['capacity_gb']} GB)" for d in s["storage"]["devices"])
    disk_txt = ", ".join(f"{n} x {k}" for k, n in sorted(disks.items())) or "no disks reported"
    tpm_txt = (
        "no TPM (no /dev/tpm0 or /dev/tpmrm0)"
        if t["type"] == "none"
        else (
            f"a {t['type']} TPM {t['family']} (manufacturer `{t['manufacturer']}`, firmware `{t['firmware_version']}`)"
        )
    )
    kind = "bare-metal" if s["virtualisation"]["systemd_detect_virt"] == "none" else "virtual"
    slots = f"{m['dimms_populated']} of {m['slots_total']} slots"
    mem = f"{m['nominal_gb']} GB {m['type']} ({m['total_gib']} GiB usable, {slots})"
    enc = (
        f"TME in CPUID {c['tme_cpuid_supported']}, enabled by firmware {c['tme_bios_enabled']}, "
        f"SME in CPUID {c['sme_cpuid_supported']}"
    )
    return (
        f"`{s['host_label']}` is a {kind} x86-64 machine: `{f['board_vendor']}` `{f['board_model']}` board, "
        f"`{f['bios_vendor']}` firmware `{f['bios_version']}` ({f['bios_date']}, {f['boot_mode']}, Secure Boot: "
        f"{f['secure_boot']}); CPU `{c['model']}` ({c['cores_total']} cores / {c['threads_total']} threads; {kinds}; "
        f"microcode `{c['microcode']}`); {mem}; storage: {disk_txt}; {tpm_txt}; memory encryption: {enc}."
    )


def table(s: dict[str, Any]) -> str:
    c, m, f, t, sw = s["cpu"], s["memory"], s["firmware"], s["tpm"], s["software"]
    rows = [
        (
            "CPU",
            f"{c['model']} (family {c['family']}, model {c['model_id']}, stepping {c['stepping']}, microcode "
            f"`{c['microcode']}`)",
        ),
        ("Cores / threads", f"{c['cores_total']} / {c['threads_total']}; L3 {c['caches']['l3']}"),
        (
            "RAM",
            f"{m['nominal_gb']} GB {m['type']} at {m['speed_mts']} MT/s ({m['dimms_populated']} of "
            f"{m['slots_total']} slots; {m['total_gib']} GiB usable)",
        ),
    ]
    rows += [
        (
            f"Disk `{d['device']}`",
            f"{d['model']} ({d['interface']}, {d['capacity_gb']} GB, rotational "
            f"{d['rotational']}, firmware `{d['firmware']}`)",
        )
        for d in s["storage"]["devices"]
    ]
    rows.append(
        (
            "TPM",
            "none"
            if t["type"] == "none"
            else f"{t['type']}, `{t['manufacturer']}` {t['vendor_string']}, "
            f"family {t['family']}, revision {t['revision']}, firmware `{t['firmware_version']}`",
        )
    )
    rows.append(
        (
            "Firmware / board",
            f"`{f['board_vendor']}` `{f['board_model']}`, `{f['bios_vendor']}` "
            f"`{f['bios_version']}` ({f['bios_date']}), {f['boot_mode']}, Secure Boot {f['secure_boot']}",
        )
    )
    rows.append(("OS / kernel", f"{sw['distro']}, Linux `{sw['kernel']}`, Firecracker `{sw['firecracker']}`"))
    return "| Component | Specification |\n|---|---|\n" + "".join(f"| {a} | {b} |\n" for a, b in rows)


def render(s: dict[str, Any]) -> str:
    """SPEC.md: the summary, the paper table and every probed section as YAML (no hand-written prose)."""
    parts = [
        f"# Machine specification: `{s['host_label']}`",
        "",
        "Generated by `tools/calibrate/spec.sh` from probes of "
        "this machine; `unknown (...)` marks a value no probe gave (fill it by hand only with the human).",
        "",
        "## 1. Summary",
        "",
        summary(s),
        "",
        "## 2. Paper table",
        "",
        table(s),
    ]
    for i, key in enumerate(
        ("virtualisation", "cpu", "memory", "storage", "firmware", "tpm", "network", "software", "power", "time_sync"),
        start=3,
    ):
        parts += [
            f"## {i}. {key.replace('_', ' ').capitalize()}",
            "",
            "```yaml",
            yaml.safe_dump(s[key], sort_keys=False, width=120).strip(),
            "```",
            "",
        ]
    return "\n".join(parts) + "\n"


def write(spec: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.yaml").write_text(scrub(yaml.safe_dump(spec, sort_keys=False, width=120)))
    (out / "SPEC.md").write_text(scrub(render(spec)))


def main(argv: list[str] | None = None) -> int:
    a = sys.argv[1:] if argv is None else argv
    if len(a) < 2:
        print("usage: python -m tools.calibrate.spec <label> <out_dir> [scratch_dir ...]", file=sys.stderr)
        return 2
    assets = os.environ.get("VOSS_ASSETS", str(Path.home() / "voss-calib" / "assets"))
    spec = collect(Probe(), a[0], a[2:], assets)
    write(spec, Path(a[1]))
    print(json.dumps({"wrote": [str(Path(a[1]) / "SPEC.md"), str(Path(a[1]) / "spec.yaml")]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
