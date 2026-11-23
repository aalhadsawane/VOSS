"""Calibrated machine fleet (docs/REVISION_PLAN.md V9.4, D-107): one machine class per calibration bundle, weighted by
a public hardware survey.

- A class takes its threads, memory and TPM kind from the machine's spec (``calibration/specs/<label>/class.yaml`` and
  ``spec.yaml``), its disk speeds from the bundle's ``hardware.yaml`` and its function run times, function start-up and
  size exponents from the bundle's ``functions.yaml``. Speed differences between classes are per function: the class
  speed is 1 and each class runs its own measured copy of every catalogue function.
- A class whose machine has no TPM takes the TPM entries (``TPM_KEYS``) from the reference bundle (the run's
  ``calibration``); the fleet records them as ``shared:<reference>``, never as measured for that class (D-107).
- The mix: each survey bucket (logical CPUs, memory bucket) goes to the nearest class by
  ``hypot(log2(cpus / threads), log2(mem / mem_bucket))``; classes at the same distance share it equally. A bucket
  farther than ``radius`` from every class is not represented well; hosts whose vendor is neither Intel nor AMD are
  not x86 and no calibrated machine represents them. Both shares are reported, the hosts still count in the weights.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from voss.core.dist import Dist
from voss.core.paths import REPO_ROOT, config_path, load_data_yaml
from voss.world.hardware import HwClass
from voss.world.substrate import _as_dist
from voss.world.workload import Catalog, FunctionSpec

MEASURED = "calibration/measured"
SPECS = REPO_ROOT / "calibration" / "specs"
TPM_KEYS: tuple[str, ...] = ("tpm2_quote", "tpm2_unseal", "verify_s")
X86_VENDORS: tuple[str, ...] = ("intel", "amd")
FN_KEYS = ("init_s", "size_exp")


class MachinesParams(BaseModel):
    """``scenario.machines``: the calibrated bundles of the fleet and the survey that weights them (D-107)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    bundles: tuple[str, ...] = Field(min_length=1)  # names under configs/calibration/measured
    survey: str  # trace with hosts.parquet (tools/traces/boinc.py)
    trace_root: str = "data/traces"
    radius: float = Field(default=1.0, gt=0)  # one power-of-two step: the survey's memory resolution


@dataclass(frozen=True)
class MachineClass:
    """One calibrated machine: hardware, its measured functions and lifecycle distributions with their provenance."""

    hw: HwClass
    functions: dict[str, dict[str, Any]]  # functions.yaml rows
    dists: dict[str, Dist]
    provenance: dict[str, str]  # distribution key -> "measured" | "shared:<reference>"


@dataclass(frozen=True)
class Mix:
    """Survey mapping: class weights, per-bucket assignment and the two unrepresented shares."""

    weights: dict[str, float]
    buckets: pd.DataFrame  # ncpus, mem_gib, vendor, count, distance, classes
    unrepresented: float  # share of hosts farther than ``radius`` from every class
    non_x86: float  # share of hosts that are not x86
    hosts: int


@dataclass(frozen=True)
class Fleet:
    reference: str
    classes: dict[str, MachineClass]
    mix: Mix
    catalogs: dict[str, tuple[FunctionSpec, ...]]  # per class, the catalogue with that class's measured run times

    @property
    def hw(self) -> dict[str, HwClass]:
        return {n: c.hw for n, c in sorted(self.classes.items())}

    def shared(self) -> dict[str, list[str]]:
        """Per class, the distribution keys taken from the reference (empty lists left out)."""
        out = {
            n: sorted(k for k, v in c.provenance.items() if v != "measured") for n, c in sorted(self.classes.items())
        }
        return {n: ks for n, ks in out.items() if ks}


def bundle_dir(name: str) -> Path:
    return config_path(f"{MEASURED}/{name}")


def bundle_name(calibration: str | None) -> str:
    """Bundle name of a ``calibration`` path (its last component)."""
    if not calibration:
        raise ValueError("scenario.machines needs calibration= one of its bundles (the reference machine)")
    return Path(calibration).name


