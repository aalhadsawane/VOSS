"""Check a calibration bundle against docs/handoff/CALIBRATION_DATA_CONTRACT.md (plan V1 step 8).

``python -m tools.calibrate.check_bundle configs/calibration/measured/<bundle> [--spec calibration/specs/<host>]``

Errors (exit 1): a required entry is missing, not tagged ``measured``, or has fewer samples than the contract asks for;
a workload function is missing or lacks an input size of the ``sebs`` suite; the machine specification lacks a field.
Warnings (exit 0, each needs a sentence in the session report): handler times do not span under 1 ms to over 10 s
across all functions, or a handler time is more than 10x away from a published SeBS value where one is listed.
Numbers are printed with ``%.3g``: a value such as ``2.5e-05`` is never shown as ``2.5``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from tools.calibrate.suites.sebs import SIZES

# entry -> minimum samples (contract §2-4); boot entries need the image boots of Part C
REQUIRED: dict[str, int] = {
    "tpm2_quote": 200,
    "verify_s": 50,
    "key_release": 200,
    "fc_boot": 100,
    "fc_restore": 50,
    "fc_snapshot_create": 50,
    "boot_firmware": 10,
    "boot_loader": 10,
    "boot_quote": 10,
    "boot_verify": 10,
    "boot_first_tls": 10,
    "boot_total": 10,
}
CONSTANTS = ("decrypt_per_MB", "image_mem_mb", "verify_s_per_MB")
# contract §1, as written by tools/calibrate/spec.sh (dotted paths into spec.yaml)
SPEC_FIELDS = (
    "cpu.model",
    "cpu.cores_total",
    "cpu.threads_total",
    "cpu.governor",
    "cpu.no_turbo",
    "cpu.tme_cpuid_supported",
    "cpu.tme_bios_enabled",
    "memory.total_gib",
    "storage.devices",
    "tpm.manufacturer",
    "tpm.family",
    "tpm.firmware_version",
    "firmware.bios_version",
    "firmware.boot_mode",
    "firmware.secure_boot",
    "software.kernel_version",
    "software.firecracker",
    "virtualisation.systemd_detect_virt",
)
# Published SeBS handler times (seconds) per (function, SeBS class); class L, fill only from a checked source.
PUBLISHED: dict[tuple[str, str], float] = {}


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text()) if path.exists() else {}


def check_distributions(bundle: Path) -> list[str]:
    dists = _load(bundle / "distributions.yaml").get("distributions", {})
    fits = _load(bundle / "fits.yaml")
    errors = []
    for key, need in sorted(REQUIRED.items()):
        d = dists.get(key)
        if d is None or d.get("tag") != "measured":
            errors.append(f"{key}: missing or not measured")
        elif float((fits.get(key) or {}).get("n", 0)) < need:
            errors.append(f"{key}: n={(fits.get(key) or {}).get('n', 0)} < {need}")
    errors += [
        f"{key}: missing or not measured" for key in CONSTANTS if (dists.get(key) or {}).get("tag") != "measured"
    ]
    return errors


def check_functions(bundle: Path) -> tuple[list[str], list[str]]:
    fns = _load(bundle / "functions.yaml").get("functions", {})
    errors, warnings, times = [], [], []
    for fn, sizes in sorted(SIZES.items()):
        prof = fns.get(fn)
        if prof is None:
            errors.append(f"function {fn}: missing")
            continue
        got = prof.get("exec_by_size") or {}
        errors += [f"function {fn}: no handler time at size {s}" for s, _ in sizes if s not in got]
        for s, row in sorted(got.items()):
            t = float(row["median_s"])
            times.append(t)
            ref = PUBLISHED.get((fn, str(row.get("sebs_class", "-"))))
            if ref is not None and not ref / 10 <= t <= ref * 10:
                warnings.append(f"function {fn} size {s}: {t:.3g} s vs published {ref:.3g} s (more than 10x apart)")
        for key in ("rss_mb", "snapshot_mb", "init_s"):
            if prof.get(key) is None:
                errors.append(f"function {fn}: {key} missing")
    if times and not (min(times) < 1e-3 and max(times) > 10.0):
        warnings.append(f"handler times span {min(times):.3g}-{max(times):.3g} s, not <1 ms to >10 s (plan F2a)")
    return errors, warnings


def check_spec(spec_dir: Path) -> list[str]:
    spec = _load(spec_dir / "spec.yaml")
    if not spec:
        return [f"specification {spec_dir / 'spec.yaml'} missing"]
    errors = [f"specification: field '{f}' missing" for f in SPEC_FIELDS if _get(spec, f) is None]
    if _get(spec, "virtualisation.systemd_detect_virt") not in (None, "none"):
        errors.append("specification: not bare metal (systemd-detect-virt is not 'none')")
    return errors


def _get(d: dict[str, Any], dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("bundle", type=Path)
    p.add_argument("--spec", type=Path, default=None, help="calibration/specs/<host_label> directory")
    a = p.parse_args(argv)
    errors = check_distributions(a.bundle)
    fn_errors, warnings = check_functions(a.bundle)
    errors += fn_errors + (check_spec(a.spec) if a.spec is not None else [])
    for w in warnings:
        print(f"WARNING {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"{a.bundle}: {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
