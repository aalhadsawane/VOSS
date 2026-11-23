"""Emulation against simulator, run for run (plan V13, handoff Part E step 3, data contract §7).

    uv run python -m tools.emu.compare --emu runs-emu/<host_label> --sim runs/emu-s1-central

Emulation runs are ``<emu>/<system>/rep<i>/``; simulator runs are found by their ``manifest.json`` and matched on the
``label`` and ``seed`` the run config carries, so a pair is the same system at the same seed. The two sides share the
scenario (the same ``configs/emu/<name>.yaml``), so a pair must also share its scenario hash; a pair that does not is
reported as a disagreement and never averaged in.

What is reported is what the handoff asks for: share of deadlines met, key holders, the start-up level mix and the
latency distribution, for emulation and simulator side by side, with the spread over the repetitions, and every
difference larger than that spread stated plainly. Nothing is tuned to make the two agree.

Metrics come from ``experiments.analysis.summary``: the same definitions the paper's other results use (D-88, G5:
lost and late are both misses).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from experiments.analysis.summary import summarize

LEVELS = ("L0", "L1", "L2", "L3")
# Rows of the side-by-side table: (metric, label, unit)
SHOWN: tuple[tuple[str, str, str], ...] = (
    ("deadline_met", "deadlines met", "%"),
    ("holders_mean", "key holders (time-averaged)", ""),
    ("holders_peak", "key holders (peak)", ""),
    ("level_L0", "start-up L0 (cold boot)", "%"),
    ("level_L1", "start-up L1 (artifacts)", "%"),
    ("level_L2", "start-up L2 (snapshot)", "%"),
    ("level_L3", "start-up L3 (warm)", "%"),
    ("p50_s", "latency p50", "s"),
    ("p99_s", "latency p99", "s"),
    ("success", "successful invocations", "%"),
)
# A difference below these is noise even when a spread is zero (a metric that cannot move in one run).
FLOOR = {"deadline_met": 1.0, "success": 1.0, "holders_mean": 0.5, "holders_peak": 1.0, "p50_s": 0.005, "p99_s": 0.02}
UNITS = {k: u for k, _l, u in SHOWN}
LABELS = {k: lbl for k, lbl, _u in SHOWN}


@dataclass(frozen=True)
class Run:
    """One run directory: the tables plus what its manifest says it was."""

    path: Path
    label: str
    seed: int
    scenario_hash: str | None
    warmup_s: float
    horizon_s: float

    def frame(self, table: str) -> pd.DataFrame:
        f = self.path / f"{table}.parquet"
        return pd.read_parquet(f) if f.exists() else pd.DataFrame()

    def metrics(self) -> dict[str, float]:
        """The paper's summary metrics plus the start-up level mix (shares among successful invocations)."""
        out = summarize(self.frame, self.warmup_s, self.horizon_s)
        inv = self.frame("invocations")
        ok = inv[inv.outcome == "ok"] if len(inv) else inv
        n = max(1, len(ok))
        for lv in LEVELS:
            out[f"level_{lv}"] = 100.0 * float((ok.start_level == lv).sum()) / n if len(ok) else float("nan")
        out["success"] = 100.0 * float((inv.outcome == "ok").mean()) if len(inv) else float("nan")
        return out

    def sync_latency(self) -> np.ndarray:
        inv = self.frame("invocations")
        if not len(inv):
            return np.zeros(0)
        ok = inv[(inv.slo_class == 0) & (inv.outcome == "ok")]
        return np.asarray(ok.e2e, dtype=float)


def _run_of(path: Path) -> Run:
    man = json.loads((path / "manifest.json").read_text())
    cfg = man.get("config", {})
    scn = cfg.get("scenario", {})
    return Run(
        path=path,
        label=str(cfg.get("label") or ""),
        seed=int(man.get("seed", cfg.get("seed", 0))),
        scenario_hash=man.get("scenario_hash"),
        warmup_s=float(scn.get("warmup_s", 0.0)),
        horizon_s=float(cfg.get("horizon_s", 0.0)),
    )


def emu_runs(root: Path) -> dict[tuple[str, int], Run]:
    """``<root>/<system>/rep<i>/`` directories, keyed by (system, seed)."""
    out: dict[tuple[str, int], Run] = {}
    for man in sorted(root.glob("*/rep*/manifest.json")):
        r = _run_of(man.parent)
        out[(man.parent.parent.name, r.seed)] = r
    return out


def sim_runs(root: Path) -> dict[tuple[str, int], Run]:
    """Every run directory with a manifest under ``root`` (or ``root`` itself), keyed by (label, seed)."""
    found = [root] if (root / "manifest.json").exists() else sorted(p.parent for p in root.rglob("manifest.json"))
    out: dict[tuple[str, int], Run] = {}
    for d in found:
        r = _run_of(d)
        if r.label:
            out[(r.label, r.seed)] = r
    return out


