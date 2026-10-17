# 03 · Scheduling (contribution C2: two-timescale, trust-aware)

All decision logic lives in `voss/policy` as **pure functions** of views, plans and predictions. Runtime actors
(doc 05) call them on timers or messages and apply results after the decision latency (doc 01 §7).

## 1. Decision levels

| Level | Who | Cadence | Decides | Method |
|---|---|---|---|---|
| Cluster arrangement | Orchestrator | 30 s + events | Membership, split/merge/move, succession lists | Rule-based with hysteresis (§2) |
| Routing | Router | Per request | Cluster for each invocation, spillover | Score over cluster summaries (§3) |
| **Slow loop: Trust & Warm-state Planning (TWP)** | Scheduler | `T_plan` 10–60 s + events | Trust-warm sets, warm units, caps, cache pins, prewarm and key-release actions | **Robust MILP** (default) or greedy (§4) |
| **Fast loop: placement** | Scheduler | Per invocation (sync), small window (async/filler) | Worker per invocation, hedge, cold path, retry | Cost-matrix greedy or min-cost flow (§5) |

**Why two timescales:**
- Trust and warm state are **set-valued and long-lived**:
  - a key released to a host stays for the session;
  - exposure depends on *how many distinct hosts* hold a key;
  - robustness to *f* defectors is a *worst case over subsets*.
- None of these is a per-assignment additive cost, and none should be solved per request.
- Placement is latency-critical and decomposes well, so it stays cheap.

## 1a. What is minimised, at which level, and why not SLO violations directly

Scheduling here has **two objectives at two levels**, and neither is "the number of SLO violations" summed over a run.
This section states exactly what each loop minimises, what it is constrained by, and why. Every symbol is defined once;
Section 9 states for each input whether it is observed, learned from history, forecast, calibrated or configured.

**The quantity we care about (the evaluation metric).** For an invocation *i* of class `sync` with deadline `D_i`, an
*SLO violation* is the event `V_i = {attempt fails} ∪ {end-to-end latency > D_i}`. The deadline is
`D_i = k_f · (w_f(in_i) + 0.05 s)` where `w_f` is the reference-core execution time of the function at its input size and
`k_f = 5` for sync functions (`world/workload.py`). We *report* violations (deadline-met fraction, success, P99) in every
experiment. Whether the scheduler *minimises* them directly depends on the level:

| Level | Minimises | Subject to | Is it SLO violations? |
|---|---|---|---|
| **Fast loop** (per invocation) | `J(i,j) = w_i·P_miss(i,j) + ε·E[T_ij] + λ_exp·x_ij` over candidate hosts *j* | eligibility (valid attested session, not past a drain deadline, assurance ≥ tenant floor, filler headroom), top-K pruning, admission, hedge budget | **Yes, per invocation:** `P_miss` is the probability that this invocation violates its SLO (failure counts as a violation). Latency `ε·E[T]` and exposure `λ_exp·x` are regularizers. |
| **Slow loop** (per cluster, every `T_plan`) | `Σ_t Λ_t u_t + donor memory/SSD cost + λ·Σ σ_t(1−a_j) y_tj + κ_switch·Σ(y−y_prev)⁺ − β·Σ b_f(w+γ s)` (doc 03 §4.2) | robust coverage of the demand quantile `q_t` (any `f_t` hosts may defect), slots, memory, SSD, failure-domain caps, assurance floor, freshness | **No, by design.** It minimises a *surrogate* of violation risk (uncovered demand `u_t`, i.e. invocations that would have to take the trust-cold path) *plus* the two costs SLOs do not see: donor resources and key exposure. |
| **Router** (per request) | `rtt + E[completion_c] + health_c + trust_cold_c + cold_fn_c` over clusters *c* | cluster has free slots and is not excluded | Partly: `health_c = health_s · max(0, miss_rate_c − θ)` penalises clusters whose *observed* violation rate exceeds θ. |

### Fast loop: the per-invocation objective

