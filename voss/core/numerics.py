"""Numeric canary (doc 01 §8, D-70): are NumPy's transcendental functions bit-identical to the reference platform?

Results are bit-reproducible across x86-64 CPUs only if NumPy's SIMD dispatch is pinned (``voss/__init__.py``) and
glibc's libm picks its FMA variants (true for every CPU since 2013). The canary hashes ``exp``, ``log``, ``power`` and
friends on fixed inputs; a mismatch means a run is statistically comparable to the published ones, not bit-comparable.
"""

from __future__ import annotations

import hashlib
import platform

import numpy as np

# Computed with the dispatch pinned to the SSE4 baseline on x86-64 Linux (numpy 2.4.6, glibc 2.39).
EXPECTED_CANARY = "c72c6744cad261c1"


def canary() -> str:
    x = np.linspace(0.01, 30.0, 4097)
    y = np.linspace(-5.0, 5.0, 4097)
    parts = (
        np.exp(y),
        np.log(x),
        np.power(x, 0.7),
        np.expm1(y),
        np.log1p(x),
        np.arctan(y),
        np.tanh(y),
        np.exp2(y),
        np.log10(x),
        np.sin(y),
        np.cos(y),
    )
    return hashlib.sha256(b"".join(p.tobytes() for p in parts)).hexdigest()[:16]


def canary_ok() -> bool:
    """True on x86-64 when the canary matches the reference; other architectures are not bit-comparable by design."""
    return platform.machine().lower() not in ("x86_64", "amd64") or canary() == EXPECTED_CANARY
