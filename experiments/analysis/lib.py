"""Analysis library (doc 06 §1, §6): a registry of named per-run metrics computed from logs only, collection of an
experiment's runs into one frame keyed by its spec, and paired comparisons against a baseline system on the same
scenarios (per-seed differences, bootstrap CIs). Experiment YAMLs name their keys, baseline and metrics under
``report``; ``python -m experiments.analysis.lib E19`` writes ``docs/pilots/E19.md`` and a CSV.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from functools import cached_property
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from experiments.analysis.common import bootstrap_ci, fmt, get, latency_metrics, manifest, report_table, table

REPO = Path(__file__).resolve().parents[2]
WARMUP_S = 60.0


class Run:
    """Lazy view of one run directory (tables are read once)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._tables: dict[str, pd.DataFrame] = {}

    def __getitem__(self, name: str) -> pd.DataFrame:
        if name not in self._tables:
            self._tables[name] = table(self.path, name)
        return self._tables[name]

    @cached_property
    def manifest(self) -> dict[str, Any]:
        return manifest(self.path)

    @property
    def cfg(self) -> dict[str, Any]:
        cfg: dict[str, Any] = self.manifest["config"]
        return cfg

    def events(self, kind: str) -> pd.DataFrame:
        ev = self["events"]
        return ev[ev.kind == kind] if len(ev) else ev

    @property
    def span_s(self) -> float:
        return float(self.cfg["horizon_s"]) + float(self.cfg["drain_s"])


Metric = Callable[[Run], float]
METRICS: dict[str, Metric] = {}


def metric(name: str) -> Callable[[Metric], Metric]:
    def deco(fn: Metric) -> Metric:
        METRICS[name] = fn
        return fn

    return deco


def _lat(key: str) -> Metric:
    return lambda r: latency_metrics(r["invocations"], WARMUP_S)[key]


for _k in ("success", "met", "p50_sync", "p99_sync", "p99_all"):
    metric(_k)(_lat(_k))


def _tenant_class() -> dict[str, str]:
    """Tenant id -> sensitivity class (configs/tenants.yaml)."""
    rows = yaml.safe_load((REPO / "configs" / "tenants.yaml").read_text())["tenants"]
    return {str(t["id"]): str(t["sensitivity"]) for t in rows}


def _p99_class(sensitivity: str) -> Metric:
    def fn(r: Run) -> float:
        inv = r["invocations"]
        ok = inv[(inv.outcome == "ok") & (inv.slo_class == 0) & (inv.t_arrive >= WARMUP_S)]
        ok = ok[ok.tenant.map(_tenant_class()) == sensitivity]
        return float(ok.e2e.quantile(0.99)) if len(ok) else np.nan

    return fn


for _s in ("low", "medium", "high"):
    metric(f"p99_sync_{_s}")(_p99_class(_s))


@metric("exposure")
def _exposure(r: Run) -> float:
    c = r["cache"]
    late = c[c.t >= WARMUP_S] if len(c) else c
    return float(late.exposure.mean()) if len(late) else np.nan


@metric("warm_mb")
def _warm(r: Run) -> float:
    c = r["cache"]
    late = c[c.t >= WARMUP_S] if len(c) else c
    return float(late.warm_mb.mean()) if len(late) else np.nan


@metric("waste")
def _waste(r: Run) -> float:
    ok = int((r["invocations"].outcome == "ok").sum())
    return (len(r.events("dispatch_accepted")) - ok) / max(ok, 1)


@metric("workers")
def _workers(r: Run) -> float:
    return float(r.cfg["scenario"]["workers"])


@metric("attested")
def _attested(r: Run) -> float:
    s = r["samples"]
    return float(s.attested.mean()) if len(s) else np.nan


@metric("ctrl_msgs_ws")
def _ctrl_msgs(r: Run) -> float:
    """Control messages per attested worker per second (payloads excluded)."""
    m = r["messages"]
    ctrl = m[~m.kind.isin(["Input", "Result", "Chunk"])]
    return float(ctrl["count"].sum()) / max(_attested(r), 1.0) / r.span_s


@metric("ctrl_kb_ws")
def _ctrl_kb(r: Run) -> float:
    m = r["messages"]
    ctrl = m[~m.kind.isin(["Input", "Result", "Chunk"])]
    return float(ctrl.bytes.sum()) / 1024 / max(_attested(r), 1.0) / r.span_s


def _component(col: str, q: float) -> Metric:
    def fn(r: Run) -> float:
        inv = r["invocations"]
        ok = inv[(inv.outcome == "ok") & (inv.t_arrive >= WARMUP_S)]
        return float(ok[col].quantile(q)) if len(ok) else np.nan

    return fn


for _c in ("decide", "route", "batch_wait"):
    metric(f"{_c}_p50")(_component(_c, 0.5))
    metric(f"{_c}_p99")(_component(_c, 0.99))


@metric("orch_cpu_s")
def _orch(r: Run) -> float:
    """Charged orchestrator decision time per simulated second."""
    s = r["solver"]
    return float(s[s.kind == "orchestrate"].charged_s.sum()) / r.span_s if len(s) else np.nan


@metric("sim_s_per_s")
def _speed(r: Run) -> float:
    """Simulator wall seconds per simulated second (performance, not a system metric)."""
    wall = float(r.manifest.get("wall_s", 0.0))
    return wall / r.span_s if wall > 0 else np.nan


