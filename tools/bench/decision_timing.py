"""Decision timing on the provider's CPU (docs/REVISION_PLAN.md V10).

    uv run python -m tools.bench.decision_timing run --workers 1000 --functions 12,100,500 --out bench/w1000
    uv run python -m tools.bench.decision_timing fit bench/* --out configs/calibration/provider

``run``: for every (pool size, function count), one short simulation of the real system (base config, hetero
planner, load proportional to the pool) on one thread. Every provisioning round (Algorithm 1, kind ``plan``) and every
placement decision (Algorithm 2, kind ``place``) is timed by the scheduler itself (``time.perf_counter`` around the
policy call) and logged with the ``work`` the decision clock receives (``solver`` table). The two kinds the
simulation does not execute are timed directly: ``route`` (the router's choice among the schedulers it knows) and
``verify`` (Ed25519 signature checks, one per receipt, as doc 09 §3 specifies). Function counts above the catalogue's
are copies of its functions under new names.

``fit``: per kind, ``seconds = a + b·work`` by non-negative least squares on per-bin medians of ``work`` (20 quantile
bins), so the many small placement decisions do not drown the large ones. Writes
``<out>/<cpu-label>/decision.yaml`` (coefficients, samples, CPU from ``lscpu``) and the pool size at which a
placement decision exceeds 10% of the median synchronous deadline (the stated limit of one scheduler).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy.optimize import nnls
from voss.core.config import DECISION_KINDS, load_config
from voss.core.paths import REPO_ROOT, config_path, load_data_yaml
from voss.metrics.schema import Table
from voss.runtime.system import run_system

WORK = {
    "plan": "decision variables of the provisioning round (functions x candidate workers)",
    "place": "candidate (invocation, worker) pairs scored by request placement",
    "route": "schedulers the router knows",
    "verify": "receipts whose signature is checked",
}
RATE_PER_WORKER = 0.1  # invocations per second per worker, the load of the sizing runs (D-97)


def catalog(n: int, tmp: Path) -> Path:
    """A functions file with ``n`` functions: the catalogue's, then copies under new names, round robin."""
    base = load_data_yaml("functions.yaml")["functions"]
    fns = [dict(base[i % len(base)], name=f"{base[i % len(base)]['name']}-{i // len(base)}") for i in range(n)]
    path = tmp / f"functions-{n}.yaml"
    path.write_text(yaml.safe_dump({"functions": fns}, sort_keys=False))
    return path


def simulate(workers: int, n_fns: int, horizon: float, tmp: Path) -> pd.DataFrame:
    """Decision samples of one short run: kind, work, wall seconds."""
    sets = [
        f"scenario.workers={workers}",
        f"scenario.load.rate={RATE_PER_WORKER * workers}",
        f"horizon_s={horizon}",
        "scenario.warmup_s=0",
        "voss.planner.name=hetero",
        "voss.planner.T_plan=10",  # more provisioning rounds per simulated second; the round itself is unchanged
    ]
    if n_fns != len(load_data_yaml("functions.yaml")["functions"]):
        sets.append(f"scenario.functions={catalog(n_fns, tmp)}")
    res = run_system(load_config(REPO_ROOT / "configs" / "base.yaml", sets))
    sol = res.recorder.frame(Table.SOLVER)
    sol = sol[sol.kind.isin(["plan", "place"])]
    inv = res.recorder.frame(Table.INVOCATIONS)
    sync = inv[inv.slo_class == 0].deadline if len(inv) else pd.Series(dtype=float)
    return pd.DataFrame(
        {
            "kind": sol.kind.to_numpy(),
            "work": sol["size"].astype(float).to_numpy(),
            "wall_s": sol.solve_wall_s.astype(float).to_numpy(),
            "workers": workers,
            "functions": n_fns,
            "sync_deadline_s": float(sync.median()) if len(sync) else np.nan,
        }
    )


def time_route(reps: int = 2000) -> pd.DataFrame:
    """The router's choice (``Router._choose``: the lowest cluster id it knows) for 1..8 known schedulers."""
    rows = []
    for k in (1, 2, 4, 8):
        scheds = {c: (0, ("scheduler", f"s{c}")) for c in range(k)}
        for _ in range(reps):
            t0 = time.perf_counter()
            _ = min(scheds) if scheds else None
            rows.append(("route", float(k), time.perf_counter() - t0))
    return pd.DataFrame(rows, columns=["kind", "work", "wall_s"])


