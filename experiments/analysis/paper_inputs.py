"""Macros for the paper's measured inputs (WRITING_SPEC.md §2 step 3): decision timing on the provider CPU and the
derivation parameters of the public traces. Result macros come from the experiment summaries (plan V12).

    uv run python -m experiments.analysis.paper_inputs          # writes manuscript/generated/inputs.tex
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from voss.core.config import load_config
from voss.core.paths import REPO_ROOT, config_path
from voss.world.network import NetworkParams

from experiments.analysis.macros import write

OUT = REPO_ROOT / "manuscript" / "generated" / "inputs.tex"


def _yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    return data


def decision(values: dict[str, float | int | str]) -> None:
    """Coefficients the base configuration charges, medians and capacity per pool (plan V10)."""
    cfg = load_config(REPO_ROOT / "configs" / "base.yaml")
    d = _yaml(config_path(cfg.decision_clock.coeffs_file))
    c = d["coeffs"]
    model = next(line for line in d["cpu"]["lscpu"] if line.startswith("Model name:"))
    values["DecCpu"] = model.split(":", 1)[1].strip().replace("(R)", "").replace("  ", " ")
    values["DecPlaceFixedMs"] = c["place"][0] * 1e3
    values["DecPlacePerPairUs"] = c["place"][1] * 1e6
    values["DecPlanPerVarUs"] = c["plan"][1] * 1e6
    values["DecVerifyPerReceiptUs"] = c["verify"][1] * 1e6
    lim = d["placement_limit"]
    med = [v["median_place_s"] for v in lim.values()]
    cap = [v["capacity_per_s"] for v in lim.values()]
    small, large = min(d["pools"]), max(d["pools"])
    values["DecPoolSmall"], values["DecPoolLarge"] = int(small), int(large)
    values["DecPlaceSmallLoMs"] = min(m[small] for m in med) * 1e3
    values["DecPlaceSmallHiMs"] = max(m[small] for m in med) * 1e3
    values["DecPlaceLargeLoMs"] = min(m[large] for m in med) * 1e3
    values["DecPlaceLargeHiMs"] = max(m[large] for m in med) * 1e3
    values["DecCapSmall"] = int(round(min(k[small] for k in cap), -2))
    values["DecCapLargeLo"] = int(round(min(k[large] for k in cap), -1))
    values["DecCapLargeHi"] = int(round(max(k[large] for k in cap), -1))
    values["DecBoundLoMs"] = round(min(v["bound_s"] for v in lim.values()) * 1e3)
    values["DecBoundHiMs"] = int(round(max(v["bound_s"] for v in lim.values()) * 1e3, -1))
    sat = {v["first_pool_saturated_at_0.1_per_worker"] for v in lim.values()}
    values["DecSaturatedPool"] = int(min(s for s in sat if s is not None))
    values["DecFnLo"], values["DecFnHi"] = int(min(d["functions"])), int(max(d["functions"]))


def traces(values: dict[str, float | int | str]) -> None:
    """Derivation parameters recorded in ``configs/traces/*/provenance.yaml``."""
    root = REPO_ROOT / "configs" / "traces"
    az = _yaml(root / "azure2019" / "provenance.yaml")["params"]
    values["AzureFnPerSplit"] = int(az["n_per_split"])
    seti = _yaml(root / "seti09" / "provenance.yaml")["params"]
    values["SetiHostsPerSplit"] = int(seti["hosts_per_split"])
    ook = _yaml(root / "ookla-fixed-2024q1" / "provenance.yaml")["params"]
    values["OoklaRadiusKm"] = int(ook["radius_km"])
    values["OoklaDraws"] = int(ook["draws_per_city"])
    for key, name in (("boinc-rosetta", "BoincRosettaActive"), ("boinc-milkyway", "BoincMilkywayActive")):
        values[name] = int(_yaml(root / key / "provenance.yaml")["params"]["hosts_active"])
    net = NetworkParams.model_validate(load_config(REPO_ROOT / "configs" / "base.yaml").scenario.network)
    values["RouteFactor"] = f"{net.route_factor:.2f}"


def build() -> dict[str, float | int | str]:
    values: dict[str, float | int | str] = {}
    decision(values)
    traces(values)
    return values


if __name__ == "__main__":
    write(build(), OUT)
    print(f"wrote {OUT}")
