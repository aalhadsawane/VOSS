"""Measured machine data for the paper, from the merged calibration bundles only (plan V9.4; markers T03-T05, T07,
T09, T13, T26, T44, T49 in the manuscript).

The three fleet classes are the bundles of ``configs/machines.yaml``. A bundle carries the machine's specification
(``meta.yaml``), the fitted distribution of every measured step (``fits.yaml`` and ``distributions.yaml``) and the
per-function execution times and co-run slowdowns (``functions.yaml``). The power-on to attested-worker time is
computed from the raw appliance records of the machine's session boots; a class whose machine has no TPM takes the
reference machine's measured TPM steps (D-107), which is recorded in the table caption.

``values`` sets the macros; ``machines_table``, ``costs_table`` and ``capacity_table`` return the rows of the
generated tables. Analysis reads logs and bundles only (AGENTS.md rule 10).
"""

from __future__ import annotations

import json
import re
import statistics
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import yaml
from voss.core.paths import REPO_ROOT

MEASURED = REPO_ROOT / "configs" / "calibration" / "measured"
RAW = REPO_ROOT / "calibration" / "raw"
REFERENCE = "node02-i7-12700-64g-nvme_nvme"

# bundle -> (label in the paper, machine it ran on)
CLASSES: tuple[tuple[str, str, str], ...] = (
    ("node02-i7-12700-64g-nvme_nvme", "i7-12700, NVMe", "node02"),
    ("node02-i7-12700-64g-nvme_hdd", "i7-12700, SATA HDD", "node02"),
    ("node04-i7-4790s-8g-hdd_hdd", "i7-4790S, SATA HDD", "node04"),
)
MACHINES = tuple(dict.fromkeys(machine for _, _, machine in CLASSES))
FLEET = REPO_ROOT / "configs" / "machines.yaml"


def fleet_bundles() -> list[str]:
    """The bundles ``configs/machines.yaml`` gives the fleet, in order."""
    config = _yaml(FLEET)
    return [str(bundle) for bundle in config["scenario"]["machines"]["bundles"]]


def _yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    return data


def meta(bundle: str) -> dict[str, Any]:
    return _yaml(MEASURED / bundle / "meta.yaml")


def distributions(bundle: str) -> dict[str, Any]:
    return cast(dict[str, Any], _yaml(MEASURED / bundle / "distributions.yaml")["distributions"])


def functions(bundle: str) -> dict[str, Any]:
    return cast(dict[str, Any], _yaml(MEASURED / bundle / "functions.yaml")["functions"])


