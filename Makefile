# Doc 01 §8 entrypoints. Single-threaded BLAS for reproducibility.
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1

UV ?= uv
RUN = $(UV) run
CONFIG ?= configs/smoke.yaml

.PHONY: check lint type imports test run repro-smoke sweep figs paper

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

sweep:
	@echo "sweep runner arrives in P8 (EXP=$(EXP))"; exit 1

figs:
	@echo "figure registry arrives in P8"; exit 1

paper:
	@echo "paper pipeline arrives in P10"; exit 1
