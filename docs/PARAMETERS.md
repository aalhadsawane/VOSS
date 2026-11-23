# Parameter ledger (docs/REVISION_PLAN.md §3 and V0.6)

Every constant a reported system uses has one row and one class:
**M** measured (calibration bundle or timing run), **T** trace (public dataset), **L** literature (checked citation),
**D** derived (formula from other rows), **A** axis (a choice shown as an axis or stated in the paper),
**S** swept (design constant with no better basis; default chosen on the development split, sensitivity reported).
There is no "assumed" class. A row marked **pending Vn** is a v1 value that phase Vn replaces or removes; no row may be
pending at the scheduler freeze (V11). The paper's constants table is generated from this file.

`tests/unit/test_parameters.py` fails if a configuration key or data file is missing here, or if a row names one that
no longer exists. When you add, rename or remove a key, change this file in the same commit.

## Configuration keys (`voss/core/config.py`, `voss/policy/plan/types.py`)

| Key | Default | Class | Basis or fate |
|---|---|---|---|
| `seed` | `1` | A | run identity; seeds listed per experiment |
| `horizon_s` | `3600.0` | A | per experiment (V9.5 sizing) |
| `system` | `'voss'` | A | system under test |
| `reference` | `'trusted_hosts'` | D | trusted always-on hosts baseline (V8): appliance ladder without attestation |
| `scenario.workers` | `1000` | A | pool size axis (R03) |
| `scenario.start_utc_h` | `0.0` | T | aligned to the trace window (V9) |
| `scenario.warmup_s` | `172800.0` | D | = `voss.keepalive_hist.range_s` (14,400 s), the longest learning window of a compared policy (guardrail 23, D-97); every R spec sets it (`tests/unit/test_r_specs.py`); the base default is replaced at the freeze (`docs/FREEZE_CHECKLIST.md`) |
| `scenario.substrate_mix` | `{'appliance_tpm': 1.0}` | A | owner classes S/P/M (V3.3) |
| `scenario.tiers` | `{'nightly': 0.6, 'idle': 0.3, 'dedicated': 0.1}` | pending V11 | v1 assumed tiers; unused with traced sessions; delete at the freeze (`docs/FREEZE_CHECKLIST.md`) |
| `scenario.hw_mix` | `{'C0': 0.1, 'C1': 0.35, 'C2': 0.35, 'C3': 0.2}` | pending V11 | v1 assumed classes; superseded by `scenario.machines` (D-107); delete at the freeze |
| `scenario.machines` | `{}` | D | calibrated fleet (V9.4, D-107): one class per measured bundle (M), weights from the BOINC host survey (T), radius 1 = one power-of-two step of the survey; empty = `hw_mix` |
| `scenario.tofu_frac` | `0.3` | pending V11 | v1 trust-on-first-use share; delete at the freeze |
| `scenario.physical_frac` | `0.0` | A | share of owners without memory encryption willing to attack physically (class P, V3.3) |
| `scenario.regime` | `'churn_med'` | T | every R spec sets `churn_seti` (seti09, Failure Trace Archive, held-out split; `tests/unit/test_r_specs.py`); the parametric default is deleted at the freeze |
| `scenario.churn` | `{}` | A | inline overrides of the regime: every R spec sets `split: heldout`; the notice fraction `graceful_frac` is an axis {0, 0.5} (R03, `configs/regimes/churn_seti.yaml`) |
| `scenario.adversary` | `{}` | A | owner faults: fraction and behaviour (R04, R05) |
| `scenario.load` | `{}` | T | every R spec sets the Azure Functions 2019 trace, held-out split (V9.1); `rate_mult` is the load axis {10.5, 21, 30} (D-99) |
| `scenario.geo` | `{}` | T | every R spec sets `pop_trace: wup2025` (World Urbanization Prospects 2025, V9.3) |
| `scenario.network` | `{}` | T | links: `link.trace` = Ookla fixed-broadband per metro (V9.3); `route_factor` 1.654 fitted to WonderProxy pings; `c_eff` 100 km/ms (fibre) |
| `scenario.envelope` | `{}` | A | D-132: donated shares `cpu_frac` 0.75, `mem_frac` 0.6, disks 0.2, stated; R07 varies `cpu_frac` {0.5, 1.0} and `mem_frac` {0.4, 0.8}; slots capped by donated memory (D-108) |
| `scenario.execution` | `{}` | pending V11 | D-133: interference from the bundle's co-run table (M), noise from measured repeat variation (D), unmeasured parts deleted; leaves pending with that change |
| `scenario.functions` | `'functions.yaml'` | A | the function catalogue (D-119): guest memory stated, deadline multiple and idempotent fraction axes |
| `scenario.tenants` | `'tenants.yaml'` | A | tenant template (D-125): key-service city and default budget |
| `voss.infra.orchestrator` | `'Frankfurt'` | A | provider site (stated in the paper) |
| `voss.infra.verifier` | `'Frankfurt'` | A | provider site |
| `voss.infra.registry` | `'Frankfurt'` | A | provider site |
| `voss.infra.scheduler` | `'Frankfurt'` | A | provider site of the one scheduler (D-83) |
| `voss.infra.scheduler_speed` | `1.0` | D | 1 = the provider CPU whose decision times are charged (`decision_clock.coeffs_file`, V10; `runtime/schedlib/provider_host.py`) |
| `voss.infra.routers` | `('Washington', 'Frankfurt', 'Singapore')` | A | provider front-end sites |
| `voss.router.cold_penalty_s` | `3.0` | D | D-115: from the reference bundle's measured attestation, key release and boot (until that change lands, the v1 seed) |
| `voss.router.cold_fn_s` | `0.5` | D | D-115: from the reference bundle's measured cold function start (until that change lands, the v1 seed) |
| `voss.router.T_dispatch` | `1.0` | S | router re-send timer |
| `voss.router.max_resends` | `3` | S | router re-sends before giving up on the scheduler |
| `voss.router.give_up_s` | `{'sync': 30.0, 'async': 300.0}` | S | router gives up after this; above every deadline |
| `voss.router.done_keep_s` | `3600.0` | D | finished invocations remembered this long (duplicate detection); 12x the async give-up, bounds memory (plan V9.5) |
| `voss.router.receipt_batch_s` | `1.0` | S | receipt batching to the DB |
| `voss.placer.sync` | `'greedy'` | A | placement algorithm (V5.2) |
| `voss.placer.async` | `'greedy'` | A | placement algorithm (V5.2) |
| `voss.placer.K` | `12` | pending V11 | deleted by D-112 (every eligible worker is a candidate) |
| `voss.placer.window_s` | `0.2` | S | batching window for asynchronous invocations |
| `voss.predictor.name` | `'blr'` | S | run-time estimator (V5.4) |
| `voss.predictor.forgetting` | `0.995` | S | run-time estimator forgetting factor |
| `voss.predictor.conformal` | `True` | S | conformal quantiles on/off |
| `voss.cost.scalarizer` | `'slo_miss'` | pending V11 | deleted by D-110 (lexicographic placement) |
| `voss.cost.eps` | `0.05` | pending V11 | deleted by D-110 |
| `voss.cost.lambda_exposure` | `1.0` | pending V11 | deleted by D-110 |
| `voss.cost.sync_weight` | `1.0` | pending V11 | deleted by D-110 |
| `voss.cost.sigma` | `{'low': 0.1, 'medium': 1.0, 'high': 3.0}` | pending V11 | deleted by D-110 |
| `voss.cost.lifecycle_aware` | `True` | pending V11 | v1 ablation switch; delete at the freeze (always on) |
| `voss.cost.wait_model` | `'ewma'` | pending V11 | deleted by D-114 (per-worker queue replay is the only model) |
| `voss.admission.enabled` | `True` | S | admission on/off |
| `voss.admission.eps` | `0.05` | S | reject when every candidate misses with probability above 1 - eps |
| `voss.admission.defer_s` | `1.0` | S | retry delay for a deferred asynchronous invocation |
| `voss.models.survival` | `'weibull'` | S | session survival estimator (V5.4) |
| `voss.models.omission` | `'beta_cusum'` | S | drop estimator (V5.4) |
| `voss.models.refit_s` | `60.0` | S | survival refit period |
| `voss.models.cusum_h` | `5.0` | S | change-detection threshold |
| `voss.planner.name` | `'milp'` | A | provisioning policy or baseline (V5, V8) |
| `voss.planner.T_plan` | `30.0` | S | plan V5.3: at least the longest preparation action, default 30 s chosen on the development split; R07 varies it |
| `voss.planner.T_solve` | `2.0` | pending V11 | deleted by D-131 (exact program) |
| `voss.planner.node_limit` | `50` | pending V11 | deleted by D-131 |
| `voss.planner.max_plan_workers` | `40` | pending V11 | deleted by D-113 (gate: a 500-worker 28 h run still fits one job) |
| `voss.planner.replan_tolerance` | `0.2` | S | re-plan only when inputs change by more than this |
| `voss.planner.hot_top_k` | `20` | pending V11 | deleted by D-113 |
| `voss.planner.hot_fn_k` | `50` | pending V11 | deleted by D-113 |
| `voss.planner.min_rate` | `0.01` | S | functions below this request rate are not provisioned |
| `voss.planner.f_from_alpha` | `0.1` | pending V11 | deleted by D-131 |
| `voss.planner.horizon_factor` | `2.0` | S | forecast horizon in provisioning periods |
| `voss.planner.cold_penalty` | `10.0` | pending V11 | deleted by D-131 |
| `voss.planner.max_parallel_prepares` | `2` | S | preparation actions per worker per round |
| `voss.planner.T_linger` | `30.0` | S | time a released worker keeps its warm sandboxes |
| `voss.planner.scenarios` | `32` | S | failure scenarios per provisioning round (hetero); the guarantee holds for the sample average |
| `voss.planner.domain_shock_p` | `0.0` | pending V11 | deleted by D-118 |
| `voss.planner.ablate` | `()` | A | ablations of plan §11.7 (homogeneous, binary, reliability_blind) for R06 |
| `voss.planner.params` | `{}` | S | container of the `voss.planner.params.*` rows; each row has its own class |
| `voss.scheduler.hetero_aware` | `True` | pending V11 | v1 ablation switch; delete at the freeze (always on) |
| `voss.scheduler.heartbeat_s` | `2.0` | S | worker report period |
| `voss.scheduler.keepalive_s` | `1.0` | S | start-up price decay tick |
| `voss.scheduler.stale_after_s` | `7.0` | S | a worker silent this long is treated as gone |
| `voss.scheduler.max_attempts` | `3` | S | attempts per invocation |
| `voss.scheduler.retry_backoff_s` | `0.2` | S | D-116: retry delay of the retry-based detectors; R07 varies {0.1, 0.4} |
| `voss.scheduler.no_candidate_retry_s` | `0.5` | S | retry delay when no candidate exists |
| `voss.scheduler.view_refresh_s` | `0.25` | S | view cache refresh |
| `voss.worker.warm_ttl_s` | `600.0` | L | fixed keep-alive baseline timer; citation to be checked in V8; also an axis |
| `voss.worker.warm_eviction` | `lru` | A | warm-sandbox eviction: `lru` or `greedy_dual` (FaaSCache baseline, V8) |
| `voss.worker.m_base_mb` | `512.0` | A | D-117: image memory reserve, a stated build parameter; R07 varies {256, 1,024}; merged with the planner's copy |
| `voss.worker.assurance_tofu_factor` | `0.9` | pending V11 | v1 trust score; delete at the freeze |
| `voss.worker.sync_priority` | `False` | A | D-114: synchronous-first on for every system; off only as the R06 ablation |
| `voss.keepalive_hist.bin_s` | `60.0` | L | Shahrad et al. ATC 2020: 1-minute bins |
| `voss.keepalive_hist.range_s` | `14400.0` | L | Shahrad et al. ATC 2020: 4-hour range |
| `voss.keepalive_hist.head_pct` | `5.0` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.tail_pct` | `99.0` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.margin` | `0.1` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.min_samples` | `10` | pending V11 | D-123: L if Shahrad et al. ATC 2020 §4.2 gives it, otherwise a listed deviation and S |
| `voss.keepalive_hist.cv_min` | `2.0` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.oob_max` | `0.2` | pending V11 | D-123: as `min_samples` |
| `voss.keepalive_hist.fallback_ttl_s` | `600.0` | D | = `voss.worker.warm_ttl_s`: out-of-range idle times fall back to the fixed timer in place of the paper's ARIMA forecast (deviation listed in `configs/baselines.yaml`) |
| `voss.cache.value` | `'gdsf'` | S | disk cache value policy |
| `voss.cache.hdd_tier` | `True` | S | hard-disk tier on/off |
| `voss.audit.p` | `0.0` | A | audit probability per idempotent invocation (V7.3; swept in R05) |
| `voss.detection.detector` | `voss` | A | `fixed`, `consecutive`, `voss` (plan V7.2) |
| `voss.detection.quantile` | `0.95` | S | voss timer: predicted completion quantile, no floor (plan V7.1, F5) |
| `voss.detection.probe_timeout_s` | `2.0` | S | an unanswered probe is drop-estimate evidence; it does not end the attempt |
| `voss.detection.consecutive_streak` | `5` | L | Envoy outlier detection `consecutive_5xx`; TODO verify |
| `voss.detection.consecutive_eject_s` | `30.0` | L | Envoy outlier detection `base_ejection_time`; TODO verify |
| `voss.detection.suspect_streak` | `2` | S | consecutive failures before a worker is marked as failed |
| `voss.detection.suspect_s` | `600.0` | S | how long a worker stays marked |
| `voss.keys.max_holders` | `None` | A | holder budget K per function key (D-85); axis {2, 4, 8, 16, unbounded} in R01 |
| `voss.keys.rotate_s` | `None` | A | key rotation period R (D-85); axis {none, 1 h, 24 h} in R07 |
| `drain_s` | `30.0` | S | simulated time after the horizon for in-flight work |
| `decision_clock.mode` | `'modeled'` | A | modeled for simulation, measured for emulation |
| `decision_clock.cpu_scale` | `1.0` | S | emulation only |
| `decision_clock.coeffs` | `{'plan': (0.02, 5e-05), 'place': (0.0002, 2e-05), 'route'...` | pending V11 | seed coefficients, used only without `coeffs_file` (unit tests); delete the seed default at the freeze |
| `decision_clock.coeffs_file` | `''` | M | measured provider coefficients (`configs/calibration/provider/<cpu>/decision.yaml`, V10) |
| `calibration` | `None` | M | measured bundle per experiment (G14) |
| `out_dir` | `'runs'` | A | output location |
| `label` | `''` | A | run label |
| `voss.planner.params.rho_mem` | `0.0001` | pending V11 | deleted by D-131 |
| `voss.planner.params.rho_ssd` | `2e-05` | pending V11 | deleted by D-131 |
| `voss.planner.params.kappa_switch` | `0.05` | pending V11 | deleted by D-131 |
| `voss.planner.params.beta_warm` | `0.05` | pending V11 | deleted by D-131 |
| `voss.planner.params.gamma` | `0.5` | pending V11 | deleted by D-131 |
| `voss.planner.params.kappa_dom` | `0.5` | pending V11 | deleted by D-131 |
| `voss.planner.params.w_max` | `4` | S | warm sandboxes per function per worker |
| `voss.planner.params.m_base_mb` | `512.0` | A | D-117: as `voss.worker.m_base_mb` (one key after the merge) |
| `voss.planner.params.use_robust` | `True` | pending V11 | deleted by D-131 (milp and greedy only) |
| `voss.planner.params.use_exposure` | `True` | pending V11 | deleted by D-131 |
| `voss.planner.params.use_domain_cap` | `True` | pending V11 | deleted by D-131 (milp and greedy only) |
| `voss.planner.params.use_freshness` | `True` | S | skip workers whose certificate expires within the horizon |
| `voss.planner.params.exposure_weight` | `1.0` | pending V11 | deleted by D-131 |
| `voss.planner.params.survival_blind` | `False` | A | ablation (R06) |

