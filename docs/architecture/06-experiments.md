# 06 · Experiments, Metrics and Hypotheses

> **v2 status.** Every v1 experiment, hypothesis and baseline listed here is retired; the mapping to v2 experiments is in `docs/REVISION_PLAN.md` §9. Rewritten in phase V8, V11, V12 of `docs/REVISION_PLAN.md`. Until then, where this document and the
> v2 decisions (`docs/DECISIONS.md` D-81 onward) disagree, the decisions win.

## 1. Pipeline

```
configs/experiments/Exx.yaml ──▶ experiments/runner.py ──▶ runs/<exp>/<run_hash>/{manifest.json, invocations.parquet,
 (base + sweep grid + seeds        (one process per run,           events.parquet, samples.parquet, plans.parquet,
  + systems on same scenario)       idempotent)                    solver.parquet, cache.parquet, messages.parquet}
runs/… ──▶ experiments/analysis/*.py (bootstrap CIs over seeds) ──▶ figures/Exx_*.pdf, tables/*.csv  (make figs / make paper)
```

- ≥ 10 seeds for headline results (≥ 5 for pilots); systems are compared paired, on the same scenario hash.
- Figures are registered functions of run directories.

## 2. Logged tables (`metrics/schema.py`)

| Table | Row per | Key fields |
|---|---|---|
| `invocations` | Invocation (final) | Ids, tenant, cluster, worker(s), hedged, attempts, outcome, **components** `route, batch_wait, decide, wait, trust, startup, net_in, exec, net_out, retry`, `start_level`, `tier`, `trust_cold`, `exposure_increment` |
| `events` | State change | Session start/end, attestation (ok/fail/expiry), suspicion, change point, succession, spillover, plan change |
| `plans` | Planner run | Cluster, `T_solve`, status, gap, objective terms (coverage shortfall, donor, exposure, churn), #trust-warm pairs, robust slack |
| `solver` | Placer/planner call | Kind, size, build_s, solve_wall_s, status |
| `cache` | Periodic + per transition | Hits per level/tier, bytes per tier, evictions, promotions, P2P bytes |
| `samples` | Periodic | Per-cluster load, SLO health, attested workers, donor memory/SSD/HDD, exposure per tenant |
| `messages` | Per kind per interval | Count, bytes, drops |
| `receipts` | Copy of the work log | For accounting experiments |

## 3. Research questions and hypotheses

| RQ | Question | Hypotheses |
|---|---|---|
| RQ1 Viability | When can attested volunteer FaaS meet a latency/success SLO? (substrate × churn × α × load × N) | Regime map (E20) |
| RQ2 Trust planning | Does slow-loop trust and warm-state planning beat reactive and keep-alive approaches? | **H1:** the MILP planner cuts P99 vs `none` and `keepalive_ttl` at equal donor memory; the gain shrinks as sessions shorten |
| RQ3 Robustness | What does f-robustness buy and cost under adversaries? | **H2:** with α adversaries, f-robust plans keep success ≥ target where non-robust plans collapse; the latency/memory price grows with f |
| RQ4 Exposure | What is the latency–exposure trade-off? | **H3:** the Pareto front has a knee; moderate exposure budgets lose little latency |
| RQ5 Malice ≈ churn | Does attestation + progress detection make malicious hosts look like churn? | **H4:** P99 under α black-holing hosts ≈ P99 under churn with an equal effective failure rate; heartbeat-only detection is much worse (H-FT1) |
| RQ6 Cold starts | How do substrates compare on cold start and trust establishment? | **H5:** appliance warm/snapshot starts ≈ Firecracker; per-session trust costs dominate; CVM classes are 10–100× slower to establish |
| RQ7 Caching | How much do tiered caches, P2P and value-based eviction help? | **H6:** SSD snapshot + HDD cold tier + P2P cut L0/L1 starts under churn; value-density beats LRU in small clusters |
| RQ8 Geo-clustering | Locality gain and optimality loss | **H7:** geo clusters reduce P50/P99 vs global at bounded gap |
| RQ9 Optimization | Where is integer programming needed, and what does it cost? | **H8:** the planner MILP beats greedy by ≥ 5% P99 in adversarial/high-churn regimes; ILP-in-fast-loop is never worth it (kill criterion, doc 03 §8) |
| RQ10 Succession | Failover cost without volunteer consensus | H-FT2 |
| RQ11 Hedging | Waste vs P99 recovered | H-FT3 |
| RQ12 Prediction | Predictor and scalarization; new workers and functions | **H9:** distribution-aware costs beat expectation-only on P99 as churn rises |
| RQ13 Accounting | Cost and completeness of attested receipts | **H10:** off the critical path, negligible latency |
| RQ14 Scalability | Workers, clusters, concurrency | — |
| RQ15 Commercial | vs Lambda/Azure-like reference (latency, success, cost) | — |
| RQ16 Simple wins | Homogeneous, stable, benign: do simple baselines match VOSS? | **H11:** yes (report it) |

