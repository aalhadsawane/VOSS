"""VOSS: Volunteer-Oriented Serverless Scheduling (doc 00)."""

import os as _os
import platform as _platform

__version__ = "0.1.0"

# D-70: NumPy's transcendental ufuncs (exp, log, power, expm1, log1p, ...) have AVX-512, AVX2 and SSE4 implementations
# that differ in the last bit, and a last-bit difference flips a near-tie in placement and diverges the whole run. Pin
# the dispatch to the SSE4 baseline (every x86-64 CPU since 2009) before NumPy is first imported. A value already set in
# the environment wins, so the pin can be lifted; ``voss.core.numerics.canary_ok`` detects an unpinned process.
NUMPY_DISPATCH_PIN = "X86_V4 X86_V3 AVX512_ICL AVX512_SPR"
if _platform.machine().lower() in ("x86_64", "amd64"):
    _os.environ.setdefault("NPY_DISABLE_CPU_FEATURES", NUMPY_DISPATCH_PIN)