## Derived per-worker quantities

| Quantity | Class | Basis |
|---|---|---|
| slots of a calibrated-fleet worker | D | min(floor(`cpu_frac` x threads), floor(donated memory / largest function `mem_mb`)), at least 1 (D-108); node04: 6 -> 4 |

## Constants in code that are not configuration keys (guardrail 27)

Found while preparing the freeze; the decision in the last column settles each, and the row leaves *pending* when
the constant is deleted or becomes a key. They are listed here so that the ledger is complete; they are not parsed by `tests/unit/test_parameters.py`.

| Constant | Value | Class | Where | Item |
|---|---|---|---|---|
| placement weight of an invocation without a waiting client | 0.3 | pending V11 | `voss/policy/cost/components.py` `slo_weight` | D-110: deleted (T47) |
| omission prior `(a0, b0)` | (0.5, 20.0) | pending V11 | `voss/policy/omission.py` `BetaCusum` | D-111: key, S (T48) |
| omission pessimistic prior after a change point | (2.0, 4.0) | pending V11 | `voss/policy/omission.py` `BetaCusum` | D-111: key, S (T48) |
| CUSUM drift `k` | 0.1 | pending V11 | `voss/policy/omission.py` `BetaCusum` | D-111: key, S (T48) |
| variance of the time to start, `(0.3 tts)^2` | 0.3 | pending V11 | `voss/policy/cost/components.py` | D-122: key, S |
| hedged requests: latencies observed before the q95 timer applies | 20 | pending V11 | `voss/policy/detect.py` `HEDGE_MIN_SAMPLES` | D-122: key, S |
| run-time model prior standard deviations | (0.7, 0.3, 0.5) | pending V11 | `voss/policy/predict/blr.py` | D-122: key, S |
| start-up price smoothing | 0.05 | pending V11 | `voss/runtime/schedlib/prices.py` `ALPHA` | D-122: key, S |
| overdue job: extra fraction of its prediction | 0.25 | pending V11 | `voss/policy/cost/wait.py` `OVERDUE_FRAC` | D-122: key, S |

