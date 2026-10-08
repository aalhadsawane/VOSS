"""Hard eligibility for placement (doc 03 §5.1, doc 08 §5): attested and not expiring, not draining, not excluded,
fresh enough heartbeat."""

from __future__ import annotations

import numpy as np

from voss.core.types import ClusterView, Invocation


def eligible(
    view: ClusterView, inv: Invocation, now: float, expiry_margin_s: float, max_age_s: float = 30.0
) -> np.ndarray:
    """Boolean mask over ``view.workers``."""
    ok: np.ndarray = (view.session_expiry > now + expiry_margin_s) & ~view.draining & (view.age < max_age_s)
    if inv.excluded:
        ok &= ~np.isin(np.asarray(view.workers), list(inv.excluded))
    return ok


def load(view: ClusterView) -> np.ndarray:
    """Occupancy per slot including the scheduler's own dispatches since ``as_of``."""
    occ: np.ndarray = (view.busy + view.queued + view.inflight) / np.maximum(view.slots, 1)
    return occ
