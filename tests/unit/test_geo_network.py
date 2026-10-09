"""Geography and ``net.send`` (doc 01 §6, doc 02 §3)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from voss.core.kernel import Kernel
from voss.core.messages import Message
from voss.core.rng import stream
from voss.world.geo import haversine_km, load_metros, local_hour
from voss.world.network import Network, NetworkParams


@dataclass(frozen=True, slots=True)
class Ping(Message):
    n: int


def _net(jitter: float = 0.0) -> tuple[Kernel, Network]:
    k = Kernel()
    return k, Network(k, NetworkParams(jitter_sigma=jitter), stream(1, "net"))


def test_metros_and_distance() -> None:
    m = load_metros()
    assert len(m) >= 100
    lon, ny = m.index("London"), m.index("New York")
    d = haversine_km(m.lat[lon], m.lon[lon], m.lat[ny], m.lon[ny])
    assert d == pytest.approx(5570, rel=0.02)
    assert local_hour(9.0, 3600.0, 0.0) == pytest.approx(10.0)
    assert local_hour(-5.0, 0.0, 2.0) == pytest.approx(21.0)


def test_delay_grows_with_distance() -> None:
    k, net = _net(jitter=0.1)
    m = load_metros()
    net.add_host("src", m.lat[m.index("London")], m.lon[m.index("London")])
    got: dict[str, float] = {}
    for city in ("Paris", "New York", "Tokyo", "Sydney"):
        i = m.index(city)
        net.add_host(city, m.lat[i], m.lon[i])
        net.attach(("rx", city), lambda msg, c=city: got.__setitem__(c, k.now))
    for city in ("Paris", "New York", "Tokyo", "Sydney"):
        net.send(("tx", "src"), ("rx", city), Ping(1), 200)
    k.run(10.0)
    assert got["Paris"] < got["New York"] < got["Tokyo"] < got["Sydney"]
    assert net.rtt("src", "Paris") < net.rtt("src", "Sydney")


def test_messages_to_down_hosts_are_lost() -> None:
    k, net = _net()
    net.add_host("a", 0.0, 0.0)
    net.add_host("b", 10.0, 10.0, last_mile_s=0.01, up_bps=1e7, down_bps=1e8)
    seen: list[int] = []
    net.attach(("rx", "b"), lambda msg: seen.append(msg.n))  # type: ignore[attr-defined]
    net.set_host_up("b", False)
    assert not net.send(("tx", "a"), ("rx", "b"), Ping(1), 100)
    net.set_host_up("b", True)
    net.send(("tx", "a"), ("rx", "b"), Ping(2), 100)
    net.set_host_up("b", False)  # goes down while message 2 is in flight
    net.set_host_up("b", True)  # new incarnation: the old channel is gone
    net.send(("tx", "a"), ("rx", "b"), Ping(3), 100)
    k.run(5.0)
    assert seen == [3]
    assert net.stats["Ping"].drops == 2 and net.stats["Ping"].count == 3


def test_partition_and_fifo() -> None:
    k, net = _net(jitter=0.5)
    net.add_host("a", 0.0, 0.0)
    net.add_host("b", 40.0, 40.0)
    seen: list[int] = []
    net.attach(("rx", "b"), lambda msg: seen.append(msg.n))  # type: ignore[attr-defined]
    for i in range(50):
        net.send(("tx", "a"), ("rx", "b"), Ping(i), 100)
    k.run(5.0)
    assert seen == list(range(50))
    net.set_partition("b", 1)
    assert not net.send(("tx", "a"), ("rx", "b"), Ping(99), 100)


def test_bulk_transfers_share_the_access_link() -> None:
    k, net = _net()
    net.add_host("reg", 0.0, 0.0)
    net.add_host("w", 0.0, 0.0, last_mile_s=0.0, up_bps=8e6, down_bps=8e6)  # 1 MB/s down
    done: list[float] = []
    net.attach(("rx", "w"), lambda msg: done.append(k.now))
    net.send(("tx", "reg"), ("rx", "w"), Ping(1), 2_000_000)
    k.run(0.001)
    net.send(("tx", "reg"), ("rx", "w"), Ping(2), 2_000_000)
    k.run(20.0)
    assert done[0] > 3.5 and done[1] > done[0]  # sharing doubles the time of the first transfer


def test_upload_cut_by_power_off_counts_as_a_drop() -> None:
    """An owner powering off mid-upload loses the transfer, and the loss is visible in the message stats."""
    k, net = _net()
    net.add_host("reg", 0.0, 0.0)
    net.add_host("w", 0.0, 0.0, last_mile_s=0.0, up_bps=8e6, down_bps=8e6)  # 1 MB/s up
    got: list[Message] = []
    net.attach(("rx", "reg"), got.append)
    assert net.send(("tx", "w"), ("rx", "reg"), Ping(1), 2_000_000)
    k.run(1.0)
    net.set_host_up("w", False)
    k.run(10.0)
    assert got == [] and net.stats["Ping"].drops == 1
