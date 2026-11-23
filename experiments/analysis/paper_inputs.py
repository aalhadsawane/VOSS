"""Macros for the paper's measured inputs (WRITING_SPEC.md §2 step 3): decision timing on the provider CPU and the
derivation parameters of the public traces. Result macros come from the experiment summaries (plan V12).

    uv run python -m experiments.analysis.paper_inputs          # writes manuscript/generated/inputs.tex
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from voss.core.config import load_config
from voss.core.paths import REPO_ROOT, config_path
from voss.world.network import NetworkParams

from experiments.analysis import calibration, fleet_mix
from experiments.analysis import traces as trace_stats
from experiments.analysis.machines import machines
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


def run_size(values: dict[str, float | int | str]) -> None:
    """Size of every reported run (D-97), from the development main specification; seeds from the R specs."""
    spec = _yaml(REPO_ROOT / "configs" / "experiments" / "D01.yaml")
    ov = dict(o.split("=", 1) for o in spec["overrides"])
    total, warm = float(ov["horizon_s"]) / 3600, float(ov["scenario.warmup_s"]) / 3600
    values["RunWorkers"] = int(ov["scenario.workers"])
    values["RunHours"], values["RunWarmupHours"] = int(total), int(warm)
    values["RunMeasuredHours"] = int(total - warm)
    seeds = {
        int(seed)
        for path in sorted((REPO_ROOT / "configs" / "experiments").glob("R0*.yaml"))
        for seed in _yaml(path)["seeds"]
    }
    values["RunSeedLo"], values["RunSeedHi"] = min(seeds), max(seeds)


# constants shown in the paper: ledger key -> (name in the paper, unit)
CONSTANTS = {
    "voss.planner.scenarios": ("failure scenarios sampled per provisioning decision ($M$)", ""),
    "voss.planner.horizon_factor": ("provisioning horizon $H$, in provisioning periods", ""),
    "voss.detection.quantile": ("quantile of the predicted completion time at which the timer expires", ""),
    "voss.detection.probe_timeout_s": ("time allowed for the answer to a progress question", "s"),
    "voss.detection.suspect_streak": ("consecutive failures after which a worker gets no invocations", ""),
    "voss.detection.suspect_s": ("time a worker gets no invocations after that", "s"),
    "voss.models.cusum_h": ("threshold of the change-point test", ""),
    "voss.models.omission_prior": ("prior $(a_0, b_0)$ of the drop estimate", ""),
    "voss.models.omission_pessimistic": ("pessimistic prior after a change point", ""),
    "voss.models.cusum_k": ("drift $k$ of the change-point test", ""),
    "voss.scheduler.max_attempts": ("attempts per invocation", ""),
    "voss.router.done_keep_s": ("time a finished invocation is remembered, to recognise a late second result", "s"),
    "voss.keys.max_holders": ("holder budget $K$ per function", ""),
    "voss.keys.rotate_s": ("key rotation period", ""),
    "voss.audit.p": ("audit probability $p$", ""),
}
CLASSES = {"M": "measured", "T": "trace", "L": "literature", "D": "derived", "A": "varied", "S": "swept"}


def ledger() -> dict[str, tuple[str, str]]:
    """Key -> (default, class) from ``docs/PARAMETERS.md``."""
    out = {}
    for line in (REPO_ROOT / "docs" / "PARAMETERS.md").read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0].startswith("`") and cells[1].startswith("`"):
            out[cells[0].strip("`")] = (cells[1].strip("`"), cells[2])
    return out


def _shown(value: str, cls: str, unit: str) -> str:
    """A ledger value as the table shows it; a tuple is printed as the ledger writes it."""
    if value == "None" or cls == "A":
        return "varied"
    if value.startswith("(") and value.endswith(")"):
        return value
    return f"{float(value):g}" + (f"~{unit}" if unit else "")


def constants_table() -> str:
    """Rows of the constants table; a constant whose ledger class is not final is left out (it is a to-do)."""
    led, rows = ledger(), ["% Generated by experiments.analysis.paper_inputs; do not edit."]
    for key, (name, unit) in CONSTANTS.items():
        value, cls = led[key]
        if cls not in CLASSES:
            continue
        rows.append(f"{name} & {_shown(value, cls, unit)} & {CLASSES[cls]} \\\\")
    rows.append("\\bottomrule")  # inside the file: a rule right after \\input fails in a tabular
    return "\n".join(rows) + "\n"


TODO_RE = re.compile(r"\\todoitem\{(T\d+)\}\{([^}]*)\}\{((?:[^{}]|\{[^{}]*\})*)\}", re.S)


def todo_list() -> str:
    """``manuscript/TODO.md``: every to-do marker in the text, grouped by what it waits for."""
    items = []
    for path in [REPO_ROOT / "manuscript" / "main.tex", *sorted((REPO_ROOT / "manuscript" / "sections").glob("*.tex"))]:
        for m in TODO_RE.finditer(path.read_text()):
            items.append((m.group(2), m.group(1), path.name, " ".join(m.group(3).split())))
    lines = [
        "# Manuscript to-do list",
        "",
        "Generated by `experiments.analysis.paper_inputs` from the `\\todoitem{id}{waits for}{what}` markers.",
        "Each marker stands where a number, table, figure or sentence is missing. Nothing in the text is a guessed",
        "value: a missing value is a marker. Remove a marker only when its source exists and the value comes from a",
        "generated macro or table.",
        "",
    ]
    for need in sorted({i[0] for i in items}):
        lines += [f"## Waits for: {need}", "", "| Id | File | What is missing |", "|---|---|---|"]
        lines += [f"| {i} | `{f}` | {text} |" for n, i, f, text in sorted(items) if n == need]
        lines.append("")
    return "\n".join(lines + OTHER)


# work on the manuscript that no marker in the text stands for
OTHER = [
    "## Not tied to a marker",
    "",
    "| What | Waits for |",
    "|---|---|",
    "| Author's read of the abstract, introduction and background; log it in HUMAN_FEEDBACK.md | author |",
    "| Verify every entry of `refs.bib` marked `TODO verify` against the publisher or DBLP | builder |",
    "| Feedback regression checklist (WRITING_SPEC.md §6) as `FEEDBACK_REGRESSION.md` | final front matter |",
    "| Generators for result macros, tables and figures from the experiment summaries | held-out experiments |",
    "| Scheduler fixed (`v2-freeze`); then the held-out experiments run once | development experiments |",
    "| Affiliation and country in `main.tex` | author |",
    "",
]


def build() -> dict[str, float | int | str]:
    values: dict[str, float | int | str] = {}
    decision(values)
    traces(values)  # trace derivation parameters
    trace_stats.values(values)  # availability statistics (T08, T15)
    run_size(values)
    machines(values)
    calibration.values(values)  # machine and start-up costs (T03-T05, T07, T09, T13, T26, T44, T49)
    fleet_mix.values(values)  # survey mapping of the calibrated fleet (T14, D-107)
    return values


TABLES = {
    "fleet.tex": fleet_mix.table,
    "tab_machines.tex": calibration.machines_table,
    "tab_costs.tex": calibration.costs_table,
    "tab_capacity.tex": calibration.capacity_table,
    "tab_trace.tex": trace_stats.table,
}


if __name__ == "__main__":
    write(build(), OUT)
    (OUT.parent / "constants.tex").write_text(constants_table())
    for name, render in TABLES.items():
        (OUT.parent / name).write_text(render())
    (REPO_ROOT / "manuscript" / "TODO.md").write_text(todo_list())
    print(f"wrote {OUT}, constants.tex, {', '.join(TABLES)} and TODO.md")
