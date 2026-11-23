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
| `scenario.warmup_s` | `14400.0` | D | = `voss.keepalive_hist.range_s` (14,400 s), the longest learning window of a compared policy (guardrail 23, D-97); every R spec sets it (`tests/unit/test_r_specs.py`) |
| `scenario.substrate_mix` | `{'appliance_tpm': 1.0}` | A | owner classes S/P/M (V3.3) |
| `scenario.machines` | required | D | calibrated fleet (V9.4, D-107; checklist 1.2): one class per measured bundle (M), weights from the BOINC host survey (T), radius 1 = one power-of-two step of the survey; the only machine path |
| `scenario.physical_frac` | `0.0` | A | share of owners without memory encryption willing to attack physically (class P, V3.3) |
| `scenario.regime` | `'churn_seti'` | T | SETI@home host availability (FTA seti09); every R spec sets the held-out split (`tests/unit/test_r_specs.py`) |
| `scenario.churn` | `{}` | A | inline overrides of the regime: every R spec sets `split: heldout`; the notice fraction `graceful_frac` is an axis {0, 0.5} (R03, `configs/regimes/churn_seti.yaml`) |
| `scenario.adversary` | `{}` | A | owner faults: fraction and behaviour (R04, R05) |
| `scenario.load` | `{'trace': 'azure2019', 'split': 'heldout'}` | T | Azure Functions 2019 arrivals (V9.1); `rate_mult` is the load axis {10.5, 21, 30} (D-99) |
| `scenario.geo` | `{'pop_trace': 'wup2025'}` | T | World Urbanization Prospects 2025 metro populations (V9.3) |
| `scenario.network` | `{'link': {'trace': 'ookla-fixed-2024q1'}}` | T | links: Ookla fixed-broadband per metro (V9.3); `route_factor` 1.654 fitted to WonderProxy pings; `c_eff` 100 km/ms (fibre) |
| `scenario.envelope` | `{}` | A | D-132: donated shares `cpu_frac` 0.75, `mem_frac` 0.6, disks 0.2, stated; R07 varies `cpu_frac` {0.5, 1.0} and `mem_frac` {0.4, 0.8}; slots capped by donated memory (D-108) |
| `scenario.execution` | `{}` | D | D-133: only overrides of the bundle's execution model (timeout_s); co-run interference is the bundle's measured table (M) and noise its measured repeat variation (D) |
| `scenario.functions` | `'functions.yaml'` | A | the function catalogue (D-119): guest memory stated; the deadline multiple and idempotent fraction are the two keys below |
| `scenario.tenants` | `'tenants.yaml'` | A | tenant template (D-125): key-service city and default budget |
| `scenario.deadline_multiple` | `5.0` | A | D-119: synchronous deadline = k x (warm run time + overhead), axis {2, 5, 10} (R07) |
| `scenario.idempotent_frac` | `1.0` | A | D-119: share of functions (name order) that may be retried, axis {0, 0.5, 1} (R07) |
| `voss.infra.orchestrator` | `'Frankfurt'` | A | provider site (stated in the paper) |
| `voss.infra.verifier` | `'Frankfurt'` | A | provider site |
| `voss.infra.registry` | `'Frankfurt'` | A | provider site |
| `voss.infra.scheduler` | `'Frankfurt'` | A | provider site of the one scheduler (D-83) |
| `voss.infra.scheduler_speed` | `1.0` | D | 1 = the provider CPU whose decision times are charged (`decision_clock.coeffs_file`, V10; `runtime/schedlib/provider_host.py`) |
| `voss.infra.routers` | `('Washington', 'Frankfurt', 'Singapore')` | A | provider front-end sites |
| `voss.router.T_dispatch` | `1.0` | S | router re-send timer |
| `voss.router.max_resends` | `3` | S | router re-sends before giving up on the scheduler |
| `voss.router.give_up_s` | `{'sync': 30.0, 'async': 300.0}` | S | router gives up after this; above every deadline |
| `voss.router.done_keep_s` | `3600.0` | D | finished invocations remembered this long (duplicate detection); 12x the async give-up, bounds memory (plan V9.5) |
| `voss.router.receipt_batch_s` | `1.0` | S | receipt batching to the DB |
| `voss.placer.sync` | `'greedy'` | A | placement algorithm (V5.2) |
| `voss.placer.async` | `'greedy'` | A | placement algorithm (V5.2) |
| `voss.placer.window_s` | `0.2` | S | batching window for asynchronous invocations |
| `voss.predictor.name` | `'blr'` | S | run-time estimator (V5.4) |
| `voss.predictor.forgetting` | `0.995` | S | run-time estimator forgetting factor |
| `voss.predictor.conformal` | `True` | S | conformal quantiles on/off |
| `voss.predictor.prior_sd` | `(0.7, 0.3, 0.5)` | S | D-122: run-time model prior standard deviations; listed, not varied (they wash out after a few observations) |
| `voss.cost.tts_cv` | `0.3` | S | D-122: spread of the time to start, `(tts_cv x tts)^2`; R07 varies {0.15, 0.6} |
| `voss.cost.overdue_frac` | `0.25` | S | D-122: extra share of its prediction an overdue job holds its slot; R07 varies {0.125, 0.5} |
| `voss.admission.enabled` | `True` | S | admission on/off |
| `voss.admission.eps` | `0.05` | S | reject when every candidate misses with probability above 1 - eps |
| `voss.admission.defer_s` | `1.0` | S | retry delay for a deferred asynchronous invocation |
| `voss.models.survival` | `'weibull'` | S | session survival estimator (V5.4) |
| `voss.verifier.valid_s` | `900.0` | A | D-120: session certificate validity; R07 varies {450, 2,700} with `reattest_every_s` |
| `voss.verifier.reattest_every_s` | `600.0` | A | D-120: re-attestation period; R07 varies {300, 1,800} with `valid_s` |
| `voss.models.omission` | `'beta_cusum'` | S | drop estimate (V5.4): `beta_cusum`; `prior_only` is the R06 ablation (D-128) |
| `voss.models.refit_s` | `60.0` | S | survival refit period |
| `voss.models.cusum_h` | `5.0` | S | change-detection threshold |
| `voss.models.omission_prior` | `(0.5, 20.0)` | S | Beta prior (a0, b0) of the drop estimate (D-111); R07 varies its strength x0.5/x2 at equal mean |
| `voss.models.omission_pessimistic` | `(2.0, 4.0)` | S | prior after a change point (D-111); R07 varies x0.5/x2 at equal mean |
| `voss.models.cusum_k` | `0.1` | S | CUSUM drift (D-111); R07 varies {0.05, 0.2} |
| `voss.planner.name` | `'hetero'` | A | VOSS's provisioning planner (D-131); the other names are baselines (V8) |
| `voss.planner.T_plan` | `30.0` | S | plan V5.3: at least the longest preparation action, default 30 s chosen on the development split; R07 varies it |
| `voss.planner.replan_tolerance` | `0.2` | S | re-plan only when inputs change by more than this |
| `voss.planner.min_rate` | `0.01` | S | functions below this request rate are not provisioned |
| `voss.planner.horizon_factor` | `2.0` | S | forecast horizon in provisioning periods |
| `voss.planner.max_parallel_prepares` | `2` | S | preparation actions per worker per round |
| `voss.planner.T_linger` | `30.0` | S | time a released worker keeps its warm sandboxes |
| `voss.planner.scenarios` | `32` | S | failure scenarios per provisioning round (hetero); the guarantee holds for the sample average |
| `voss.planner.ablate` | `()` | A | ablations of plan §11.7 (homogeneous, binary, reliability_blind) for R06 |
| `voss.planner.params` | `{}` | S | container of the `voss.planner.params.*` rows (w_max, use_freshness, survival_blind) |
| `voss.scheduler.heartbeat_s` | `2.0` | S | worker report period |
| `voss.scheduler.stale_after_s` | `7.0` | S | a worker silent this long is treated as gone |
| `voss.scheduler.max_attempts` | `3` | S | attempts per invocation |
| `voss.scheduler.retry_backoff_s` | `0.2` | S | D-116: retry delay of the retry-based detectors; R07 varies {0.1, 0.4} |
| `voss.scheduler.no_candidate_retry_s` | `0.5` | S | retry delay when no candidate exists |
| `voss.scheduler.view_refresh_s` | `0.25` | S | view cache refresh |
| `voss.worker.warm_ttl_s` | `600.0` | L | fixed keep-alive baseline timer, 10 min (Shahrad et al., ATC 2020); also an axis |
| `voss.worker.warm_eviction` | `lru` | A | warm-sandbox eviction: `lru` or `greedy_dual` (FaaSCache baseline, V8) |
| `voss.worker.m_base_mb` | `512.0` | A | D-117: image memory reserve, a stated build parameter, read by the worker and every planner; R07 varies {256, 1,024} |
| `voss.worker.sync_priority` | `True` | A | D-114: synchronous-first on for every system; off only as the R06 ablation |
| `voss.keepalive_hist.bin_s` | `60.0` | L | Shahrad et al. ATC 2020: 1-minute bins |
| `voss.keepalive_hist.range_s` | `14400.0` | L | Shahrad et al. ATC 2020: 4-hour range |
| `voss.keepalive_hist.head_pct` | `5.0` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.tail_pct` | `99.0` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.margin` | `0.1` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.min_samples` | `10` | S | D-123: the paper gives no minimum; a stated deviation (`configs/baselines.yaml`) |
| `voss.keepalive_hist.cv_min` | `2.0` | L | Shahrad et al. ATC 2020 |
| `voss.keepalive_hist.oob_max` | `0.2` | S | D-123: the paper gives no fallback threshold; a stated deviation (`configs/baselines.yaml`) |
| `voss.keepalive_hist.fallback_ttl_s` | `600.0` | D | = `voss.worker.warm_ttl_s`: out-of-range idle times fall back to the fixed timer in place of the paper's ARIMA forecast (deviation listed in `configs/baselines.yaml`) |
| `voss.cache.value` | `'gdsf'` | S | disk cache value policy |
| `voss.cache.hdd_tier` | `True` | S | hard-disk tier on/off |
| `voss.audit.p` | `0.0` | A | audit probability per idempotent invocation (V7.3; swept in R05) |
| `voss.detection.detector` | `voss` | A | `fixed`, `consecutive`, `hedged`, `voss` (plan V7.2); `voss_no_backup` is the R06 ablation (D-128) |
| `voss.detection.quantile` | `0.95` | S | voss timer: predicted completion quantile, no floor (plan V7.1, F5) |
| `voss.detection.hedge_min_samples` | `20` | S | D-122: hedged requests use the deadline until this many latencies are observed; listed, not varied (the baseline's warm-up) |
| `voss.detection.probe_timeout_s` | `2.0` | S | an unanswered probe is drop-estimate evidence; it does not end the attempt |
| `voss.detection.consecutive_streak` | `5` | L | Envoy outlier detection `consecutive_5xx` (default 5; Envoy proto, checked at the freeze) |
| `voss.detection.consecutive_eject_s` | `30.0` | L | Envoy outlier detection `base_ejection_time` (default 30 s; Envoy proto, checked at the freeze) |
| `voss.detection.suspect_streak` | `2` | S | consecutive failures before a worker is marked as failed |
| `voss.detection.suspect_s` | `600.0` | S | how long a worker stays marked |
| `voss.keys.max_holders` | `None` | A | holder budget K per function key (D-85); axis {2, 4, 8, 16, unbounded} in R01 |
| `voss.keys.rotate_s` | `None` | A | key rotation period R (D-85); axis {none, 1 h, 24 h} in R07 |
| `drain_s` | `30.0` | S | simulated time after the horizon for in-flight work |
| `decision_clock.mode` | `'modeled'` | A | modeled for simulation, measured for emulation |
| `decision_clock.cpu_scale` | `1.0` | S | emulation only |
| `decision_clock.coeffs` | `{}` | D | empty unless a unit test passes its own; every run sets `coeffs_file` (V10; checklist 2.11) |
| `decision_clock.coeffs_file` | `''` | M | measured provider coefficients (`configs/calibration/provider/<cpu>/decision.yaml`, V10) |
| `calibration` | `'configs/calibration/measured/node02-i7-12700-64g-nvme_nvme'` | M | the fleet's reference machine (D-107, D-130); every experiment sets one of the fleet's measured bundles (guardrail 28) |
| `out_dir` | `'runs'` | A | output location |
| `label` | `''` | A | run label |
| `voss.planner.params.w_max` | `4` | S | warm sandboxes per function per worker |
| `voss.planner.params.use_freshness` | `True` | S | skip workers whose certificate expires within the horizon |
| `voss.planner.params.survival_blind` | `False` | A | ablation (R06) |

## Derived per-worker quantities

| Quantity | Class | Basis |
|---|---|---|
| slots of a calibrated-fleet worker | D | min(floor(`cpu_frac` x threads), floor(donated memory / largest function `mem_mb`)), at least 1 (D-108); node04: 6 -> 4 |

## Constants in code that are not configuration keys (guardrail 27)

None at the freeze: the four v1 code constants became keys in D-122 (rows above).

**Unverified seeds for the paper agent (one note, not a citation).** The TLS CPU costs
(`voss.world.network.tls_msg_cpu_s`, `tls_handshake_cpu_s`) and the in-region data-centre last mile
(`voss.world.reference_cloud.DC_LAST_MILE_S`) have no measured value in the bundles. They are stated as assumed in the
methodology or replaced by the `tls` calibration suite; the paper must not present them as measured.

## Data files (`configs/`, excluding calibration bundles and experiment specs)

Numbers inside data files carry their own `provenance` tags (`tests/unit/test_data_provenance.py`). The class here is
for the file as a whole.

| File | Class | Basis or fate |
|---|---|---|
| `configs/base.yaml` | A | defaults of every run |
| `configs/request_bytes.yaml` | D | bytes a client sends per measured input size of each guest function (D-106) |
| `configs/functions.yaml` | L | function catalogue (D-119): guest memory stated (A); run times and start-up are overridden per machine class from the bundles (M) |
| `configs/regimes/adversary_all.yaml` | A | D-121: owner behaviour parameters, axes of the threat, stated with R04/R05 |
| `configs/regimes/adversary_mixed.yaml` | A | D-121: owner behaviour parameters, axes of the threat, stated with R04/R05 |
| `configs/regimes/adversary_none.yaml` | A | D-121: owner behaviour parameters, axes of the threat, stated with R04/R05 |
| `configs/regimes/churn_seti.yaml` | T | SETI@home host availability (FTA seti09), one host's week per worker (V9.2); `graceful_frac` axis; no synthetic tiers or shocks (checklist 2.9) |
| `configs/machines_mix.yaml` | T | survey mapping of the fleet overlay (D-107), generated by `experiments.analysis.fleet_mix` from the gitignored survey; the paper reads this file |
| `configs/smoke.yaml` | A | test configuration |
| `configs/substrates/appliance_tpm.yaml` | M | doc 04 §3: session steps measured (bundle), message sizes derived from the quote/certificate formats; certificate timings are the verifier's keys (D-120) |
| `configs/baselines.yaml` | D | systems compared: source, overrides, deviations (V8) |
| `configs/traces/wup2025/provenance.yaml` | T | trace wup2025, release data-wup2025-1085a0d3 (plan V9) |
| `configs/traces/boinc-rosetta/provenance.yaml` | T | trace boinc-rosetta, release data-boinc-rosetta-1085a0d3 (plan V9) |
| `configs/traces/boinc-milkyway/provenance.yaml` | T | trace boinc-milkyway, release data-boinc-milkyway-1085a0d3 (plan V9) |
| `configs/traces/seti09/provenance.yaml` | T | trace seti09, release data-seti09-79bec54d (plan V9) |
| `configs/traces/azure2019/provenance.yaml` | T | Azure Functions 2019 sample, release data-azure2019-*: functions and per-minute arrivals per split (V9.1) |
| `configs/traces/ookla-fixed-2024q1/provenance.yaml` | T | Ookla fixed-broadband links per metro, release data-ookla-fixed-2024q1-* (V9.3) |
| `configs/traces/wonderproxy-2020-07/provenance.yaml` | T | WonderProxy all-pairs pings: fitted route factor 1.654 (V9.3) |
| `configs/substrates/trusted_hosts.yaml` | M | appliance_tpm ladder without attestation or key release (V8); certificate timings are the verifier's keys (D-120) |
| `configs/references/trusted_hosts.yaml` | A | trusted always-on hosts: the reference machine (node02 NVMe), host count from the pool's slots divided among the router metros (D-124) |
| `configs/tenants.yaml` | A | tenant template (D-125): key-service city and default holder budget |
| `configs/toy.yaml` | A | test configuration |
