"""Building blocks of owner faults: adversarial owner effects and network omission filters."""

from __future__ import annotations

import pytest
from voss.core.ids import WorkerId
from voss.core.kernel import Kernel
from voss.core.messages import Heartbeat, Join
from voss.core.rng import RngFactory
from voss.runtime.workerlib.faults import Adversary
from voss.world.network import Network, NetworkParams


def _adv(name: str, omit_p: float = 1.0, throttle: float = 1.0, start: float = 10.0) -> Adversary:
    return Adversary(name, omit_p, throttle, ((start, 100.0),), 1, RngFactory(1).stream("test.adv"))


def test_black_hole_omits_only_while_defecting() -> None:
    a = _adv("black_hole")
    assert not a.omits("t0", 5.0) and a.omits("t0", 50.0) and not a.omits("t0", 150.0)
    assert a.exec_factor(50.0) == 1.0


def test_selective_targets_the_hottest_tenant() -> None:
    a = _adv("selective")
    for _ in range(5):
        a.dispatched("hot")
    a.dispatched("cold")
    assert a.omits("hot", 50.0) and not a.omits("cold", 50.0)


def test_throttle_and_partial_omission() -> None:
    assert _adv("throttle", omit_p=0.0, throttle=0.25).exec_factor(50.0) == pytest.approx(4.0)
    a = _adv("omit_random", omit_p=0.5)
    hits = sum(a.omits("t0", 50.0) for _ in range(400))
    assert 140 < hits < 260
    assert not _adv("fake_signals").omits("t0", 50.0)


def test_network_filter_drops_silently() -> None:
    k = Kernel()
    net = Network(k, NetworkParams(), RngFactory(1).stream("net"))
    got: list[object] = []
    for h, lat in (("a", 0.0), ("b", 1.0)):
        net.add_host(h, lat, 0.0)
    net.attach(("orch", "b"), got.append)
    net.set_filter("a", lambda _src, _dst, msg: isinstance(msg, Heartbeat))  # drop heartbeats only
    ka = Join(WorkerId(0), "c", 0.0, 1.0, 1.0, 1, 0, ("agent", 0))
    assert net.send(("sched", "a"), ("orch", "b"), ka, 64)
    assert net.send(("sched", "a"), ("orch", "b"), Heartbeat(None), 64)  # type: ignore[arg-type]
    k.run(10.0)
    assert got == [ka] and net.stats["Heartbeat"].drops == 1


def test_inline_mix_replaces_the_regime_mix() -> None:
    from voss.core.config import ScenarioConfig
    from voss.world.adversary import load_adversary_regime

    sc = ScenarioConfig.model_validate({"adversary": {"regime": "adversary_all", "mix": {"black_hole": 1.0}}})
    assert load_adversary_regime(sc).mix == {"black_hole": 1.0}
