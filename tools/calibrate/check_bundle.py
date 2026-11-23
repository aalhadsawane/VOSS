"""Check a calibration bundle against docs/handoff/CALIBRATION_DATA_CONTRACT.md (plan V1 step 8).

``python -m tools.calibrate.check_bundle configs/calibration/measured/<bundle> [--spec calibration/specs/<host>]``
``[--shared-from configs/calibration/measured/<reference>]``

Errors (exit 1): an entry the simulator reads (``simulator_entries``: every ``measured/<name>`` of
``configs/substrates/*.yaml`` and every bundle key read in ``voss/``) or a contract entry is missing, not tagged
``measured`` (the bundle then holds the placeholder's literature/assumed value, guardrails 28-29), or has fewer
samples than the contract asks for; a measured disk speed of the bundle's tier is missing; a workload function is
missing or lacks an input size of the ``sebs`` suite; the machine specification lacks a field.
``--shared-from`` accepts the TPM entries a class did not measure from the reference bundle (D-107) and prints
them as ``SHARED``; every other missing entry is still an error.
Warnings (exit 0, each needs a sentence in the session report): handler times do not span under 1 ms to over 10 s
across all functions, or a handler time is more than 10x away from a published SeBS value where one is listed.
Numbers are printed with ``%.3g``: a value such as ``2.5e-05`` is never shown as ``2.5``.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml
from voss.world.machines import TPM_KEYS

from tools.calibrate.suites.sebs import SIZES

REPO = Path(__file__).resolve().parents[2]
# entry -> minimum samples (contract §2-4). Constants count the samples their median was taken over.
REQUIRED: dict[str, int] = {
    "tpm2_quote": 200,
    "verify_s": 50,
    "kbs_check_s": 200,
    "fc_boot": 100,
    "fc_restore": 50,
    "fc_snapshot_create": 50,
    "dispatch": 200,
    "snapshot_touched_frac": 100,  # 10 restores of each of the ten functions on the bundle's tier
    "reboot_to_kernel": 10,
    "appliance_userspace": 10,
    "verify_s_per_MB": 20,
    "tpm2_unseal": 50,
    "key_release": 200,
    "decrypt_per_MB": 1,
}
# on/off ratios: measured only when both phases ran on the node (a BIOS change, human approval; contract §6). The
# simulator does not read them (D-104: memory encryption is not modelled), so they are reported, not demanded.
RATIOS = ("tme_cpu_factor", "tme_mem_factor")
HARDWARE = ("ssd_read_MBps", "ssd_write_MBps")  # the bundle tier's disk speeds (hardware class C0)
_CODE_REF = re.compile(
    r"""bundle(?:\[|\.get\()\s*["']([A-Za-z0-9_]+)["']|["']([A-Za-z0-9_]+)["']\s+in\s+(?:self\.)?bundle"""
)


def simulator_entries(repo: Path = REPO) -> set[str]:
    """Bundle entries the simulator reads: substrate ``measured/<name>`` references and keys read in ``voss/``."""
    refs: set[str] = set()
    for sub in sorted((repo / "configs" / "substrates").glob("*.yaml")):
        refs |= set(re.findall(r"measured/([A-Za-z0-9_]+)", sub.read_text()))
    for py in sorted((repo / "voss").rglob("*.py")):
        refs |= {a or b for a, b in _CODE_REF.findall(py.read_text())}
    return refs


def unmeasured(dists: dict[str, Any], repo: Path = REPO) -> list[str]:
    """Entries the simulator reads that the bundle does not hold as ``measured`` (guardrails 28, 29)."""
    return sorted(k for k in simulator_entries(repo) if (dists.get(k) or {}).get("tag") != "measured")


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


def _missing(key: str, d: dict[str, Any] | None) -> str:
    held = f"the bundle holds the placeholder, tag {d.get('tag')}" if d else "absent from the bundle"
    why = "; needs tme --phase on and --phase off on this node (BIOS change, human approval)" if key in RATIOS else ""
    return f"{key}: missing, not measured ({held}{why})"


def check_distributions(
    bundle: Path, shared_from: Path | None = None, shared_out: list[str] | None = None
) -> list[str]:
    """Errors of one bundle; ``shared_from`` supplies the TPM entries D-107 shares with the reference class."""
    dists = _load(bundle / "distributions.yaml").get("distributions", {})
    fits = _load(bundle / "fits.yaml")
    ref = _load(shared_from / "distributions.yaml").get("distributions", {}) if shared_from else {}
    ref_fits = _load(shared_from / "fits.yaml") if shared_from else {}
    errors = []
    for key in sorted({*REQUIRED, *simulator_entries()}):
        d = dists.get(key)
        if d is None or d.get("tag") != "measured":
            r = ref.get(key)
            n = float((ref_fits.get(key) or {}).get("n", 0))
            if (
                key in TPM_KEYS
                and r is not None
                and r.get("tag") == "measured"
                and (key not in REQUIRED or n >= REQUIRED[key])
            ):
                if shared_out is not None:
                    shared_out.append(f"{key}: shared from {shared_from}")
                continue
            errors.append(_missing(key, d))
        elif key in REQUIRED and float((fits.get(key) or {}).get("n", 0)) < REQUIRED[key]:
            errors.append(f"{key}: n={(fits.get(key) or {}).get('n', 0)} < {REQUIRED[key]}")
    hw = (_load(bundle / "hardware.yaml").get("classes") or {}).get("C0") or {}
    errors += [f"hardware C0 {f}: missing, not measured" for f in HARDWARE if f not in hw]
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
    p.add_argument(
        "--shared-from",
        type=Path,
        default=None,
        help="reference bundle whose measured TPM entries this class shares (D-107)",
    )
    a = p.parse_args(argv)
    shared: list[str] = []
    errors = check_distributions(a.bundle, a.shared_from, shared)
    fn_errors, warnings = check_functions(a.bundle)
    errors += fn_errors + (check_spec(a.spec) if a.spec is not None else [])
    for s in shared:
        print(f"SHARED {s}")
    for w in warnings:
        print(f"WARNING {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"{a.bundle}: {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
