"""Worker population (doc 02 §1): location, hardware, substrate, tier, identity, failure domain, link, envelope."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from voss.core.config import ScenarioConfig
from voss.core.rng import RngFactory
from voss.world.geo import Metros, jitter_location
from voss.world.hardware import HwClass

TIERS: tuple[str, ...] = ("nightly", "idle", "dedicated")


class GeoParams(BaseModel):
    """Doc 02 §1 location model. tag: assumed."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    metros: str = "geo/metros.csv"
    jitter_km: float = Field(default=30.0, ge=0)
    asns_per_city: int = Field(default=3, ge=1)
    asn_zipf: float = Field(default=1.0, ge=0)
    regions: tuple[str, ...] = ()  # empty = world; else workers and demand only in these regions (E05 dispersion)


class LinkParams(BaseModel):
    """Residential access links (doc 02 §1, §3). tag: assumed (typical residential broadband)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    down_mbps_median: float = 100.0
    down_sigma: float = 0.8
    up_ratio_median: float = 0.3
    up_ratio_sigma: float = 0.6
    last_mile_ms_median: float = 10.0
    last_mile_sigma: float = 0.5
    relayed_frac: float = Field(default=0.15, ge=0, le=1)


class EnvelopeParams(BaseModel):
    """Donor envelope: share of the machine VOSS may use during a session (doc 02 §1). tag: assumed."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    cpu_frac: float = Field(default=0.75, gt=0, le=1)
    mem_frac: float = Field(default=0.6, gt=0, le=1)
    ssd_frac: float = Field(default=0.2, ge=0, le=1)
    hdd_frac: float = Field(default=0.2, ge=0, le=1)


@dataclass(frozen=True)
class WorkerTable:
    """Struct-of-arrays worker table; categorical columns are indices into the name tuples."""

    city: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    tz: np.ndarray
    hw: np.ndarray
    substrate: np.ndarray
    tier: np.ndarray
    asn: np.ndarray
    domain: np.ndarray
    down_bps: np.ndarray
    up_bps: np.ndarray
    last_mile_s: np.ndarray
    relayed: np.ndarray
    known_good: np.ndarray
    slots: np.ndarray
    speed: np.ndarray
    mem_mb: np.ndarray
    ssd_mb: np.ndarray
    hdd_mb: np.ndarray
    identity: tuple[str, ...]
    hw_names: tuple[str, ...]
    substrate_names: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.city)

    def to_frame(self) -> pd.DataFrame:
        cols: dict[str, Any] = {}
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, np.ndarray) or f.name == "identity":
                cols[f.name] = list(v) if f.name == "identity" else v
        df = pd.DataFrame(cols)
        df["hw_name"] = [self.hw_names[i] for i in self.hw]
        df["substrate_name"] = [self.substrate_names[i] for i in self.substrate]
        df["tier_name"] = [TIERS[i] for i in self.tier]
        return df


def _pick(gen: np.random.Generator, mix: dict[str, float], names: tuple[str, ...], n: int) -> np.ndarray:
    p = np.array([mix.get(k, 0.0) for k in names], dtype=float)
    if p.sum() <= 0:
        raise ValueError(f"empty mix {mix}")
    return gen.choice(len(names), size=n, p=p / p.sum())


def _links(gen: np.random.Generator, lp: LinkParams, n: int) -> dict[str, np.ndarray]:
    down = gen.lognormal(np.log(lp.down_mbps_median), lp.down_sigma, n) * 1e6
    ratio = np.minimum(gen.lognormal(np.log(lp.up_ratio_median), lp.up_ratio_sigma, n), 1.0)
    return {
        "down_bps": down,
        "up_bps": down * ratio,
        "last_mile_s": gen.lognormal(np.log(lp.last_mile_ms_median), lp.last_mile_sigma, n) / 1e3,
        "relayed": gen.random(n) < lp.relayed_frac,
    }


def _domains(gen: np.random.Generator, city: np.ndarray, gp: GeoParams) -> tuple[np.ndarray, np.ndarray]:
    """ASN per worker; failure domain = (asn, city), numbered densely in sorted order."""
    k = gp.asns_per_city
    w = 1.0 / np.arange(1, k + 1) ** gp.asn_zipf
    local = gen.choice(k, size=len(city), p=w / w.sum())
    asn = city * k + local
    _, domain = np.unique(asn, return_inverse=True)
    return asn, domain


def _envelope(hw: list[HwClass], ep: EnvelopeParams) -> dict[str, np.ndarray]:
    return {
        "slots": np.array([max(1, int(h.cores * ep.cpu_frac)) for h in hw]),
        "speed": np.array([h.speed for h in hw]),
        "mem_mb": np.array([h.mem_gb * 1024 * ep.mem_frac for h in hw]),
        "ssd_mb": np.array([h.ssd_gb * 1024 * ep.ssd_frac for h in hw]),
        "hdd_mb": np.array([h.hdd_gb * 1024 * ep.hdd_frac for h in hw]),
    }


def generate_workers(
    sc: ScenarioConfig, metros: Metros, hw_classes: dict[str, HwClass], rng: RngFactory
) -> WorkerTable:
    """Doc 02 §1. Each attribute family draws from its own stream."""
    n = sc.workers
    gp = GeoParams.model_validate(sc.geo)
    g_loc = rng.stream("workers.location")
    city = g_loc.choice(len(metros), size=n, p=metros.weights())
    lat, lon = jitter_location(metros.lat[city], metros.lon[city], gp.jitter_km, g_loc)
    hw_names = tuple(sorted(hw_classes))
    substrate_names = tuple(sorted(sc.substrate_mix))
    hw = _pick(rng.stream("workers.hw"), sc.hw_mix, hw_names, n)
    asn, domain = _domains(rng.stream("workers.asn"), city, gp)
    g_id = rng.stream("workers.identity")
    identity = tuple(hashlib.sha256(g_id.bytes(32)).hexdigest()[:16] for _ in range(n))
    return WorkerTable(
        city=city,
        lat=lat,
        lon=lon,
        tz=metros.tz[city],
        hw=hw,
        substrate=_pick(rng.stream("workers.substrate"), sc.substrate_mix, substrate_names, n),
        tier=_pick(rng.stream("workers.tier"), sc.tiers, TIERS, n),
        asn=asn,
        domain=domain,
        known_good=rng.stream("workers.firmware").random(n) >= sc.tofu_frac,
        identity=identity,
        hw_names=hw_names,
        substrate_names=substrate_names,
        **_links(rng.stream("workers.link"), LinkParams.model_validate(sc.network.get("link", {})), n),
        **_envelope([hw_classes[hw_names[i]] for i in hw], EnvelopeParams.model_validate(sc.envelope)),
    )
