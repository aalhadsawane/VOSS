"""Geo network and ``net.send`` (doc 01 §6, doc 02 §3).

``RTT(a, b) = last_mile_a + last_mile_b + km / c_eff × route_factor`` (+ relay penalty), with lognormal jitter on
the propagation term per message. One-way delay is ``RTT / 2`` plus serialization. Bulk payloads
(``>= bulk_threshold_bytes``) share the bottleneck worker access link by processor sharing; the core network is
uncontended. Control messages on one channel are delivered FIFO (a TLS stream). The first message on a channel pays
a TLS handshake (one RTT + CPU); every message pays a per-message TLS CPU cost.

A message is lost if its source is down when sent, or if its destination is down, has restarted (new incarnation)
or is partitioned from the source at delivery time.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Hashable
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, ConfigDict

from voss.core.ids import Addr
from voss.core.kernel import Kernel
from voss.core.messages import Message
from voss.world.geo import haversine_scalar
from voss.world.resources import Link

Handler = Callable[[Message], None]


class NetworkParams(BaseModel):
    """Doc 02 §3. tag: literature (fiber ≈ 2/3 c ⇒ ~100 km per ms of RTT; route inflation ~1.3), else assumed."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    c_eff_km_per_ms: float = 100.0
    route_factor: float = 1.3
    jitter_sigma: float = 0.1
    relay_extra_ms: float = 20.0
    infra_last_mile_ms: float = 1.0
    infra_bw_mbps: float = 10_000.0
    bulk_threshold_bytes: int = 65_536
    local_delay_s: float = 1e-5
    tls_msg_cpu_s: float = 2e-5  # TODO verify: calibration suite `tls`
    tls_handshake_cpu_s: float = 1e-3  # TODO verify: calibration suite `tls`
    link: dict[str, float] = {}  # consumed by workers.LinkParams


@dataclass
class Host:
    lat: float
    lon: float
    last_mile_s: float
    up_bps: float
    down_bps: float
    relayed: bool
    link: Link | None
    up: bool = True
    incarnation: int = 0
    partition: int = 0


@dataclass
class MsgStats:
    count: int = 0
    bytes: int = 0
    drops: int = 0