def _median_of(dist: dict[str, Any]) -> float:
    """Median of an empirical distribution (middle quantile) or of a fitted one."""
    q = dist.get("quantiles")
    if q:
        return float(q[len(q) // 2])
    return float(dist["median"])


def measured(bundle: str, key: str) -> float:
    """Median of ``key`` if this class measured it, else the reference machine's measured median (D-107)."""
    dist = distributions(bundle)[key]
    if dist.get("tag") == "measured":
        return _median_of(dist)
    return _median_of(distributions(REFERENCE)[key])


def boots(bundle: str) -> list[dict[str, float]]:
    """The machine's session boots from the raw appliance records: one dict per ``reboot_to_kernel``."""
    raw_files = meta(bundle)["raw_files"]
    paths = sorted(RAW / k for k in raw_files if "/appliance/" in k and k.endswith("records.jsonl"))
    out: list[dict[str, float]] = []
    cur: dict[str, float] | None = None
    for path in paths:
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record["probe"] == "reboot_to_kernel":
                if cur:
                    out.append(cur)
                cur = {}
            if cur is not None:
                cur[str(record["probe"])] = float(record["value"])
    if cur:
        out.append(cur)
    return out


def attestation_s(bundle: str) -> float:
    """Median time from agent ready to verifier acceptance in the machine's own session boots."""
    rows = [b["appliance_attested"] - b["appliance_userspace"] for b in boots(bundle) if "appliance_attested" in b]
    return float(statistics.median(rows))


def power_on_s(bundle: str) -> float:
    """Median power-on to verifier acceptance. The machine's own attestation when it measured one, else its boot plus
    the reference machine's measured attestation step (D-107)."""
    values = []
    for boot in boots(bundle):
        if "appliance_attested" in boot:
            values.append(boot["reboot_to_kernel"] + boot["appliance_attested"])
        else:
            values.append(boot["reboot_to_kernel"] + boot["appliance_userspace"] + attestation_s(REFERENCE))
    return float(statistics.median(values))


def cpu_label(bundle: str) -> str:
    name = str(meta(bundle)["host"]["cpu_model"])
    name = re.sub(r"^\d+(?:st|nd|rd|th) Gen ", "", name)
    name = name.replace("(R)", "").replace("(TM)", "")
    name = re.sub(r"\s+CPU @.*$", "", name)
    return " ".join(name.split())


def cores(bundle: str) -> int:
    return int(meta(bundle)["host"]["cores"])


def threads(bundle: str) -> int:
    return int(meta(bundle)["host"]["threads"])


def mem_gib(bundle: str) -> float:
    return float(meta(bundle)["host"]["mem_kb"]) / 1024**2


def disk_label(bundle: str) -> str:
    """The disk the bundle ran on (the bundle name's suffix), with its model and size."""
    tier = bundle.rsplit("_", 1)[-1]
    disk = next(d for d in meta(bundle)["host"]["disks"] if bool(d["rotational"]) == (tier == "hdd"))
    model, size = str(disk["model"]), float(disk["size_gb"])
    model = re.sub(r"(\d)(TB|GB)\b", r"\1 \2", model)
    label = f"{size / 1000:.0f} TB" if size >= 1000 else f"{size:.0f} GB"
    if not re.search(r"\d+\s*(?:GB|TB)", model, re.IGNORECASE):
        model = f"{model} {label}"
    return f"{model} ({'SATA' if disk['rotational'] else 'NVMe'})"


def tpm_label(bundle: str) -> str:
    vendor = str(meta(bundle)["host"].get("tpm_vendor") or "")
    return "Intel PTT (firmware)" if vendor == "INTC" else ("none" if not vendor else f"{vendor} TPM 2.0")


def slowdowns(bundle: str, n: int) -> list[float]:
    """Measured co-run slowdowns at ``n`` concurrent sandboxes, over the functions measured there."""
    rows_by_fn = [{str(k): float(v) for k, v in f["interference"].items()} for f in functions(bundle).values()]
    key = str(n)
    rows = [row[key] for row in rows_by_fn if key in row]
    if rows:
        return rows
    lower = max(int(k) for row in rows_by_fn for k in row if int(k) <= n)
    return [row[str(lower)] for row in rows_by_fn if str(lower) in row]


def _ms(seconds: float) -> str:
    value = seconds * 1e3
    if value >= 1000:
        return f"{value:,.0f}".replace(",", "{,}")
    if value >= 10:
        return f"{value:.3g}"
    return f"{value:.2g}"


def _seconds(seconds: float) -> str:
    return f"{seconds:.3g}"


def values(out: dict[str, float | int | str]) -> None:
    """Macros for the machine and cost sentences (T03-T05, T09, T13, T26, T44, T49)."""
    assert set(fleet_bundles()) == {bundle for bundle, _, _ in CLASSES}, "table does not match configs/machines.yaml"
    power = [power_on_s(b) for b, _, _ in CLASSES]
    boot = [measured(b, "fc_boot") * 1e3 for b, _, _ in CLASSES]
    restore = [measured(b, "fc_restore") * 1e3 for b, _, _ in CLASSES]
    fns = [functions(b) for b, _, _ in CLASSES]
    pairs = sum(len(f["exec_by_size"]) for f in fns[0].values())
    sizes = [len(f["exec_by_size"]) for f in fns[0].values()]
    runs = {int(row["n"]) for f in fns[0].values() for row in f["exec_by_size"].values()}
    out["MachCount"] = len(MACHINES)
    out["MachClasses"] = len(CLASSES)
    out["MachProcClasses"] = len({cpu_label(b) for b, _, _ in CLASSES})
    out["MachPowerOnLo"], out["MachPowerOnHi"] = round(min(power)), round(max(power))
    out["MachBootLo"], out["MachBootHi"] = round(min(boot)), round(max(boot))
    out["MachRestoreLo"], out["MachRestoreHi"] = round(min(restore), 1), round(max(restore), 1)
    out["MachFns"] = len(fns[0])
    out["MachPairs"] = pairs
    out["MachSizesLo"], out["MachSizesHi"] = min(sizes), max(sizes)
    assert len(runs) == 1, f"runs per size differ across functions: {sorted(runs)}"
    out["MachRuns"] = runs.pop()


def machines_table() -> str:
    """Rows of the machine table: processor, cores/threads, memory, disk and TPM per calibrated class (T13)."""
    rows = [
        "% Generated by experiments.analysis.paper_inputs; do not edit.",
        "Processor & Cores / threads & Memory (GiB) & Disk & TPM \\\\",
        "\\midrule",
    ]
    for bundle, _, _ in CLASSES:
        rows.append(
            f"{cpu_label(bundle)} & {cores(bundle)} / {threads(bundle)} & {mem_gib(bundle):.1f} & "
            f"{disk_label(bundle)} & {tpm_label(bundle)} \\\\"
        )
    rows.append("\\bottomrule")
    return "\n".join(rows) + "\n"


def costs_table() -> str:
    """Rows of the per-step cost table: steps down, calibrated classes across (T07, T13)."""
    heads = " & ".join(label for _, label, _ in CLASSES)
    rows = ["% Generated by experiments.analysis.paper_inputs; do not edit.", f"Step & {heads} \\\\", "\\midrule"]
    steps: tuple[tuple[str, Callable[[str], str]], ...] = (
        ("Power-on to verifier accepted (s)", lambda b: _seconds(power_on_s(b))),
        ("Sandbox boot (ms)", lambda b: _ms(measured(b, "fc_boot"))),
        ("Snapshot load, warm cache (ms)", lambda b: _ms(measured(b, "fc_restore"))),
        ("Snapshot create (ms)", lambda b: _ms(measured(b, "fc_snapshot_create"))),
        ("Key release (ms)", lambda b: _ms(measured(b, "key_release"))),
        ("TPM quote (ms)", lambda b: _ms(measured(b, "tpm2_quote"))),
        ("Verifier check (ms)", lambda b: _ms(measured(b, "verify_s"))),
    )
    for name, fn in steps:
        rows.append(f"{name} & " + " & ".join(fn(b) for b, _, _ in CLASSES) + " \\\\")
    rows.append("\\bottomrule")
    return "\n".join(rows) + "\n"


def capacity_table() -> str:
    """Rows of the capacity table: one column per machine, with its limit, memory and measured co-run slowdown (T09)."""
    machines = [next(b for b, _, m in CLASSES if m == machine) for machine in MACHINES]
    heads = " & ".join(cpu_label(b) for b in machines)
    rows = ["% Generated by experiments.analysis.paper_inputs; do not edit.", f"Property & {heads} \\\\", "\\midrule"]
    rows.append("Concurrency limit & " + " & ".join(str(cores(b)) for b in machines) + " \\\\")
    rows.append("Memory (GiB) & " + " & ".join(f"{mem_gib(b):.1f}" for b in machines) + " \\\\")
    for label, n in (("Slowdown at 2", 2), ("Slowdown at the limit", None)):
        cells = []
        for b in machines:
            values = slowdowns(b, cores(b) if n is None else n)
            cells.append(f"{statistics.median(values):.2f} ({min(values):.2f}--{max(values):.2f})")
        rows.append(f"{label} & " + " & ".join(cells) + " \\\\")
    counts = [f"{len(slowdowns(b, 2))} / {len(slowdowns(b, cores(b)))}" for b in machines]
    rows.append("Functions measured & " + " & ".join(counts) + " \\\\")
    rows.append("\\bottomrule")
    return "\n".join(rows) + "\n"