For invocation *i* (tenant *t*, remaining deadline budget `b_i = D_i − (now − t_arrive,i)`) and candidate host *j*:

```
P_miss(i,j) = p_fail(i,j) + (1 − p_fail(i,j)) · P( T_ij > b_i )              # a failure is a violation
p_fail(i,j) = 1 − S_j(ē_ij + 2 s) · (1 − p_j)                              # session end or omission; ē = predicted mean run time
T_ij        = max(wait_j, trust_ij, fetch_ij) + rest_ij + net_ij + exec_ij   # completion time; moment-matched shifted log-normal
                                                                                 # (variance of the non-execution part taken as (0.3·max(...))²)
x_ij        = σ_t · (1 − a_j)  if j does not yet hold tenant t's key, else 0 # exposure increment
J(i,j)      = w_i · P_miss(i,j) + ε · E[T_ij] + λ_exp · x_ij                 # default scalarizer `slo_miss`
```

Defaults (`configs`, tag *assumed*): `w_i = 1` for sync and `0.3` for async/filler, `ε = 0.05` per second, `λ_exp = 1`,
`σ ∈ {low 0.1, medium 1, high 3}`. Units are **miss-equivalents**: one second of expected latency is priced like a 5%
increase in violation probability, and giving a medium-sensitivity tenant's key to a new host of assurance 0.8 costs
`1·(1−0.8) = 0.2`, i.e. the same as a 20% chance of violating the SLO. The greedy placer takes invocations in order of
tightest remaining budget and assigns each the host with minimum `J`, adding a per-slot penalty for hosts already chosen
in the same call (`policy/place/greedy.py`).

**Why per-invocation violation probability and not "P99".** P99 is a statistic of a population and cannot be assigned to
one decision. Minimising each invocation's own violation probability against its own remaining budget is the decision-level
quantity whose average is the deadline-miss rate and whose tail is the P99; E03 compares it with expectation-, quantile-,
CVaR- and tardiness-based scalarizers (`expected`, `mean_spread`, `quantile`, `cvar`, `tardiness`).

### Slow loop: why the planner does not minimise SLO violations directly

The planner decides *which hosts hold keys and warm state for the next horizon `H`* (`H = horizon_factor · T_plan = 60 s`).
Minimising violations directly was rejected for five reasons:

1. **Circularity.** Whether an invocation violates its SLO depends on the fast loop's later decisions, which depend on the
   plan. A planner that minimised violations would have to optimise over the placer's policy (a bilevel problem) per solve.
2. **No per-request information.** At planning time the individual invocations do not exist. What exists is a *forecast*
   of demand; the planner can only reason about capacity relative to that forecast.
3. **Rare, noisy events.** Violations are 1–5% events. A planner optimising an empirical or simulated violation count would
   chase variance; a coverage constraint at a chosen demand quantile is stable and interpretable.
4. **Violations are not the only cost.** Pre-warming everything would minimise violations and hold every tenant's key on
   every host. The scarce resources are donor memory/disk and key exposure (Section 4.2 of doc 04). The planner is
   therefore a *cost minimisation under a coverage requirement*, and the trade-off is reported as a Pareto front (E23).
5. **Hard SLO constraints are infeasible in general.** Under churn and adversaries no plan can guarantee a deadline; a
   robust coverage requirement against *any `f_t` defectors* is the strongest statement that does not assume a model of
   the adversary (doc 03 §4.2).

