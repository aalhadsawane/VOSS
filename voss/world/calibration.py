"""Measured overrides from a calibration bundle (doc 10 §1): function profiles (``functions.yaml``) written by
``tools/calibrate/ingest.py``. The calibrated fleet is the only machine path (D-107); bundles without a profile keep
the catalogue's values, which every reported run then overrides per class (``world/machines.py``)."""

from __future__ import annotations

from typing import Any

from voss.core.paths import config_path, load_data_yaml

FN_FIELDS = ("init_s", "work_ref_s", "size_exp")


def bundle_file(calibration: str | None, name: str) -> dict[str, Any]:
    if not calibration:  # unit tests may build a catalogue without a bundle
        return {}
    path = config_path(calibration) / f"{name}.yaml"
    return load_data_yaml(path) if path.exists() else {}


def function_overrides(calibration: str | None) -> dict[str, dict[str, float]]:
    """Measured ``init_s``, ``work_ref_s`` and ``size_exp`` per function (missing values are not overridden)."""
    fns = bundle_file(calibration, "functions").get("functions") or {}
    return {
        name: {k: float(v) for k, v in prof.items() if k in FN_FIELDS and v is not None}
        for name, prof in sorted(fns.items())
    }


def function_sizes(calibration: str | None) -> dict[str, dict[float, float]]:
    """Measured median handler seconds per input size (``exec_by_size``) per function; empty for bundles without
    them (plan V9.1: trace functions are mapped across every measured (function, input size) profile)."""
    fns = bundle_file(calibration, "functions").get("functions") or {}
    return {
        name: {float(k): float(row["median_s"]) for k, row in sorted((prof.get("exec_by_size") or {}).items())}
        for name, prof in sorted(fns.items())
        if prof.get("exec_by_size")
    }
