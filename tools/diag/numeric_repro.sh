#!/bin/bash
# Diagnostic (D-68): do the simulator's result hashes depend on the CPU's numeric kernels?
# Runs E24 seed 1 (4 runs, ~1 min) under several numeric settings and prints the result hashes plus the machine.
# Usage: tools/diag/numeric_repro.sh [out-dir]    Compare the printed hashes between machines.
set -u
OUT=${1:-/tmp/numeric-repro}
AVX512="AVX512F AVX512CD AVX512_SKX AVX512_CLX AVX512_CNL AVX512_ICL AVX512_SPR"
echo "machine: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2) | cores $(nproc) | avx512: $(grep -c avx512f /proc/cpuinfo)"
uv run python - <<'PY'
import numpy
print("numpy", numpy.__version__)
try:
    from numpy._core._multiarray_umath import __cpu_features__ as f  # numpy >= 2
except ImportError:
    from numpy.core._multiarray_umath import __cpu_features__ as f
print("numpy SIMD features in use:", " ".join(sorted(k for k, v in f.items() if v)))
PY
variant() { # name, then env assignments
  local name=$1; shift
  rm -rf "$OUT/$name"
  env "$@" uv run python -m experiments.sweep E24 --jobs "$(nproc)" --seeds 1 --out "$OUT/$name" > "$OUT-$name.log" 2>&1
  echo "== $name: $*"
  uv run python - "$OUT/$name/E24/index.csv" <<'PY'
import csv, sys
for r in sorted(csv.DictReader(open(sys.argv[1])), key=lambda r: r["run_dir"]):
    print("  ", r["run_dir"].split("/")[-1], r["result_hash"][:16])
PY
}
variant default            X=1
variant coretype_haswell   OPENBLAS_CORETYPE=Haswell
variant npy_no_avx512      NPY_DISABLE_CPU_FEATURES="$AVX512"
variant haswell_no_avx512  OPENBLAS_CORETYPE=Haswell NPY_DISABLE_CPU_FEATURES="$AVX512"
variant nehalem_no_simd    OPENBLAS_CORETYPE=Nehalem NPY_DISABLE_CPU_FEATURES="$AVX512 AVX2 FMA3 AVX512F"
