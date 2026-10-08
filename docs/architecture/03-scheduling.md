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
wait       = ready_at[j] (per-core readiness, doc 08 §5)
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