## 4. Systems and baselines (registered names)

| Group | Names |
|---|---|
| VOSS | `voss_full` |
| Planning | `plan_none`, `keepalive_ttl`, `plan_greedy`, `plan_milp`, `milp_no_robust`, `milp_no_exposure`, `milp_no_domain`, `plan_oracle` (analysis only) |
| Placement | `greedy`, `flow`, `ilp_window`, `random`, `round_robin`, `least_loaded`, `jsq`, `po2`, `warm_first`, `latency_aware`, `reliability_aware`, `k8s_*`, `nearest_edge`, `hash_locality` |
| Routing | `score`, `nearest`, `least_loaded`, `po2_nearby`, `warm_aware` |
| Detection | `progress` vs `heartbeat_only` |
| Hedging | `off`, `always`, `risk_proportional` |
| Cache | `gdsf` vs `lru`; P2P on/off; HDD tier on/off |
| Clustering | `none_global`, `static_regions`, `static_kmeans`, `dynamic` |
| Substrates | `none`, `appliance_tpm`, `drtm_hv`, `cvm_snp`, `coco_pool` |
| Reference | `ref_lambda_like`, `ref_azure_like` |

**Ablations (MUST):** remove each of geo-clustering, dynamic orchestration, planning, robustness, exposure, hedging,
progress detection, prediction (→ instantaneous), lifecycle/cache awareness, heterogeneity, the HDD tier, P2P.

## 5. Experiment catalogue

| ID | Purpose | Sweeps | Primary outputs | RQ | Phase |
|---|---|---|---|---|---|
| E01 | Simulator validation vs single-box emulation | Small scenarios | CDF error of end-to-end and components | — | P9 |
| **E-CS1** | **Cold start and trust establishment across sandbox classes** (user request) | Class ∈ {firecracker, qemu_vm, kata (measured); appliance L0–L3 + session boot (measured); cvm_snp, coco_pool, severifast-like, qemu_snp_ovmf, qemu_tdx (literature ranges)}; per SeBS function | Start-up latency per level, trust establishment, memory per instance | RQ6 | P9 |
| E02 | Cluster size × planner/placer time × end-to-end latency | N, `T_plan`, hot set size, `T_solve`, K | Solve-time distribution, decision share, knee | RQ9 | P4 |
| E03 | Predictors × scalarizations | Predictor, scalarizer, churn | Accuracy, calibration, P99, regret | RQ12 | P3 |
| E04 | Planner comparison | none / keepalive / greedy / MILP / variants | P99, success, donor memory, exposure | RQ2, RQ9 | P4 |
| E05 | Geo vs global | Clustering, dispersion | P50/P99, optimality gap | RQ8 | P5 |
| E06 | Dynamic vs static clusters | Churn, skew, diurnal | P99, migrations | RQ8 | P5 |
| E07 | Routing and priced spillover | Router, flash crowds | P99, spillover, exposure | RQ8 | P5 |
| E08 | Robustness vs adversaries | α, strategy mix, f | Success, P99, waste | RQ3, RQ5 | P6 |
| E09 | Caching | Tiers, budgets, P2P, eviction, version churn | Level shares, hit ratios, P99, donor bytes | RQ7 | P4 |
| E10 | Homogeneous benign null | Heterogeneity, churn off | Where simple wins | RQ16 | P5 |
| E11 | Error injection and staleness | Prediction noise, heartbeat period | Robustness curves | RQ12 | P6 |
| E12 | Reputation dynamics | Long horizon, on-off identities | Starvation, concentration, Jain | — | P7 |
| E13 | Accounting | Receipt volume, verification CPU, settlement period | Overhead, completeness | RQ13 | P7 |
| E14 | Donation sessions | Session length, tier mix, graceful fraction, fake drains | Viability, P99 | RQ1 | P6 |
| E15 | Scheduler faults | Crash, black-hole, partition, slow scheduler | Detection time, failover, P99 timeline | RQ10 | P6 |
| E16 | Hedging | θ, budget, α | Waste vs P99 | RQ11 | P6 |
| E17 | Commercial comparison | Workload, load | Latency, success, cost per M | RQ15 | P8 |
| E18 | Scalability | 10 → 10⁵ workers | Overheads | RQ14 | P8 |
| E19 | Ablations | Each switch | Bars with CIs, tornado | all | P8 |
| **E20** | **Viability map** | substrate × churn × α × load × N | Regime maps vs best baseline | RQ1 | P10 |
| **E23** | **Latency × exposure × robustness Pareto** | σ, `λ_exposure`, f | Fronts per tenant class | RQ3, RQ4 | P4–P6 |

