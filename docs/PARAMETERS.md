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
| `reference` | `'ref_lambda_like'` | pending V8 | trusted always-on hosts baseline; v1 vendor-named profiles deleted |
| `scenario.workers` | `1000` | A | pool size axis (R03) |
| `scenario.start_utc_h` | `0.0` | T | aligned to the trace window (V9) |
| `scenario.warmup_s` | `172800.0` | pending V9 | session warm-up of the parametric generator; replaced by trace alignment |
| `scenario.substrate_mix` | `{'appliance_tpm': 1.0}` | A | owner classes S/P/M (V3.3) |
| `scenario.tiers` | `{'nightly': 0.6, 'idle': 0.3, 'dedicated': 0.1}` | pending V9 | v1 assumed worker tiers; replaced by traced availability |
| `scenario.hw_mix` | `{'C0': 0.1, 'C1': 0.35, 'C2': 0.35, 'C3': 0.2}` | pending V9 | v1 assumed classes; becomes calibrated machines weighted by a hardware survey (V9.4) |
| `scenario.tofu_frac` | `0.3` | pending V4 | v1 firmware trust-on-first-use share; removed with trust scores |
| `scenario.regime` | `'churn_med'` | pending V9 | parametric churn regime; replaced by traced sessions |
| `scenario.churn` | `{}` | pending V9 | inline churn overrides |
| `scenario.adversary` | `{}` | A | owner faults: fraction and behaviour (R04, R05) |
| `scenario.load` | `{}` | pending V9 | parametric arrivals; replaced by the Azure 2019 trace |
| `scenario.geo` | `{}` | pending V9 | metro and region data |
| `scenario.network` | `{}` | pending V9 | link and delay model; replaced by broadband measurement data (V9.3) |
| `scenario.envelope` | `{}` | pending V5 | donated shares 0.75/0.6/0.2; removed by the capacity model (V5.5) |
| `scenario.execution` | `{}` | pending V5 | execution noise and interference; interference becomes measured (V5.5) |
| `scenario.functions` | `'functions.yaml'` | pending V9 | catalogue of measured functions (V1, V9.1) |
| `scenario.tenants` | `'tenants.yaml'` | pending V9 | tenant structure from the trace (owner hash) |
| `voss.infra.orchestrator` | `'Frankfurt'` | A | provider site (stated in the paper) |
| `voss.infra.verifier` | `'Frankfurt'` | A | provider site |
| `voss.infra.registry` | `'Frankfurt'` | A | provider site |
| `voss.infra.scheduler` | `'Frankfurt'` | A | provider site of the one scheduler (D-83) |
| `voss.infra.scheduler_speed` | `1.0` | pending V10 | replaced by measured decision timing |
| `voss.infra.routers` | `('Washington', 'Frankfurt', 'Singapore')` | A | provider front-end sites |
| `voss.router.cold_penalty_s` | `3.0` | pending V5 | prior price of a start without key; replaced by measured start-up costs |
| `voss.router.cold_fn_s` | `0.5` | pending V5 | prior price of a cold function start; replaced by measured start-up costs |
| `voss.router.T_dispatch` | `1.0` | S | router re-send timer |
| `voss.router.max_resends` | `3` | S | router re-sends before giving up on the scheduler |
| `voss.router.give_up_s` | `{'sync': 30.0, 'async': 300.0}` | S | router gives up after this; above every deadline |
| `voss.router.receipt_batch_s` | `1.0` | S | receipt batching to the DB |
| `voss.placer.sync` | `'greedy'` | A | placement algorithm (V5.2) |
| `voss.placer.async` | `'greedy'` | A | placement algorithm (V5.2) |
| `voss.placer.K` | `12` | pending V5 | 12 candidates; removed (all holders are candidates) |
| `voss.placer.window_s` | `0.2` | S | batching window for asynchronous invocations |
| `voss.predictor.name` | `'blr'` | S | run-time estimator (V5.4) |
| `voss.predictor.forgetting` | `0.995` | S | run-time estimator forgetting factor |
| `voss.predictor.conformal` | `True` | S | conformal quantiles on/off |
| `voss.cost.scalarizer` | `'slo_miss'` | pending V5 | v1 weighted cost; replaced by deadline-miss probability with tie-break |
| `voss.cost.eps` | `0.05` | pending V5 | v1 weight 0.05 on expected latency; removed |
| `voss.cost.lambda_exposure` | `1.0` | pending V4 | v1 exposure weight; removed (holder budget K) |
| `voss.cost.sync_weight` | `1.0` | pending V5 | v1 weight; removed |
| `voss.cost.sigma` | `{'low': 0.1, 'medium': 1.0, 'high': 3.0}` | pending V4 | v1 sensitivity weights 0.1/1/3; removed |
| `voss.cost.lifecycle_aware` | `True` | pending V5 | v1 ablation switch |
| `voss.cost.wait_model` | `'ewma'` | pending V5 | per-worker queue replay becomes the only model |
| `voss.admission.enabled` | `True` | S | admission on/off |
| `voss.admission.eps` | `0.05` | S | reject when every candidate misses with probability above 1 - eps |
| `voss.admission.defer_s` | `1.0` | S | retry delay for a deferred asynchronous invocation |
| `voss.models.survival` | `'weibull'` | S | session survival estimator (V5.4) |
| `voss.models.omission` | `'beta_cusum'` | S | drop estimator (V5.4) |
| `voss.models.refit_s` | `60.0` | S | survival refit period |
| `voss.models.cusum_h` | `5.0` | S | change-detection threshold |
| `voss.planner.name` | `'milp'` | A | provisioning policy or baseline (V5, V8) |
| `voss.planner.T_plan` | `30.0` | pending V5 | provisioning period; D lower bound and S above it (V5.3) |
| `voss.planner.T_solve` | `2.0` | pending V5 | exact program time limit; exact program becomes an offline check |
| `voss.planner.node_limit` | `50` | pending V5 | exact program node limit |
| `voss.planner.max_plan_workers` | `40` | pending V5 | cap of 40; removed |
| `voss.planner.replan_tolerance` | `0.2` | S | re-plan only when inputs change by more than this |
| `voss.planner.hot_top_k` | `20` | pending V5 | cap; removed |
| `voss.planner.hot_fn_k` | `50` | pending V5 | cap; removed |
| `voss.planner.min_rate` | `0.01` | S | functions below this request rate are not provisioned |
| `voss.planner.f_from_alpha` | `0.1` | pending V5 | f as a tenth of the pool; replaced by derived f (V5.3) |
| `voss.planner.horizon_factor` | `2.0` | S | forecast horizon in provisioning periods |
| `voss.planner.cold_penalty` | `10.0` | pending V5 | v1 objective weight; removed |
| `voss.planner.max_parallel_prepares` | `2` | S | preparation actions per worker per round |
| `voss.planner.T_linger` | `30.0` | S | time a released worker keeps its warm sandboxes |
| `voss.planner.params` | `{}` | pending V5 | objective parameters (rows below) |
| `voss.scheduler.hetero_aware` | `True` | pending V5 | v1 ablation switch |
| `voss.scheduler.heartbeat_s` | `2.0` | S | worker report period |
| `voss.scheduler.keepalive_s` | `1.0` | S | start-up price decay tick |
| `voss.scheduler.stale_after_s` | `7.0` | S | a worker silent this long is treated as gone |
| `voss.scheduler.max_attempts` | `3` | S | attempts per invocation |
| `voss.scheduler.retry_backoff_s` | `0.2` | pending V7 | retry delay; replaced by backup attempts |
| `voss.scheduler.no_candidate_retry_s` | `0.5` | S | retry delay when no candidate exists |
| `voss.scheduler.view_refresh_s` | `0.25` | S | view cache refresh |
| `voss.worker.warm_ttl_s` | `600.0` | L | fixed keep-alive baseline timer; citation to be checked in V8; also an axis |
| `voss.worker.m_base_mb` | `512.0` | pending V5 | image memory; becomes measured image_mem |
| `voss.worker.assurance_tofu_factor` | `0.9` | pending V4 | trust scores removed |
| `voss.worker.sync_priority` | `False` | pending V5 | synchronous-first queueing; on for every system in v2 |
| `voss.keepalive_hist.bin_s` | `1.0` | pending V8 | 1 s (v1); published value 60 s |
| `voss.keepalive_hist.range_s` | `1800.0` | pending V8 | 30 min (v1); published value 4 h |
| `voss.keepalive_hist.head_pct` | `5.0` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.tail_pct` | `99.0` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.margin` | `0.1` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.min_samples` | `10` | pending V8 | not in the paper; check |
| `voss.keepalive_hist.cv_min` | `2.0` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.oob_max` | `0.2` | pending V8 | out-of-range rule; check against the paper |
| `voss.keepalive_hist.fallback_ttl_s` | `600.0` | pending V8 | fallback when the histogram is not representative |
| `voss.cache.value` | `'gdsf'` | S | disk cache value policy |
| `voss.cache.hdd_tier` | `True` | S | hard-disk tier on/off |
| `voss.detection.watchdog_slack` | `1.2` | pending V7 | 1.2; removed (timeout = predicted q95) |
| `voss.detection.watchdog_min_s` | `3.0` | pending V7 | 3 s floor; removed (F5) |
| `voss.detection.probe_timeout_s` | `2.0` | pending V7 | no longer gates the retry; S for evidence |
| `voss.detection.suspect_streak` | `2` | S | consecutive failures before a worker is marked as failed |
| `voss.detection.suspect_s` | `600.0` | S | how long a worker stays marked |
| `voss.keys.max_holders` | `None` | A | holder budget K per function key (D-85); axis {2, 4, 8, 16, unbounded} in R01 |
| `drain_s` | `30.0` | S | simulated time after the horizon for in-flight work |
| `decision_clock.mode` | `'modeled'` | A | modeled for simulation, measured for emulation |
| `decision_clock.cpu_scale` | `1.0` | S | emulation only |
| `decision_clock.coeffs` | `{'plan': (0.02, 5e-05), 'place': (0.0002, 2e-05), 'route'...` | pending V10 | replaced by timed policy code |
| `calibration` | `None` | M | measured bundle per experiment (G14) |
| `out_dir` | `'runs'` | A | output location |
| `label` | `''` | A | run label |
| `voss.planner.params.rho_mem` | `0.0001` | pending V5 | v1 objective weight; replaced by the V5.1 objective |
| `voss.planner.params.rho_ssd` | `2e-05` | pending V5 | v1 objective weight |
| `voss.planner.params.kappa_switch` | `0.05` | pending V5 | v1 objective weight |
| `voss.planner.params.beta_warm` | `0.05` | pending V5 | v1 objective weight |
| `voss.planner.params.gamma` | `0.5` | pending V5 | v1 snapshot value ratio |
| `voss.planner.params.kappa_dom` | `0.5` | pending V5 | failure-domain cap; becomes holders in distinct domains |
| `voss.planner.params.w_max` | `4` | S | warm sandboxes per function per worker |
| `voss.planner.params.m_base_mb` | `512.0` | pending V5 | image memory; becomes measured |
| `voss.planner.params.use_robust` | `True` | A | ablation (R06) |
| `voss.planner.params.use_exposure` | `True` | pending V4 | removed |
| `voss.planner.params.use_domain_cap` | `True` | A | ablation |
| `voss.planner.params.use_freshness` | `True` | S | skip workers whose certificate expires within the horizon |
| `voss.planner.params.exposure_weight` | `1.0` | pending V4 | removed |
| `voss.planner.params.survival_blind` | `False` | A | ablation (R06) |

