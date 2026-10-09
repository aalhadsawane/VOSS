"""P6 building blocks: adversarial owner effects, the control-fault trace, network omission filters, succession rank."""

from __future__ import annotations

import pytest
from voss.core.ids import WorkerId
from voss.core.kernel import Kernel
from voss.core.messages import Heartbeat, KeepaliveSummary
from voss.core.rng import RngFactory
from voss.policy.succession_rank import rank
from voss.runtime.faultdriver import blackhole
from voss.runtime.workerlib.faults import Adversary
from voss.world.network import Network, NetworkParams
from voss.world.scenario import control_faults


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


def test_control_fault_trace() -> None:
    df = control_faults([{"t": 30, "kind": "sched_crash"}, {"t": 10, "kind": "sched_slow", "factor": 5}])
    assert list(df.kind) == ["sched_slow", "sched_crash"] and df.target.iloc[0] == "cluster:0"
    with pytest.raises(ValueError):
        control_faults([{"t": 1, "kind": "meteor"}])


def test_network_filter_drops_silently() -> None:
    k = Kernel()
    net = Network(k, NetworkParams(), RngFactory(1).stream("net"))
    got: list[object] = []
    for h, lat in (("a", 0.0), ("b", 1.0)):
        net.add_host(h, lat, 0.0)
    net.attach(("orch", "b"), got.append)
    net.set_filter("a", blackhole)
    ka = KeepaliveSummary(0, 1, WorkerId(0), 1, 0.0)  # type: ignore[arg-type]
    assert net.send(("sched", "a"), ("orch", "b"), ka, 64)
    assert net.send(("sched", "a"), ("orch", "b"), Heartbeat(None), 64)  # type: ignore[arg-type]
    k.run(10.0)
    assert got == [ka] and net.stats["Heartbeat"].drops == 1


def test_rank_is_a_product_of_factors() -> None:
    cands = {WorkerId(1): (1.0, 0.9, 0.5), WorkerId(2): (2.0, 0.9, 0.1), WorkerId(3): (1.0, 0.95, 0.5)}
    assert rank(cands) == [WorkerId(3), WorkerId(1), WorkerId(2)]
    assert rank(cands, frozenset({WorkerId(3)})) == [WorkerId(1), WorkerId(2)]
