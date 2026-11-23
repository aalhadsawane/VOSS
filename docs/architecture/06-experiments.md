# 06 · Experiments, Metrics and Hypotheses

> **v2 status.** §3 holds the v2 hypotheses (plan V12.1). Every v1 experiment and baseline listed elsewhere here is retired; the mapping to v2 experiments is in `docs/REVISION_PLAN.md` §9. Rewritten in phase V8, V11, V12 of `docs/REVISION_PLAN.md`. Until then, where this document and the
> v2 decisions (`docs/DECISIONS.md` D-81 onward) disagree, the decisions win.

## 1. Pipeline

```
configs/experiments/Exx.yaml ──▶ experiments/runner.py ──▶ runs/<exp>/<run_hash>/{manifest.json, invocations.parquet,
 (base + sweep grid + seeds        (one process per run,           events.parquet, samples.parquet, plans.parquet,
  + systems on same scenario)       idempotent)                    solver.parquet, cache.parquet, messages.parquet}
runs/… ──▶ experiments/analysis/*.py (bootstrap CIs over seeds) ──▶ figures/Exx_*.pdf, tables/*.csv  (make figs / make paper)
```

- ≥ 10 seeds for headline results (≥ 5 for pilots); systems are compared paired, on the same scenario hash.
- Shared cells across specs are seeded from R01's release before the later spec runs (`docs/validation/HELDOUT_RUNBOOK.md`);
  the runner is idempotent per spec directory but does not deduplicate across specs.
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

## 3. v2 hypotheses (plan V12.1; written before any held-out run)

Written from the design (plan §2, §11, V7) before the held-out sweep, on the development code; no held-out result
exists when they are committed, and the development runs (`D01`-`D03`, `docs/validation/development-log.md`) are not
evidence for or against them (guardrail 31). They are not changed after the first held-out run starts. The R01-R09
specs (`configs/experiments/R*.yaml`, held-out split, calibrated fleet, seeds 1-10) carry the grids;
`tests/unit/test_r_specs.py` checks them against plan V12.2.

**Primary metric** (D-88, guardrail 19): *deadline met*, the share of synchronous invocations arriving after the
warm-up that return a correct result within their deadline; lost, late and wrong (forged) answers are misses
(`experiments/analysis/metrics.py` `deadline_met`). Latency percentiles include lost invocations, censored at the
deadline.

**Systems.** "Every baseline" in H1 and H2 is every provisioning baseline of `configs/baselines.yaml` that runs as a
volunteer system: `on_demand`, `fixed_keepalive`, `hybrid_histogram`, `prereleased_keys`, `eviction_aware`, `kpa`,
`greedy_dual`. Two entries are not baselines of these hypotheses: `trusted_hosts` is the upper bound (hosts that never
leave and need no attestation, R09), and `exact_program` is an offline optimality check that is not run as a system
(the D01 header gives its cost). If a baseline is added to or removed from `configs/baselines.yaml` before the
sweep, this list changes with it, in the same commit.

**Verdict rule** (plan V12.1). Every comparison is paired by seed: the same scenario hash, one difference per seed,
mean over the 10 seeds, 95% bootstrap interval of that mean (10,000 resamples of seeds). H1-H3 form one family with
Holm's correction over every comparison listed below (120 in all); an interval is read at its Holm-adjusted level.
*Supported*: the adjusted interval excludes zero in the stated direction. *Refuted*: it excludes zero in the opposite
direction. *Inconclusive*: otherwise. Every comparison is reported, whichever way it falls (guardrail 20). H4 and H5
are outside the family.

