# 03 · Scheduling Design (contributions C2, C3, C4)

All policies here are **pure** (live in `voss/policy`), take views/summaries/predictions and return decisions.
The runtime actors (`Router`, `SchedulerRole`, `Orchestrator`) call them and apply the result after the
decision latency.

## 1. Three decision levels

| Level | Cadence | Input (stale) | Output |
|---|---|---|---|
| Orchestrator | every `T_orch` (e.g., 30 s) + event triggers | `ClusterSummary` per cluster, worker coordinates, drain notices, demand forecast | `MoveOp`s: move worker, split, merge |
| Router | per request | `ClusterSummary[]` (load, warm-fn sets, SLO health, predicted completion) + origin RTT | cluster id (+ spillover) |
| Cluster scheduler | per invocation (fast path) or per window | `ClusterView` + predictions + reputation | placements, lifecycle actions, retries |

## 2. Orchestrator: cluster arrangement (C2)

The orchestrator is provider-run and assumed reliable (07 §1). Its cluster state lives in the cloud operational DB (07 §2).

**State:** membership map `worker → cluster`, per-cluster medoid (RTT space).

**Initial clustering:** (also builds each cluster's scheduler succession list, 07 §4.2); k-medoids on worker RTT embedding (lat/lon + last-mile), `k = ceil(N / N_target)`,
`N_target` from the §8.6 knee (config).

**Triggers (all rule-based, each individually switchable for ablation):**

| Trigger | Condition | Action |
|---|---|---|
| Size floor | `size(C) < N_min` (live workers) | Borrow nearest border workers from the largest neighbour; else merge |
| Size ceiling | `size(C) > N_max` (ILP bound) | Split by 2-medoids |
| SLO health | EWMA(miss rate) > θ for ≥ `m` periods | Borrow from neighbours with headroom |
| Demand imbalance | Utilization gap between neighbours > δ | Lend workers to the busy one |
| Diurnal/forecast | Forecast demand next hour (EWMA of same-hour history) exceeds capacity | Pre-move workers |
| Drain notice | Worker announces departure | Rebalance before it leaves |
| Scheduler loss | No scheduler for `T_orphan` and no eligible worker to promote | Reassign its workers to neighbors, router spillover (07 §4.3) |

**Stability:** per-worker cooldown (`min_dwell`), hysteresis deadband on thresholds, max moves per period, and a
**migration cost** (moved worker loses warm state in old cluster; image cache relevance) subtracted from benefit. Worker
chosen to move = border worker (min RTT-to-target minus RTT-to-home) with lowest warm-state value.
`static_regions`, `static_kmeans`, `random_partition` baselines use the same membership structure with the
orchestrator disabled or replaced.

## 3. Global router (orchestrator tier)

Routers are the orchestrator tier's front door: stateless apart from a pending-invocation table, provider-hosted.

Chooses cluster per request using only `ClusterSummary` (updated every `T_sum`, e.g., 1–5 s):

```
score(c) = rtt(origin, c) + predicted_cluster_completion(c, fn) + penalty(health(c)) − bonus(warm_fn(c, fn))
```

Default `route=score`; baselines: `nearest`, `least_loaded`, `po2_nearby`, `warm_aware`. **Spillover** occurs when
the best cluster is saturated (utilization > ρ or SLO-health degraded); an orphaned cluster (control plane lost,
see 04) is excluded after its summary expires. The router adds a small calibrated decision delay.

## 4. Cluster scheduler pipeline

The cluster scheduler is a **role hosted by a worker**, appointed (with an epoch) by the orchestrator and replaceable by
any eligible worker (07): there is no replicated log, so a decision is dispatched as soon as it is made. Solve time on
the scheduler host scales with the host's speed (01 §7). Clusters are kept **small** (tens of workers, `N_target` from
E02) because ILP cost grows quickly with window size × cluster size.

```
arrival ─▶ admission ─▶ ┬─ fast path (sync SLO):  immediate greedy over CostMatrix row(s)
                        └─ window path (async/filler): batch Δ (ms–s) → solve → dispatch
          periodic: rebalance / prewarm planning (window solver or heuristic)
```

- `placer_mode: fast | window | hybrid` (default **hybrid**: fast for sync; window for async/filler and for
  prewarm/rebalance planning). Resolves the spec's "ILP in loop vs. on the side" as a configurable axis (ADR-006).
