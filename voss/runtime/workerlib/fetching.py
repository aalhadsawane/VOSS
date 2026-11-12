"""Artifact fetches for the worker agent (doc 02 §6): content-addressed, coalesced per digest, from a peer first
(P2P, chosen by the scheduler's source hints) and the registry otherwise; GDSF bookkeeping on insert."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from voss.core.ids import Addr, FnId
from voss.core.messages import Chunk, Fetch
from voss.policy.cache_value import GdsfState, gdsf_value
from voss.runtime.actor import ActorContext
from voss.runtime.workerlib.host import HostLocal
from voss.world.cache import Entry
from voss.world.lifecycle import artifact_sizes
from voss.world.workload import FunctionSpec

MB = 1024 * 1024


class FetchMixin:
    host: HostLocal
    ctx: ActorContext
    addr: Addr
    digests: dict[FnId, dict[str, str]]
    fetch_waiters: dict[str, list[Callable[[], None]]]
    fetch_kind: dict[str, tuple[str, float, float]]
    gdsf: GdsfState

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def touched_frac(self) -> float: ...

    def use_gdsf(self) -> None:
        """Value-density eviction (doc 02 §6) instead of LRU."""
        st = self.gdsf
        c = self.host.cache
        c.value = lambda e: gdsf_value(st, e.digest, e.hits, e.size_mb, e.last_used)

        def evicted(e: Entry) -> None:
            st.inflation = max(st.inflation, c.value(e))

        c.on_evict = evicted

    def fetch(self, fn: FunctionSpec, artifacts: tuple[str, ...], cont: Callable[[], None]) -> None:
        """Fetch missing artifacts (ciphertext) from the provider's registry."""
        digests, sizes = self.digests[FnId(fn.name)], artifact_sizes(fn, self.touched_frac())
        missing = [a for a in artifacts if self.host.cache.touch(digests[a], self.now) is None]
        remaining = {"n": len(missing)}

        def one() -> None:
            remaining["n"] -= 1
            if remaining["n"] == 0:
                cont()

        if not missing:
            self.ctx.kernel.after(0.0, cont)
            return
        for a in missing:
            d = digests[a]
            waiters = self.fetch_waiters.setdefault(d, [])
            waiters.append(one)
            if len(waiters) == 1:
                saved = sizes[a] * 8 / max(self.host.static.down_bps if self.host.static else 1e8, 1.0)
                self.fetch_kind[d] = (a, sizes[a] / MB, saved + (fn.init_s if a == "snapshot" else 0.0))
                self.send(self.ctx.directory.registry, Fetch(d, int(sizes[a]), self.addr))

    def _chunk(self, m: Chunk) -> None:
        kind, size_mb, saved = self.fetch_kind.pop(m.digest, ("bundle", m.nbytes / MB, 0.0))
        self.gdsf.saved_s[m.digest] = saved
        self.host.cache.insert(m.digest, kind, size_mb, self.now)
        for cont in self.fetch_waiters.pop(m.digest, []):
            cont()
