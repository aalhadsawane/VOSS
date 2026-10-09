"""P5: cluster formation (doc 03 §2): k-medoids, size ceiling, failure-domain diversity, nearest cluster."""

from __future__ import annotations

import numpy as np
from voss.core.rng import RngFactory
from voss.policy.orchestrate import (
    ClusterInfo,
    ClusterParams,
    balance,
    diversify,
    form_clusters,
    great_circle,
    kmedoids,
    nearest_cluster,
)


def _blobs(seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    g = RngFactory(seed).stream("test.blobs")
    centres = [(51.5, 0.0), (40.7, -74.0), (35.7, 139.7)]  # London, New York, Tokyo
    lat = np.concatenate([c[0] + g.normal(0, 1.0, 20) for c in centres])
    lon = np.concatenate([c[1] + g.normal(0, 1.0, 20) for c in centres])
    return lat, lon


def test_great_circle_known_distance() -> None:
    d = great_circle(np.array([51.5]), np.array([-0.13]), 48.86, 2.35)[0]  # London - Paris
    assert 330 < d < 350


def test_kmedoids_separates_far_groups_deterministically() -> None:
    lat, lon = _blobs()
    labels, med = kmedoids(lat, lon, 3)
    again, med2 = kmedoids(lat, lon, 3)
    assert (labels == again).all() and (med == med2).all()
    for g in range(3):
        assert len(set(labels[g * 20 : (g + 1) * 20].tolist())) == 1
    assert len(set(labels.tolist())) == 3


def test_kmedoids_edge_cases() -> None:
    labels, med = kmedoids(np.zeros(0), np.zeros(0), 3)
    assert len(labels) == 0 and len(med) == 0
    labels, med = kmedoids(np.array([10.0, 11.0]), np.array([5.0, 5.0]), 5)
    assert len(med) == 2


def test_balance_enforces_size_ceiling() -> None:
    lat, lon = _blobs()
    labels = np.zeros(len(lat), dtype=np.int64)
    labels[-2:] = [1, 2]
    med = np.array([0, len(lat) - 2, len(lat) - 1])
    out = balance(labels, lat, lon, med, max_size=25)
    assert np.bincount(out, minlength=3).max() <= 25


def test_diversify_reaches_d_min_where_possible() -> None:
    labels = np.array([0] * 6 + [1] * 6)
    domain = np.array([7] * 6 + [1, 2, 3, 4, 5, 6])
    out = diversify(labels, domain, d_min=3)
    for c in (0, 1):
        assert len(set(domain[out == c].tolist())) >= 3
    assert np.bincount(out).tolist() == [6, 6]  # swaps, not moves


def test_form_clusters_uses_target_size() -> None:
    lat, lon = _blobs()
    p = ClusterParams(target_size=20, max_size=30, d_min=1)
    labels, med = form_clusters(lat, lon, np.arange(len(lat)), p)
    assert len(med) == 3 and np.bincount(labels).max() <= 30


def test_nearest_cluster_skips_full() -> None:
    a = ClusterInfo(0, set(range(5)), (51.5, 0.0))
    b = ClusterInfo(1, set(range(10, 12)), (40.7, -74.0))
    assert nearest_cluster(50.0, 1.0, [a, b], max_size=10) == 0
    assert nearest_cluster(50.0, 1.0, [a, b], max_size=5) == 1
    assert nearest_cluster(50.0, 1.0, [a, b], max_size=2) is None
