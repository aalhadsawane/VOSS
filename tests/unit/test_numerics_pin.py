"""NumPy's SIMD dispatch is pinned before NumPy is imported, so transcendental results are CPU-independent (D-70)."""

from __future__ import annotations

import platform
import subprocess
import sys

import pytest

X86 = platform.machine().lower() in ("x86_64", "amd64")


def _run(code: str, env_extra: dict[str, str] | None = None) -> str:
    import os

    env = {k: v for k, v in os.environ.items() if k != "NPY_DISABLE_CPU_FEATURES"}
    env.update(env_extra or {})
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env)
    return out.stdout.strip()


@pytest.mark.skipif(not X86, reason="the canary is defined for x86-64")
def test_import_voss_pins_dispatch_and_canary_matches() -> None:
    out = _run("import voss\nfrom voss.core.numerics import canary_ok\nprint(canary_ok())")
    assert out == "True"


@pytest.mark.skipif(not X86, reason="the canary is defined for x86-64")
def test_experiments_import_pins_before_pandas() -> None:
    out = _run("import experiments.sweep\nfrom voss.core.numerics import canary_ok\nprint(canary_ok())")
    assert out == "True"


@pytest.mark.skipif(not X86, reason="the canary is defined for x86-64")
def test_explicit_environment_wins() -> None:
    """An empty value lifts the pin; the canary then either matches (no AVX-512 on this CPU) or flags the process."""
    out = _run("import voss, os\nprint(os.environ['NPY_DISABLE_CPU_FEATURES'] == '')", {"NPY_DISABLE_CPU_FEATURES": ""})
    assert out == "True"
