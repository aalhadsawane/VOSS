"""Scenario traces: sessions, adversaries, workload, substrates (doc 02; roadmap P1 exit)."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError
from voss.core.config import RunConfig, ScenarioConfig
from voss.core.rng import RngFactory
from voss.world.adversary import BEHAVIORS, generate_adversaries
from voss.world.geo import load_metros
from voss.world.machines import load_fleet
from voss.world.sessions import generate_sessions
from voss.world.substrate import SUBSTRATES, LadderSpec, load_bundle, load_substrate
from voss.world.workers import generate_workers
from voss.world.workload import generate_arrivals, load_catalog, popularity

from tests.fixtures.fleet import CALIBRATION, FLEET, PLACEHOLDER

METROS = load_metros()
CHURN = {"trace": "test", "trace_root": "tests/fixtures/traces"}


def _workers(sc: ScenarioConfig, seed: int = 1):  # type: ignore[no-untyped-def]
    fleet = load_fleet(FLEET, CALIBRATION, load_catalog(sc, CALIBRATION))
    return generate_workers(sc, METROS, fleet.hw, RngFactory(seed), fleet.mix.weights)


def _sessions_sc(**kw: object) -> ScenarioConfig:
    return ScenarioConfig.model_validate({"machines": FLEET, "churn": CHURN, **kw})


def test_workers_attributes() -> None:
    sc = ScenarioConfig(workers=2000, machines=FLEET)
    w = _workers(sc)
    assert len(w) == 2000 and len(set(w.identity)) == 2000
    assert (w.up_bps <= w.down_bps).all() and (w.slots >= 1).all()
    # failure domains are (asn, city): workers of one domain share a city
    for d in np.unique(w.domain)[:50]:
        assert len(np.unique(w.city[w.domain == d])) == 1


def test_sessions_well_formed() -> None:
    sc = _sessions_sc(workers=300)
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


def test_adversary_schedules_match_spec() -> None:
    sc = ScenarioConfig(workers=1000, machines=FLEET, adversary={"regime": "adversary_all", "alpha": 0.2})
    w = _workers(sc)
    tr = generate_adversaries(sc, w, 7200.0, RngFactory(5))
    adv = tr.adversaries()
    assert abs(len(adv) - 200) <= 25  # colluders take whole domains (may overshoot slightly)
    names = [tr.name(i) for i in adv]
    for b in BEHAVIORS[1:]:
        if b != "forge":  # forging needs class-P owners: test_forgers_are_class_p_owners
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
    sc = ScenarioConfig(workers=200, machines=FLEET)
    tr = generate_adversaries(sc, _workers(sc), 3600.0, RngFactory(1))
    assert len(tr.adversaries()) == 0


def test_workload_popularity_and_rate() -> None:
    sc = ScenarioConfig(
        machines=FLEET,
        load={"regime": "", "rate": 50, "zipf_s": 1.0, "mmpp": {"enabled": False}, "diurnal": {"amplitude": 0.0}},
    )
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
    sc = ScenarioConfig(
        machines=FLEET,
        load={
            "regime": "",
            "rate": 100,
            "zipf_s": 1.0,
            "mmpp": {"enabled": False},
            "flash_crowds": [{"t": 1200, "duration_s": 300, "mult": 5.0, "fn": "top", "city": "London"}],
        },
    )
    arr = generate_arrivals(sc, load_catalog(sc), METROS, 3600.0, RngFactory(1)).frame
    inside = ((arr.t >= 1200) & (arr.t < 1500)).sum() / 300
    before = ((arr.t >= 600) & (arr.t < 1200)).sum() / 600
    assert inside > 2 * before


def test_all_substrates_validate() -> None:
    bundle = load_bundle(PLACEHOLDER)
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


def test_default_workers() -> None:
    assert RunConfig.model_validate({"scenario": {"machines": FLEET}}).scenario.workers == 1000


def test_forgers_are_class_p_owners() -> None:
    """Plan V7.3: only owners with physical access (class P) can forge results."""
    sc = ScenarioConfig(
        workers=1000,
        machines=FLEET,
        physical_frac=0.3,
        adversary={"regime": "adversary_all", "alpha": 0.1, "mix": {"forge": 1.0}},
    )
    w = _workers(sc)
    tr = generate_adversaries(sc, w, 7200.0, RngFactory(5))
    forgers = [i for i in tr.adversaries() if tr.name(i) == "forge"]
    assert len(forgers) == 100 and all(w.owner_class[i] == 1 for i in forgers)
    none = ScenarioConfig(
        workers=1000, machines=FLEET, adversary={"regime": "adversary_all", "alpha": 0.1, "mix": {"forge": 1.0}}
    )
    tr0 = generate_adversaries(none, _workers(none), 7200.0, RngFactory(5))
    assert not any(tr0.name(i) == "forge" for i in tr0.adversaries())