**How the planner still serves the SLO.** The robust coverage constraint is a *chance-constraint surrogate*: with arrivals
modelled as Poisson, the number of concurrently running invocations of tenant *t* is Poisson with mean `λ_t · s_t`
(M/G/∞), so `q_t = Q_0.95(λ_t · s_t)` slots are enough to run every invocation immediately with probability 0.95 under the
forecast. Requiring provisioned, available capacity `Σ_j S_j(H)(1−p_j) c_tj ≥ q_t` even after removing the `f_t` largest
allocations bounds the share of invocations that must fall back to the trust-cold path, which is the dominant cause of
SLO violations on volunteer hosts. Uncovered demand `u_t` is priced at `Λ_t = 10` per slot, two orders of magnitude above
the per-unit memory price (`ρ_mem = 10⁻⁴` per MB, i.e. 0.05 for a 512 MB VM) and the exposure price (≈0.2 per added key
holder), so coverage is satisfied unless it is infeasible within budgets, in which case the shortfall is reported
(`PLAN_INFEASIBLE`). The Poisson model is the planner's *assumption*: the simulated arrivals are a Markov-modulated process with 4× bursts, so coverage is below 95% during bursts. This is a design rationale, not a theorem; the actual violation rate is measured by the experiments.

**What is deliberately not optimised.** No explicit P99 target, throughput, fairness across donors, or provider cost; the
reference-cloud comparison (E17) reports cost after the fact. Reputation never enters `p_fail` (doc 09 §1).

## 2. Orchestrator: cluster arrangement

Provider-run, trusted, assumed reliable; state in the operational DB (doc 08).

- **Initial clustering:** k-medoids on worker RTT embedding, `k = ceil(N / N_target)`. `N_target` is small (tens),
  from E02. It bounds both the planner MILP size and intra-cluster RTT.
- **Diversity requirement (new):** each cluster should contain ≥ `D_min` failure domains and enough assurance mass
  for its hot tenants' floors, so f-robust plans are feasible.
- **Triggers** (each switchable for ablation):

| Trigger | Condition | Action |
|---|---|---|
| Size floor/ceiling | live attested workers < `N_min` or > `N_max` | Borrow or merge / split |
| SLO health | Router-observed miss rate > θ for `m` periods | Borrow from neighbors with headroom |
| Demand imbalance | Utilization gap > δ | Lend workers |
| Forecast | Next-hour demand exceeds capacity | Pre-move workers |
| Diversity deficit | < `D_min` domains or infeasible robust plan reported by scheduler | Swap workers with neighbors |
| Scheduler loss | No progress / no keepalive (doc 07) | Appoint successor; reassign if orphaned |

- **Stability:** per-worker dwell time, hysteresis, max moves per period, and a migration cost (a moved worker
  loses trust-warm and cache relevance).
- Also maintains each cluster's **succession list** (doc 07).

## 3. Router (orchestrator tier, regional)

`score(c) = rtt(origin, c) + E[completion_c(f)] + penalty(health_c) + trust_cold_penalty(c, t)`

- `trust_cold_penalty`: zero if cluster *c* has trust-warm capacity for tenant *t* in its summary; otherwise the
  expected key release + cold start, plus an exposure increment. **Spillover is therefore a priced decision.**
- **Progress watchdog:** no `ACCEPTED` within `T_dispatch` triggers a re-send; after `T_spill` it spills over. Repeated
  stalls are reported to the orchestrator (doc 07).
- Baselines: `nearest`, `least_loaded`, `po2_nearby`, `warm_aware` (ignores trust).

## 4. Slow loop: Trust & Warm-state Planner (TWP)

### 4.1 Inputs (from the scheduler's view; all estimates, no ground truth)

| Input | Source |
|---|---|
| Attested workers `J`, slots `cap_j`, memory/SSD/HDD budgets, cache inventory, trust flags `K[t,j]`, attestation expiry | Heartbeats (doc 08 §5) |
| Survival over horizon `S_j(H)` | Survival model (§6.3) |
| Omission rate `p_j` and change-point state | Omission model (§6.4) |
| Assurance `a_j` | Verifier-issued certificate + freshness (doc 04 §8) |
| Failure domain `d(j)` | Membership data |
| Demand forecast per hot tenant/function: rate `λ_t`, required concurrent capacity quantile `q_t = Q_0.95(λ_t × service time)` | Arrival forecaster (§6.2) |
| Tenant sensitivity `σ_t`, assurance floor `a_min,t`, robustness level `f_t` | Tenant config |
| Previous plan | Scheduler state |

