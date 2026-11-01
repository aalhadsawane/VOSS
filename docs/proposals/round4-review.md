# Round 4 design review (WP5, before code)

Reviewer stance: OSDI/NSDI/ToIT program committee. Scope: WP1 and WP2 as written in `docs/PLAN-ROUND4.md`, the math
in `docs/proposals/planner-v2.md`, the hypotheses in WP3, and the 25-page outline (WP4). I wrote no code. Line numbers
refer to `main` at the time of writing.

## 0. Must change before implementation finishes (summary)

1. **E04's planner gain comes from 3 of 10 seeds, and keys do not explain it.** Per-seed `paper/tables/E04.csv`:
   `keepalive_ttl` is within about 10% of `plan_greedy` on synchronous P99 in 7 of 10 seeds at both churn levels. The
   27% and 57% headline gaps come from seeds 2, 8 and 10 (for example, high churn seed 10: 11.8 s against 2.1 s).
   The share of trust-cold starts is about 0.1% for **every** system (0.06 to 0.16%, `trust_cold` column), including
   `keepalive_ttl` and `plan_none`. The warm share (`l3_share`) is 0.98 for both keep-alive and greedy. So, in E04 as
   it stands, the planner wins in the tail of a few bad scenarios (most likely city shocks and bursts), not by saving
   key releases. Decision 3 ("session-spanning state") is therefore **not yet supported by E04's mechanism data**.
   Before the paper is rewritten around it: (a) break down the slowest 1% of requests in those seeds by delay component
   (the placer already logs the five predicted parts; outcomes log the timings); (b) run the session experiment E25
   (§4.4). Section 3 explains why the value of keeping a key for the whole session goes to a reactive policy too, and
   what only a planner adds.
2. **WP1's baseline as specified will be weaker than the existing `keepalive_ttl`, so H12 is rigged in our favour.**
   In a 900 s run with 60 s warm-up, a 600 s TTL almost never expires (`configs/experiments/E04.yaml:9-10`,
   `voss/world/cache.py:202-215`): `keepalive_ttl` is close to "never evict". A histogram policy that unloads at the 99th
   percentile of idle time can only lose warm hits against it. Fixes: (i) add `keepalive_inf` (`warm_ttl_s=1e9`, config
   only) and test H12 against the **best** single loop per regime; (ii) learn idle times per **sandbox instance**, not per
   function (§1.2); (iii) lengthen E04 v2 to 1800 s with 300 s warm-up so the histogram has samples; (iv) re-warm on any
   current key holder, not "the same worker", which may have left.
3. **Add an exposure-matched key-provisioning baseline.** Greedy holds 2.7× the exposure and 1.5× the warm memory of
   keep-alive (`manuscript/generated/tab_planners.tex`: 19.9 against 7.4; 94 against 61 GB). Every reviewer will ask
   whether keys held ahead on a few reliable machines, with no optimiser, do as well. `provisioned_keys` (§1.3) answers
   that, and it matters more than the histogram baseline.
4. **WP2 drops the coverage constraint without saying so.** Planner v2 maximises `U − κ` with no `q_t` (`planner-v2.md`
   §3), yet WP2 still requires "robust slack holds" (`PLAN-ROUND4.md:68`, `types.py:127`). Pick one. My recommendation:
   drop `q_t` in v2, keep `robust_slack` as a reported metric and not a test, and add a robustness certificate:
   `min_{|R|≤f} U_t(S∖R)` computed exactly by enumeration. That is cheap: `C(15,4) = 1365` evaluations.
5. **Put session value in the cost, not in the utility** (`PLAN-ROUND4.md:61-62`). Multiplying `U_t` by `E[remaining
   session]` counts it twice, because the planner re-plans every 30 s and holder sets persist. The correct form is
   renewal–reward: the one-off prepare cost is divided by the expected residence, so
   `κ_tj = σ_t(1−a_j) + ρ_mem m_t c_tj + c_prep,tj·[y_prev,tj = 0] / E[min(L_j, T)]`. It stays modular and non-negative,
   so the distorted-greedy guarantee still applies (§2.4).
6. **One heap for warm sandboxes and snapshot pins mixes RAM MB with SSD MB** (`planner-v2.md:103-107`,
   `PLAN-ROUND4.md:63-64`), and the warm and snapshot gains of one function are substitutes. Use two passes (warm under
   RAM, then snapshots under SSD given `w_f`) or one Lagrange price per resource.
7. **`erlang_dpp` must update its virtual queue on every round, including reused plans.** `planning.py:171` skips the
   planner when the input signature is unchanged. The queue must also use **measured** exposure (`view.trust`, which
   includes keys released on demand by placement), not planned exposure. Start `Q_t(0)` from `σ_t`, not 0: a 900 s run
   has only about 30 rounds.
8. **Change the WP3 decision rule from superiority to non-inferiority.** From the E04 pairs, the log-ratio of P99 for
   MILP over greedy has a standard deviation of 0.061 at medium churn and 0.172 at high churn. A 5% gain needs about 12
   seeds at medium churn and about 93 at high churn for 80% power. H13 as written is very likely to come out
   inconclusive, as H8 did, and greedy would then stay the default while the paper presents v2's math. That is the worst
   outcome. Rule: adopt `erlang_greedy` if it is non-inferior (upper 95% CI of the paired P99 ratio below +5% at medium
   and +10% at high churn, with warm memory and exposure no higher), then rerun everything (§4.3). Use 20 seeds in E04.
