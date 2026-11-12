# Doc 01 §8 entrypoints. Single-threaded BLAS for reproducibility.
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
# D-70: pin NumPy's SIMD dispatch (voss/__init__.py does it too, but pytest imports NumPy first).
ifeq ($(shell uname -m),x86_64)
export NPY_DISABLE_CPU_FEATURES=X86_V4 X86_V3 AVX512_ICL AVX512_SPR
endif

UV ?= uv
RUN = $(UV) run
CONFIG ?= configs/smoke.yaml

.PHONY: check lint type imports test run repro-smoke sweep manuscript

check: lint type imports test

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

type:
	$(RUN) mypy

imports:
	$(RUN) lint-imports

test:
	$(RUN) pytest

run:
	$(RUN) voss run $(CONFIG)

repro-smoke:
	rm -rf runs/repro-smoke
	$(RUN) voss run configs/toy.yaml --out runs/repro-smoke
	$(RUN) voss repro runs/repro-smoke/manifest.json

JOBS ?= 4

sweep:
	@test -n "$(EXP)" || (echo "usage: make sweep EXP=<NAME> [JOBS=4]"; exit 2)
	$(RUN) python -m experiments.sweep $(EXP) --jobs $(JOBS)

# Manuscript (plan V14). Generated inputs come from experiments.analysis (plan V2).
manuscript:
	cd manuscript && latexmk -pdf -interaction=nonstopmode main.tex