**Hot set:** only tenants/functions above a rate threshold (top-k) are planned. The long tail uses the cold path.
This keeps the MILP small.

### 4.2 Robust MILP

**Variables:**
- `y[t,j] ∈ {0,1}`: tenant *t* is trust-warm on worker *j* for the horizon (key released, artifacts at ≥ L1).
- `s[f,j] ∈ {0,1}`: snapshot of function *f* pinned on *j* (L2, SSD tier).
- `w[f,j] ∈ ℤ≥0`: warm VMs of *f* kept on *j* (L3).
- `c[t,j] ≥ 0`: slots of *j* earmarked for *t* (soft cap for the fast loop).
- Auxiliaries `θ_t`, `π[t,j] ≥ 0` for the robust constraint.

**Objective (minimize; each term logged separately for Pareto analysis):**

```
  Σ_t  ColdPenalty_t · u_t                                              # uncovered demand (u_t ≥ shortfall, below)
+ Σ_j  ρ_mem · (Σ_f m_f w[f,j]) + ρ_ssd · (Σ_f size_f s[f,j])           # donor cost
+ Σ_t  σ_t · Σ_j (1 − a_j) · y[t,j]                                     # exposure (doc 04 §8)
+ Σ_t,j  κ_switch · max(0, y[t,j] − y_prev[t,j])                         # plan churn (linearized)
- Σ_f,j  β_warm · benefit(f) · (w[f,j] + γ s[f,j])                       # warm-start savings (concave approx.)
```

**Constraints:**

```
Robust coverage, per hot tenant t:
  Σ_j c[t,j]·S_j(H)·(1 − p_j)  −  ( f_t·θ_t + Σ_j π[t,j] )  + u_t  ≥  q_t
  π[t,j] ≥ c[t,j] − θ_t ,  π[t,j] ≥ 0                         # = sum of the f_t largest c[t,·] (exact, LP duality)
Coupling:          c[t,j] ≤ cap_j · y[t,j];   w[f,j] ≤ W_max · y[t(f),j];   s[f,j] ≤ y[t(f),j]
Slots:             Σ_t c[t,j] ≤ cap_j
Memory:            Σ_f m_f w[f,j] + m_base ≤ M_j          SSD: Σ_f size_f s[f,j] ≤ SSD_j
Domain cap:        Σ_{j ∈ D} c[t,j] ≤ κ_dom · Σ_j c[t,j]   for every failure domain D
Assurance floor:   y[t,j] = 0 if a_j < a_min,t
Freshness:         y[t,j] = 0 if attestation expires within H and no re-quote fits
```

**Size:** one cluster has ~30 workers × (≤ 20 hot tenants, ≤ 50 hot functions), so about 10³–3·10³ integers.

**Solver:** HiGHS via `scipy.optimize.milp`, deterministic settings, time limit `T_solve` (default 2 s simulated
budget). Warm-started from the previous plan; falls back to the incumbent, then to greedy.

### 4.3 Greedy planner (baseline and fallback)

For each hot tenant in decreasing `λ_t × ColdPenalty_t`:
1. Repeatedly add the worker maximizing `S_j(1−p_j) a_j / (memory cost + σ_t(1−a_j))` under the assurance floor and
   domain cap, until robust coverage holds: coverage with the `f_t` largest contributions removed is ≥ `q_t`.
2. Then add warm VMs and snapshots by value density until budgets bind.

### 4.4 From plan to actions

`Plan = {y, s, w, c, valid_until}`. `diff(plan_prev, plan)` yields idempotent actions sent to workers:

| Action | Message | Worker effect |
|---|---|---|
| Make trust-warm | `PREPARE(t, fns)` | Request key from KBS; fetch/decrypt bundles (P2P/registry); pin |
| Pin snapshot | `PIN_SNAPSHOT(f)` | Create (if trust-warm) or fetch from a same-class trust-warm peer |
| Keep warm VMs | `WARM(f, n)` | Boot/restore n VMs |
| Unpin / release | `RELEASE(t)` | Unpin; drop key after `T_linger` (no in-flight work) |