- **Admission control:** if predicted `pMiss ≈ 1` on all candidates → reject (sync) or defer (async/filler).
  Backpressure: bounded cluster queue; overflow triggers router spillover.
- **Filler class:** placed only on slots idle beyond sync headroom; preempted (killed, re-queued) when a sync
  invocation needs the slot. Never counted as SLO traffic.
- **Candidate pruning:** top-`K` workers per invocation by a cheap lower bound (`wait + startup + net`); ILP
  size is `W×K`.

## 5. Prediction (`policy/predict`)

Interface (batch, vectorized):

```python
class Predictor(Protocol):
    def predict(self, fn: IntArr, in_bytes: FloatArr, workers: WorkerFeatures, load: FloatArr) -> LogDist  # [W, N]
    def update(self, obs: ExecObservation) -> None   # online, from completed invocations only
```

`LogDist` carries `(mu, sigma, nu)` of log-runtime (Student-t family; Gaussian when `nu=∞`) with `.mean()`,
`.quantile(q)`, `.cdf(x)`, `.cvar(a)`.

**Default (`blr`)**: Bayesian linear regression in log space with factorized features:
`log T = f_fn + g·log(in_bytes) − log(speed_node) + δ_node + β·load + ε`. Function and node terms are one-hot with
**hierarchical shrinkage** (partial pooling); closed-form recursive update with forgetting factor `γ`; a **split-
conformal scale factor** corrects interval calibration. Cold start: new node's `speed_node` prior from its
benchmark; new function's prior from the nearest profiled function (by features). Evaluated **online,
time-ordered** only.

Other registered predictors: `global_mean, worker_mean, fn_mean, pair_mean, ewma, loglinear_ols, gbq_quantile,
knn_similarity`. Metrics: MAE/RMSE/MAPE/bias/tail error + interval calibration (coverage), plus downstream
scheduling regret (H6).

**Other cost components** are state + estimates, not learned: `T_net` from per-worker bandwidth/RTT estimates
(EWMA of observed transfers, benchmark prior), `T_startup` from lifecycle state × calibration distribution,
`T_wait` from queue length × predicted residuals (stale view + local bookkeeping).

## 6. Risk: reliability estimate vs. reputation (the double-counting rule, spec §4.4)

Two signals with **disjoint inputs**, which is how double counting is avoided:

| Signal | Answers | Built from | Enters cost via |
|---|---|---|---|
| **Survival model** `S(τ ∣ age, tier, local_hour, declared window, drain deadline)` | P(worker stays available over `[now, now+T]`) | Observed session lengths, owner-busy/crash events, declared windows; Weibull per (tier, region) with time-of-day hazard; Kaplan–Meier as comparison | `pFail`, i.e. inside `pMiss` and the failure term |
| **Reputation** | Commitment-keeping and timeliness (honesty only under the optional `crash_plus_lazy` extension) | **Only** broken Tier-1/2 commitments (leaving inside declared window), envelope shortfall, timeliness bonus (plus verification mismatches in the extension). **Never** owner preemption of Tier 0, crashes, or ordinary failures | `repPenalty` and eligibility threshold |

Hard constraints from known information: a drain deadline `D` removes any placement with predicted completion past
`D`; declared windows are constraints for Tier 1. Ablations: `no_survival`, `no_reputation`, and
`reputation_includes_failures` (to show the double-counting effect).

## 7. Cost matrix and scalarization (`policy/cost.py`)

`CostModel.build(invs, view, predictors) → CostMatrix` with **separate named components**, each `[W×N]`:

```
wait, startup, net, exec (LogDist), pFail, wasted_time, recovery, repPenalty, donorCost, feasible (bool)
```

Completion distribution per pair: shifted lognormal by moment-matching (Fenton–Wilkinson) of independent terms
(`wait`, `startup`, `net`, `exec`) plus the failure branch:

```
pMiss(i,j) = 1 − (1 − pFail(i,j)) · P(T(i,j) ≤ d_i)
failure cost = pFail · (wasted_time + recovery)      # recovery ≈ expected re-placement latency, approximated
```

`Scalarizer` maps components to the scalar cost `Ĉ[i,j]` (registered, swappable):