**Pilot order:** E-CS1 (measured part) → E04 → E08 → E09 → E23 → the rest.

## 6. Statistical protocol

- Per-run percentiles first, then mean ± 95% bootstrap CI across seeds. Never pool-then-percentile alone.
- Paired comparisons on the same scenario hash.
- **Literature-only parameters** (CVM classes) are swept over their ranges. Every headline claim is labeled robust or
  "flips at X".
- Regimes where baselines win are reported.

## 7. Validation and calibration

See doc 10:
- measured distributions from the i7 node;
- the single-box emulation testbed;
- one validation note per model in `docs/validation/` (observation → parameter → model → error).

## 8. Round 4 (pre-registered)

Written before any E04b or E25 run (specs `configs/experiments/E04b.yaml`, `E25.yaml`; design: `docs/PLAN-ROUND4.md` §2b-2c,
`docs/proposals/round4-review.md` §4). Supersedes the unregistered H12-H14 of the plan, which are restated here.

**Design.** 200 workers, 10 inv/s, horizon 1800 s, arrivals before 300 s excluded from latency metrics (warm-up). All
systems use the corrected request placement (`voss.cost.wait_model=per_worker`, `voss.worker.sync_priority=true`, D-77)
except the continuity row `plan_greedy_oldwait`, which only bridges to E04 and enters no test. E04b: regimes `churn_med`
and `churn_high`, seeds 1-20 (`plan_milp` 1-10), systems `plan_none`, `keepalive_ttl`, `keepalive_inf`, `hist_prewarm`,
`provisioned_keys`, `plan_greedy`, `plan_milp`, `erlang_greedy`, `erlang_dpp`. E25: `churn_med` with every tier's session
length rescaled to 0.25, 1 and 4 times the mean, idle and dedicated Weibull shape 0.6 and 1.0, seeds 1-10, systems
`keepalive_inf`, `hist_prewarm`, `provisioned_keys`, `plan_greedy`, `plan_greedy_blind` (greedy with
`voss.planner.params.survival_blind=true`), `erlang_greedy`.

**Definitions.** Primary metric: per-run P99 of synchronous end-to-end latency (successful synchronous requests), paired by
seed (same scenario hash), per regime. Ratio `r = P99(candidate) / P99(reference)`; the estimate is the mean over seeds of
per-seed ratios, with a paired bootstrap 95% CI (10,000 resamples of seeds) and, as a robustness check, the median ratio and
a Wilcoxon signed-rank test. "Best single loop" in a regime is the system among `keepalive_ttl`, `keepalive_inf`,
`hist_prewarm` with the lowest mean P99 in that regime, chosen on the test seeds themselves (this favours the baseline, so
it is conservative for H12). Warm memory = `warm_mb`; exposure = the logged time-average `exposure`. Secondary metrics
(reported, no verdicts): mean synchronous latency, `met`, `success`, trust-cold share, `waste`.

