"""P5: routing over cluster summaries (doc 03 §3): priced trust-cold spillover and the baselines."""

from __future__ import annotations

from voss.core.registry import REGISTRY
from voss.core.rng import RngFactory
from voss.core.types import ClusterCard
from voss.policy import route as _routes  # noqa: F401  (registers routing policies)
from voss.policy.route import RouteRequest

LONDON, PARIS, NYC = (51.5, -0.1), (48.9, 2.3), (40.7, -74.0)


def _card(cid: int, at: tuple[float, float], load: float = 0.3, warm: bool = True, free: int = 10) -> ClusterCard:
    trust = {"t0": 1.0} if warm else {}
    return ClusterCard(cid, at[0], at[1], load, free, 0.0, 0.5, trust, {"f": 2} if warm else {})


def _route(name: str, req: RouteRequest, seed: int = 0) -> int | None:
    out: int | None = REGISTRY.get("route", name)(req, RngFactory(seed).stream("test.route"))
    return out


def test_score_prefers_near_trust_warm() -> None:
    req = RouteRequest(LONDON, "t0", "f", (_card(0, PARIS), _card(1, NYC)))
    assert _route("score", req) == 0


def test_score_prices_trust_cold_spillover() -> None:
    near_cold, far_warm = _card(0, PARIS, warm=False), _card(1, NYC)
    assert _route("score", RouteRequest(LONDON, "t0", "f", (near_cold, far_warm))) == 1
    cheap = RouteRequest(LONDON, "t0", "f", (near_cold, far_warm), cold_penalty_s=0.0, exposure_s=0.0, cold_fn_s=0.0)
    assert _route("score", cheap) == 0
    assert _route("nearest", RouteRequest(LONDON, "t0", "f", (near_cold, far_warm))) == 0


def test_score_avoids_overload_and_unhealthy() -> None:
    hot = _card(0, PARIS, load=8.0)
    req = RouteRequest(LONDON, "t0", "f", (hot, _card(1, NYC)))
    assert _route("score", req) == 1
    assert _route("least_loaded", req) == 1


def test_excluded_and_full_clusters() -> None:
    cards = (_card(0, PARIS, free=0), _card(1, NYC))
    assert _route("nearest", RouteRequest(LONDON, "t0", "f", cards)) == 1
    assert _route("nearest", RouteRequest(LONDON, "t0", "f", cards, excluded=frozenset({1}))) == 0
    assert _route("score", RouteRequest(LONDON, "t0", "f", cards, excluded=frozenset({0, 1}))) is None


def test_po2_is_seeded_and_warm_aware_ignores_trust() -> None:
    cards = (_card(0, PARIS), _card(1, NYC, load=0.1), _card(2, LONDON, load=0.9))
    req = RouteRequest(LONDON, "t0", "f", cards)
    assert _route("po2_nearby", req, 3) == _route("po2_nearby", req, 3)
    cold_trust = ClusterCard(0, PARIS[0], PARIS[1], 0.3, 10, 0.0, 0.5, {}, {"f": 2})
    assert _route("warm_aware", RouteRequest(LONDON, "t0", "f", (cold_trust, _card(1, NYC)))) == 0