Actions are rate-limited per worker (`max_parallel_prepares`) and ordered by value. Workers report completion in
heartbeats. The plan is valid only for state the worker has *confirmed*, so the fast loop never assumes a trust-warm
host that is not yet warm.

## 5. Fast loop: placement

### 5.1 Candidates for invocation *i* of tenant *t*

1. **Trust-warm candidates:** `{j : y[t,j]=1, confirmed}` with remaining earmarked slots `c[t,j]` (soft) and free
   slots (hard).
2. **Cold-path candidates:** other attested workers meeting the assurance floor. Their cost adds key release
   (KBS RTT), artifact fetch, and an **exposure increment** `σ_t(1−a_j)` when *j* is new for *t*.
3. Pruned to top-`K` by a cheap lower bound.

### 5.2 Cost matrix

For each candidate pair `(i, j)` the cost model (`policy/cost`) produces named components:

```
wait       = max(0, busy_j + queued_j + inflight_j − slots_j + 1) · svc / slots_j      # queue-length estimate (implemented)
                                                                                 # svc = scheduler's EWMA of observed execution times;
                                                                                 # doc 08 §5 describes a per-slot residual-time `ready_at`, which is not implemented (D-69)
trust      = 0 if K[t,j]=1 else KBS_rtt(j, t) + check
startup    = ladder cost from the worker's cache level for f (L3 ≈ 0, L2 restore@tier, L1 boot+init@tier, L0 fetch+…)
net        = input + output transfer over geo network (+TLS)
exec       = LogDist from the predictor × substrate slowdown
pFail      = 1 − S_j(T_completion) · (1 − p_j)          # churn + omission
exposure   = σ_t (1 − a_j) if j not yet a key-holder for t else 0
```

The completion distribution is a moment-matched shifted lognormal over `wait + trust + startup + net + exec`.

| Scalarizer | Formula |
|---|---|
| **`slo_miss`** (default) | `w_i·pMiss + ε·E[T] + λ_exp·exposure` |
| Others (sweeps) | `expected`, `mean_spread`, `quantile`, `cvar`, `tardiness` |

### 5.3 Placers

| Placer | Use |
|---|---|
| `greedy` (default, sync) | Best scalar cost; updates local bookkeeping |
| `flow` (async/filler windows) | Min-cost assignment of window invocations to `(worker, slot)` pairs; polynomial |
| `ilp_window` (baseline only) | Old per-window ILP, kept to show the slow/fast split is better |
| Baselines | `random, round_robin, least_loaded, jsq, po2, warm_first, latency_aware, reliability_aware, k8s_*, nearest_edge, hash_locality` |

All placers see the same candidates and cost matrix.

### 5.4 Hedging, retries, admission

- **Hedge** (idempotent, sync): if `pMiss(best) > θ_hedge` and the cluster hedge budget allows, send a tied duplicate
  to the best trust-warm candidate **in another failure domain**, and cancel the loser on first `RESULT`. This is the
  main defense against black-holing and on-off hosts.
- **Retry:** on a watchdog or failure, re-place with the failed worker excluded. Prefer trust-warm candidates; elapsed
  time counts.
- **Admission:** if no candidate has `pMiss < 1−ε`, reject (sync) or defer (async).
- **Filler:** only on slots idle beyond sync headroom; preempted by sync.

## 6. Prediction (`policy/predict`, `policy/survival.py`, `policy/omission.py`)

### 6.1 Execution time

Bayesian log-linear regression with hierarchical shrinkage, a forgetting factor and conformal calibration (unchanged
design):
- `log T = f_fn + g·log(in_bytes) − log(speed_j) + δ_j + β·load + ε`.
- Priors come from SeBS profiling on node C0 (doc 10).
- Online and time-ordered evaluation only.

