"""Worker side of the histogram keep-alive baseline (doc 03 §7, D-77): apply a ``KeepWarm`` directive. Sets the
function's keep-alive window (the cache drops its sandboxes after it), unloads the sandbox that just finished when
the scheduler wants a pre-warm gap, and builds a warm sandbox in the background when asked (only with the tenant's
key: a single loop plans no key releases)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from voss.core.messages_ka import KeepWarm
from voss.runtime.workerlib.host import HostLocal
from voss.world.workload import FunctionSpec


class KeepWarmMixin:
    host: HostLocal
    keys: set[str]
    catalog: dict[Any, FunctionSpec]

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def _build(self, fn: FunctionSpec, then: Callable[[], None]) -> None: ...

    def _keep_warm(self, m: KeepWarm) -> None:
        fn, h = self.catalog.get(m.fn), self.host
        if fn is None or fn.tenant not in self.keys:
            return
        h.cache.warm_ttls[fn.name] = m.keepalive_s
        if m.unload:
            h.cache.take_warm(fn.name)
        if m.build:

            def park() -> None:
                h.cache.park_warm(fn.name, fn.mem_mb, self.now)

            self._build(fn, then=park)