**Verdict rule** (as in §6, extended): *supported* if the CI of the effect lies entirely on the claimed side of the
threshold (for superiority hypotheses: upper limit of `r` below the stated bound; for non-inferiority: upper limit of `r`
below the margin) and the direction holds for the median ratio; *weak* if the point estimate meets the threshold but the CI
includes it; *inconclusive* if the CI contains both the threshold and no effect and the width exceeds the threshold
margin; *refuted* if the CI lies entirely on the wrong side of the threshold. H12-H15 are one family: Holm correction
over their primary comparisons (each comparison counts per regime; corrected level 0.05, CIs widened to the
Holm-adjusted level before applying the rule). H16 is a separate family (shape of a curve) and gets descriptive CIs only.
Results are reported whichever way they fall; regimes where a baseline wins are reported.

| ID | Hypothesis | Comparison and threshold |
|---|---|---|
| **H12** | The default planner (`plan_greedy`) beats the best single loop. | `r = P99(plan_greedy)/P99(best single loop) <= 0.95`, per regime (churn_med, churn_high), E04b. Holm. |
| **H13** | `erlang_greedy` is non-inferior to `plan_greedy` (the adoption rule for the default). | `r = P99(erlang_greedy)/P99(plan_greedy) <= 1.05` at churn_med and `<= 1.10` at churn_high, **and** mean `warm_mb` and mean `exposure` of `erlang_greedy` not above `plan_greedy`'s (paired CI upper limit of the difference `<= 0`; a 5% tolerance on each counts as "no more"). Supported only if all three hold. Superiority (`r <= 0.95`) is a secondary, expected-inconclusive question. |
| **H14** | `erlang_dpp` respects its exposure budget at no latency cost relative to `erlang_greedy`. | (a) per-tenant time-average exposure within the budget `PlanParams.e_budget` (1.5, plus 10% tolerance); (b) `r = P99(erlang_dpp)/P99(erlang_greedy) <= 1.05`, per regime. Holm over (b). |
| **H15** | Planning ahead beats merely holding keys early: `plan_greedy` vs `provisioned_keys` (same holder count per tenant from greedy, workers chosen by reliability only, no robust coverage, no warm-state planning beyond the worker TTL). | `r = P99(plan_greedy)/P99(provisioned_keys) <= 0.95`, per regime. If `r` is within `[0.95, 1.05]` with a CI inside it, the verdict is "no difference" and the planner's gain is attributed to holding keys on enough reliable workers. Holm. |
| **H16** | In E25, the planner's advantage over the best single loop is an inverted U in mean session length, and depends on survival information. | (a) Advantage `A(M, k) = 1 - P99(plan_greedy)/P99(best single loop)` at each (M, k) (best single loop chosen per cell among `keepalive_inf`, `hist_prewarm`): supported if `A(1) > A(0.25)` and `A(1) > A(4)` at shape 0.6 or at shape 1.0 with paired CIs of both differences excluding 0; weak if only the point estimates order so; refuted if `A` is monotone with CIs excluding 0 on both steps. (b) Survival dependence: `B(M, k) = P99(plan_greedy_blind)/P99(plan_greedy) - 1`; supported if `B > 0` with CI excluding 0 at shape 0.6 and `B` at shape 0.6 exceeds `B` at shape 1.0 (a falling hazard is what survival information exploits); weak if only the point estimates; refuted if `B <= 0` with the CI excluding 0. |

### 8.1 Capacity-model sensitivity (pre-registered before any run; D-80)

