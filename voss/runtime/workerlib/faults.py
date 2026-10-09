"""Adversarial owner behavior applied to its own host (doc 02 §7, doc 04 §2): the trace says who defects, how and
when; the owner can only omit or delay (the attested stack cannot be changed), so effects are dropped results and
throttled execution. ``replay`` needs no effect (TLS rejects replays) and ``fake_signals`` are fake drain notices in
the session trace."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from voss.world.adversary import AdversaryTrace

OMITTING = ("omit_random", "black_hole", "on_off", "colluding_domain", "selective")


@dataclass
class Adversary:
    name: str
    omit_p: float
    throttle_f: float
    windows: tuple[tuple[float, float], ...]
    hot_k: int
    gen: np.random.Generator
    seen: dict[str, int] = field(default_factory=dict)

    @classmethod
    def of(cls, trace: AdversaryTrace, w: int, gen: np.random.Generator) -> Adversary | None:
        name = trace.name(w)
        if name == "benign":
            return None
        p = trace.params
        return cls(name, float(trace.omit_p[w]), float(trace.throttle_f[w]), trace.windows[w], p.selective_hot_k, gen)

    def defecting(self, t: float) -> bool:
        return any(a <= t < b for a, b in self.windows)

    def dispatched(self, tenant: str) -> None:
        """Traffic analysis: the owner learns which tenants it serves most (sizes and timing are visible)."""
        self.seen[tenant] = self.seen.get(tenant, 0) + 1

    def omits(self, tenant: str, t: float) -> bool:
        """Drop this finished attempt's result, outcome and any probe reply about it."""
        if self.name not in OMITTING or not self.defecting(t):
            return False
        if self.name == "selective":
            hot = sorted(self.seen, key=lambda k: (-self.seen[k], k))[: self.hot_k]
            if tenant not in hot:
                return False
        return bool(self.gen.random() < self.omit_p)

    def exec_factor(self, t: float) -> float:
        return 1.0 / self.throttle_f if self.name == "throttle" and self.defecting(t) else 1.0
