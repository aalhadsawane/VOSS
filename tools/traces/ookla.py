"""Home network links from Ookla Open Data fixed-broadband tiles (docs/REVISION_PLAN.md V9.3).

    uv run python -m tools.traces.ookla --out data/traces/ookla-fixed-2024q1 [--parquet <tiles>] [--radius-km 30]

For each metro of ``configs/geo/metros.csv``: the tiles whose centre lies within ``radius_km`` of the metro, and
``--draws`` (download, upload, latency) triples drawn from them with probability proportional to the tile's number of
tests (so the three values stay correlated as measured). A worker in that metro draws one triple (``world/workers.py``).
Latency is the Speedtest round trip to a nearby server; the simulator's last-mile delay is half of it (stated in the
paper). Licence: CC BY-NC-SA 4.0 (non-commercial research use; derived files carry the same licence and attribution).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from voss.core.rng import stream

from tools.traces.common import download, write_provenance

URL = "https://ookla-open-data.s3.amazonaws.com/parquet/performance/type=fixed/year=2024/quarter=1/2024-01-01_performance_fixed_tiles.parquet"
SOURCE = {
    "name": "Speedtest by Ookla Global Fixed Network Performance Map Tiles, Q1 2024",
    "url": URL,
    "description": "https://github.com/teamookla/ookla-open-data",
    "licence": "CC BY-NC-SA 4.0",
    "attribution": (
        "Speedtest by Ookla Global Fixed and Mobile Network Performance Maps, accessed via AWS Open Data. Based on "
        "analysis by the VOSS authors of Speedtest by Ookla data for Q1 2024. Ookla trademarks used under license."
    ),
}
REPO = Path(__file__).resolve().parents[2]
COLS = ["tile_x", "tile_y", "avg_d_kbps", "avg_u_kbps", "avg_lat_ms", "tests"]


def metros() -> pd.DataFrame:
    return pd.read_csv(REPO / "configs" / "geo" / "metros.csv", comment="#")


def km(lat0: float, lon0: float, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Great-circle distance in km (haversine, Earth radius 6371 km)."""
    p0, p, dl = np.radians(lat0), np.radians(lat), np.radians(lon - lon0)
    a = np.sin((p - p0) / 2) ** 2 + np.cos(p0) * np.cos(p) * np.sin(dl / 2) ** 2
    out: np.ndarray = 2 * 6371.0 * np.arcsin(np.sqrt(a))
    return out


def derive(tiles: pd.DataFrame, cities: pd.DataFrame, radius_km: float, draws: int, seed: int) -> pd.DataFrame:
    """Per-city link triples and coverage counts."""
    parts = []
    for c in cities.itertuples():
        box = tiles[(tiles.tile_y - c.lat).abs() < radius_km / 100 + 0.5]
        box = box[(box.tile_x - c.lon).abs() < radius_km / 100 + 1.0]
        near = box[km(c.lat, c.lon, box.tile_y.to_numpy(), box.tile_x.to_numpy()) <= radius_km]
        near = near.sort_values(["tile_y", "tile_x"]).reset_index(drop=True)
        if near.empty:
            continue
        w = near.tests.to_numpy(dtype=float)
        pick = stream(seed, "traces.ookla", c.name).choice(len(near), size=draws, p=w / w.sum())
        d = near.iloc[pick]
        parts.append(
            pd.DataFrame(
                {
                    "city": c.name,
                    "down_kbps": d.avg_d_kbps.to_numpy(),
                    "up_kbps": d.avg_u_kbps.to_numpy(),
                    "lat_ms": d.avg_lat_ms.to_numpy(),
                    "tiles": len(near),
                    "tests": int(w.sum()),
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.traces.ookla")
    p.add_argument("--out", type=Path, default=Path("data/traces/ookla-fixed-2024q1"))
    p.add_argument("--parquet", type=Path, default=None)
    p.add_argument("--work", type=Path, default=Path("data/raw/ookla"))
    p.add_argument("--radius-km", type=float, default=30.0)
    p.add_argument("--draws", type=int, default=500)
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args(argv)
    src = a.parquet or download(URL, a.work / "2024-01-01_performance_fixed_tiles.parquet")
    tiles = pq.read_table(src, columns=COLS).to_pandas()
    cities = metros()
    links = derive(tiles, cities, a.radius_km, a.draws, a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    links.to_parquet(a.out / "links.parquet", index=False)
    covered = sorted(links.city.unique())
    missing = sorted(set(cities.name) - set(covered))
    print(f"{len(covered)} of {len(cities)} metros covered; none within {a.radius_km} km: {missing}")
    params = {
        "radius_km": a.radius_km,
        "draws_per_city": a.draws,
        "seed": a.seed,
        "weight": "tests per tile",
        "last_mile": "half the Speedtest round-trip latency",
        "cities_without_tiles": missing,
    }
    write_provenance(a.out, SOURCE, [src], params)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
