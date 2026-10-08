# 06 · Experiments, Metrics and Hypotheses

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