## Data files (`configs/`, excluding calibration bundles and experiment specs)

Numbers inside data files carry their own `provenance` tags (`tests/unit/test_data_provenance.py`). The class here is
for the file as a whole.

| File | Class | Basis or fate |
|---|---|---|
| `configs/base.yaml` | A | defaults of every run |
| `configs/e01/base.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/e01/i7-12700-64g/base.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/e01/i7-12700-64g/s1_stable.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/e01/i7-12700-64g/s2_churn.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/e01/i7-12700-64g/s3_omit.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/e01/i7-12700-64g/s3_omit_load.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/e01/i7-12700-64g/s4_load.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/e01/s1_stable.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/e01/s2_churn.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/e01/s3_omit.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/e01/s3_omit_load.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/e01/s4_load.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/request_bytes.yaml` | D | bytes a client sends per measured input size of each guest function (D-106) |
| `configs/functions.yaml` | pending V11 | D-119: guest memory (A), deadline multiple and idempotent fraction keys; leaves pending with that change |
| `configs/functions_e01.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/hardware/C0.yaml` | pending V11 | v1 machine class; the fleet is the only path (D-107); delete at the freeze |
| `configs/hardware/C1.yaml` | pending V11 | v1 machine class; the fleet is the only path (D-107); delete at the freeze |
| `configs/hardware/C2.yaml` | pending V11 | v1 machine class; the fleet is the only path (D-107); delete at the freeze |
| `configs/hardware/C3.yaml` | pending V11 | v1 machine class; the fleet is the only path (D-107); delete at the freeze |
| `configs/hardware/DC.yaml` | pending V11 | deleted by D-124 (trusted hosts are the reference machine) |
| `configs/hardware/E0.yaml` | pending V11 | v1 machine class; the fleet is the only path (D-107); delete at the freeze |
| `configs/hardware/E1.yaml` | pending V11 | v1 machine class; the fleet is the only path (D-107); delete at the freeze |
| `configs/hardware/I7_64G.yaml` | pending V11 | v1 machine class; the fleet is the only path (D-107); delete at the freeze |
| `configs/regimes/adversary_all.yaml` | A | D-121: owner behaviour parameters, axes of the threat, stated with R04/R05 |
| `configs/regimes/adversary_collude.yaml` | pending V11 | D-121: no spec uses it; delete at the freeze |
| `configs/regimes/adversary_mixed.yaml` | A | D-121: owner behaviour parameters, axes of the threat, stated with R04/R05 |
| `configs/regimes/adversary_none.yaml` | A | D-121: owner behaviour parameters, axes of the threat, stated with R04/R05 |
| `configs/regimes/churn_burst.yaml` | pending V11 | parametric regime no reported spec uses; delete at the freeze (tests that use it move to a test fixture) |
| `configs/regimes/churn_correlated.yaml` | pending V11 | parametric regime no reported spec uses; delete at the freeze (tests that use it move to a test fixture) |
| `configs/regimes/churn_e01.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/regimes/churn_high.yaml` | pending V11 | parametric regime no reported spec uses; delete at the freeze (tests that use it move to a test fixture) |
| `configs/regimes/churn_low.yaml` | pending V11 | parametric regime no reported spec uses; delete at the freeze (tests that use it move to a test fixture) |
| `configs/regimes/churn_med.yaml` | pending V11 | parametric regime no reported spec uses; delete at the freeze (tests that use it move to a test fixture) |
| `configs/regimes/churn_seti.yaml` | T | SETI@home host availability (FTA seti09), one host's week per worker (V9.2); `graceful_frac` axis |
| `configs/regimes/load_default.yaml` | pending V11 | parametric regime no reported spec uses; delete at the freeze (tests that use it move to a test fixture) |
| `configs/regimes/load_flash.yaml` | pending V11 | parametric regime no reported spec uses; delete at the freeze (tests that use it move to a test fixture) |
| `configs/machines.yaml` | D | calibrated fleet overlay (V9.4, D-107): node02 (reference) and node04, Rosetta@home survey |
| `configs/machines_mix.yaml` | T | survey mapping of the fleet overlay (D-107), generated by `experiments.analysis.fleet_mix` from the gitignored survey; the paper reads this file |
| `configs/smoke.yaml` | A | test configuration |
| `configs/substrates/appliance_tpm.yaml` | pending V11 | D-120: steps measured (bundle), `valid_s`/`reattest_every_s` A, message sizes D, `assurance_base` deleted; leaves pending with that change |
| `configs/substrates/none.yaml` | pending V11 | no reported system uses it; delete at the freeze |
| `configs/baselines.yaml` | D | systems compared: source, overrides, deviations (V8) |
| `configs/traces/wup2025/provenance.yaml` | T | trace wup2025, release data-wup2025-1085a0d3 (plan V9) |
| `configs/traces/boinc-rosetta/provenance.yaml` | T | trace boinc-rosetta, release data-boinc-rosetta-1085a0d3 (plan V9) |
| `configs/traces/boinc-milkyway/provenance.yaml` | T | trace boinc-milkyway, release data-boinc-milkyway-1085a0d3 (plan V9) |
| `configs/traces/seti09/provenance.yaml` | T | trace seti09, release data-seti09-79bec54d (plan V9) |
| `configs/traces/azure2019/provenance.yaml` | T | Azure Functions 2019 sample, release data-azure2019-*: functions and per-minute arrivals per split (V9.1) |
| `configs/traces/ookla-fixed-2024q1/provenance.yaml` | T | Ookla fixed-broadband links per metro, release data-ookla-fixed-2024q1-* (V9.3) |
| `configs/traces/wonderproxy-2020-07/provenance.yaml` | T | WonderProxy all-pairs pings: fitted route factor 1.654 (V9.3) |
| `configs/substrates/trusted_hosts.yaml` | M | appliance_tpm ladder without attestation or key release (V8) |
| `configs/references/trusted_hosts.yaml` | A | trusted always-on hosts: 40 per router metro (V8) |
| `configs/tenants.yaml` | pending V11 | D-125: reduce to `kbs_city` and the default budget; leaves pending with that change |
| `configs/tenants_e01.yaml` | pending V11 | v1 emulation; V13 builds its own scenario; delete at the freeze |
| `configs/toy.yaml` | A | test configuration |
