"""Measured overrides from a calibration bundle (doc 10 §1): hardware class fields (``hardware.yaml``) and function
profiles (``functions.yaml``) written by ``tools/calibrate/ingest.py``. The placeholder bundle has neither, so runs
without measured data keep the literature values of ``configs/hardware`` and ``configs/functions.yaml``."""

from __future__ import annotations

from typing import Any

from voss.core.paths import config_path, load_data_yaml

PLACEHOLDER = "calibration/placeholder/c0"
FN_FIELDS = ("init_s", "work_ref_s", "size_exp")


def bundle_file(calibration: str | None, name: str) -> dict[str, Any]:
    path = config_path(calibration or PLACEHOLDER) / f"{name}.yaml"
    return load_data_yaml(path) if path.exists() else {}


def hardware_overrides(calibration: str | None) -> dict[str, dict[str, float]]:
    classes: dict[str, dict[str, float]] = bundle_file(calibration, "hardware").get("classes") or {}
    return classes


def function_overrides(calibration: str | None) -> dict[str, dict[str, float]]:
    """Measured ``init_s``, ``work_ref_s`` and ``size_exp`` per function (missing values are not overridden)."""
    fns = bundle_file(calibration, "functions").get("functions") or {}
    return {
        name: {k: float(v) for k, v in prof.items() if k in FN_FIELDS and v is not None}
        for name, prof in sorted(fns.items())
    }
