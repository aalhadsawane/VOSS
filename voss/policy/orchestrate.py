"""Cluster arrangement (doc 03 §2): k-medoids on geography with failure-domain diversity, and the orchestrator's
rule-based triggers with hysteresis. Pure functions of declared locations and reported summaries."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class ClusterParams:
    """tag: assumed; ``target_size`` is chosen from E02 (D-19)."""

    target_size: int = 30
    min_size: int = 10
    max_size: int = 60
    d_min: int = 3
    dwell_s: float = 600.0
    max_moves: int = 10
    slo_theta: float = 0.2
    slo_periods: int = 3
    imbalance_delta: float = 0.4
    max_moves_per_h: int = 3


@dataclass(frozen=True)
class MoveOp:
    worker: int
    src: int
    dst: int
    reason: str


@dataclass
class ClusterInfo:
    """Orchestrator's record of one cluster (from membership and summaries)."""

    cluster: int
    members: set[int] = field(default_factory=set)
    medoid: tuple[float, float] = (0.0, 0.0)
    load: float = 0.0
    slo_miss: float = 0.0
    bad_periods: int = 0
    infeasible: bool = False
    forecast: float = 0.0  # forecast demand / capacity


def great_circle(lat: np.ndarray, lon: np.ndarray, lat0: float, lon0: float) -> np.ndarray:
    p1, p2 = np.radians(lat), math.radians(lat0)
    dl = np.radians(lon0 - lon)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * math.cos(p2) * np.sin(dl / 2) ** 2
    out: np.ndarray = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return out


def kmedoids(lat: np.ndarray, lon: np.ndarray, k: int, iters: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic k-medoids (farthest-point init, alternate assign / re-centre). Returns labels and medoid
    indices. Distances are great-circle km, a proxy of the RTT embedding (doc 03 §2)."""
    n = len(lat)
    k = max(1, min(k, n))
    if n == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    dist0 = great_circle(lat, lon, float(np.median(lat)), float(np.median(lon)))
    med = [int(np.argmin(dist0))]
    dmin = great_circle(lat, lon, lat[med[0]], lon[med[0]])
    for _ in range(1, k):
        nxt = int(np.argmax(dmin))
        med.append(nxt)
        dmin = np.minimum(dmin, great_circle(lat, lon, lat[nxt], lon[nxt]))
    labels = np.zeros(n, dtype=np.int64)
    for _ in range(iters):
        d = np.stack([great_circle(lat, lon, lat[m], lon[m]) for m in med], axis=1)
        labels = np.argmin(d, axis=1)
        new = []
        for c in range(k):
            idx = np.flatnonzero(labels == c)
            if not len(idx):
                new.append(med[c])
                continue
            sub = np.stack([great_circle(lat[idx], lon[idx], lat[i], lon[i]) for i in idx], axis=1)
            new.append(int(idx[int(np.argmin(sub.sum(axis=0)))]))
        if new == med:
            break
        med = new
    return labels, np.array(med, dtype=np.int64)


def balance(labels: np.ndarray, lat: np.ndarray, lon: np.ndarray, medoids: np.ndarray, max_size: int) -> np.ndarray:
    """Move the farthest members out of over-full clusters to the nearest cluster with room."""
    out = labels.copy()
    k = len(medoids)
    d = np.stack([great_circle(lat, lon, lat[m], lon[m]) for m in medoids], axis=1)
    for c in range(k):
        over = np.flatnonzero(out == c)
        while len(over) > max_size:
            far = int(over[np.argmax(d[over, c])])
            sizes = np.bincount(out, minlength=k)
            options = [x for x in np.argsort(d[far]) if x != c and sizes[x] < max_size]
            if not options:
                break
            out[far] = int(options[0])
            over = np.flatnonzero(out == c)
    return out


def diversify(labels: np.ndarray, domain: np.ndarray, d_min: int) -> np.ndarray:
    """Swap workers between clusters until each has ≥ ``d_min`` failure domains where possible (doc 03 §2)."""
    out = labels.copy()
    for c in np.unique(out):
        mine = np.flatnonzero(out == c)
        doms = set(domain[mine].tolist())
        if len(doms) >= d_min:
            continue
        for j in np.flatnonzero(out != c):
            if len(doms) >= d_min:
                break
            if domain[j] in doms:
                continue
            donor = out[j]
            donor_members = np.flatnonzero(out == donor)
            if len(set(domain[donor_members].tolist())) <= d_min or len(donor_members) <= 1:
                continue
            same = [i for i in mine if (domain[mine] == domain[i]).sum() > 1]
            if not same:
                break
            out[j], out[same[0]] = c, donor
            doms.add(int(domain[j]))
            mine = np.flatnonzero(out == c)
    return out


def form_clusters(
    lat: np.ndarray, lon: np.ndarray, domain: np.ndarray, p: ClusterParams
) -> tuple[np.ndarray, np.ndarray]:
    """Initial arrangement: ``k = ceil(N / N_target)`` k-medoids, size ceiling, diversity."""
    k = max(1, math.ceil(len(lat) / p.target_size))
    labels, med = kmedoids(lat, lon, k)
    labels = balance(labels, lat, lon, med, p.max_size)
    return diversify(labels, domain, p.d_min), med


def nearest_cluster(lat: float, lon: float, clusters: list[ClusterInfo], max_size: int) -> int | None:
    """Cluster with the nearest medoid that still has room (``None`` if all are full)."""
    best, best_d = None, math.inf
    for c in clusters:
        if len(c.members) >= max_size:
            continue
        d = float(great_circle(np.array([lat]), np.array([lon]), *c.medoid)[0])
        if d < best_d or (d == best_d and best is not None and c.cluster < best):
            best, best_d = c.cluster, d
    return best