| Name | Ĉ |
|---|---|
| `slo_miss` (**primary**, spec §8.1) | `w_i·pMiss + ε·E[T] + λ·repPenalty + donorCost` |
| `expected` | `E[T] + failure cost + …` |
| `mean_spread` | `E[T] + κ·sd(T)` |
| `quantile` | `Q_q(T)` (q = 0.9/0.95) |
| `cvar` | `CVaR_α(T)` |
| `tardiness` | `E[max(0, T−d)]` (for invocations that will miss) |
| `makespan` / `sum_latency` | batch/filler and baseline comparison |

**Correlated failure** is handled by *constraints* in the placer (failure-domain caps, anti-affinity for replicas),
never by costs.

## 8. Placers (`policy/place`)

All implement `place(PlaceRequest) → Placement`; `PlaceRequest` carries invocations, candidates, `CostMatrix`,
capacities, time limit. Coupling within a window is handled by **slot expansion**: each node `j` exposes slots
`(j, k)` for position `k` in its queue; `wait` of slot `k` = base wait + (k−1)·(predicted mean exec of the window's
function mix on `j`), the positional-cost trick behind the polynomial matching result (verify: Horn;
Bruno–Coffman–Sethi).

| Placer | Formulation | Handles |
|---|---|---|
| `greedy` | Sequential best-cost; updates local state per assignment | Everything approximately; fast path |
| `mcf` / `matching` | Assignment of invocations to `(node, slot)`; `scipy.optimize.linear_sum_assignment` (or OR-Tools min-cost flow) | Slot capacity, positional queue cost. **Polynomial.** |
| `lp_round` | LP relaxation of ILP + rounding | Approximation baseline |
| `ilp` | Binary `x[i,j,k]`, plus `y[f,j]` (function instance started on node: pay start-up once, shared by co-placed invocations of `f`), memory packing `Σ mem ≤ free_mem_j`, failure-domain caps, replica anti-affinity, reputation thresholds. Solver: `scipy.optimize.milp` (HiGHS) default; OR-Tools CP-SAT as a second solver | Everything; **NP-hard** (generalized assignment) |

Solver options (registered): `time_limit`, `warm_start=greedy`, `pruning_K`. On timeout use incumbent, else fall
back to greedy; log `status, gap, solve_wall_s`. **The paper shows which constraints force `ilp` over `mcf`**
(`y` coupling, memory packing, domain caps) with an ablation that removes each constraint and measures quality
and solve-time differences; if `mcf` ≈ `ilp`, report that.

**Non-VOSS baselines** (same interface, ignore parts of the cost matrix): `random, round_robin, least_loaded,
jsq, po2, fastest_predicted, latency_aware, reliability_aware, weighted_score, k8s_least_allocated, k8s_binpack,
k8s_spread, warm_first, hash_locality, min_min, sufferage, boinc_pull_replicate, condor_match, nearest_edge`.
Full list and which are Phase 8 vs. nice-to-have in 06.

## 9. Failure handling (`policy/retry`)

On a failure outcome, `RetryPolicy` decides: `retry_same | retry_other | retry_most_reputable | retry_lowest_cost`,
`max_attempts`, optional **hedge** after `h` ms (idempotent functions only; tied-request cancel), optional
**cross-cluster retry**, and optional **replication** for critical invocations (domain-spread). Retries re-enter
the placer with the failed worker excluded and the elapsed time counted; wasted and duplicate work are logged.
Failures are never treated as infinite latency; they are retried and counted as misses. Failure *detection* (predictor-driven
watchdogs, accrual detector), hedge budgets and retry-storm control are specified in 07 §5.

## 10. Lifecycle policies (C4, `policy/keepalive.py`)

- `KeepAlivePolicy.ttl(worker, fn, view) → seconds`: `none | fixed | histogram (Shahrad) | greedy_dual
  (FaasCache-style) | churn_aware` (TTL scaled by worker survival and reputation, bounded by donor memory budget).
- `PrewarmPolicy.plan(forecast, view) → [(worker, fn, target_state)]`: from per-cluster arrival forecasts
  (EWMA by hour); run on the window path/periodically; bounded by donor memory/disk budgets.
- Snapshots on/off, P2P seeding on/off are config flags in the lifecycle model.
- Placement preference for `S3 > S2 > S1 > S0` emerges from `startup` cost vs. `wait` and risk in the matrix, not
  from a hard rule (that rule exists only as the `warm_first` baseline).
