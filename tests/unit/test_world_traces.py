"""Scenario traces: sessions, adversaries, workload, substrates (doc 02; roadmap P1 exit)."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError
from voss.core.config import RunConfig, ScenarioConfig
from voss.core.rng import RngFactory
from voss.world.adversary import BEHAVIORS, generate_adversaries
from voss.world.geo import load_metros
from voss.world.hardware import load_hw_classes
from voss.world.sessions import generate_sessions
from voss.world.substrate import SUBSTRATES, LadderSpec, load_bundle, load_substrate
from voss.world.workers import TIERS, generate_workers
from voss.world.workload import generate_arrivals, load_catalog, popularity

METROS = load_metros()


def _workers(sc: ScenarioConfig, seed: int = 1):  # type: ignore[no-untyped-def]
    return generate_workers(sc, METROS, load_hw_classes(sorted(sc.hw_mix)), RngFactory(seed))


def test_workers_attributes() -> None:
    sc = ScenarioConfig(workers=2000)
    w = _workers(sc)
    assert len(w) == 2000 and len(set(w.identity)) == 2000
    assert set(np.unique(w.tier)) == {0, 1, 2}
    assert (w.up_bps <= w.down_bps).all() and (w.slots >= 1).all()
    # failure domains are (asn, city): workers of one domain share a city
    for d in np.unique(w.domain)[:50]:
        assert len(np.unique(w.city[w.domain == d])) == 1


def test_session_tails_are_heavy() -> None:
    sc = ScenarioConfig(workers=600, tiers={"idle": 1.0}, warmup_s=7 * 86400)
    w = _workers(sc)
    tr = generate_sessions(sc, w, METROS, 3600.0, RngFactory(1))
    s = tr.sessions[tr.sessions.reason != "shock"]
    length = (s.end - s.start).to_numpy()
    assert len(length) > 1000
    assert length.std() / length.mean() > 1.2  # CV > 1: heavier than exponential
    assert np.quantile(length, 0.99) / np.median(length) > 15


def test_sessions_well_formed() -> None:
    sc = ScenarioConfig(workers=300, regime="churn_high")
    tr = generate_sessions(sc, _workers(sc), METROS, 3600.0, RngFactory(2))
    s = tr.sessions.sort_values(["worker", "start"])
    assert (s.end > s.start).all()
    for _, g in s.groupby("worker"):
        assert (g.start.to_numpy()[1:] >= g.end.to_numpy()[:-1]).all()
    graceful = s.drain_t.notna()
    assert (s.drain_t[graceful] <= s.end[graceful]).all()
    ev = tr.events()
    assert (np.diff(ev.t.to_numpy()) >= 0).all()
    assert set(ev.kind) == {"SESSION_START", "SESSION_END", "DRAIN_NOTICE"}


def test_timezone_waves() -> None:
    sc = ScenarioConfig(workers=3000, tiers={"nightly": 1.0}, warmup_s=86400, regime="churn_low")
    w = _workers(sc)
    tr = generate_sessions(sc, w, METROS, 86400.0, RngFactory(3))
    hours = np.arange(0, 24)
    peaks = {}
    for tz in (9.0, 1.0, -5.0):
        mask = np.isclose(w.tz, tz)
        ids = set(np.flatnonzero(mask))
        active = [len(ids.intersection(tr.active_at(h * 3600.0))) / len(ids) for h in hours]
        peaks[tz] = int(hours[int(np.argmax(active))])
    # night peaks track local time: UTC peak ≈ (local ~2-3 am) − tz, so UTC+9 peaks ~8-9 h before UTC+1
    gap = (peaks[1.0] - peaks[9.0]) % 24
    assert 6 <= gap <= 10, peaks
    gap = (peaks[-5.0] - peaks[1.0]) % 24
    assert 4 <= gap <= 8, peaks


def test_regional_shocks_end_sessions_together() -> None:
    sc = ScenarioConfig(workers=800, regime="churn_burst")
    tr = generate_sessions(sc, _workers(sc), METROS, 3600.0, RngFactory(4))
    shocked = tr.sessions[tr.sessions.reason == "shock"]
    assert len(shocked) > 0
    assert shocked.end.value_counts().max() >= 2


def test_adversary_schedules_match_spec() -> None:
    sc = ScenarioConfig(workers=1000, adversary={"regime": "adversary_all", "alpha": 0.2})
    w = _workers(sc)
    tr = generate_adversaries(sc, w, 7200.0, RngFactory(5))
    adv = tr.adversaries()
    assert abs(len(adv) - 200) <= 25  # colluders take whole domains (may overshoot slightly)
    names = [tr.name(i) for i in adv]
    for b in BEHAVIORS[1:]:
        assert names.count(b) >= 15, b
    p = tr.params
    for i in adv:
        if tr.name(i) == "on_off":
            win = tr.windows[i]
            full = [b - a for a, b in win if a > p.start_t and b < 7200]
            assert all(d == pytest.approx(p.on_off_bad_s) for d in full)
            gaps = [win[j + 1][0] - win[j][1] for j in range(len(win) - 1)]
            assert all(g == pytest.approx(p.on_off_good_s) for g in gaps)
    coll = [i for i in adv if tr.name(i) == "colluding_domain"]
    for d in np.unique(w.domain[coll]):
        assert set(np.flatnonzero(w.domain == d)) <= set(coll)
    c = coll[0]
    assert not tr.defecting(c, p.collude_t - 1) and tr.defecting(c, p.collude_t + 1)
    assert tr.omit_p[[i for i in adv if tr.name(i) == "throttle"]].max() == 0.0


def test_no_adversaries_by_default() -> None:
    sc = ScenarioConfig(workers=200)
    tr = generate_adversaries(sc, _workers(sc), 3600.0, RngFactory(1))
    assert len(tr.adversaries()) == 0


def test_workload_popularity_and_rate() -> None:
    sc = ScenarioConfig(load={"rate": 50, "mmpp": {"enabled": False}, "diurnal": {"amplitude": 0.0}})
    cat = load_catalog(sc)
    arr = generate_arrivals(sc, cat, METROS, 3600.0, RngFactory(1)).frame
    assert len(arr) / 3600 == pytest.approx(50, rel=0.03)
    share = popularity(len(cat.functions), 1.0, RngFactory(1).stream("workload.popularity"))
    counts = np.bincount(arr.fn, minlength=len(cat.functions)) / len(arr)
    assert np.argmax(counts) == np.argmax(share)
    assert (np.diff(arr.t.to_numpy()) >= 0).all()
    sync = arr.slo_class == 0
    assert np.isfinite(arr.deadline_s[sync]).all() and (arr.deadline_s[sync] > 0).all()


def test_flash_crowd() -> None:
    sc = ScenarioConfig(load={"regime": "load_flash", "mmpp": {"enabled": False}})
    arr = generate_arrivals(sc, load_catalog(sc), METROS, 3600.0, RngFactory(1)).frame
    inside = ((arr.t >= 1200) & (arr.t < 1500)).sum() / 300
    before = ((arr.t >= 600) & (arr.t < 1200)).sum() / 600
    assert inside > 2 * before


def test_all_substrates_validate() -> None:
    bundle = load_bundle("calibration/placeholder/c0")
    for name in SUBSTRATES:
        prof = load_substrate(name, bundle)
        assert prof.ladder.path(prof.ladder.levels[0])
    with pytest.raises(ValueError, match="missing from calibration bundle"):
        load_substrate("appliance_tpm", {})


def test_ladder_validation() -> None:
    with pytest.raises(ValidationError):
        LadderSpec(levels=("L0", "L3"), ready="L3", busy="L3", transitions={"L0->L9": ()})
    with pytest.raises(ValidationError):
        LadderSpec(levels=("L0", "L1", "L3"), ready="L3", busy="L3", transitions={"L0->L3": ()})


def test_tiers_constant() -> None:
    assert TIERS == ("nightly", "idle", "dedicated")
    assert RunConfig().scenario.workers == 1000
