# Held-out runbook (V12.1-V12.3)

The one-time held-out sweep (guardrail 31) is started by committed request files under `runs/requests/experiment/`
(D-90). This page records the order and the shared-cell seeding the specs assume; it does not change a spec's grid,
systems or run count.

## Order

1. Commit the hypotheses H1-H5 (`docs/architecture/06-experiments.md` §3) before any request file (checklist 5.3).
2. Run `R01` first. Its release asset (`runs-R01-<run id>`) holds every central-cell run.
3. Run `R02`, `R06`, `R07`, `R08` and `R09` after R01, seeding the shared cells (below).
4. Run `R03`, `R04`, `R05` after R01 (their grids do not share R01 cells, but they use the same frozen code).
5. Run `verify.yml` on each finished spec (V12.3).

## D-113 gate

If the D-113 wall-clock gate fails (the 500-worker 28 h run does not fit one job), the planning-pool and candidate
caps return as swept constants (option B of D-113) and R07 must gain their variants before the tag. Do not add those
variants pre-emptively.

## Shared cells

`R02`, `R06`, `R07`, `R08` and `R09` contain R01's central cell (`K` = 8, `rate_mult` = 21, `voss`) and say so in
their headers; `tests/unit/test_r_specs.py::test_central_cell_runs_are_r01_runs` checks that the config hashes are
equal. The runner is idempotent per spec directory (`runs/<spec>/<config_hash>/`), but it does **not** deduplicate
across specs. Before dispatching such a spec, seed its shared run directories from R01's release:

```sh
# one directory per shared config hash; the manifest is what the runner checks
for h in $(uv run python - <<'PY'
from pathlib import Path
from experiments.sweep import plan
from tests.unit.test_r_specs import spec
import tempfile
with tempfile.TemporaryDirectory() as d:
    print("\n".join(sorted({p.config_hash for p in plan("R08", Path(d))[0] if p.label == "w500"})))
PY
); do
  mkdir -p "runs/R08/$h"
  tar -xzf "runs-R01-<run id>.tar.zst" -C "runs/R08/$h" --strip-components=2 "R01/$h"
done
```

The exact extraction path depends on the release asset layout; the requirement is that `runs/<spec>/<hash>/manifest.json`
exists for every shared cell before the request file is pushed. The spec's own run count already counts the shared
cell once, so the seeded directories must not be duplicated.

## After the sweep

- Every cell appears in the paper or its appendix (guardrail 20).
- One code revision (`v2-freeze`) for all reported results (guardrail 22).
