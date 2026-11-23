# Freeze checklist (plan V11.4-V11.5; exit criteria of V11)

Every item must hold before the commit is tagged `v2-freeze`. Each has the command that checks it, run from the
repository root; "empty" means the command prints nothing. Decisions D-110 to D-131 (`docs/DECISIONS.md`) are the
owner's answers to the freeze questions; the code changes they need land as small PRs into `revision-v2` (A-F below)
before the tag. After the tag, `voss/` and `configs/` change only by bug fixes listed in the methodology (V11.4).

## 1. The calibrated fleet is the only path (D-107, D-130)

| # | Item | Check |
|---|---|---|
| 1.1 | The assumed classes C0-C3, E0, E1, I7_64G and DC are deleted (DC by D-124). | `ls configs/hardware/` (empty or absent) |
| 1.2 | `scenario.hw_mix` is deleted and `scenario.machines` is required, not opt-in; the fleet overlay is the base, so `configs/machines.yaml` merges into `configs/base.yaml`. | `grep -rn 'hw_mix' voss configs experiments tests` (empty) |
| 1.3 | The config hash no longer special-cases an empty fleet. | `grep -n 'machines' voss/core/config.py` (no `if not tree["scenario"]["machines"]`) |
| 1.4 | The base calibration is a measured bundle of the fleet, not the placeholder. | `grep -n '^calibration' configs/base.yaml` (a `measured/` path); `ls configs/calibration/placeholder` (absent) |
| 1.5 | Every fleet bundle passes the contract. | `uv run python -m tools.calibrate.check_bundle configs/calibration/measured/node02-i7-12700-64g-nvme_nvme`; the same for `node02-i7-12700-64g-nvme_hdd`; `uv run python -m tools.calibrate.check_bundle configs/calibration/measured/node04-i7-4790s-8g-hdd_hdd --shared-from configs/calibration/measured/node02-i7-12700-64g-nvme_nvme` (0 errors each; the node04 TPM entries are shared by D-107) |
| 1.6 | The methodology states two machine models and the unbooted image (D-130). | `grep -n 'node04\|two machine' manuscript/sections/*.tex` |

## 2. Dormant options and v1 mechanisms are deleted (guardrail 32)

| # | Item | Check |
|---|---|---|
| 2.1 | PR A (D-110): lexicographic placement; `voss.cost` weights, exposure term and the 0.3 deleted. | `grep -rn 'lambda_exposure\|sync_weight\|scalarizer\|slo_weight' voss` (empty) |
| 2.2 | PR B (D-112, D-113): candidate cap and planning-pool caps deleted; the D-113 gate measured (one 500-worker 28 h run fits one job) and recorded in the development log. If the gate fails, the three planning caps return as swept constants and R07 gains their variants before the tag (not pre-emptively). | `grep -rn 'placer.K\|max_plan_workers\|hot_top_k\|hot_fn_k' voss` (empty on the pass path; on the fallback path the three planning keys are present and R07 has their variants); `grep -n 'D-113' docs/validation/development-log.md` |
| 2.3 | PR C (D-114): `sync_priority` on for every system, `ewma` wait model deleted. | `grep -rn 'ewma' voss/runtime voss/policy/cost` (empty); `grep -n 'sync_priority' configs/base.yaml` |
| 2.4 | PR D (D-115): start-up price priors from the reference bundle. | `grep -n 'cold_penalty_s\|cold_fn_s' voss/core/config.py` (no literal 3.0 / 0.5 default) |
| 2.5 | PR E (D-111, D-116, D-117, D-119, D-120, D-122, D-124, D-125, D-128): new keys for the drop-estimate constants, the code constants, the deadline multiple and idempotent fraction, certificate timings; one image-memory key; trusted hosts on the reference machine; tenant template reduced; detector profiles "backup off" and "drop estimate off". | `grep -n 'HEDGE_MIN_SAMPLES = \|OVERDUE_FRAC = \|ALPHA = ' -r voss` (empty); `uv run pytest -q tests/unit/test_r_specs.py` |
| 2.6 | PR F (D-131): `milp`, `greedy` and every v1 objective weight deleted; the hetero planner and its brute-force property test remain. | `ls voss/policy/plan/milp.py voss/policy/plan/greedy.py` (absent); `grep -rn 'rho_mem\|kappa_switch\|exposure_weight' voss` (empty); `uv run pytest -q tests/property/test_hetero_provisioning.py` |
| 2.7 | D-118: domain shocks deleted from provisioning. | `grep -rn 'domain_shock' voss` (empty) |
| 2.8 | v1 switches and trust scores deleted: `lifecycle_aware`, `hetero_aware`, `tofu_frac`, `assurance_tofu_factor`, `tiers`, `assurance`. | `grep -rn 'lifecycle_aware\|hetero_aware\|tofu\|assurance' voss` (empty) |
| 2.9 | Unused data files deleted: v1 emulation (`configs/e01/`, `functions_e01.yaml`, `tenants_e01.yaml`, `churn_e01.yaml`), parametric churn and load regimes, `adversary_collude.yaml`, `substrates/none.yaml`. Tests that used them get fixtures under `tests/`. | `ls configs/e01 configs/regimes/churn_med.yaml configs/regimes/load_default.yaml 2>&1 \| grep -v 'No such'` (empty) |
| 2.10 | The base config's v1 defaults are replaced by what every R spec sets (warm-up 14,400, `churn_seti`, the Azure trace, `wup2025`, Ookla links). | `grep -n 'warmup_s\|regime\|load' configs/base.yaml` |
| 2.11 | `decision_clock.coeffs` has no seed default (unit tests pass their own). | `grep -n 'coeffs:' voss/core/config.py` |
| 2.12 | No registered name is unused by a spec, a baseline or a test. | `uv run pytest -q tests/unit/test_baselines.py tests/unit/test_conventions.py` |