@dataclass(frozen=True)
class Pair:
    system: str
    seed: int
    emu: Run
    sim: Run | None
    emu_metrics: dict[str, float]
    sim_metrics: dict[str, float] | None

    @property
    def hash_ok(self) -> bool:
        return self.sim is not None and self.emu.scenario_hash == self.sim.scenario_hash

    @property
    def comparable(self) -> bool:
        return self.sim_metrics is not None and self.hash_ok


def pair_up(
    emu: dict[tuple[str, int], Run],
    sim: dict[tuple[str, int], Run],
    metrics_of: Callable[[Run], dict[str, float]] | None = None,
) -> list[Pair]:
    """Pair emulation and simulator runs on (system, seed); ``metrics_of`` lets a test supply the metrics."""
    m = metrics_of or Run.metrics
    out = []
    for (system, seed), e in sorted(emu.items()):
        s = sim.get((system, seed))
        out.append(Pair(system, seed, e, s, m(e), m(s) if s is not None else None))
    return out


def _fmt(value: float | None, unit: str) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "–"
    return f"{value:.3f}{unit}" if unit == "s" else f"{value:.1f}{unit}"


@dataclass(frozen=True)
class Cell:
    """One metric of one system over its repetitions."""

    metric: str
    emu_mean: float
    emu_spread: float
    sim_mean: float
    sim_spread: float
    diff: float

    @property
    def within_spread(self) -> bool:
        if np.isnan(self.diff):
            return False
        return abs(self.diff) <= max(self.emu_spread, self.sim_spread, FLOOR.get(self.metric, 0.0))


def _mean_spread(values: list[float]) -> tuple[float, float]:
    a = np.array(values, dtype=float)
    if not len(a):
        return float("nan"), float("nan")
    return float(np.nanmean(a)), float(np.nanmax(a) - np.nanmin(a))


def cells(pairs: list[Pair]) -> dict[str, list[Cell]]:
    """Per system, per metric: mean and spread (max − min) over repetitions, and the difference of the means."""
    by_system: dict[str, list[Pair]] = {}
    for p in pairs:
        by_system.setdefault(p.system, []).append(p)
    out: dict[str, list[Cell]] = {}
    for system, ps in sorted(by_system.items()):
        rows = []
        for key in (k for k, _l, _u in SHOWN):
            # the emulation's own numbers stand even when no simulator run can be compared with them
            emu_mean, emu_spread = _mean_spread([p.emu_metrics[key] for p in ps])
            sim_mean, sim_spread = _mean_spread(
                [p.sim_metrics[key] for p in ps if p.comparable and p.sim_metrics is not None]
            )
            if np.isnan(emu_mean):
                continue
            rows.append(Cell(key, emu_mean, emu_spread, sim_mean, sim_spread, sim_mean - emu_mean))
        out[system] = rows
    return out


def disagreements(pairs: list[Pair], table: dict[str, list[Cell]]) -> list[str]:
    """Every difference larger than the spread, stated plainly, plus every pair that could not be compared."""
    out = []
    for p in pairs:
        if p.sim is None:
            out.append(f"{p.system} rep{p.seed}: no simulator run with label {p.system!r} and seed {p.seed}.")
        elif not p.hash_ok:
            out.append(
                f"{p.system} rep{p.seed}: scenario hashes differ (emulation {p.emu.scenario_hash}, "
                f"simulator {p.sim.scenario_hash}); the pair is not comparable and is left out of the table."
            )
    for system, rows in table.items():
        for c in rows:
            if np.isnan(c.sim_mean) or c.within_spread:
                continue
            unit = UNITS[c.metric]
            out.append(
                f"{system}: {LABELS[c.metric]} is {_fmt(c.emu_mean, unit)} in emulation and {_fmt(c.sim_mean, unit)} "
                f"in the simulator, a difference of {_fmt(c.diff, unit)}; the spread over repetitions is "
                f"{_fmt(c.emu_spread, unit)} (emulation) and {_fmt(c.sim_spread, unit)} (simulator)."
            )
    return out


def table_md(table: dict[str, list[Cell]], pairs: list[Pair]) -> list[str]:
    lines = [
        "| system (reps) | metric | emulation mean [spread] | simulator mean [spread] | difference | within spread |",
        "|---|---|---|---|---|---|",
    ]
    for system, rows in table.items():
        n = len([p for p in pairs if p.system == system])
        for c in rows:
            unit = UNITS[c.metric]
            status = "–" if np.isnan(c.sim_mean) else ("yes" if c.within_spread else "NO")
            lines.append(
                f"| {system} ({n}) | {LABELS[c.metric]} | {_fmt(c.emu_mean, unit)} [{_fmt(c.emu_spread, unit)}] | "
                f"{_fmt(c.sim_mean, unit)} [{_fmt(c.sim_spread, unit)}] | {_fmt(c.diff, unit)} | {status} |"
            )
    return lines


