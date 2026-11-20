"""The mapping of sampled trace functions to measured (function, input size) profiles (docs/REVISION_PLAN.md V9.1),
for one calibration bundle and split: one row per trace function and the share outside the measured range.

    uv run python -m tools.traces.mapping --calibration <bundle> [--split dev] [--csv out.csv]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from voss.core.config import ScenarioConfig
from voss.core.paths import load_data_yaml
from voss.world.calibration import function_overrides, function_sizes
from voss.world.trace_load import load_trace_functions, request_kb
from voss.world.workload import Catalog, FunctionSpec, LoadRegime, TenantSpec


def mapping(calibration: str, split: str, trace: str = "azure2019") -> tuple[str, pd.DataFrame]:
    sc = ScenarioConfig()
    meas = function_overrides(calibration)
    fns = tuple(
        FunctionSpec.model_validate(f | meas.get(f["name"], {})) for f in load_data_yaml(sc.functions)["functions"]
    )
    ten = tuple(TenantSpec.model_validate(t) for t in load_data_yaml(sc.tenants)["tenants"])
    reg = LoadRegime(regime="trace", rate=1, zipf_s=0, trace=trace, split=split)
    tf = load_trace_functions(reg, Catalog(fns, ten), function_sizes(calibration))
    rules = load_data_yaml("request_bytes.yaml")
    param_kb = min(f.in_kb for f in fns)
    req = [
        request_kb(b, k, rules, param_kb) if tf.per_size else float("nan")
        for b, k in zip(tf.table.base, tf.table.size_kb, strict=True)
    ]
    tf.table["request_kb"] = req
    cols = ["fn", "dur_p50_ms", "base", "size_kb", "request_kb", "profile_s", "outside"]
    head = (
        f"{len(tf.table)} trace functions ({tf.dropped} without a duration left out); "
        f"profiles per input size: {tf.per_size}; outside the measured range: {tf.outside:.1%}"
    )
    return head, tf.table[cols]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.traces.mapping")
    p.add_argument("--calibration", required=True)
    p.add_argument("--split", default="dev", choices=("dev", "heldout"))
    p.add_argument("--csv", type=Path, default=None)
    a = p.parse_args(argv)
    head, table = mapping(a.calibration, a.split)
    print(head)
    by = table.groupby(["base", "size_kb"]).size().rename("trace_functions")
    print(by.to_string())
    if a.csv:
        table.to_csv(a.csv, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
