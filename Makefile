# Doc 01 §8 entrypoints. Single-threaded BLAS for reproducibility.
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1

UV ?= uv
RUN = $(UV) run
CONFIG ?= configs/smoke.yaml

.PHONY: check lint type imports test run repro-smoke sweep figs paper paper-analyze

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

paper-analyze:
	$(RUN) python -m experiments.paper analyze