### 6.2 Arrival forecast (feeds the planner)

Per hot tenant/function per cluster: EWMA of rates at two scales (minutes, same hour of past days) plus a Poisson
quantile for `q_t`. Baselines: last-value, oracle (analysis only).

### 6.3 Survival (churn)

Session residual life `S_j(τ | session age, tier, local hour, drain notice)`:
- Weibull per (tier, region) with time-of-day hazard; Kaplan–Meier as a comparison.
- Drain notices are **hints that only shorten** predicted life (doc 07: they may be fake).

### 6.4 Omission (adversaries)

- `p_j` = Beta posterior on accepted invocations that end in a result vs omission.
- **Change-point detection** (CUSUM on omission indicators): when it fires, the host's trust-warm eligibility is
  reset and `p_j` restarts from a pessimistic prior. This defeats on-off attackers.
- **Robustness does not rely on this model:** the planner's `f_t`-robust coverage holds against *any* `f_t`
  defectors, including ones with a perfect record.
- `f_t = ⌈α_assumed · N_cluster⌉` by default; tenants may opt down.

**Reputation is separate** (doc 09): it measures declared-commitment behavior and feeds rewards. It never double
counts `p_j`.

## 7. Baselines and ablations (scheduler side)

- **Planning:**
  - `none` (reactive cold path only);
  - `keepalive_ttl` (classic per-function keep-alive, no trust planning);
  - `greedy` planner;
  - MILP variants: `−robust (f=0)`, `−exposure (σ=0)`, `−domain_cap`, `−freshness`;
  - `oracle_demand` (analysis only).
- **Placement:** listed in §5.3, all with the same plan.
- **Hedging:** off / always / risk-proportional.
- **Detection:** progress-based vs heartbeat-only (doc 07).
- **Cache:** value-density vs LRU; P2P on/off; HDD tier on/off.

## 8. Where integer programming is justified (answers spec RQ16)

Only the planner needs it, for:
- set coverage (`y`);
- the robust top-f coverage;
- the memory/SSD knapsack;
- domain caps;
- the coupling between `y`, `s` and `w`.

Placement decomposes into assignment/flow. Experiment E04 compares MILP vs greedy planner vs no planner. **Kill
criterion:** if the MILP improves P99 by < 5% over greedy in all regimes, greedy becomes the method and the MILP is
reported as an upper-bound reference.

## 9. Information model: what each decision uses, and from where

Policies never see ground truth. Every input to a decision is one of five kinds, and this table states which, for every
quantity used by the planner, placer, router, hedger and detectors (code: `runtime/schedlib/*`, `policy/*`).

| Kind | Meaning |
|---|---|
| **O** observed | Reported by an attested agent or trusted router by message; stale by at most the heartbeat period (2 s) plus network delay, with the scheduler's own dispatches since the last report added (`inflight`) |
| **H** learned from history | An estimator updated online from *past outcomes only* |
| **F** forecast | A quantity computed from H-quantities for the future (a horizon, an upcoming window) |
| **C** calibrated model | A constant or formula fixed before the run, from the calibration bundle, the function catalogue or the geography model; **not** learned online |
| **P** policy | Configured by the tenant or operator (weights, floors, budgets) |