def spec_label(bundle: str) -> str:
    """``node02-i7-12700-64g-nvme_nvme`` -> ``node02-i7-12700-64g-nvme`` (the bundle's disk tier is the suffix)."""
    return bundle.rsplit("_", 1)[0]


def mem_bucket(gib: float) -> float:
    """The survey's memory bucket: nearest power of two GiB (tools/traces/boinc.py)."""
    return float(2.0 ** round(math.log2(max(gib, 0.5))))


def _disk_gb(spec: dict[str, Any], rotational: bool) -> float:
    devs = [d for d in spec["storage"]["devices"] if bool(d.get("rotational")) is rotational]
    return float(devs[0]["capacity_gb"]) if devs else 0.0


def load_hw(bundle: str) -> HwClass:
    """Hardware of one bundle: spec threads and memory, the disk the bundle ran on as the fast tier (its suffix),
    a rotational disk as the second tier only when the fast tier is not one, and the bundle's measured disk speeds."""
    label, tier = spec_label(bundle), bundle.rsplit("_", 1)[1]
    cls = load_data_yaml(SPECS / label / "class.yaml")
    spec = load_data_yaml(SPECS / label / "spec.yaml")
    disk = load_data_yaml(bundle_dir(bundle) / "hardware.yaml")["classes"]["C0"]
    return HwClass(
        name=bundle,
        speed=1.0,
        cores=int(cls["threads"]),
        mem_gb=float(cls["mem_gib"]),
        ssd_gb=_disk_gb(spec, tier == "hdd"),
        hdd_gb=0.0 if tier == "hdd" else _disk_gb(spec, True),
        cpu_model=str(cls["cpu"]),
        tpm=str(cls["tpm"]),
        mem_encryption=bool(cls.get("mem_encryption", False)),
        **{k: float(v) for k, v in disk.items()},
    )