9. **Wording of guarantees.** The paper may claim the (1−1/e) bound only for the per-tenant subproblem under a cardinality
   limit. It must not claim the Orlin–Schulz–Udwani constant or the drift-plus-penalty O(1/V) optimality (§2). The
   status text of C-44 in `CRITIQUE.md` ("chosen by distorted greedy with a (1 − 1/e) guarantee") must be scoped the
   same way.

---

## 1. WP1: the strong single-loop baseline

### 1.1 Is the hybrid histogram the right strongest single-loop competitor?

It is the one reviewers expect, because it is cited (Shahrad et al., ATC'20), deployed, and C-15, C-33 and C-42 ask for
it. In our setting, though, it attacks the wrong cost. It predicts **when** a unit of warm state will be needed again. Our
runs are short and dense (10 inv/s over 12 functions), the TTL already keeps everything warm, and 98% of starts are warm
for both keep-alive and greedy. What separates the systems is the tail under churn and shocks. The histogram policy has
no answer for a lost worker; it only adds unloads. Expect it to lose to `keepalive_ttl` on P99 and to win on memory.
That makes it a necessary baseline but not the strongest one. Report it on a P99 × warm-memory × exposure plane, never
on P99 alone.

### 1.2 Fidelity

| Aspect | Azure (Shahrad et al. §4) | WP1 as written | Verdict |
|---|---|---|---|
| Unit | application, which is Azure's unit of memory | function (`PLAN-ROUND4.md:40`) | **OK**: our unit of warm state is a function sandbox. Say "per unit of warm state" in the paper; C-14 already notes the difference. |
| Where | central controller, cluster-wide statistics | implementer decides (`:49`) | **Must be scheduler-side.** Worker-side histograms split the arrivals n ways and stretch idle times, and a worker that leaves loses its histogram. Send `WARM`/`RELEASE` as plan actions so the network delay is charged. |
| Idle time | end of execution to next invocation, per app (apps mostly have concurrency 1) | per function, "end of one invocation to the next arrival" | **Wrong for concurrency > 1.** Hot functions have several sandboxes, so per-function gaps are about 0 and the policy degenerates. Use the idle periods of each **sandbox instance** (time a warm sandbox waits between uses). The per-function pre-warm applies only when the function's pool reaches zero. |
| Bins and range | 1 min bins, 4 h range | "scale to horizon" | Use 1 s bins and a 30 min range (configurable). State the scaling explicitly: Azure's resolution relative to its range. |
| Windows | pre-warm = 5th percentile, keep-alive = 99th percentile, 10% margins (check exact formulas against the paper) | same | OK. Add: if pre-warm < 1 bin, **do not unload** (Azure's behaviour). |
| Representativeness | coefficient of variation of bin counts; out-of-bound idle times go to ARIMA | CV and min samples, then fixed TTL | Acceptable. Out-of-range idle times cannot occur in a 30 min run; say so and omit ARIMA. |
| Keys | n/a (trusted servers) | only current key holders re-warm | OK and necessary: it is what makes it a single loop. Re-warm on **any** current holder (best by the placer's cost), not on "the same worker". |
| Warm-up | days of history | 60 s warm-up in a 900 s run | **Too short.** E04 v2: 1800 s, metrics after 300 s, for all systems. |

### 1.3 Other baselines a reviewer would demand, ranked

| Rank | Baseline | What it isolates | Cost | Recommend |
|---|---|---|---|---|
| 1 | **`provisioned_keys`**: per tenant, keep the key on the `N_t` workers with the best `S_j(H)·a_j`, refilled when one leaves (one rule, applied on membership change). Warm state is left to the worker TTL. `N_t` is set so that mean exposure matches greedy's in E04 v1 (and a second point at keep-alive's exposure). It is the analogue of provisioned concurrency. | Separates **planning** (an optimiser over sets) from merely **holding keys ahead of time**. If it matches greedy at equal exposure, the paper's claim shrinks to "pre-provision keys"; if not, the set optimisation earns its place. | Small: about 60 lines, an empty warm plan, same `Plan` type. | **Yes (addition 1)** |
| 2 | **`keepalive_inf`**: `warm_ttl_s = 1e9`, evicted only under memory pressure. | Upper bound of every keep-alive policy in short runs. With no memory pressure, FaasCache's greedy-dual keep-alive reduces to it. | Config only | **Yes (addition 2, free)** |
| 3 | FaasCache (greedy-dual-size-frequency keep-alive) | Cost-aware eviction under memory pressure | Medium. `voss/policy/cache_value.py` already has GDSF for the disk cache; warm-VM eviction would need wiring. | No. One sentence: memory never binds in E04 (warm GB well under budget), so GDSF equals `keepalive_inf`. |
| 4 | Warm pool sized by Erlang-B per function, no key planning | Stage B without Stage A | Small, once `erlang.py` exists | No. Use it instead as an ablation of `erlang_greedy` (`stage_b_only`) in E19 if time allows. |
| 5 | Snapshot-first (restore everything, no warm pool) | C-33 snapshot family | Small | No. Lifecycle-aware placement and snapshot tiers are already in all systems (E19 `-lifecycle`). Say so. |

---

## 2. WP2 and planner v2: a check of the math

### 2.1 Claim by claim

| # | Claim (`planner-v2.md` line) | Correct? | Holds in our setting? |
|---|---|---|---|
| F1 | Insensitivity of M/G/c/c (`:29-31`) | Yes, for **Poisson** arrivals with blocked requests cleared (Sevastyanov 1957). Lost requests going "elsewhere" is exactly blocked-cleared, **provided they never come back to this pool**. | **Partly.** (a) Arrivals are a Markov-modulated Poisson process with 4× bursts, and insensitivity does not hold for non-Poisson input. Frame B as a pointwise-stationary approximation (Green & Kolesar 1991) using the 60 s EWMA rate. (b) An overflowed request creates a new key holder, because keys persist for the session (`worker_agent.py:322`), so `c` grows reactively. (c) Placement may **queue** on a holder rather than overflow (the wait term of the five delays), so this is not a pure loss system. (d) Slots are shared across tenants: I found no consumer of `Plan.c` outside the planner, so the "reserved slots" in `scheduling.tex:45-46` need verifying. (e) Omitted requests are retried. Present F1 as **the model**, not as a fact about the system. |
| F2 | Recursion (`:34`) | Yes | Yes |
| F3 | B decreasing and convex in integer c (`:36-37`; Messerli 1972), and in continuous c (Jagers & van Doorn 1986) | Yes | Yes. Needed only for integer `c_tj`, unless the continuous extension is used. |
| A1 | `U_t` monotone and submodular (`:56-59`) | **Yes**, and stronger than stated: the pointwise argument needs neither independence of `X_j` nor Bernoulli survival. It holds for **any joint survival distribution that does not depend on `S`**, so correlated (city-shock) failures are covered. Independence is needed only to compute the expectation by convolution. | Needs **fixed integer `c_tj`** chosen before the selection (the proposal does not say how; greedy uses fractional `c`, `greedy.py:31`). Needs `c_tj` not to depend on other tenants' choices, which is false when slots are shared (`greedy.py:48`, one `free` vector across tenants). |
| A1′ | `e_j = S_j(H)(1−p_j)` as one machine-level Bernoulli (`:48-50`) | Modelling choice | **Mismatch.** `p_j` is a per-request drop probability. A dropping worker keeps its slot and costs a watchdog timeout plus a retry; it does not lose capacity. Use `S_j(H)` for survival and put `p_j` in the modular cost as the expected retry delay, `λ_tj·p_j·T_detect`; or keep the thinning and call it an approximation. |
| A2 | Cost modular (`:61-65`) | Yes, including the switch cost and the session-amortised prepare cost of §0.5 | Must stay **non-negative**. No negative "keep" bonus for previous holders: set their switch cost to 0 instead. |
| A3 | Distorted greedy gives `U(S) − κ(S) ≥ (1−1/e)U(OPT) − κ(OPT)` (`:67-70`) | Yes for: `U` normalised, monotone, submodular and ≥ 0; `κ` modular and ≥ 0; **a cardinality constraint `k`**, with OPT the best set of size ≤ k (Harshaw et al. 2019, Thm. 3). The weight `(1−1/k)^{k−i−1}` and "add only if positive" match. "Strongest known guarantee" should read "matches the best known". | **Only per tenant, given a fixed ground set.** It is broken by: (i) shared worker slots and memory across tenants (sequential per-tenant greedy gives no joint guarantee); (ii) the domain cap, a ratio constraint that is not a matroid (a per-domain count limit would be a partition matroid, but plain distorted greedy has no published (1−1/e) bound under a matroid: that needs continuous greedy or local search, e.g. Sviridenko–Vondrák–Ward 2017; verify); (iii) per-worker memory knapsacks; (iv) the robust buffer. Assurance floor and freshness only filter the ground set and are harmless. The bound is also vacuous when `κ(OPT) ≥ (1−1/e)U(OPT)`. |
| A4 | Robust buffer of the `f` largest singletons, ≈0.387 (`:72-77`) | **Overstated.** The Orlin–Schulz–Udwani constant is **asymptotic** (k → ∞, τ = o(√k)), and their buffer is not simply the τ largest singletons (its size grows with k; check the exact algorithm). Bogunovic et al.'s PRO-GREEDY covers τ = o(k), also asymptotically, with a partitioned buffer. Neither covers submodular-minus-modular objectives. | **No guarantee in our sizes**: k ≈ 5–15 holders, f = ⌈0.1·40⌉ = 4 ≈ √k. Keep the buffer as a heuristic "inspired by" OSU and **certify** it: compute `min_{|R|≤f} U_t(S∖R)` exactly and report it. |
| B1 | Marginal allocation optimal (`:97-101`) | Yes for one separable concave knapsack with equal sizes (Gross; Fox). With unequal sizes it is optimal for the piecewise-linear relaxation, and the integer loss is at most the largest single increment. | **Relaxation only.** The real constraints are per-worker memory, `w_max` per (function, worker) and holders only, i.e. multiple knapsacks. Claim optimality for the pooled problem, then pack first-fit, and report the packing loss (pooled value minus packed value). |
| B2 | Model of the warm pool | — | **Mismatch.** With the worker TTL on (600 s, not overridden for greedy), sandboxes created by cold starts persist, and the plan's `w` is a **floor** (`warm_pins`, `cache.py:207-208`). The miss probability is `B(max(w, reactive pool), a)`, not `B(w, a)`, so Stage B **overstates** its gains. Either run v2 with `warm_ttl_s` = the histogram window, or say Stage B sets a floor. This also predicts that Stage B will gain little over greedy. Note that greedy is less wrong than `planner-v2.md:16-18` says: it caps units at the Poisson 95% quantile and averages the value over them (`planning.py:107,120-121`), a step approximation of the Erlang curve. |
| B3 | Snapshots in the same heap (`:103-107`) | Joint value `λ[τ_b − B(w)(τ_b − 1{s}(τ_b−τ_r))]`: warm and snapshot are **substitutes** (jointly submodular, not separable), and they use different resources | Two passes, or one price per resource. No optimality claim. |
| B4 | Churn: "use the expected number of survivors" (`:109-111`) | `B(E[W]) ≤ E[B(W)]` by convexity, so this is **optimistic** | Use the survivor distribution (the same convolution as Stage A). |
| D1 | Drift-plus-penalty: O(1/V) utility gap, budget met, queue O(V) (`:120-124`) | Neely's theorem assumes i.i.d. or ergodic random states, decision sets **independent of past decisions**, bounded second moments, Slater feasibility, and a per-slot problem solved exactly or within an **additive** constant | **Mostly fails.** Key holdings and warm state persist and switching costs couple rounds; the per-round solve is only (1−1/e)-approximate (multiplicative); a run has about 30 rounds. **What does hold**, for every sample path: `(1/K)Σ_k E_t(k) ≤ E_t^max + Q_t(K)/K`. Claim that, and report `Q_t(K)/K`. Weight rounds by their duration (event-triggered re-plans make rounds unequal). |

### 2.2 What the paper may state (proposed wording)

- **Model 1 (loss model; literature).** *If tenant `t`'s requests arrive as a Poisson process of rate `λ_t`, each holds a
  slot for a mean `s_t`, and a request that finds all `C` slots of `t`'s key holders busy is served on the slow path at
  extra delay `Δ_t`, then the slow-path fraction is `B(C, λ_t s_t)` whatever the service-time distribution
  [Sevastyanov 1957].* Then add: "We use this as a planning model. Our arrivals are bursty, slots are shared and placement
  may queue; Section X measures the outcome directly."
- **Proposition 1 (ours, one-paragraph proof).** *Let `c_tj ∈ ℕ` be fixed and `X_j ∈ {0,1}` any random survival
  indicators whose joint law does not depend on `S`. Then `U_t(S) = λ_tΔ_t E[1 − B(Σ_{j∈S} X_j c_tj, a_t)]` is
  normalised, monotone and submodular.* (State explicitly that correlated failures are allowed.)
- **Proposition 2 (literature, applied).** *For one tenant, a fixed ground set of eligible workers and at most `k`
  holders, distorted greedy returns `S` with `U_t(S) − κ_t(S) ≥ (1−1/e)U_t(O) − κ_t(O)` for every feasible `O` with
  `|O| ≤ k`, where `κ_t` is the non-negative modular cost (exposure, memory, amortised prepare)* [Harshaw et al. 2019].
  Then add: "Tenants are processed in priority order on the remaining capacity, and the domain cap and the
  sacrificial buffer are applied as heuristics; we give no guarantee for the joint plan, and instead report the gap to
  the exact MILP (E04)."
- **Proposition 3 (literature).** *For the pooled warm-sandbox problem with equal sandbox sizes, marginal allocation on
  the Erlang-B gains is optimal; with unequal sizes it is within one sandbox's gain of optimal* [Fox 1966]. Then add:
  "Packing onto workers can lose more; we report the packing loss."
- **Remark (sample path).** *Under the exposure price, the time-average exposure exceeds the budget by at most
  `Q_t(K)/K`.*
- **Proposition 4 (amortisation; renewal–reward; ours, elementary).** See §3.
- **Drop:** "strongest known guarantee"; any approximation constant for robust selection; "within O(1/V) of optimal";
  "the planner has a (1−1/e) guarantee" without the per-tenant qualifier; "the robust buffer covers correlated losses"
  (it covers the worst case of any `f` removals, which is a different statement); "makes no probabilistic assumption"
  (C-13, `scheduling.tex:102-103`).

### 2.3 Do the inputs in `PlanInput` and `planning.py` support the model? Mismatches

| Needed | Available | Gap and fix |
|---|---|---|
| `λ_f` per function | only inside `fn_benefit` and `fn_units` (`planning.py:106-107`) | Add `fn_rate` from `demand.rate["fn:…"]`. |
| `s_f`, `s_t` (slot hold time) | `forecaster.service` holds **execution time only** (`scheduler_role.py:356-357`); tenant default 1.0 s if unseen (`arrivals.py:79`) | Slot hold time = start-up + input transfer + execution. Under-estimating it makes `a` too small and B optimistic. Add `fn_hold` = EWMA of (finish − slot acquisition), or at least execution plus the mean start-up. |
| `Δ_t` (slow-path delay, s) | `cold_penalty = 10.0` constant, unitless (`planning.py:101`); the scheduler has the measured price `Prices.cold_trust` (D-33, `scheduler_role.py:91`) | Pass `Prices.cold_trust` (+ cold start) as `delta_t` in seconds. |
| `τ_boot`, `τ_restore` per function | `saved = rootfs/500 + boot + init`, with a hard-coded 500 MB/s (`planning.py:120`); no restore time | Take both from the same cost card the placer uses; tag the 500 MB/s `# TODO verify` or remove it. |
| `E[min(L_j, T)]` (residence) | only `S_j(H)` at H = 60 s (`planning.py:80`, `types.py:44`) | Add `residence[J]` = ∫₀ᵀ S_j(τ)dτ from the same Weibull model (closed form via the incomplete gamma, or 20-point quadrature) in `planning.py`. The layering contract is fine. |
| Integer `c_tj` per holder | `cap` (float slots); greedy uses fractional `c` | Rule: `c_tj = min(cap_j, ⌈a_t⌉ + 1)`, or a candidate set of `{1, 2, cap_j}` per (t, j). Must be fixed before Stage A. |
| `k` per tenant | absent | Default `k = |eligible|`, or `⌈2(q_t + f_t)⌉`. Document it. |
| `p_j` semantics | per-request drop probability (`types.py:45`) | See A1′. |
| Exposure budget `E_t^max` | absent from `configs/tenants.yaml` | Add a field (data, not code); default = per-tenant exposure measured for `keepalive_ttl` in E04 v1 (§4.2 H14′). |
| Measured exposure for DPP | `view.trust` (all keys, including on-demand), `view.pinned` (planned) | DPP must use `view.trust`. |
| Plan reuse | `planning.py:171` skips the planner | DPP queue update must run every round; or add `Q` to the signature. |
| Ablation flags | `use_robust`, `use_exposure`, `use_domain_cap`, `use_freshness` (`types.py:28-31`; `configs/ablations.yaml:5-7`) | v2 must honour all four, or E19 is meaningless for v2. |
| Rate bias | rate = max(60 s EWMA, 15 min EWMA): deliberately high | State that `a_t` is biased upwards, so Erlang sizing is conservative. |
| Decision clock | modeled as `0.02 + 5·10⁻⁵ × (4T+2F)J` (`planning.py:182`) | Variable count is meaningless for v2; see §4.5. |

### 2.4 Implementation notes that affect correctness

- Lazy evaluation is valid with distorted greedy if the cache stores the **raw** gain `ΔU` and the current weight is
  applied at comparison time. Because the weight `(1−1/k)^{k−i−1}` grows with `i`, a stale `ΔU` is still an upper bound.
- Return the better of (distorted greedy) and (plain greedy on `U − κ`, stopping at a non-positive marginal). The
  maximum keeps the guarantee and is usually better in practice.
- Test "submodularity of `U_t`" with **correlated** survival too (Proposition 1 claims it).
- Exact `E[B(C)]`: support ≤ Σ`c_tj` ≤ 40×slots; incremental convolution per added holder; removing a holder (for the
  robustness certificate) is a deconvolution, which is numerically unstable. Recompute from scratch for the ≤ 1365
  subsets instead.

---

## 3. Session-spanning state: a formulation that survives review

**The trap.** "A key release serves every request for the rest of the session, so its value is `λ·Δ·E[remaining
session]`" is true, but it is true for a **reactive** policy too. In VOSS a key fetched on demand stays until the session
ends (`worker_agent.py:322`; it is dropped only by a planner `RELEASE`, `workerlib/planned.py:170`). TTL policies capture
that value. What only a planner captures is:

1. **Foresight.** The prepare cost `c_prep` is paid off the critical path. A myopic per-request rule compares a holder
   (no Δ) with a non-holder (Δ now) and never invests Δ now for value later.
2. **Selection by residual life.** With Weibull shape < 1 the residual session grows with age, so choosing holders by
   `E[min(L_j, T)]` lowers the rate at which holders must be replaced. Placement chooses by the current request's miss
   probability, not by amortisation.
3. **Set sizing and robustness.** How many holders, and covering `f` losses.

**Proposition 4 (renewal–reward amortisation).** *Let worker `j` with age `x_j` hold `t`'s key from now until its
session ends or the tenant stops being hot, `R_j = min(L_j, T_hot)`, where `L_j` is the residual session, independent
of demand. If `j` serves a share `π_j` of `t`'s requests that would otherwise take the slow path, the long-run delay
saved per second by holding the key is `π_j λ_t Δ_t (1−p_j)`, and the cost per second is
`σ_t(1−a_j) + ρ_mem m_t c_tj + c_prep / E[R_j]`. Holding is worthwhile iff*
`E[R_j] ≥ c_prep / (π_j λ_t Δ_t (1−p_j) − σ_t(1−a_j) − ρ_mem m_t c_tj)`.
*For a Weibull residual session of shape `k`, scale `η`, `E[R_j] = ∫₀^{T_hot} exp(−((x_j+τ)/η)^k + (x_j/η)^k) dτ`,
which increases with age `x_j` iff `k < 1`.*

This gives the paper three sentences that a TTL policy cannot match: the planner (a) pays `c_prep` before demand,
(b) ranks workers by `c_prep/E[R_j]`, so machines that have been up longer are cheaper key holders, and (c) declines
keys on machines whose expected residence is below the break-even. It also gives the model term (§0.5).

**Consequence for the experiment (and a correction to decision 3).** The planner's advantage over a reactive policy is
roughly `Δ_t × (holder replacements per second avoided)` minus wasted investments. Replacements scale with `N_t/E[L]`, so
the advantage **does not grow monotonically with session length**:
- very long sessions: churn → 0, the reactive policy pays Δ once per holder and then matches the planner (E10's
  dedicated pool is the closest test, and there the planner still won, an anomaly to explain);
- very short sessions: `E[R] < c_prep/(λΔ)`, so investments do not pay back and the planner should decline;
- in between: maximum advantage.

Pre-register an **inverted U** in the session-scale sweep, not "grows with session length". Pre-register that the
selection effect (2) **vanishes at Weibull shape k = 1** (memoryless: age carries no information).

**Cheapest decisive test.** A `survival_blind` ablation: run the default planner with `survival` and `residence`
replaced by their cluster means (one switch in `PlanParams`). If the P99 gap to `histogram_prewarm` survives intact,
knowing session survival is not what the planner exploits, and decision 3 must be dropped from the lead claims.

**Also do (analysis, no simulation).** One small figure of break-even `E[R]` against `λΔ` with the calibrated
`c_prep`, with the measured session distributions of the three churn tiers overlaid. It shows where key planning can pay
at all.

---

## 4. Experiment plan

### 4.1 Are H12–H14 fair, pre-registrable and powered?

| Hypothesis | Problem | Fix |
|---|---|---|
| H12: greedy beats `histogram_prewarm` by ≥5% | Rigged (§0.2); ignores that greedy uses 2.7× exposure and 1.5× memory; at 10 seeds the MDE of greedy against keep-alive is 32% (medium) and 61% (high) because single-loop P99 is heavy-tailed across seeds | **H12′**: default VOSS against the **best single loop per regime** (min P99 over `keepalive_ttl`, `keepalive_inf`, `histogram_prewarm`, selected on pilot seeds 21–25, tested on 1–20): ≥10% lower P99, plus **H12b** against `provisioned_keys` at matched exposure: ≥5%. Report per-seed ratios, the median ratio and a Wilcoxon signed-rank test besides the mean. |
| H13: `erlang_greedy` beats greedy by ≥5% | Underpowered (§0.8); Stage B gain overstated (B2) | **H13′ non-inferiority** (the adoption rule) + H13″ superiority (secondary, expected inconclusive). |
| H14: `erlang_dpp` meets its budget | Close to a tautology if measured on planned exposure; the budget value is not specified | **H14′**: budget = per-tenant exposure of `keepalive_ttl` in E04 v1 (known now, so pre-registrable). (a) measured time-average exposure, including on-demand keys, ≤ 1.1 × budget; (b) `Q_t(K)/K` ≤ 10% of budget; (c) P99 ≤ 0.95 × best single loop. This is the iso-exposure question every reviewer asks, and it turns `erlang_dpp` from decoration into the answer. |
| H15 (new): session | — | Inverted U over session scale; the selection effect is zero at k = 1; `survival_blind` loses ≥50% of the gap at k ≤ 0.7. |

Correct H12′–H15 with Holm across the family. Primary metric: synchronous P99. Pre-registered secondaries with lower
variance: mean synchronous latency, deadline-met share, trust-cold share, warm GB, exposure, **distinct key holders per
hour** (§6, O8).

### 4.2 Final E04 (v2)

1800 s horizon, 300 s warm-up, 200 workers, 10 inv/s, `churn_med` and `churn_high`, **20 seeds** (1–20).

| System | Note |
|---|---|
| `plan_none` | reference |
| `keepalive_ttl` (600 s) | existing |
| `keepalive_inf` | new, config only |
| `histogram_prewarm` | WP1, fixed per §1.2 |
| `provisioned_keys` (exposure matched to greedy) | new baseline |
| `plan_greedy` | existing |
| `plan_milp` | 10 seeds only (cost); charged its solve time (§4.5) |
| `erlang_greedy` | WP2 |
| `erlang_dpp` (budget = keep-alive exposure) | WP2 |

Run count: 8 × 2 × 20 + 1 × 2 × 10 = **340 runs** (E04 v1 had 80). A third regime (`churn_low`) adds 170; I would skip it
and rely on E25 for the session dimension.

### 4.3 What must be rerun if the default planner changes

The default is set in `configs/pilot.yaml:10` and inherited by every experiment based on it. If `erlang_greedy` becomes
the default: **E05, E06, E07, E08, E10, E13, E14, E15, E16, E17, E18, E19, E20a–c, E24** inherit it (rerun all); E04 is
rerun anyway; **E23** pins `milp` (`E23.yaml:9`) and must move to the default planner, otherwise the trade-off front
describes a planner the paper does not use. `exposure_weight` must keep its meaning in v2 (`σ_t` multiplier). E09 pins `greedy` (`E09.yaml:10`): switch it
or keep it as a deliberate greedy-only experiment. E24 pins only its baseline. E01, E03 and E12 are unaffected. This is the full `paper-rerun`, about 2,400
runs: compute cost, not scientific risk. It is the reason to prefer the non-inferiority rule: the paper's planner
section will present v2's math, and results produced by greedy would contradict it.

### 4.4 New experiment E25: session length and shape (small)

- E25a, session scale: one churn tier (`scenario.tiers={idle: 1.0}`), Weibull length scaled by
  s ∈ {0.25, 0.5, 1, 2, 4} (five regime YAMLs, data only), 1800 s, 10 seeds; systems `histogram_prewarm`,
  `provisioned_keys`, `plan_greedy`, `erlang_greedy`, `erlang_greedy+survival_blind` → 5 × 5 × 10 = **250 runs**.
- E25b, shape at fixed mean: k ∈ {0.5, 0.7, 1.0}, systems `histogram_prewarm`, `erlang_greedy`,
  `erlang_greedy+survival_blind` → 3 × 3 × 10 = **90 runs**.
- Report the absolute P99 gap and the mean delay saved per request against s, with paired CIs. One figure.

Total new runs for round 4: 340 + 340 = **680**, plus the 2,400-run full rerun if the default changes.

### 4.5 Should measured solve time be charged?

Yes for the planner comparison, but reproducibly. Measured wall time breaks bit reproducibility (doc 01 §8). Instead,
measure each planner's solve time against instance size once (E02-style, recorded as a calibration bundle with its
hash), fit `a + b·size` **per planner**, and run E04 v2 in modeled mode with those coefficients. Use a size measure
that fits each planner: `(T, F, J)`, not the MILP's variable count. Effect: ≈0 for the greedy family (ms against a 30 s
period, under 0.1%); 4–24 s of staleness for the MILP, which is what C-16 asks for. State in the paper what is charged.

---

## 5. A 25-page outline (acmsmall, references included)

Section budget (pages). Changes against WP4 (`PLAN-ROUND4.md:84-86`) are shown in brackets.

| § | Content | Pages |
|---|---|---|
| 1 Introduction | problem, why trust changes cold start, two loops, 5 claims, results in one paragraph | 1.5 |
| 2 Background and problem | where the time goes (Fig. cost, half width); volunteer churn (one paragraph with the Weibull evidence); attestation in **one paragraph + citations** (TPM quote, Keylime, KBS); problem statement | 1.3 [−0.2] |
| 3 Design | parties, what the provider stores, two architectures (one combined figure with the broker), sessions, life of an invocation; threat model as **4 bullet lines** (no table); exposure definition | 2.5 [−0.5] |
| 4 Scheduling | why two loops (Table horizons: keep it, it carries the argument) 0.7; loss model + Propositions 1–3 + algorithms (pseudo-code box, 12 lines) 1.8; session-spanning state, Proposition 4 + break-even figure 0.8; exposure budget remark 0.3; placement 0.6; estimators 0.6; clusters and routing 0.2 | 5.0 |
| 5 Reaching a volunteer scheduler | broker, NAT, why volunteer-hosted (C-31) | 1.0 [−0.5] |
| 6 Failures | judging by returned work; succession without agreement; receipts (2 sentences) | 1.5 |
| 7 Method | simulator, calibration, protocol (paired seeds, pre-registration, Holm), reproducibility (one paragraph; appendix A goes to the artifact) | 1.3 [−0.2] |
| 8 Results | §8.1 is the planner needed: Pareto figure (P99 against exposure, both regimes, all 9 systems) + small table 1.6; §8.2 session-spanning state: E25 figure 0.8; §8.3 ablations (Fig. ablation) 0.6; §8.4 returned-work detection (inline numbers from E08 and E15; one compact table) 0.8; §8.5 robustness and exposure trade-off (merge E23 into the §8.1 figure) 0.3; §8.6 what does not pay (geo, caching, hedging) 0.5; §8.7 feasibility (Fig. viability panel A only) and commercial reference, scale, calibration sensitivity, one paragraph each 0.9 | 5.5 [+0.5] |
| 9 Related work | serverless cold start (keep-alive, histogram, FaasCache, snapshots, provisioned concurrency), volunteer computing, confidential serverless, two-timescale edge placement, submodular and robust placement | 1.0 |
| 10 Discussion and limits | threats to validity, scope of claims | 1.4 [−0.1] |
| 11 Conclusion | | 0.3 |
| References | about 60 entries | 1.7 |
| **Total** | | **24.5** (0.5 slack for float placement) |

**Cut:** attestation figure (`trust.tex:60`); threat table (`trust.tex:17`); failover diagram (`faulttol.tex:53`);
separate loops diagram (merge into the architecture figure); `tab_adversary` (inline 3 numbers); viability panels B and
C (one sentence each); hypothesis scorecard and appendix A (to the artifact); trust-technology details beyond one table
row each.
**Expand:** planner model and propositions; session-spanning state; baselines (§8.1); the per-seed honesty about tails.
**Figures and tables that survive (7):** Fig. cost (half width), Fig. architecture+broker, Table horizons, Fig. planner
Pareto (new), Fig. session sweep (new), Fig. ablation, Fig. viability A; plus small Table planners and Table faults.

**Five lead claims** (conditional on round-4 results; reword if a hypothesis fails):
1. On volunteer machines with attestation, start-up cost is dominated by per-session trust (reboot, attestation, key
   release) that is paid once and amortised over a donation session, so cold-start management becomes a problem of
   placing **trust and session state**, not only of timing keep-alive.
2. Decisions that last a session and are properties of a set (who holds a key; robustness to `f` losses; exposure)
   belong on a slow loop. We give a loss-model planner whose per-tenant subproblem is monotone submodular minus modular,
   with a (1−1/e) guarantee per tenant and an exactly certified robustness level.
3. Against the strongest single-loop policies (adaptive histogram keep-alive, unbounded keep-alive) and against keys
   provisioned ahead on the most reliable machines at equal exposure, planning lowers synchronous P99 by X–Y% under
   churn. The gain comes from foresight and from choosing long-lived holders (survival-blind ablation; it vanishes for
   memoryless sessions).
4. Exposure can be budgeted: at the exposure of a keep-alive policy, the budgeted planner keeps Z% of the latency gain.
5. Judging machines by returned work makes attested owners who drop work behave like churn (success V% at α = 0.2
   against W% with heartbeats), and schedulers can be replaced without an agreement protocol.

---

## 6. The ten reviewer objections that will remain after round 4

| # | Objection | Strongest defence | Needs |
|---|---|---|---|
| O1 | Simulation only, calibrated on one laptop (C-24) | E01 validates start-up and execution against measurements; E24 shows planning's advantage grows under measured parameters; the simulator charges every delay | Text (scope the claims to relative comparisons) |
| O2 | Toy workload: 6 tenants, 12 functions, MMPP, no traces (C-14, C-21) | The hot-set limits and the per-tenant structure are stated; the loss model needs only rate and mean | **Experiment if any budget remains**: a 100-tenant Zipf workload, or a replay of a slice of the Azure Functions 2019 trace (config + loader); at least report the cold-path share of tail tenants |
| O3 | The planner buys latency with 2.7× exposure and 1.5× memory | `provisioned_keys` at matched exposure (H12b) and `erlang_dpp` at keep-alive exposure (H14′) | Experiment (in E04 v2) |
| O4 | The headline gain is 3 of 10 seeds | Per-seed reporting, median ratio, rank test; mechanism breakdown of those seeds (shocks? bursts?); the planner's value *is* tail robustness under correlated loss, which is what Proposition 1 and the robust buffer target | Analysis (tail breakdown) + text; 20 seeds |
| O5 | The theory does not cover the implemented system (shared slots, queueing, bursts, buffer, domain cap) | Per-tenant propositions stated with their assumptions; certificates (robust utility, packing loss) and the MILP gap measured empirically | Text (the §2.2 wording) |
| O6 | Too many hypotheses, too few seeds, inconclusive verdicts (H2, H6, H8, H-FT3) | Pre-registration, power computed from v1 pairs, Holm correction, inconclusive results reported as such | Text + 20 seeds in E04 |
| O7 | Supply premise: donation needs a reboot; consumer RAM is physically attackable; a volunteer-hosted scheduler (C-06, C-08, C-31, C-32) | Scope to scheduled or dedicated donors and software-level adversaries; confidential VMs as the alternative trust technology (already measured); the provider-hosted option is discussed | Text |
| O8 | Exposure is an arbitrary score; a time average rewards rotating keys over many machines (C-11) | Report **distinct holders per tenant per hour** next to time-average exposure; Proposition 4 favours long-lived holders, which also lowers distinct holders; show the result under a second trust-score table. `scheduling.tex:14` says a release "cannot be undone", yet the metric drops released holders: fix one of the two | Analysis (from existing logs) + text |
| O9 | Economics: never faster than the Lambda-like reference, cost-competitive only above about 20 inv/s (C-25) | Say plainly that the contribution is feasibility and scheduling under churn and trust, not beating the cloud; give the cost crossover | Text |
| O10 | Short runs (900–1800 s) against sessions of hours; the decision clock is modeled (C-12, C-16) | E25 sweeps session scale relative to the horizon; per-planner refitted decision clock (§4.5); a 2 h run of the default against the best single loop for 5 seeds as a steady-state check (20 runs) | Experiment (small) + text |

Not in the top ten but should get one sentence each: idempotence as a product contract (C-09, C-10), planning period
not swept (C-12), geo-clustering refuted (already reported honestly).
