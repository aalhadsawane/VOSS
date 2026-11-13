"""Wide-area delay from WonderProxy's public all-pairs pings (docs/REVISION_PLAN.md V9.3).

    uv run python -m tools.traces.pings --out data/traces/wonderproxy-2020-07

The simulator's wide-area round trip is ``km / c_eff × route_factor`` plus both last miles (``world/network.py``,
``c_eff`` = 100 km per ms of round trip, light in fibre). For every pair of ping servers more than ``--min-km`` apart,
take the pair's median RTT over the day; fit ``RTT = a + b · km`` by least absolute deviations (robust to congested
pairs); ``route_factor = b × c_eff``. The dataset states no licence, so only this fitted statistic is kept (no raw or
per-pair data is redistributed); the source is cited.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.optimize import linprog

from tools.traces.common import download, write_provenance
from tools.traces.ookla import km

BASE = "https://wp-public-data.s3.amazonaws.com/pings/"
PINGS, SERVERS = "pings-2020-07-19-2020-07-20.csv.gz", "servers-2020-07-19.csv"
SOURCE = {
    "name": "WonderProxy global ping statistics, 2020-07-19 to 2020-07-20",
    "url": BASE + PINGS,
    "description": "https://wonderproxy.com/blog/a-day-in-the-life-of-the-internet/",
    "licence": "none stated; only a fitted statistic is kept, no raw data is redistributed",
}
C_EFF_KM_PER_MS = 100.0  # light in fibre (2/3 c) over a round trip


def pair_medians(pings: pd.DataFrame, servers: pd.DataFrame) -> pd.DataFrame:
    med = pings.groupby(["source", "destination"])["avg"].median().reset_index()
    s = servers.set_index("id")[["latitude", "longitude"]]
    med = med[med.source.isin(s.index) & med.destination.isin(s.index)]  # pings from servers missing in the list
    a, b = s.loc[med.source].to_numpy(), s.loc[med.destination].to_numpy()
    d = np.array([km(x[0], x[1], np.array([y[0]]), np.array([y[1]]))[0] for x, y in zip(a, b, strict=True)])
    return med.assign(km=d)


def lad_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Least-absolute-deviation line ``y = a + b x`` as a linear program."""
    n = len(x)
    c = np.r_[0.0, 0.0, np.ones(2 * n)]
    a_eq = np.c_[np.ones(n), x, np.eye(n), -np.eye(n)]
    bounds = [(None, None), (None, None)] + [(0, None)] * (2 * n)
    r = linprog(c, A_eq=a_eq, b_eq=y, bounds=bounds, method="highs")
    return float(r.x[0]), float(r.x[1])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.traces.pings")
    p.add_argument("--out", type=Path, default=Path("data/traces/wonderproxy-2020-07"))
    p.add_argument("--work", type=Path, default=Path("data/raw/wonderproxy"))
    p.add_argument("--min-km", type=float, default=500.0)
    p.add_argument("--max-pairs", type=int, default=4000, help="pairs used in the fit (deterministic sample)")
    a = p.parse_args(argv)
    src = [download(BASE + PINGS, a.work / PINGS), download(BASE + SERVERS, a.work / SERVERS)]
    pairs = pair_medians(pd.read_csv(src[0], usecols=["source", "destination", "avg"]), pd.read_csv(src[1]))
    pairs = pairs[(pairs.km >= a.min_km) & pairs["avg"].notna()].sort_values(["source", "destination"])
    fit_on = pairs.iloc[np.linspace(0, len(pairs) - 1, min(a.max_pairs, len(pairs))).astype(int)]
    icpt, slope = lad_fit(fit_on.km.to_numpy(), fit_on["avg"].to_numpy())
    resid = pairs["avg"] - (icpt + slope * pairs.km)
    stat = {
        "route_factor": round(slope * C_EFF_KM_PER_MS, 3),
        "intercept_ms": round(icpt, 2),
        "pairs": len(pairs),
        "pairs_in_fit": len(fit_on),
        "median_abs_residual_ms": round(float(resid.abs().median()), 2),
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "route_fit.yaml").write_text(yaml.safe_dump(stat, sort_keys=False))
    print(stat)
    write_provenance(
        a.out,
        SOURCE,
        src,
        {"min_km": a.min_km, "statistic": "median RTT per pair, LAD fit vs km", "c_eff_km_per_ms": C_EFF_KM_PER_MS},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
