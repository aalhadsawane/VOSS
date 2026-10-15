"""Paper tables (ROADMAP P10): everything under ``paper/tables`` and ``paper/*.md`` is a function of the run logs
(and the simulated E-CS1 table). Called by ``python -m experiments.paper analyze``; each function writes one artifact
and returns its path so the pipeline can list them in ``paper/manifest.json``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.analysis import pareto, scorecard, viability
from experiments.analysis.lib import collect, report, run_dirs, spec

REPO = Path(__file__).resolve().parents[2]
# Existing per-experiment report modules: (module, experiment) pairs. Each takes ``root`` (a sweep directory) and --out.
LEGACY = {
    "E04": "p4", "E09": "p4", "E02": "p4",
    "E05": "p5", "E06": "p5", "E07": "p5", "E10": "p5",
    "E08": "p6", "E14": "p6", "E15": "p6", "E16": "p6",
    "E12": "p7", "E13": "p7",
}  # fmt: skip
GENERIC = ("E17", "E18", "E19", "E24")


def has_runs(exp: str, runs: Path) -> bool:
    return (runs / exp).exists() and bool(run_dirs(exp, runs))


def legacy_table(exp: str, runs: Path, out: Path) -> Path | None:
    """Run the pilot-era report module for ``exp`` into ``out`` (same statistics, now over 10 seeds)."""
    if not has_runs(exp, runs):
        return None
    dst = out / f"{exp}.md"
    subprocess.run(
        [sys.executable, "-m", f"experiments.analysis.{LEGACY[exp]}", exp, str(runs / exp), "--out", str(dst)],
        check=True, cwd=REPO,
    )  # fmt: skip
    return dst


def generic_table(exp: str, runs: Path, out: Path) -> Path | None:
    if not has_runs(exp, runs):
        return None
    df = collect(exp, runs)
    dst = out / f"{exp}.md"
    dst.write_text(report(exp, df))
    df.drop(columns=["run_dir"]).to_csv(dst.with_suffix(".csv"), index=False)
    return dst


def e03_table(runs: Path, out: Path) -> Path | None:
    if not has_runs("E03", runs):
        return None
    dst = out / "E03.md"
    dirs = [str(d) for d in run_dirs("E03", runs)]
    subprocess.run([sys.executable, "-m", "experiments.analysis.e03", *dirs, "--out", str(dst)], check=True, cwd=REPO)
    return dst


def viability_table(exp: str, runs: Path, out: Path) -> Path | None:
    if not has_runs(exp, runs):
        return None
    df = collect(exp, runs)
    cell = [k for k in spec(exp)["report"]["keys"] if k != "label"]
    table = viability.cells(df, cell)
    dst = out / f"{exp}.md"
    dst.write_text(viability.markdown(exp, cell, table, viability.system_stats(df, cell), df))
    table.to_csv(dst.with_suffix(".csv"), index=False)
    return dst


def pareto_table(runs: Path, out: Path) -> tuple[Path | None, pd.DataFrame]:
    if not has_runs("E23", runs):
        return None, pd.DataFrame()
    res = pareto.analyse(pareto.config_means(collect("E23", runs)))
    dst = out / "E23.md"
    dst.write_text(pareto.markdown(res))
    res.to_csv(dst.with_suffix(".csv"), index=False)
    return dst, res


def h3_row(res: pd.DataFrame) -> dict[str, object]:
    """H3: the latency-exposure front has a knee, and the knee loses little latency for a lot of exposure."""
    row: dict[str, object] = {
        "id": "H3",
        "claim": "Pareto front has a knee; moderate exposure loses little latency",
        "exp": "E23",
        "cmp": "knee vs best-latency front point",
        "metric": "p99_sync",
    }
    nan = np.nan
    if not len(res) or not res.knee.any():
        return row | {"verdict": "no data", "delta": nan, "lo": nan, "hi": nan, "base": nan, "n": 0}
    front = res[res.front2]
    k, best = res[res.knee].iloc[0], front.loc[front.p99_sync.idxmin()]
    lat_loss = float(k.p99_sync / best.p99_sync - 1.0)
    exp_saved = float(1.0 - k.exposure / front.exposure.max())
    ok = len(front) >= 3 and lat_loss <= 0.10 and exp_saved >= 0.20
    verdict = "supported" if ok else ("weak" if len(front) >= 3 else "inconclusive")
    return row | {
        "verdict": verdict,
        "delta": float(k.p99_sync - best.p99_sync),
        "lo": nan,
        "hi": nan,
        "base": float(best.p99_sync),
        "n": int(k.n),
        "note": f"exposure -{100 * exp_saved:.0f}% at the knee",
    }


def h5_rows(csv: Path) -> list[dict[str, object]]:
    """H5 from the simulated E-CS1 table (mid points of literature ranges): trust cost per session vs start level."""
    if not csv.exists():
        return []
    d = pd.read_csv(csv)
    d = d[(d.range_at == 0.5) & d.fn.isin(["-", "dynamic-html"])]

    def p50(sub: str, what: str) -> float:
        v = d[(d.substrate == sub) & (d.what == what)].p50_s
        return float(v.iloc[0]) if len(v) else np.nan

    base = {"exp": "E-CS1 (sim)", "metric": "p50 s", "lo": np.nan, "hi": np.nan, "n": 1}
    rows = []
    for claim, a, b, lo_ok, hi_ok in (
        ("appliance warm start ≈ Firecracker without attestation (L3)", p50("appliance_tpm", "start_L3"),
         p50("none", "start_L3"), 0.9, 1.1),
        ("appliance snapshot start ≈ Firecracker without attestation (L2)", p50("appliance_tpm", "start_L2"),
         p50("none", "start_L2"), 0.9, 1.1),
        ("CVM classes are 10-100x slower than the appliance to establish trust", p50("cvm_snp", "session_establish"),
         p50("appliance_tpm", "session_establish"), 10.0, 100.0),
    ):  # fmt: skip
        r = a / b if b else np.nan
        verdict = "supported" if lo_ok <= r <= hi_ok else "refuted"
        rows.append(
            base
            | {
                "id": "H5",
                "claim": claim,
                "cmp": "ratio - 1 (mid-range)",
                "delta": r - 1.0,
                "base": 1.0,
                "verdict": verdict,
            }
        )
    return rows


def scorecard_files(runs: Path, ecs1_csv: Path, res: pd.DataFrame, out: Path) -> list[Path]:
    sc = scorecard.run_all(runs)
    extra = [h3_row(res), *h5_rows(ecs1_csv)]
    sc = pd.concat([sc, pd.DataFrame(extra)], ignore_index=True) if extra else sc
    sc = sc.sort_values("id", kind="stable", key=scorecard.order_key).reset_index(drop=True)
    sc["cell"] = sc["cell"].fillna("")
    paths = [out.parent / "hypotheses.md", out.parent / "negative-results.md"]
    paths[0].write_text(scorecard.markdown(sc))
    paths[1].write_text(scorecard.negative_results(sc))
    sc.to_csv(out / "hypotheses.csv", index=False)
    return paths
