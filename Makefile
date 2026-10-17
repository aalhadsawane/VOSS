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

.PHONY: check lint type imports test run repro-smoke sweep figs paper paper-analyze paper-verify manuscript manuscript-gen

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
	@test -n "$(EXP)" || (echo "usage: make sweep EXP=E19 [JOBS=4]"; exit 2)
	$(RUN) python -m experiments.sweep $(EXP) --jobs $(JOBS)

figs:
	$(RUN) python -m experiments.figures $(if $(EXP),--exp $(EXP),)

# ROADMAP P10: every frozen spec (10 seeds, idempotent: finished runs are reused), then all tables, figures and the
# hypothesis scorecard under paper/. Hours of CPU on a cold checkout; `make paper-analyze` redraws from runs/ in seconds.
paper:
	$(RUN) python -m experiments.paper all --jobs $(JOBS)

# Compare a rerun of the sweeps with the recorded result hashes (paper/run-hashes.csv): bit-for-bit reproduction check.
paper-verify:
	$(RUN) python -m experiments.paper_verify --tables

paper-analyze:
	$(RUN) python -m experiments.paper analyze

# Manuscript (ROADMAP P11): numbers and tables are generated from paper/ and configs/calibration/, figures from paper/tables;
# needs a LaTeX distribution (latexmk, IEEEtran). `make manuscript-gen` regenerates the inputs only.
manuscript-gen:
	$(RUN) python -m experiments.paper_tex
	$(RUN) python -m experiments.paper_figs

manuscript: manuscript-gen
	cd manuscript && latexmk -pdf -interaction=nonstopmode main.tex