@metric("cost_per_m")
def _cost(r: Run) -> float:
    """USD per million invocations: published per-request and GB-s prices for a reference cloud (billed duration =
    startup + execution, at the provider's granularity), the orchestrator tier's VMs for VOSS (E17)."""
    inv = r["invocations"]
    ok = inv[inv.outcome == "ok"]
    if not len(ok):
        return np.nan
    if r.cfg["system"] == "reference_cloud":
        return _cloud_bill(r, ok) / len(inv) * 1e6
    tier = yaml.safe_load((REPO / "configs" / "references" / "voss_tier.yaml").read_text())
    nodes = len(r.cfg["voss"]["infra"]["routers"]) + int(tier["extra_nodes"])
    return nodes * float(tier["node_per_h"]) * r.span_s / 3600 / len(inv) * 1e6


def _cloud_bill(r: Run, ok: pd.DataFrame) -> float:
    from voss.core.config import RunConfig  # noqa: PLC0415
    from voss.world.reference_cloud import load_reference  # noqa: PLC0415
    from voss.world.workload import load_catalog  # noqa: PLC0415

    pr = load_reference(r.cfg["reference"]).pricing
    mem = {f.name: f.mem_mb for f in load_catalog(RunConfig.model_validate(r.cfg).scenario).functions}
    mb = np.maximum(pr.min_mem_mb, np.ceil(ok.fn.map(mem).to_numpy() / pr.mem_step_mb) * pr.mem_step_mb)
    ms = np.maximum(pr.min_billed_ms, np.ceil((ok.startup + ok.exec).to_numpy() * 1000))
    return float(len(r["invocations"]) * pr.per_m_requests / 1e6 + (mb / 1024 * ms / 1000).sum() * pr.per_gb_s)


@metric("credits_per_m")
def _credits(r: Run) -> float:
    """Volunteer work credits (non-monetary reference units) per million invocations."""
    cr = r["credits"]
    if r.cfg["system"] == "reference_cloud":
        return np.nan  # providers are paid in money, not credits
    return float(cr.amount.sum()) / max(len(r["invocations"]), 1) * 1e6 if len(cr) else np.nan


# --- collection and reports ---------------------------------------------------------------------------------------
def spec(exp: str) -> dict[str, Any]:
    out: dict[str, Any] = yaml.safe_load((REPO / "configs" / "experiments" / f"{exp}.yaml").read_text())
    return out


def run_dirs(exp: str, root: Path) -> list[Path]:
    """Runs of the experiment: the sweep index when present (its order), else every run directory."""
    index = root / exp / "index.csv"
    if index.exists():
        df = pd.read_csv(index)
        return [Path(d) for d in df[df.status != "failed"].run_dir]
    return sorted(d for d in (root / exp).iterdir() if (d / "manifest.json").exists())


def key_value(cfg: dict[str, Any], key: str) -> str:
    v = cfg.get("label", "") if key == "label" else get(cfg, key)
    if isinstance(v, dict | list):
        return yaml.safe_dump(v, default_flow_style=True).strip()
    return str(v)


def collect(exp: str, root: Path, metrics: list[str] | None = None) -> pd.DataFrame:
    sp = spec(exp)
    rep = sp.get("report", {})
    keys, names = list(rep.get("keys", ["label"])), metrics or list(rep.get("metrics", []))
    rows = []
    for d in run_dirs(exp, root):
        r = Run(d)
        row: dict[str, Any] = {k: key_value(r.cfg, k) for k in keys}
        row |= {"seed": r.cfg["seed"], "scenario": r.manifest.get("scenario_hash"), "run_dir": str(d)}
        row |= {m: METRICS[m](r) for m in names}
        rows.append(row)
    return pd.DataFrame(rows)


def paired(df: pd.DataFrame, key: str, baseline: str, m: str) -> pd.DataFrame:
    """Per-seed difference of ``m`` against ``baseline`` on the same scenario, mean and bootstrap CI per system."""
    base = df[df[key] == baseline].set_index("scenario")[m]
    rows = []
    for label, g in df[df[key] != baseline].groupby(key):
        d = (g.set_index("scenario")[m] - base.reindex(g.scenario).to_numpy()).dropna().to_numpy()
        mean, lo, hi = bootstrap_ci(d)
        rows.append({key: label, "metric": m, "delta": mean, "lo": lo, "hi": hi, "n": len(d)})
    return pd.DataFrame(rows)


def _cell(d: pd.DataFrame, label: str) -> str:
    row = d.loc[label]
    return fmt(float(row.delta), float(row.lo), float(row.hi), digits=3)


def report(exp: str, df: pd.DataFrame) -> str:
    rep = spec(exp).get("report", {})
    keys, names = list(rep.get("keys", ["label"])), list(rep.get("metrics", []))
    out = report_table(exp, df, keys, names, {})
    base = rep.get("baseline")
    if base and keys == ["label"]:
        out += f"\nPaired differences vs `{base}` (same scenarios, per seed; 95% bootstrap CI):\n\n"
        out += f"| label | {' | '.join(f'Δ {m}' for m in names)} |\n|" + "---|" * (len(names) + 1) + "\n"
        diffs = {m: paired(df, "label", base, m).set_index("label") for m in names}
        for lab in sorted(set(df.label) - {base}):
            cells = [_cell(diffs[m], lab) for m in names]
            out += f"| {lab} | {' | '.join(cells)} |\n"
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("exp")
    p.add_argument("--runs", type=Path, default=Path("runs"))
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args()
    df = collect(a.exp, a.runs)
    out = a.out or REPO / "docs" / "pilots" / f"{a.exp}.md"
    out.write_text(report(a.exp, df))
    df.drop(columns=["run_dir"]).to_csv(out.with_suffix(".csv"), index=False)
    print(out)


if __name__ == "__main__":
    main()
