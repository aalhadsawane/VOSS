"""Geography: metro table, great-circle distance, local time (doc 02 §1, §3)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voss.core.paths import config_path

EARTH_RADIUS_KM = 6371.0
KM_PER_DEG_LAT = 111.0


@dataclass(frozen=True)
class Metros:
    """Struct-of-arrays metro table."""

    name: tuple[str, ...]
    lat: np.ndarray
    lon: np.ndarray
    tz: np.ndarray
    pop: np.ndarray
    region: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.name)

    def index(self, name: str) -> int:
        return self.name.index(name)

    def weights(self) -> np.ndarray:
        w: np.ndarray = self.pop / self.pop.sum()
        return w


def load_metros(path: str | Path = "geo/metros.csv") -> Metros:
    rows = list(csv.DictReader(line for line in config_path(path).open() if not line.startswith("#")))
    return Metros(
        name=tuple(r["name"] for r in rows),
        lat=np.array([float(r["lat"]) for r in rows]),
        lon=np.array([float(r["lon"]) for r in rows]),
        tz=np.array([float(r["tz"]) for r in rows]),
        pop=np.array([float(r["pop"]) for r in rows]),
        region=tuple(r["region"] for r in rows),
    )


def haversine_km(
    lat1: np.ndarray | float, lon1: np.ndarray | float, lat2: np.ndarray | float, lon2: np.ndarray | float
) -> np.ndarray | float:
    """Great-circle distance in km (vectorized)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    d = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return float(d) if np.ndim(d) == 0 else d


def jitter_location(
    lat: np.ndarray, lon: np.ndarray, km: float, gen: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Uniform jitter within a disc of radius ``km`` around each point."""
    n = len(lat)
    r = km * np.sqrt(gen.random(n))
    theta = 2 * np.pi * gen.random(n)
    dlat = r * np.cos(theta) / KM_PER_DEG_LAT
    dlon = r * np.sin(theta) / (KM_PER_DEG_LAT * np.maximum(np.cos(np.radians(lat)), 0.1))
    return lat + dlat, lon + dlon


def local_hour(tz: np.ndarray | float, t: np.ndarray | float, start_utc_h: float) -> np.ndarray | float:
    """Local hour of day in [0, 24) at simulated time ``t`` (seconds) for UTC offsets ``tz``."""
    h = np.mod(start_utc_h + np.asarray(t) / 3600.0 + np.asarray(tz), 24.0)
    return float(h) if np.ndim(h) == 0 else h


def diurnal(hour: np.ndarray | float, peak_h: float, amplitude: float) -> np.ndarray | float:
    """Cosine diurnal factor with mean 1: ``1 + A·cos(2π(h − peak)/24)``."""
    f = 1.0 + amplitude * np.cos(2 * np.pi * (np.asarray(hour) - peak_h) / 24.0)
    return float(f) if np.ndim(f) == 0 else f