| ID | Claim | Metric and experiment | Comparisons | Refuted by |
|---|---|---|---|---|
| **H1** | At equal holder budget `K`, VOSS meets more synchronous deadlines than every baseline. | Deadline met; R01 (`K` {2, 4, 8, 16, unbounded} × load {2.2, 4.4, 6.3} (D-138)). | `voss − b` for each of the 7 baselines `b` at each of the 15 cells: 105. H1 holds at a `K` if it is supported for every baseline at every load at that `K`. | An adjusted interval entirely below zero for any baseline at any cell (that baseline meets more deadlines there). |
| **H2** | VOSS reaches 95% deadlines met with fewer key holders than every baseline. | `K95(s)` = the smallest `K` of the R01 axis at which system `s` meets 95%: the lower end of the 95% bootstrap interval of its mean deadline met is at least 0.95. Unbounded counts as larger than 16; a system that does not reach 95% at any `K` has `K95` = "not reached", larger than every `K`. Per load level of R01. Secondary (no verdict): mean concurrent holders at that cell. | For each baseline `b`, at the central load (rate_mult 4.4): `K95(voss) < K95(b)`, tested as the paired difference `voss − b` at `K = K95(voss)` (supported if the adjusted interval is above zero and the upper end of `b`'s own interval is below 0.95): 7. | `K95(b) ≤ K95(voss)` for any baseline, or VOSS not reaching 95% at any `K` (then plan V12.4's last rows apply). |
| **H3** | Under 10% and 20% dropping owners, the `voss` detector meets more deadlines than `consecutive` (Envoy outlier ejection). | Deadline met; R04 (dropping owners {0, 10, 20%} × strategy × detector, VOSS provisioning for every detector). | `voss − consecutive` at 10% and 20% for each of the 4 strategies (black hole, random omission, on/off, throttle): 8. The 0% cells are the no-fault control, reported, not tested. `fixed_timeout` and `hedged` are reported in the same figure without a verdict. | An adjusted interval entirely below zero at any tested cell. |
| **H4** | With audit rate `p`, a forging worker is banned after the number of forged results predicted by `1 − (1 − p)^n`. Holds for owner class P only (only class-P owners can forge; guardrail 24). | `n` = forged results of idempotent invocations a forging worker returned before its ban, censored at its session end; R05 (class-P share {5, 20%} × `forge_p` {0.5, 1} × `p` {0, 1, 5%}). Secondary: forged results accepted, honest workers banned, audit overhead (extra attempts). Not a deadline-met claim; deadline met is reported with forged answers counted as misses. | Per cell with `p` > 0: the Kaplan-Meier estimate of `P(banned by n)` against `1 − (1 − p)^n`, pooled over seeds, 95% confidence band. At `p` = 0 no worker may be banned. | The prediction lies outside the band at any `n` up to the predicted 90th percentile (`ln 0.1 / ln(1 − p)`), in any cell; or any ban at `p` = 0; or any honest worker banned. |
| **H5** | There is a pool size and load below which no policy meets 95% of deadlines. Descriptive: always reported (plan V12.4). | Deadline met; R03 (pool {100, 300, 500} × load {2.2, 4.4, 6.3} (D-138) × notice fraction {0, 0.5}, every system of R01 and the upper bound). A cell is *met* by a system if the lower end of its 95% bootstrap interval is at least 0.95. | None tested; the result is the region map per system and its boundary. | Some system meets 95% in every cell of the R03 grid (the boundary is then outside the grid, and the paper says so with the grid's limits). |

**What each hypothesis does not cover.** H1 and H2 hold for the traced load and sessions and the calibrated fleet of
the held-out split; R07 reports how they move with the stated assumptions. H3 is for the four dropping strategies of
R04 with the parameters stated in its header. H4 assumes the audit holder is honest or of a different forger
(digests of different forgers differ); with colluding forgers it is an upper bound on detection. R02 (mechanism), R06
(ablation), R07 (sensitivity), R08 (scale) and R09 (upper bound) are descriptive and carry no hypothesis.

| Spec | Question | Hypothesis |
|---|---|---|
| R01 | deadlines met against key holders | H1, H2 |
| R02 | why baselines miss (R01 central cell, time series) | — |
| R03 | operating region | H5 |
| R04 | owners who drop work | H3 |
| R05 | owners who forge (class P) | H4 |
| R06 | ablation | — |
| R07 | sensitivity to assumptions | — |
| R08 | one scheduler's limit | — |
| R09 | trusted always-on hosts (upper bound) | — |

The v1 research questions and hypotheses H1-H18 of earlier versions of this document are retired (plan §9); their IDs
are not reused for anything but the five above.

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
