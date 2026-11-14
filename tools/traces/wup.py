"""Metro populations from the UN World Urbanization Prospects 2025 (docs/REVISION_PLAN.md V9.4, cities).

    uv run python -m tools.traces.wup --out data/traces/wup2025 [--xlsx <WUP2025-F21-DEGURBA-Cities_Pop.xlsx>]

Workers and demand are spread over the metros of ``configs/geo/metros.csv`` in proportion to population; the table's
own figures are rough public numbers. WUP 2025 defines cities in one way for every country (Degree of Urbanisation:
contiguous 1 km² cells with at least 1,500 inhabitants per km², at least 50,000 inhabitants) and gives each city's
population-weighted centre. WUP cities never overlap, so each metro takes the summed population, in ``--year``, of the
WUP cities whose centre lies within ``radius_km`` of it and nearer to it than to any other metro (30 km, the radius of
the Ookla links of V9.3). Limit, stated in the paper: suburbs below the density threshold belong to no city, which
lowers sprawling metros (most in the USA) against the table. GeoNames was tried first and dropped: its records for a
city and for the city's parts overlap, so sums over a radius count people twice.
Licence: CC BY 3.0 IGO (United Nations, DESA, Population Division).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from tools.traces.common import download, write_provenance
from tools.traces.ookla import km, metros

URL = "https://population.un.org/wup/assets/Download/Cities/WUP2025-F21-DEGURBA-Cities_Pop.xlsx"
SOURCE = {
    "name": "World Urbanization Prospects: The 2025 Revision, F21 (population of cities, Degree of Urbanisation)",
    "url": URL,
    "description": "https://population.un.org/wup/downloads",
    "licence": "CC BY 3.0 IGO",
    "attribution": (
        "United Nations, Department of Economic and Social Affairs, Population Division (2025). World Urbanization "
        "Prospects: The 2025 Revision, Online Edition."
    ),
}


def read_cities(path: Path, year: int) -> pd.DataFrame:
    """WUP cities with name, ISO2, centre and population (persons) in ``year``."""
    d = pd.read_excel(path, sheet_name="Data")
    col = next(c for c in d.columns if str(c).split(".")[0] == str(year))
    out = pd.DataFrame(
        {
            "wup_name": d.City_Name.astype(str),
            "iso2": d.ISO2_Code.astype(str),
            "lat": d.PWCent_Latitude.astype(float),
            "lon": d.PWCent_Longitude.astype(float),
            "pop": d[col].astype(float) * 1000.0,
        }
    )
    return out[out["pop"].notna() & (out["pop"] > 0)].reset_index(drop=True)


def match(cities: pd.DataFrame, wup: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    """Per metro: summed population and count of the WUP cities assigned to it (nearest metro, within ``radius_km``),
    and the largest of them (to check the match by name)."""
    lat, lon, pop = wup.lat.to_numpy(), wup.lon.to_numpy(), wup["pop"].to_numpy()
    d = np.stack([km(c.lat, c.lon, lat, lon) for c in cities.itertuples()])  # metros x WUP cities
    near = np.argmin(d, axis=0)
    ok = d[near, np.arange(len(wup))] <= radius_km
    rows = []
    for i, c in enumerate(cities.itertuples()):
        mine = np.flatnonzero(ok & (near == i))
        top = int(mine[np.argmax(pop[mine])]) if len(mine) else -1
        rows.append(
            {
                "city": c.name,
                "pop": float(pop[mine].sum()),
                "wup_cities": len(mine),
                "largest": wup.wup_name[top] if top >= 0 else "",
                "table_pop_m": float(c.pop),
            }
        )
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.traces.wup")
    p.add_argument("--out", type=Path, default=Path("data/traces/wup2025"))
    p.add_argument("--xlsx", type=Path, default=None)
    p.add_argument("--work", type=Path, default=Path("data/raw/wup"))
    p.add_argument("--radius-km", type=float, default=30.0)
    p.add_argument("--year", type=int, default=2024)
    a = p.parse_args(argv)
    src = a.xlsx or download(URL, a.work / "WUP2025-F21-DEGURBA-Cities_Pop.xlsx")
    pops = match(metros(), read_cities(src, a.year), a.radius_km)
    a.out.mkdir(parents=True, exist_ok=True)
    pops.to_parquet(a.out / "metro_pop.parquet", index=False)
    empty = sorted(pops.city[pops["pop"] <= 0])
    ratio = pops["pop"][pops["pop"] > 0] / (pops.table_pop_m * 1e6)
    print(f"{len(pops)} metros, total {pops['pop'].sum() / 1e6:.1f} M; unmatched: {empty}")
    print(f"WUP / table population: median {ratio.median():.2f}, min {ratio.min():.2f}, max {ratio.max():.2f}")
    params = {
        "year": a.year,
        "radius_km": a.radius_km,
        "match": "sum of WUP cities whose population-weighted centre is within radius_km, each to its nearest metro",
        "unmatched_metros": empty,
    }
    write_provenance(a.out, SOURCE, [src], params)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
