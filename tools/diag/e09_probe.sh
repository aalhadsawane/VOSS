#!/bin/bash
# Diagnostic (D-68 follow-up): print the machine and the E09 seed-1 result hashes (5 runs, ~40 s).
# Reference values from the developer container (Intel Sapphire Rapids, glibc 2.41):
#   44579f9d4a0532d4 b0ed65d3...   e680343620a4e394 780c9730...
set -u
OUT=${1:-/tmp/e09-probe}
echo "machine: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2) | cores $(nproc) | avx512f: $(grep -c avx512f /proc/cpuinfo) | avx2: $(grep -c ' avx2' /proc/cpuinfo)"
echo "os: $(. /etc/os-release; echo "$PRETTY_NAME") | kernel $(uname -r) | glibc $(ldd --version | head -1 | awk '{print $NF}')"
uv run python - <<'PY'
import numpy, scipy, sys
print("python", sys.version.split()[0], "| numpy", numpy.__version__, "| scipy", scipy.__version__)
try:
    from numpy._core._multiarray_umath import __cpu_features__ as f
except ImportError:
    from numpy.core._multiarray_umath import __cpu_features__ as f
print("numpy SIMD in use:", " ".join(sorted(k for k, v in f.items() if v)))
PY
rm -rf "$OUT"
uv run python -m experiments.sweep E09 --jobs "$(nproc)" --seeds 1 --out "$OUT" > "$OUT.log" 2>&1
uv run python - "$OUT/E09/index.csv" <<'PY'
import csv, sys
for r in sorted(csv.DictReader(open(sys.argv[1])), key=lambda r: r["run_dir"]):
    print("  ", r["run_dir"].split("/")[-1], r["result_hash"][:16])
PY