def _raw_dists(bundle: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = load_data_yaml(bundle_dir(bundle) / "distributions.yaml")["distributions"]
    return out


def class_dists(bundle: str, reference: str) -> tuple[dict[str, Dist], dict[str, str]]:
    """Distributions of a class; a TPM entry the class did not measure comes from the reference, labelled shared.
    Any other entry the class did not measure is refused (guardrails 28, 29)."""
    own, ref = _raw_dists(bundle), _raw_dists(reference)
    merged: dict[str, Dist] = {}
    prov: dict[str, str] = {}
    for key in sorted(set(own) | set(ref)):
        entry = own.get(key)
        if entry is not None and entry.get("tag") == "measured":
            merged[key], prov[key] = _as_dist(entry), "measured"
        elif key in TPM_KEYS and key in ref and ref[key].get("tag") == "measured":
            merged[key], prov[key] = _as_dist(ref[key]), f"shared:{reference}"
        else:
            raise ValueError(f"{bundle}: distribution {key} is not measured (D-107 shares only {TPM_KEYS})")
    return merged, prov


def load_class(bundle: str, reference: str) -> MachineClass:
    fns = load_data_yaml(bundle_dir(bundle) / "functions.yaml")["functions"]
    dists, prov = class_dists(bundle, reference)
    return MachineClass(load_hw(bundle), fns, dists, prov)


def class_function(base: dict[str, Any], name: str, size_kb: float | None) -> dict[str, float]:
    """Measured fields of one catalogue function on one class: at the mapped input size for a trace function, else at
    the function's reference input."""
    out = {k: float(base[k]) for k in FN_KEYS}
    if size_kb is None:
        return out | {"work_ref_s": float(base["work_ref_s"])}
    sizes = {float(k): float(v["median_s"]) for k, v in (base.get("exec_by_size") or {}).items()}
    if size_kb not in sizes:
        raise ValueError(f"{name}: no measured run time at input size {size_kb:g}")
    return out | {"work_ref_s": sizes[size_kb]}


def class_catalog(catalog: Catalog, mc: MachineClass) -> tuple[FunctionSpec, ...]:
    """The catalogue as it runs on one class: same functions, the class's measured ``work_ref_s``, ``init_s`` and
    ``size_exp`` (a trace function at its mapped input size, ``Catalog.profiles``)."""
    out = []
    for f in catalog.functions:
        base, size = catalog.profiles.get(f.name, (f.name, None))
        if base not in mc.functions and size is None:
            # A synthetic copy of a catalogue function (the decision-timing bench appends -0, -1, ... to raise the
            # function count) uses the base function's measured profile on every class. ``base`` may be the copied
            # name (a trace function maps to it) or the function itself.
            stem = base.rsplit("-", 1)[0]
            if stem in mc.functions:
                base = stem
        if base not in mc.functions:
            raise ValueError(f"{mc.hw.name}: function {base} not measured")
        out.append(f.model_copy(update=class_function(mc.functions[base], f.name, size) | {"base": base}))
    return tuple(out)


def survey_table(mp: MachinesParams) -> pd.DataFrame:
    d = Path(mp.trace_root) / mp.survey / "hosts.parquet"
    return pd.read_parquet(d if d.is_absolute() else REPO_ROOT / d)


def distances(ncpus: np.ndarray, mem: np.ndarray, hw: list[HwClass]) -> np.ndarray:
    """Hosts x classes distance on log2 threads and log2 memory bucket."""
    t = np.log2(np.array([h.cores for h in hw], dtype=float))
    m = np.log2(np.array([mem_bucket(h.mem_gb) for h in hw]))
    out: np.ndarray = np.hypot(np.log2(ncpus)[:, None] - t, np.log2(mem)[:, None] - m)
    return out


def survey_mix(table: pd.DataFrame, hw: dict[str, HwClass], radius: float) -> Mix:
    """Weights of the classes from the survey's host counts (ties share a bucket equally)."""
    names = sorted(hw)
    d = distances(table.ncpus.to_numpy(float), table.mem_gib.to_numpy(float), [hw[n] for n in names])
    best = d.min(axis=1)
    tie = np.isclose(d, best[:, None], rtol=0, atol=1e-9)
    count = table["count"].to_numpy(float)
    share = (tie / tie.sum(axis=1, keepdims=True)) * count[:, None]
    total = float(count.sum())
    buckets = table[["ncpus", "mem_gib", "vendor", "count"]].assign(
        distance=best, classes=["+".join(n for n, t in zip(names, row, strict=True) if t) for row in tie]
    )
    return Mix(
        weights={n: float(share[:, i].sum() / total) for i, n in enumerate(names)},
        buckets=buckets.reset_index(drop=True),
        unrepresented=float(count[best > radius].sum() / total),
        non_x86=float(count[~table.vendor.isin(X86_VENDORS).to_numpy()].sum() / total),
        hosts=int(total),
    )


def load_fleet(raw: dict[str, Any], calibration: str | None, catalog: Catalog) -> Fleet:
    """The fleet of ``scenario.machines``; the run's calibration bundle is the reference machine."""
    mp = MachinesParams.model_validate(raw)
    ref = bundle_name(calibration)
    if ref not in mp.bundles:
        raise ValueError(f"scenario.machines: reference bundle {ref} (calibration) is not among {mp.bundles}")
    classes = {b: load_class(b, ref) for b in sorted(set(mp.bundles))}
    mix = survey_mix(survey_table(mp), {n: c.hw for n, c in classes.items()}, mp.radius)
    return Fleet(ref, classes, mix, {n: class_catalog(catalog, c) for n, c in classes.items()})


def fleet_columns(fleet: Fleet) -> dict[str, list[str]]:
    """What the scenario hash covers of a fleet: hardware, per-class catalogues, distributions and their provenance."""
    cs = sorted(fleet.classes.items())
    return {
        "hw": [c.hw.model_dump_json() for _, c in cs],
        "functions": [f.model_dump_json() for n, _ in cs for f in fleet.catalogs[n]],
        "dists": [
            f"{n}|{k}|{d.model_dump_json()}|{c.provenance[k]}" for n, c in cs for k, d in sorted(c.dists.items())
        ],
        "weights": [f"{n}|{w!r}" for n, w in sorted(fleet.mix.weights.items())],
    }