| Quantity | Used by | Kind | Source and update rule | Before enough data |
|---|---|---|---|---|
| Slots, memory/SSD budgets, speed, link rates, location, tier, session start | planner, placer | O (static, at `JOIN`) | worker agent's declared envelope; **speed and link rates are taken as exact** | n/a |
| Busy, queued slots, cache tier per function, provisioned tenants, session expiry, drain deadline | placer, planner | O | heartbeat every `heartbeat_s = 2 s`; dispatches since then counted as `inflight`; a worker whose report is older than `stale_after_s = 7 s` is not included in plans | worker left out of the plan |
| Assurance `a_j` | planner, placer | O (certified) | issued by the verifier from the substrate, quote freshness, firmware policy | n/a |
| Execution time of a function on a host | placer | **H** | Bayesian log-linear regression per function, forgetting factor 0.995, per-worker offsets shrunk to 0 (prior count 5), conformal spread over the last 500 residuals | prior from the function catalogue (`work_ref_s`, `size_exp`, σ = 0.35) |
| Predicted completion `T_ij` | placer | **F** | wait + trust + start-up + network + execution, moment-matched to a shifted log-normal | as above |
| Wait for a slot | placer | **O + H** | occupancy from heartbeats × scheduler's EWMA service time (weights 0.98/0.02) | `svc = 1 s` |
| Start-up and trust-establishment time per tier and substrate | placer, planner | **C** | means of the substrate profile's transitions (calibration bundle); **not** re-learned online | n/a |
| Network RTT and transfer time | placer, router | **C** | great-circle distance / (100 km per ms) × 1.3 route factor, bytes / declared link rate; **no jitter and no measurement** | n/a |
| Session survival `S_j(τ)` | planner, placer | **H → F** | per-tier Weibull by censored maximum likelihood on completed sessions and live ages, refit every 60 s; 24-bin local-hour hazard multiplier after 48 session ends; drain notices only shorten | prior shape 0.7, scale 7200 s until 20 sessions of the tier have ended |
| Omission probability `p_j` | planner, placer, detectors | **H** | Beta posterior of accepted invocations that returned no result, mid-session only; CUSUM (k = 0.1, h = 5) resets the host to Beta(2, 4) | Beta(0.5, 20), mean 0.024 |
| Arrival rate per tenant and function | planner | **H → F** | counts in 10 s bins; EWMA with τ = 60 s and 900 s; forecast = max(short, long, regional rate pushed by routers); a key is planned only if its forecast rate is at least `min_rate = 0.01/s` and it is among the top 20 tenants / 50 functions | rate 0 (not planned until seen) |
| Demand quantile `q_t` | planner | **F** | Poisson 95% quantile of `rate × service time` (concurrency of an M/G/∞ system); service time per key is an EWMA (0.9/0.1) of observed execution times | catalogue `work_ref_s` |
| Warm benefit `b_f` | planner | **F + C** | `rate · H · (rootfs/500 MB/s + boot + init) / warm units` (start-up seconds saved) | n/a |
| Tenant sensitivity σ, assurance floor, robustness `f_t` | all | **P** | tenant configuration; default `f_t = ⌈0.1 · N_cluster⌉` | n/a |
| Objective weights (`Λ`, `ρ`, `λ`, `ν`, `β`, `γ`, `ε`) | planner, placer | **P** (tag *assumed*) | configuration; swept in E04, E19, E23 | n/a |
| Cluster load, SLO-miss rate, overhead, cold prices, provisioned capacity | router | **O** | scheduler summary every `summaries_s = 1 s`; cold prices are what the cluster *measured* (D-33), with prior 3 s and 0.5 s until measured | priors |

**What is never used.** The true session end time, true runtime and noise of an invocation, a host's true adversarial
behaviour, future arrivals, and other hosts' true state. A lint rule and `import-linter` forbid `voss.policy` from
importing `voss.world`. The `plan_oracle` baseline, which does use ground truth, exists for analysis only.

**How much is history versus forecast.** The slow loop is mostly forecast: demand and survival over a 60 s horizon,
extrapolated from rates smoothed over minutes (τ = 60 s, 900 s) and from session-length statistics accumulated over the
whole run. The fast loop is mostly observation: occupancy, cache state and provisioning are at most a few seconds old, and
only the execution-time distribution, survival over the next few seconds and omission probability are statistical
estimates. The **speculative** parts are exactly those marked C: the scheduler assumes start-up costs and network
times equal the calibrated nominal values, and that declared speeds are exact. In a deployment these would be measured
online; that this POC does not do so is a stated limitation, and E11-style error-injection sweeps (prediction noise,
stale views) are not part of the paper's experiments.