class Network:
    """Delivers messages between attached addresses with geo-derived delay (doc 01 §6)."""

    def __init__(self, kernel: Kernel, params: NetworkParams, gen: np.random.Generator) -> None:
        self.k, self.p, self.gen = kernel, params, gen
        self.hosts: dict[Hashable, Host] = {}
        self.handlers: dict[Addr, Handler] = {}
        self.stats: dict[str, MsgStats] = defaultdict(MsgStats)
        self._fifo: dict[tuple[Addr, Addr], float] = {}
        self._channels: set[tuple[Addr, Addr, int, int]] = set()
        self._rtt: dict[tuple[Hashable, Hashable], float] = {}
        self.filters: dict[Hashable, Callable[[Addr, Addr, Message], bool]] = {}

    def add_host(
        self,
        host: Hashable,
        lat: float,
        lon: float,
        last_mile_s: float | None = None,
        up_bps: float | None = None,
        down_bps: float | None = None,
        relayed: bool = False,
        up: bool = True,
    ) -> None:
        """Register a host; infra hosts omit link parameters and get the uncontended infra profile."""
        infra = up_bps is None
        bw = self.p.infra_bw_mbps * 1e6
        up_r, down_r = (bw, bw) if infra else (float(up_bps or bw), float(down_bps or bw))
        lm = self.p.infra_last_mile_ms / 1e3 if last_mile_s is None else last_mile_s
        link = None if infra else Link(self.k, up_r, down_r)
        self.hosts[host] = Host(lat, lon, lm, up_r, down_r, relayed, link, up)

    def attach(self, addr: Addr, handler: Handler) -> None:
        if addr[1] not in self.hosts:
            raise KeyError(f"unknown host {addr[1]!r}")
        self.handlers[addr] = handler

    def set_host_up(self, host: Hashable, up: bool) -> None:
        """Bring a host down (in-flight bulk transfers are lost) or up (new incarnation, new channels)."""
        h = self.hosts[host]
        if up and not h.up:
            h.incarnation += 1
        if not up and h.link is not None:
            h.link.reset()
        h.up = up

    def set_filter(self, host: Hashable, drop: Callable[[Addr, Addr, Message], bool] | None) -> None:
        """An owner silently dropping some of its host's outgoing messages (omission faults, doc 07 §1)."""
        if drop is None:
            self.filters.pop(host, None)
        else:
            self.filters[host] = drop

    def set_partition(self, host: Hashable, group: int) -> None:
        self.hosts[host].partition = group

    def is_up(self, host: Hashable) -> bool:
        return self.hosts[host].up

    def rtt(self, a: Hashable, b: Hashable) -> float:
        """Jitter-free RTT in seconds (ground truth; policies only see estimates)."""
        if a == b:
            return 2 * self.p.local_delay_s
        key = (a, b)
        cached = self._rtt.get(key)
        if cached is not None:
            return cached
        ha, hb = self.hosts[a], self.hosts[b]
        km = haversine_scalar(ha.lat, ha.lon, hb.lat, hb.lon)
        prop = km / self.p.c_eff_km_per_ms * self.p.route_factor / 1e3
        relay = self.p.relay_extra_ms / 1e3 * (int(ha.relayed) + int(hb.relayed))
        rtt = ha.last_mile_s + hb.last_mile_s + prop + relay
        self._rtt[key] = rtt
        return rtt

    def send(self, src: Addr, dst: Addr, msg: Message, size_bytes: int) -> bool:
        """Send ``msg``; returns ``False`` if it is dropped at the source."""
        st = self.stats[type(msg).__name__]
        st.count += 1
        st.bytes += size_bytes
        hs, hd = self.hosts[src[1]], self.hosts[dst[1]]
        if not hs.up or hs.partition != hd.partition or not hd.up:
            st.drops += 1
            return False
        drop = self.filters.get(src[1])
        if drop is not None and drop(src, dst, msg):
            st.drops += 1
            return True  # silently lost on the way: the sender cannot tell
        if src[1] == dst[1]:
            self.k.after(self.p.local_delay_s, self._deliver, src, dst, msg, hd.incarnation)
            return True
        one_way = self._one_way(src, dst, hs, hd)
        if size_bytes >= self.p.bulk_threshold_bytes:
            self._bulk(src, dst, msg, size_bytes, one_way, hd.incarnation)
            return True
        ser = size_bytes * 8 / min(hs.up_bps, hd.down_bps)
        t = max(self.k.now + one_way + ser, self._fifo.get((src, dst), 0.0))
        self._fifo[(src, dst)] = t
        self.k.at(t, self._deliver, src, dst, msg, hd.incarnation)
        return True

    def _one_way(self, src: Addr, dst: Addr, hs: Host, hd: Host) -> float:
        base = self.rtt(src[1], dst[1])
        jitter = float(self.gen.lognormal(0.0, self.p.jitter_sigma)) if self.p.jitter_sigma > 0 else 1.0
        lm = hs.last_mile_s + hd.last_mile_s
        one_way = (lm + (base - lm) * jitter) / 2 + self.p.tls_msg_cpu_s
        chan = (src, dst, hs.incarnation, hd.incarnation)
        if chan not in self._channels:
            self._channels.add(chan)
            one_way += base + self.p.tls_handshake_cpu_s
        return one_way

    def _bulk(self, src: Addr, dst: Addr, msg: Message, size: int, one_way: float, inc: int) -> None:
        hs, hd = self.hosts[src[1]], self.hosts[dst[1]]
        side = hs.link.up if hs.link is not None and (hd.link is None or hs.up_bps <= hd.down_bps) else None
        if side is None and hd.link is not None:
            side = hd.link.down
        if side is None:
            self.k.after(one_way + size * 8 / min(hs.up_bps, hd.down_bps), self._deliver, src, dst, msg, inc)
            return
        side.submit(size, lambda: self.k.after(one_way, self._deliver, src, dst, msg, inc))

    def _deliver(self, src: Addr, dst: Addr, msg: Message, inc: int) -> None:
        hs, hd = self.hosts[src[1]], self.hosts[dst[1]]
        handler = self.handlers.get(dst)
        if not hd.up or hd.incarnation != inc or hs.partition != hd.partition or handler is None:
            self.stats[type(msg).__name__].drops += 1
            return
        handler(msg)
