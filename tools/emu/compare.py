"""E01: simulator against emulation (doc 10 §4, doc 06 §5): ``python -m tools.emu.compare --root runs-e01``.

Run directories are ``<root>/<scenario>-<sim|emu>-<seed>``. The two sides share the scenario (same exogenous traces)
but not the trajectory, so runs are compared as distributions, never invocation by invocation.

Metrics and thresholds are fixed here, before any E01 run (the paper's protocol for hypotheses): per scenario and
seed, with relative error ``(sim - emu) / emu``:

* sync end-to-end latency (successful invocations): relative error of P50 and P99 and the Kolmogorov-Smirnov distance;
* component medians (route, decide, net, wait, trust, startup, exec): relative error, reported, not thresholded;
* success rate and deadline-met fraction: difference in percentage points (sim - emu);
* start-level shares (L0..L3 among successes): total-variation distance.

Verdict per scenario over seeds, on the seed means: ``close`` if |P50 error| <= 25%, |P99 error| <= 40%, |success
difference| <= 2 points, KS <= 0.20 and level-share TV <= 0.15; ``partly`` if at least half of those hold; else
``far``. These cut-offs are judgements about what is good enough to trust a policy comparison, not statistics.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

THRESH = {"p50": 0.25, "p99": 0.40, "success_pp": 2.0, "ks": 0.20, "level_tv": 0.15}
COMPONENTS = ("route", "decide", "net_in", "wait", "trust", "startup", "exec", "net_out")
LEVELS = ("L0", "L1", "L2", "L3")


def load(run: Path) -> pd.DataFrame:
    return pd.read_parquet(run / "invocations.parquet")


def sync_ok(inv: pd.DataFrame) -> pd.DataFrame:
    return inv[(inv.slo_class == 0) & (inv.outcome == "ok")]


def level_shares(inv: pd.DataFrame) -> np.ndarray:
    ok = inv[inv.outcome == "ok"]
    n = max(1, len(ok))
    return np.array([(ok.start_level == lv).sum() / n for lv in LEVELS])


def metrics(inv: pd.DataFrame) -> dict[str, float]:
    s = sync_ok(inv)
    out: dict[str, float] = {
        "n": float(len(inv)),
        "success": 100.0 * float((inv.outcome == "ok").mean()),
        "met": 100.0 * float(inv.met.fillna(False).astype(bool).mean()),
        "n_sync_ok": float(len(s)),
    }
    for q in (50, 90, 99):
        out[f"p{q}"] = float(np.percentile(s.e2e, q)) if len(s) else float("nan")
    ok = inv[inv.outcome == "ok"]
    for c in COMPONENTS:
        out[f"{c}_med"] = float(ok[c].median()) if len(ok) else float("nan")
    return out


def rel(sim: float, emu: float) -> float:
    return (sim - emu) / emu if emu > 0 else float("nan")


def compare_pair(sim: pd.DataFrame, emu: pd.DataFrame) -> dict[str, float]:
    ms, me = metrics(sim), metrics(emu)
    row: dict[str, float] = {
        "p50_err": rel(ms["p50"], me["p50"]),
        "p99_err": rel(ms["p99"], me["p99"]),
        "p90_err": rel(ms["p90"], me["p90"]),
        "success_pp": ms["success"] - me["success"],
        "met_pp": ms["met"] - me["met"],
        "ks": float(ks_2samp(sync_ok(sim).e2e, sync_ok(emu).e2e).statistic)
        if len(sync_ok(sim)) and len(sync_ok(emu))
        else float("nan"),
        "level_tv": 0.5 * float(np.abs(level_shares(sim) - level_shares(emu)).sum()),
        "sim_p50": ms["p50"],
        "emu_p50": me["p50"],
        "sim_p99": ms["p99"],
        "emu_p99": me["p99"],
    }
    for c in COMPONENTS:
        row[f"{c}_err"] = rel(ms[f"{c}_med"], me[f"{c}_med"])
    return row


def verdict(mean: dict[str, float]) -> tuple[str, dict[str, bool]]:
    checks = {
        "p50": abs(mean["p50_err"]) <= THRESH["p50"],
        "p99": abs(mean["p99_err"]) <= THRESH["p99"],
        "success": abs(mean["success_pp"]) <= THRESH["success_pp"],
        "ks": mean["ks"] <= THRESH["ks"],
        "level_tv": mean["level_tv"] <= THRESH["level_tv"],
    }
    n = sum(checks.values())
    return ("close" if n == len(checks) else "partly" if n >= len(checks) / 2 else "far"), checks


def pairs(root: Path) -> dict[str, dict[int, tuple[Path, Path]]]:
    found: dict[str, dict[int, dict[str, Path]]] = {}
    for d in sorted(root.iterdir()):
        m = re.fullmatch(r"(.+)-(sim|emu)-(\d+)", d.name)
        if m and (d / "invocations.parquet").exists():
            found.setdefault(m.group(1), {}).setdefault(int(m.group(3)), {})[m.group(2)] = d
    return {
        sc: {seed: (v["sim"], v["emu"]) for seed, v in sorted(seeds.items()) if {"sim", "emu"} <= set(v)}
        for sc, seeds in found.items()
    }


def cdf_figure(root: Path, sc: str, seeds: dict[int, tuple[Path, Path]], out: Path) -> None:
    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415

    fig, ax = plt.subplots(figsize=(4.5, 3.2))
    for side, color, idx in (("simulator", "tab:blue", 0), ("emulation", "tab:red", 1)):
        x = np.sort(np.concatenate([sync_ok(load(p[idx])).e2e.to_numpy() for p in seeds.values()]))
        ax.step(x, np.arange(1, len(x) + 1) / len(x), where="post", color=color, label=side)
    ax.set_xscale("log")
    ax.set_xlabel("sync end-to-end latency (s)")
    ax.set_ylabel("CDF")
    ax.set_title(sc)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / f"cdf-{sc}.pdf")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.emu.compare", description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("runs-e01"))
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    out = a.out or a.root / "report"
    out.mkdir(parents=True, exist_ok=True)
    rows, lines = (
        [],
        [
            "| scenario | seeds | P50 err | P99 err | KS | success (pp) | met (pp) | level TV | verdict |",
            "|---|---|---|---|---|---|---|---|---|",
        ],
    )
    for sc, seeds in sorted(pairs(a.root).items()):
        per = [compare_pair(load(s), load(e)) | {"scenario": sc, "seed": seed} for seed, (s, e) in seeds.items()]
        rows += per
        df = pd.DataFrame(per)
        mean = df.drop(columns=["scenario", "seed"]).mean().to_dict()
        v, _ = verdict(mean)
        lines.append(
            f"| {sc} | {len(df)} | {mean['p50_err']:+.0%} | {mean['p99_err']:+.0%} | {mean['ks']:.2f} | "
            f"{mean['success_pp']:+.1f} | {mean['met_pp']:+.1f} | {mean['level_tv']:.2f} | {v} |"
        )
        cdf_figure(a.root, sc, seeds, out)
    pd.DataFrame(rows).to_csv(out / "e01_pairs.csv", index=False)
    (out / "e01_summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