def time_verify(reps: int = 20) -> pd.DataFrame:
    """Ed25519 verification of a batch of ``n`` receipts (doc 09 §3), n = 1..1,000."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: PLC0415

    key = Ed25519PrivateKey.generate()
    pub = key.public_key()
    rows = []
    for n in (1, 10, 100, 1000):
        msgs = [f"receipt {i} attempt 0 worker 7 digest {i * 31}".encode() for i in range(n)]
        sigs = [key.sign(m) for m in msgs]
        for _ in range(reps):
            t0 = time.perf_counter()
            for m, s in zip(msgs, sigs, strict=True):
                pub.verify(s, m)
            rows.append(("verify", float(n), time.perf_counter() - t0))
    return pd.DataFrame(rows, columns=["kind", "work", "wall_s"])


def cmd_run(a: argparse.Namespace) -> None:
    a.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for n_fns in a.functions:
            t0 = time.perf_counter()
            df = simulate(a.workers, n_fns, a.horizon, Path(tmp))
            df.to_parquet(a.out / f"w{a.workers}-f{n_fns}.parquet", index=False)
            print(f"workers={a.workers} functions={n_fns}: {len(df)} decisions in {time.perf_counter() - t0:.0f} s")
    if a.micro:
        pd.concat([time_route(), time_verify()], ignore_index=True).to_parquet(a.out / "micro.parquet", index=False)
    (a.out / "lscpu.txt").write_text(subprocess.run(["lscpu"], capture_output=True, text=True, check=False).stdout)


def fit_kind(df: pd.DataFrame, bins: int = 20) -> dict[str, Any]:
    """``a + b·work`` (a, b >= 0) through per-bin medians; R² on the bin medians."""
    q = pd.qcut(df.work.rank(method="first"), min(bins, len(df)), labels=False)
    med = df.groupby(q).agg(work=("work", "median"), wall=("wall_s", "median"))
    x = np.column_stack([np.ones(len(med)), med.work.to_numpy()])
    (a, b), _ = nnls(x, med.wall.to_numpy())
    pred = a + b * med.work.to_numpy()
    ss = float(((med.wall - med.wall.mean()) ** 2).sum())
    r2 = 1.0 - float(((med.wall - pred) ** 2).sum()) / ss if ss > 0 else 1.0
    return {"a": float(a), "b": float(b), "r2": round(r2, 4), "samples": len(df), "work_max": float(df.work.max())}


def cpu_label(lscpu: str) -> str:
    """Lower-case model name, e.g. ``intel-xeon-platinum-8573c``."""
    m = re.search(r"^Model name:\s*(.+)$", lscpu, re.M)
    name = (m.group(1) if m else "unknown").lower()
    name = re.sub(r"\((r|tm)\)|cpu|@.*|\d+(th|st|nd|rd) gen", " ", name)
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def limit(sim: pd.DataFrame) -> dict[str, Any]:
    """Per function count: the median placement time per pool size and the first pool where it exceeds 10% of the
    median synchronous deadline (``null`` if no measured pool reaches it)."""
    out: dict[str, Any] = {}
    place = sim[sim.kind == "place"]
    for n_fns, g in place.groupby("functions"):
        by_pool = g.groupby("workers").wall_s.median().sort_index()
        bound = 0.1 * float(g.sync_deadline_s.median())
        over = [int(w) for w, s in by_pool.items() if s > bound]
        out[str(n_fns)] = {
            "median_place_s": {int(w): float(s) for w, s in by_pool.items()},
            "bound_s": bound,
            "first_pool_over": over[0] if over else None,
        }
    return out


def cmd_fit(a: argparse.Namespace) -> None:
    dirs = [Path(d) for d in a.dirs]
    sim = pd.concat([pd.read_parquet(p) for d in dirs for p in sorted(d.glob("w*-f*.parquet"))], ignore_index=True)
    micro = pd.concat([pd.read_parquet(p) for d in dirs for p in sorted(d.glob("micro.parquet"))], ignore_index=True)
    lscpu = next(d / "lscpu.txt" for d in dirs if (d / "lscpu.txt").exists()).read_text()
    allk = pd.concat([sim[["kind", "work", "wall_s"]], micro], ignore_index=True)
    fits = {k: fit_kind(allk[allk.kind == k]) for k in DECISION_KINDS}
    label = cpu_label(lscpu)
    rec = {
        "provenance": {"default": "measured", "source": a.source, "note": "tools/bench/decision_timing.py (plan V10)"},
        "cpu": {"label": label, "lscpu": lscpu.strip().splitlines()},
        "work_units": WORK,
        "coeffs": {k: [f["a"], f["b"]] for k, f in fits.items()},
        "fit": fits,
        "pools": sorted(int(w) for w in sim.workers.unique()),
        "functions": sorted(int(f) for f in sim.functions.unique()),
        "placement_limit": limit(sim),
    }
    dst = a.out / label
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "decision.yaml").write_text(yaml.safe_dump(rec, sort_keys=False))
    for k, f in fits.items():
        print(f"{k}: a={f['a']:.3g} s, b={f['b']:.3g} s per unit, R2={f['r2']}, n={f['samples']}")
    print(f"wrote {dst / 'decision.yaml'}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.bench.decision_timing")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--workers", type=int, required=True)
    r.add_argument("--functions", type=lambda s: [int(x) for x in s.split(",")], default=[12, 100, 500])
    r.add_argument("--horizon", type=float, default=300.0)
    r.add_argument("--micro", action="store_true", help="also time route and verify")
    r.add_argument("--out", type=Path, required=True)
    f = sub.add_parser("fit")
    f.add_argument("dirs", nargs="+")
    f.add_argument("--out", type=Path, default=config_path("calibration/provider"))
    f.add_argument("--source", default="local run")
    a = p.parse_args(argv)
    cmd_run(a) if a.cmd == "run" else cmd_fit(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