def report_md(table: dict[str, list[Cell]], pairs: list[Pair], dis: list[str], emu_root: Path, sim_root: Path) -> str:
    systems = sorted(table)
    bullets = [f"- {d}" for d in dis] or ["- none: every metric is inside the spread of the repetitions."]
    head = [
        "# Emulation against simulator (plan V13, handoff Part E)",
        "",
        "> Draft produced by `tools.emu.compare`. Fill in the machine, the code revision, the preflight output and one",
        "> sentence for each disagreement, then save it as `docs/validation/emulation-<host_label>.md`.",
        "",
        f"- emulation runs: `{emu_root}`",
        f"- simulator runs: `{sim_root}`",
        f"- systems: {', '.join(systems) if systems else 'none'}",
        f"- repetitions: {', '.join(str(s) for s in sorted({p.seed for p in pairs}))}",
        f"- pairs compared: {sum(1 for p in pairs if p.comparable)} of {len(pairs)}",
        "",
        "## Side by side",
        "",
        *table_md(table, pairs),
        "",
        "## Disagreements larger than the spread",
        "",
        *bullets,
        "",
        "## What is real and what is modelled",
        "",
        "- Real: Firecracker boot, snapshot, restore and the measured functions in the guest; the TPM quote at every",
        "  session start; the worker cores, memory limit and network namespace; the policy code and its measured",
        "  decision time; arrivals and session ends from the scenario.",
        "- Modelled: every actor message (delay, bandwidth, loss) through the simulator's network model, which both",
        "  sides run; key release and attestation beyond the quote; every volunteer machine other than node02.",
        "- Emulation and simulator share the scenario hash; a pair that does not is not compared.",
        "",
    ]
    return "\n".join(head)


def cdf_figure(pairs: list[Pair], system: str, out: Path) -> Path | None:
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    good = [p for p in pairs if p.system == system and p.comparable]
    if not good:
        return None
    fig, ax = plt.subplots(figsize=(4.5, 3.2))
    emu = np.sort(np.concatenate([p.emu.sync_latency() for p in good]))
    sim = np.sort(np.concatenate([p.sim.sync_latency() for p in good if p.sim is not None]))
    for name, x, color in (("emulation", emu, "tab:red"), ("simulator", sim, "tab:blue")):
        if len(x):
            ax.step(x, np.arange(1, len(x) + 1) / len(x), where="post", color=color, label=name)
    ax.set_xscale("log")
    ax.set_xlabel("synchronous end-to-end latency (s)")
    ax.set_ylabel("CDF")
    ax.set_title(system)
    ax.legend()
    fig.tight_layout()
    path = out / f"cdf-{system}.pdf"
    fig.savefig(path)
    plt.close(fig)
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.emu.compare", description=__doc__)
    ap.add_argument("--emu", type=Path, required=True, help="emulation output root, e.g. runs-emu/<host_label>")
    ap.add_argument("--sim", type=Path, required=True, help="simulator runs (a run directory or a tree of them)")
    ap.add_argument("--out", type=Path, default=None, help="report directory (default: <emu>/report)")
    a = ap.parse_args(argv)
    out = a.out or a.emu / "report"
    out.mkdir(parents=True, exist_ok=True)
    pairs = pair_up(emu_runs(a.emu), sim_runs(a.sim))
    if not pairs:
        print(f"no emulation runs under {a.emu}/<system>/rep<i>/", flush=True)
        return 1
    table = cells(pairs)
    dis = disagreements(pairs, table)
    (out / "compare.md").write_text("\n".join(table_md(table, pairs)) + "\n")
    (out / "report.md").write_text(report_md(table, pairs, dis, a.emu, a.sim))
    rows = [
        {"system": p.system, "seed": p.seed, "side": side, **mets}
        for p in pairs
        for side, mets in (("emu", p.emu_metrics), ("sim", p.sim_metrics))
        if mets is not None
    ]
    pd.DataFrame(rows).to_csv(out / "pairs.csv", index=False)
    for system in table:
        cdf_figure(pairs, system, out)
    print("\n".join(table_md(table, pairs)))
    print()
    print("\n".join(f"- {d}" for d in dis) if dis else "- no disagreement larger than the spread")
    print(f"\nwrote {out}/compare.md, report.md, pairs.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
