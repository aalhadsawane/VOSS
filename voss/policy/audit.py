"""Sampled audit of results (docs/REVISION_PLAN.md V7.3; doc 04: integrity against class-P owners rests on it).

An idempotent invocation is audited with probability ``p``: a second holder, with a different owner and failure domain
from every worker that already ran it, executes it again and the result digests are compared. On a mismatch a third
holder breaks the tie; the worker in the minority is banned (the verifier refuses its sessions).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

import numpy as np

from voss.core.ids import WorkerId


def select(idempotent: bool, gen: np.random.Generator, p: float) -> bool:
    """Whether to audit this invocation (non-idempotent invocations are never re-executed)."""
    return idempotent and p > 0 and bool(gen.random() < p)


def target(
    workers: Sequence[WorkerId],
    domain: Sequence[int],
    holder: Sequence[bool],
    used: set[WorkerId],
    gen: np.random.Generator,
) -> WorkerId | None:
    """A uniformly chosen holder outside every failure domain of the ``used`` workers, or ``None``."""
    bad = {d for w, d in zip(workers, domain, strict=True) if w in used}
    ok = [w for w, d, h in zip(workers, domain, holder, strict=True) if h and w not in used and d not in bad]
    return ok[int(gen.integers(len(ok)))] if ok else None


def minority(digests: Mapping[WorkerId, int]) -> list[WorkerId] | None:
    """Workers whose digest differs from a strict majority; ``None`` while there is no majority (ask another)."""
    top, n = Counter(digests.values()).most_common(1)[0]
    if 2 * n <= len(digests):
        return None
    return sorted(w for w, d in digests.items() if d != top)
