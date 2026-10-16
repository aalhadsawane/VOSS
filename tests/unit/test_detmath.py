"""``voss.core.detmath``: fixed-order arithmetic that matches numpy to rounding error and avoids BLAS (D-68)."""

from __future__ import annotations

import numpy as np

from voss.core import detmath


def test_inv3_matches_numpy() -> None:
    m = np.array([[4.0, 1.0, 0.5], [1.0, 3.0, 0.2], [0.5, 0.2, 2.0]])
    assert np.allclose(detmath.inv3(m), np.linalg.inv(m), rtol=1e-12, atol=1e-14)


def test_products_match_numpy() -> None:
    rng = np.random.default_rng(1)
    x, cov = rng.normal(size=(7, 3)), np.diag([1.0, 2.0, 3.0]) + 0.1
    beta = rng.normal(size=3)
    assert np.allclose(detmath.rows_dot3(x, beta), x @ beta, rtol=1e-12)
    assert np.allclose(detmath.quad3(x, cov), np.einsum("ij,jk,ik->i", x, cov, x), rtol=1e-12)
    assert np.allclose(detmath.matvec3(cov, beta), cov @ beta, rtol=1e-12)
    assert np.isclose(detmath.dot(x[:, 0], x[:, 1]), float(x[:, 0] @ x[:, 1]), rtol=1e-12)


def test_dot_is_order_independent_and_log_safe_floors() -> None:
    a = np.array([1e16, 1.0, -1e16, 1.0])
    assert detmath.dot(a, np.ones(4)) == 2.0 == detmath.dot(a[::-1], np.ones(4))  # fsum: exact, order independent
    assert detmath.log_safe(np.array([0.0, 1.0]))[1] == 0.0
    assert np.isfinite(detmath.log_safe(np.array([0.0]))[0])