## 3. Parameter ledger (guardrail 27; V11 exit criterion)

| # | Item | Check |
|---|---|---|
| 3.1 | No row is pending, in any table. | `grep -n 'pending' docs/PARAMETERS.md` (empty) |
| 3.2 | Every key and data file has a row. | `uv run pytest -q tests/unit/test_parameters.py` |
| 3.3 | `scenario.envelope` is class A (D-132); `scenario.execution` takes interference and noise from the bundles and drops the assumed tail mixture (D-133, a code PR). | `grep -rn 'tail_p\|tail_median\|noise_sigma: float = Field(default' voss/world/execution.py` (empty) |
| 3.4 | Literature values are checked: `voss.worker.warm_ttl_s` ("citation to be checked"), the Envoy defaults (`consecutive_streak`, `consecutive_eject_s`), the histogram limits (D-123). | `grep -rn 'TODO verify\|to be checked' voss docs/PARAMETERS.md configs/baselines.yaml` (empty) |
| 3.5 | Every S constant VOSS reads has an R07 variant or a stated exemption. | `uv run pytest -q tests/unit/test_r_specs.py -k r07` |
| 3.6 | The manuscript's parameter TODOs are closed (T47, T48). | `grep -n 'T47\|T48' manuscript/sections/*.tex manuscript/TODO.md` (empty) |

## 4. Development log complete (V11.3)

| # | Item | Check |
|---|---|---|
| 4.1 | The `D01a` rerun after iteration 2 is logged with its run ID and result. | `grep -n 'Rerun' docs/validation/development-log.md` (one per iteration) |
| 4.2 | The 24 h `D02_DROP` rerun of iteration 2 is logged. | `grep -n 'D02_DROP' docs/validation/development-log.md` |
| 4.3 | Iteration 3 (key service and release fix, D-109) is logged; at most five iterations in all. | `grep -c '^## Iteration' docs/validation/development-log.md` (≤ 5) |
| 4.4 | The changes of D-110 to D-131 are logged as one dev rerun of `D01a` (bug fixes and freeze decisions, not an iteration), with the D-113 gate. | `grep -n 'D-110' docs/validation/development-log.md` |
| 4.5 | The known holder-budget overshoot (9 holders for `K` = 8 while a release is in flight) is fixed or stated as a limit with its measured size. | `grep -n 'overshoot\|9 holders' docs/validation/development-log.md` |
| 4.6 | The choice of VOSS's provisioning and the S defaults are recorded as decisions (V11.3, plan §10.4). | `grep -n 'D-1[0-9][0-9]' docs/DECISIONS.md` |

## 5. Held-out specs and hypotheses (V12.1-V12.2)

The shared central cells of R02, R06, R07, R08 and R09 are seeded from R01's release before their request files are
pushed; the procedure is in `docs/validation/HELDOUT_RUNBOOK.md` (the runner does not deduplicate across specs).

| # | Item | Check |
|---|---|---|
| 5.1 | R01-R09 match plan V12.2 and the decisions (D-126 R03 pools, D-127 R08, D-128 R06, D-129 R07). | `uv run pytest -q tests/unit/test_r_specs.py` |
| 5.2 | R06 and R07 gain the variants whose keys PRs C and E add (synchronous-first off, backup off, drop estimate off; prior strength, `k`, deadline multiple, idempotent fraction, certificate timings, `0.3 tts`, `OVERDUE_FRAC`). | `grep -n 'Added when their keys land' configs/experiments/R06.yaml configs/experiments/R07.yaml` (empty) |
| 5.3 | Hypotheses H1-H5 are committed before any held-out request. | `git log -1 --format=%cI -- docs/architecture/06-experiments.md` earlier than `git log --diff-filter=A --format=%cI -- 'runs/requests/experiment/r0*' \| tail -1` |
| 5.4 | No held-out request file exists before the tag. | `ls runs/requests/experiment/ \| grep -i '^r0'` (empty) |
| 5.5 | The baseline list of H1/H2 matches `configs/baselines.yaml`. | `uv run pytest -q tests/unit/test_r_specs.py -k r01` |

## 6. Green and tagged

| # | Item | Check |
|---|---|---|
| 6.1 | Lint, types, import layering and tests pass. | `make check` |
| 6.2 | A run reproduces its result hash. | `make repro-smoke` |
| 6.3 | One fleet run at the R01 central cell finishes within one job and under 10 GB (D-97 margin after D-113). | the run's `manifest.json` wall time and `peak_rss_mb` |
| 6.4 | The tag exists on `revision-v2` and nothing under `voss/` or `configs/` changed after it except listed bug fixes. | `git tag -l v2-freeze`; `git diff --stat v2-freeze revision-v2 -- voss configs` |