The planner's lead in E04b is a queueing effect on the few workers that hold a tenant's key (`docs/validation/E04-tail.md`),
so it depends on how many invocations a worker runs at once and on whether running work is time-shared. Two assumptions
fix that in the simulator and are tested here, both on the E04b scenario at `churn_med`, E04b seeds (20), systems
`plan_greedy`, `keepalive_ttl` and `provisioned_keys`, corrected placement as in E04b, paired by seed. In both, the
comparison is `r = P99(plan_greedy)/P99(keepalive_ttl)`; `keepalive_ttl` stands for the best single loop (in E04b its
P99 is within noise of `keepalive_inf`, the other candidate, so the claim is not weaker).

- **E26a (H17), donated CPU share.** `scenario.envelope.cpu_frac` ∈ {0.5, 0.75, 1.0} (0.75 reuses E04b if the config
  hashes match). Slots per worker are `max(1, floor(cpu_frac × cores))`: C0 10/15/20, C1 2/3/4, C2 4/6/8, C3 2/3/4. The
  memory invariant of doc 02 §4 holds for all three values on C0-C3 (the guard refuses E0 at 1.0; E0 is not used).
- **E26b (H18), CPU overcommit with time-sharing.** New parameters, defaults leaving every existing result and hash
  unchanged: `scenario.envelope.cpu_overcommit` ρ (default 1) and the run-time factor `max(1, busy / (cpu_frac × cores))`
  applied at the start of an invocation (static, like the existing interference term) only when ρ > 1. The concurrency
  limit is `min(floor(ρ × cpu_frac × cores), floor(mem_mb / max function mem_mb))`, so memory still bounds
  running work (this is the worst-case form of memory admission; for ρ = 1 it equals today's `slots`). ρ ∈ {1, 2, 4} at
  `cpu_frac = 0.75`. Effective limits: C3 3/4/4, C1 3/6/9, C2 6/12/19, C0 15/30/60. Time-sharing lets a short
  synchronous job start next to a long asynchronous one at the price of a slower run, which is what an overcommitted host
  does; full processor sharing (re-timing running work as others start and finish) is not modelled (ROADMAP).

| ID | Hypothesis | Comparison and threshold |
|---|---|---|
| **H17** | The planner's P99 lead over the best single loop does not depend on the assumed donated CPU share. | `r` at `cpu_frac` 0.5 and 1.0: supported if the upper limit of the 95% CI of `r` is `<= 0.95` at both; weak if both point estimates are `<= 0.95` but a CI includes 0.95; refuted if at either value the CI lies entirely above 0.95. Holm over the two comparisons. Secondary, descriptive: the lead at 0.75, exposure ratio planner/single loop, holders per tenant. |
| **H18** | The planner's lead survives CPU overcommit with time-sharing. | `r` at ρ = 2 and ρ = 4: same verdict rule and Holm correction as H17. Secondary, descriptive: share of synchronous invocations that wait more than 1 s for a slot, per system and ρ; warm memory; exposure. |

Stated expectation, written before the runs: the lead shrinks as slots per worker rise (H17 at 1.0) and as work is
time-shared (H18), because both shorten the queue behind long asynchronous jobs; we do not know whether it falls below
5%. Results are reported whichever way they fall. If H18 is refuted, the paper states that the lead holds for
run-to-completion workers with a concurrency limit and not for time-shared hosts, in the abstract, results and
limitations; defaults and the planner are not changed on this evidence alone.

**Limits stated in advance.** Ten seeds (E25, `plan_milp`) and 20 seeds (E04b) give limited power against heavy-tailed
single-loop P99 (the E04 seeds 2, 8, 10 episodes, `docs/validation/E04-tail.md`); an inconclusive verdict is reported as
such and does not change the default planner. The decision rule of `docs/PLAN-ROUND4.md` §2b applies: if H13 is supported,
`erlang_greedy` becomes the default and the inheriting experiments are rerun; otherwise greedy stays. Measured solve time is not
charged to the simulated clock in E04b (greedy-family solves take milliseconds against a 30 s planning period; the MILP
keeps its configured `T_solve`); this is stated in the paper (C-16 remains open for the MILP).