## Data files (`configs/`, excluding calibration bundles and experiment specs)

Numbers inside data files carry their own `provenance` tags (`tests/unit/test_data_provenance.py`). The class here is
for the file as a whole.

| File | Class | Basis or fate |
|---|---|---|
| `configs/base.yaml` | A | defaults of every run |
| `configs/e01/base.yaml` | pending V13 | v1 emulation scenario |
| `configs/e01/i7-12700-64g/base.yaml` | pending V13 | v1 emulation scenario |
| `configs/e01/i7-12700-64g/s1_stable.yaml` | pending V13 | v1 emulation scenario |
| `configs/e01/i7-12700-64g/s2_churn.yaml` | pending V13 | v1 emulation scenario |
| `configs/e01/i7-12700-64g/s3_omit.yaml` | pending V13 | v1 emulation scenario |
| `configs/e01/i7-12700-64g/s3_omit_load.yaml` | pending V13 | v1 emulation scenario |
| `configs/e01/i7-12700-64g/s4_load.yaml` | pending V13 | v1 emulation scenario |
| `configs/e01/s1_stable.yaml` | pending V13 | v1 emulation scenario |
| `configs/e01/s2_churn.yaml` | pending V13 | v1 emulation scenario |
| `configs/e01/s3_omit.yaml` | pending V13 | v1 emulation scenario |
| `configs/e01/s3_omit_load.yaml` | pending V13 | v1 emulation scenario |
| `configs/e01/s4_load.yaml` | pending V13 | v1 emulation scenario |
| `configs/functions.yaml` | pending V1/V9 | literature placeholders (F2); replaced by measured profiles of every function |
| `configs/functions_e01.yaml` | pending V13 | v1 emulation catalogue |
| `configs/hardware/C0.yaml` | pending V9 | machine class; v2 classes are the calibrated machines |
| `configs/hardware/C1.yaml` | pending V9 | machine class; v2 classes are the calibrated machines |
| `configs/hardware/C2.yaml` | pending V9 | machine class; v2 classes are the calibrated machines |
| `configs/hardware/C3.yaml` | pending V9 | machine class; v2 classes are the calibrated machines |
| `configs/hardware/DC.yaml` | pending V9 | machine class; v2 classes are the calibrated machines |
| `configs/hardware/E0.yaml` | pending V9 | machine class; v2 classes are the calibrated machines |
| `configs/hardware/E1.yaml` | pending V9 | machine class; v2 classes are the calibrated machines |
| `configs/hardware/I7_64G.yaml` | pending V9 | machine class; v2 classes are the calibrated machines |
| `configs/regimes/adversary_all.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/regimes/adversary_collude.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/regimes/adversary_mixed.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/regimes/adversary_none.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/regimes/churn_burst.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/regimes/churn_correlated.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/regimes/churn_e01.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/regimes/churn_high.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/regimes/churn_low.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/regimes/churn_med.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/regimes/load_default.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/regimes/load_flash.yaml` | pending V9 | assumed parametric regime; replaced by traces or kept as a labelled sensitivity |
| `configs/smoke.yaml` | A | test configuration |
| `configs/substrates/appliance_tpm.yaml` | pending V4 | substrate profile; ref_* become the trusted-host baseline in V8 |
| `configs/substrates/none.yaml` | pending V4 | substrate profile; ref_* become the trusted-host baseline in V8 |
| `configs/substrates/ref_azure_like.yaml` | pending V4 | substrate profile; ref_* become the trusted-host baseline in V8 |
| `configs/substrates/ref_lambda_like.yaml` | pending V4 | substrate profile; ref_* become the trusted-host baseline in V8 |
| `configs/tenants.yaml` | pending V9 | assumed tenants; replaced by trace owners |
| `configs/tenants_e01.yaml` | pending V13 | v1 emulation tenants |
| `configs/toy.yaml` | A | test configuration |
