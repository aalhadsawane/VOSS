"""Named, independent random streams (doc 01 §3).

``stream(name, *keys)`` derives a generator from ``hash(master_seed, name, keys)``. Streams never share state, so
adding a component never perturbs another one, and an invocation's draws are common random numbers across systems.
"""

from __future__ import annotations

import hashlib

import numpy as np

Key = str | int | float


def derive_seed(master_seed: int, name: str, *keys: Key) -> int:
    """128-bit seed from a stable hash of ``(master_seed, name, keys)``."""
    text = "\x1f".join([str(master_seed), name, *(repr(k) for k in keys)])
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:16], "little")


def stream(master_seed: int, name: str, *keys: Key) -> np.random.Generator:
    """A fresh generator for ``(master_seed, name, keys)``; identical inputs give identical sequences."""
    return np.random.Generator(np.random.PCG64(derive_seed(master_seed, name, *keys)))


class RngFactory:
    """Binds a master seed so components can call ``rng.stream(name, *keys)``."""

    def __init__(self, master_seed: int) -> None:
        self.master_seed = int(master_seed)

    def stream(self, name: str, *keys: Key) -> np.random.Generator:
        return stream(self.master_seed, name, *keys)
