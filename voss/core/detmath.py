"""Platform-independent small linear algebra (doc 01 §8, D-68).

BLAS and LAPACK pick CPU-specific kernels (OpenBLAS ``DYNAMIC_ARCH``), whose summation order and fused operations differ
between microarchitectures; a last-bit difference in a prediction flips a near-tie in placement and the whole
discrete-event trajectory diverges. The simulator's linear algebra is tiny (3x3 regression, short dot products), so it
uses only exactly rounded IEEE operations in a fixed order (elementwise numpy, Python floats, ``math.fsum``), which give
identical results on every CPU. Nothing here calls BLAS or LAPACK.
"""

from __future__ import annotations

import math

import numpy as np


def dot(a: np.ndarray, b: np.ndarray) -> float:
    """Dot product of two vectors, correctly rounded (``math.fsum`` of the exact elementwise products)."""
    return math.fsum((np.asarray(a, dtype=float) * np.asarray(b, dtype=float)).tolist())


def inv3(m: np.ndarray) -> np.ndarray:
    """Inverse of a 3x3 matrix by cofactors, in a fixed operation order."""
    a, b, c, d, e, f, g, h, i = (float(v) for v in np.asarray(m, dtype=float).ravel())
    co = (
        e * i - f * h,
        c * h - b * i,
        b * f - c * e,
        f * g - d * i,
        a * i - c * g,
        c * d - a * f,
        d * h - e * g,
        b * g - a * h,
        a * e - b * d,
    )
    det = a * co[0] + b * co[3] + c * co[6]
    return np.array([[v / det for v in co[0:3]], [v / det for v in co[3:6]], [v / det for v in co[6:9]]])


def matvec3(m: np.ndarray, v: np.ndarray) -> np.ndarray:
    """``m @ v`` for a 3x3 matrix and a 3-vector: ``(m[r,0]*v0 + m[r,1]*v1) + m[r,2]*v2`` per row."""
    return np.array([(m[r, 0] * v[0] + m[r, 1] * v[1]) + m[r, 2] * v[2] for r in range(3)])


def rows_dot3(x: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Row-wise ``x @ v`` for an ``n x 3`` matrix and a 3-vector (elementwise, fixed order)."""
    out: np.ndarray = (x[:, 0] * v[0] + x[:, 1] * v[1]) + x[:, 2] * v[2]
    return out


def quad3(x: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Row-wise quadratic form ``x_i^T cov x_i`` for an ``n x 3`` matrix, in a fixed operation order."""
    t = [(x[:, 0] * cov[0, k] + x[:, 1] * cov[1, k]) + x[:, 2] * cov[2, k] for k in range(3)]
    out: np.ndarray = (t[0] * x[:, 0] + t[1] * x[:, 1]) + t[2] * x[:, 2]
    return out


def log_safe(v: np.ndarray, floor: float = 1e-9) -> np.ndarray:
    """Elementwise ``log(max(v, floor))`` with the C library's scalar ``log`` (no vectorized math-library variant)."""
    return np.array([math.log(max(x, floor)) for x in np.asarray(v, dtype=float).tolist()])
