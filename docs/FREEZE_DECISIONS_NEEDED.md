# Decisions needed before the scheduler freeze (plan V11.4)

Prepared on branch `v2/V11-freeze-prep` from the repository alone. Each item is a constant or a design point that the
repository cannot settle: no calibration bundle, trace statistic, checked citation, derivation in code or experiment
axis supports a value. Every item lists the ledger rows or code it covers, the options, what each costs, and a
recommendation. Answer each with its letter (for example "1A, 2B, ..."); the answers become decisions in
`docs/DECISIONS.md` and the rows leave *pending* in `docs/PARAMETERS.md`.

"Dev rerun" means one rerun of `D01a` (development split, central cell) after the change, as a bug fix or an
iteration of V11.3 (two of the five iterations are used, `docs/validation/development-log.md`). A change that alters
VOSS's decisions must happen before the `v2-freeze` tag; after the tag only listed bug fixes are allowed.

Items 1-16 are constants; items 17-22 are about the held-out specs and what the freeze needs.

## Constants

### 1. Placement weights (T47)
Rows: `voss.cost.eps` 0.05, `voss.cost.sync_weight` 1.0, `voss.cost.scalarizer`, `voss.cost.lambda_exposure` 1.0,
`voss.cost.sigma`; the hard-coded 0.3 of `slo_weight` (`voss/policy/cost/components.py`). Placement minimises
`w·pMiss + ε·E[C] + λ·exposure` (`voss/policy/cost/scalarize.py`), with `w` 1 for synchronous and 0.3 for
asynchronous invocations. The exposure term is v1's: `σ_tenant · (1 − assurance)` for a candidate that does not hold
the key (`components.py`), still non-zero today. `ε` also sets the load step of batched asynchronous placement
(`runtime/schedlib/decide.py`). The plan (§2, §3 table) says "no weights; lexicographic tie-break".
- **A. Lexicographic.** Lowest `pMiss`, ties to the lowest `E[C]`; delete `eps`, `sync_weight`, `scalarizer`,
  `lambda_exposure`, `sigma` and the 0.3; the batch load step uses the slot's mean service time. Cost: a code change in
  `policy/cost`, every system's placement changes (shared code), one dev rerun; the paper's eq. (place) loses both
  weights. Synchronous invocations already come first in a batch, so the 0.3 has no replacement.
- **B. Keep the weights as S.** Ledger S, R07 varies `ε` ×0.5/×2 and the asynchronous weight {0.15, 0.6}; the
  exposure term is still deleted (the plan removes exposure). Cost: four more R07 variants (40 runs); a lift of the 0.3
  into config; the paper justifies two weights.
- **Recommendation: A.** It is what the plan states, it removes three ledger rows and a hard-coded constant, and
  `pMiss` ties are common (warm holders with `pMiss` near 0), so the tie-break does the work `ε` did.

### 2. Drop-estimate constants (T48)
Hard-coded in `BetaCusum` (`voss/policy/omission.py`): prior `(a0, b0)` = (0.5, 20) (prior drop rate 2.4%),
pessimistic prior (2, 4) after a change point, CUSUM drift `k` 0.1. `voss.models.cusum_h` 5 and
`voss.scheduler.max_attempts` 3 are already S.
- **A. Config keys, class S, swept.** Add `voss.models.omission_prior`, `omission_pessimistic`, `cusum_k`; R07
  varies the prior's strength (`a0 + b0` ×0.5/×2 at equal mean) and `k` {0.05, 0.2}. Cost: small code change; six R07
  variants (60 runs).
- **B. Derive `k` from Page's rule.** `k = (p0 + p1)/2` with `p0` the prior mean and `p1` the pessimistic mean
  (0.024, 0.33 → 0.18): D, no sweep for `k`; the two priors stay S as in A. Cost: as A, one fewer variant, and `k`
  changes from 0.1 to 0.18 (dev rerun).
- **Recommendation: A** (no behaviour change before the freeze; the sweep shows whether `k` matters).

### 3. Placement candidate cap
Row `voss.placer.K` 12 (pending V5, "removed: all holders are candidates"). It still keeps the 12 best candidates by
a lower bound (`policy/cost/components.py`, `prune` keeps 36 before that). With `K` ≤ 8 every holder survives; at
`K` 16 and unbounded, and for non-holder candidates, it cuts.
- **A. Remove the cap.** Cost: placement scores every eligible worker; the measured place coefficient is 0.25 µs per
  candidate pair (V10), so 500 candidates add about 0.13 ms per decision; one dev rerun at `K` 16.
- **B. Keep 12 as S.** R07 varies it {6, 24}. Cost: 20 runs; the paper says placement sees 12 candidates.
- **Recommendation: A**, as the plan says.

### 4. Planning-pool caps
Rows `voss.planner.max_plan_workers` 40, `hot_top_k` 20, `hot_fn_k` 50 (pending V5, "removed: all live workers are
planned"). VOSS's provisioning (`hetero`) sees at most 40 workers, chosen by slots × the v1 assurance score with
previous holders first (`runtime/schedlib/planning.py`), out of 500; at most 20 tenants and 50 functions.
- **A. Remove the caps.** Every live attested worker and every function above `min_rate` is planned. Cost: plan time
  is charged at 40.7 µs per decision variable (V10); 500 workers × 65 active functions is about 1.3 s per round
  against a 30 s period; one dev rerun; the assurance score leaves the scheduler.
- **B. Keep them as S.** R07 varies them ×0.5/×2. Cost: 60 runs; the heterogeneity claim then holds for a pool
  pre-filtered by a v1 score, which the paper must state.
- **Recommendation: A.** The core contribution (plan §11) is the choice among heterogeneous workers; a 40-worker
  pre-filter by another rule undercuts it.

### 5. Synchronous-first queueing and the per-worker wait model
Rows `voss.worker.sync_priority` False, `voss.cost.wait_model` `ewma` (pending V5). The plan (V5.2, §3) says
synchronous invocations are served first on every worker in every system and that per-worker queue replay is the only
wait model; D01-D03 ran with both defaults (off, `ewma`), and R06 lists "synchronous-first" as an ablation.
- **A. Turn both on for every system** (base config), delete the `ewma` model, one dev rerun; R06 then ablates
  `sync_priority`. Cost: one dev round, a shared-code change for all systems.
- **B. Keep FIFO and `ewma`**, delete both options and drop "synchronous-first" from R06 and the plan (guardrails 25,
  32). Cost: none in runs; the design loses a mechanism.
- **Recommendation: A** if the dev round is available, since the plan's design has it; otherwise B. Until answered,
  the R specs leave both at their defaults and R06 has no synchronous-first variant.

### 6. Start-up price priors
Rows `voss.router.cold_penalty_s` 3.0, `voss.router.cold_fn_s` 0.5 (pending V5): the scheduler's prior start-up
prices before it observes any, smoothed with the hard-coded 0.05 (`runtime/schedlib/prices.py`).
- **A. Derive them from the reference bundle** (D): the measured attestation + key release + boot of the startup
  model, and the measured cold function start. Cost: code change, dev rerun.
- **B. S, swept** ×0.5/×2 in R07. Cost: 40 runs.
- **Recommendation: A.** The bundle has the values; a prior from it is not a free choice.

### 7. Retry backoff
Row `voss.scheduler.retry_backoff_s` 0.2 (pending V7, "replaced by backup attempts"). Still the delay of a retry
(`BasicRetry`), which the `fixed` and `consecutive` detectors use.
- **A. S, swept** {0.1, 0.4} in R07. Cost: 20 runs.
- **B. 0** (retry at once, as a backup is). Cost: dev rerun of D02_DROP's baselines.
- **Recommendation: A** (a client backoff is the retry baselines' standard mechanism, guardrail 18).

### 8. Image memory reserve
Rows `voss.worker.m_base_mb` and `voss.planner.params.m_base_mb`, both 512 (pending V5). D-103: unmeasured until a
node boots the real image; V5 must measure it or state it as a limit.
- **A. Measure** on the bare-metal visit (V13) and take the reference's value (M). Cost: waits for the visit.
- **B. State it as a build parameter** of the image (A), varied {256, 1,024} in R07. Cost: 20 runs, one sentence in
  the limits.
- **Recommendation: B now, A if V13 measures it before the freeze**; in both cases merge the two keys into one.

### 9. Correlated failures in provisioning
Row `voss.planner.domain_shock_p` 0 (pending V9, "estimated from the availability trace"). No estimator exists; at 0
the planner assumes independent failures, so the §11.7 ablation "independent failures" equals VOSS.
- **A. Estimate it** from the seti09 development split (share of provisioning horizons in which a city loses more
  than one host at once): D. Cost: an analysis script and a definition; dev rerun.
- **B. Delete domain shocks** from the planner, the design text and R06 (guardrails 25, 32). Cost: the paper drops
  the correlated-failure part of the reliability model.
- **Recommendation: B** unless the author wants the correlated-failure claim; the trace has no failure domains
  beyond city, and backups already go to another owner, city and ISP.

### 10. Function catalogue
Data file `configs/functions.yaml` (pending V1/V9). With a measured bundle run times come from the bundle, but the
catalogue still supplies `mem_mb` (it sets a fleet worker's slots, D-108: node04 gets 4), `slo_k` (deadline
multiple), `idempotent`, `in_sigma` (unused with `exec_by_size`, D-105) and sizes.
- **A.** `mem_mb` = the guest memory the image gives each Firecracker sandbox (a build parameter, A, stated);
  `slo_k` and the idempotent fraction become axes with config keys (plan §3: {2, 5, 10} and {0, 0.5, 1}) and R07
  variants; `in_sigma` deleted. Cost: two new keys and their plumbing; R07 +4 variants (40 runs).
- **B.** Keep the catalogue values and state them as literature placeholders. Not allowed for reported results
  (guardrails 28, 29).
- **Recommendation: A.**

### 11. Session certificate and attestation messages
Data file `configs/substrates/appliance_tpm.yaml` (pending V4): `reattest_every_s` 600, `valid_s` 900 (D-95: how long
a departed machine keeps its places in the budget), message sizes 6/2/4/1/2/1 KB, `assurance_base` 0.80 (v1 exposure).
- **A.** `valid_s` and `reattest_every_s` are A (the verifier's policy), varied {300/450, 1,800/2,700} in R07;
  message sizes D from the quote and certificate formats; delete `assurance_base`. Cost: 20 runs; a short derivation.
- **B.** Keep the values as S. Cost: the same runs, a weaker statement.
- **Recommendation: A.**

### 12. Owner behaviour parameters
Data files `configs/regimes/adversary_*.yaml` and `AdversaryParams` (tagged assumed): `omit_p` 0.5, on/off 1,800 s
good / 600 s bad, `throttle_f` 0.3, `forge_p` 0.5 (R05 axis {0.5, 1}), `start_t` 0.
- **A.** Class A: they describe the threat, are stated with R04/R05, and the paper's claims are worded for them;
  delete the regimes no spec uses (`adversary_collude`, `adversary_mixed` if R04 uses single strategies). Cost: none.
- **B.** Sweep each in R04. Cost: R04 grows by a factor of 2-3.
- **Recommendation: A.**

### 13. Constants in code that are not keys
Listed in `docs/PARAMETERS.md` ("Constants in code"): the time-to-start variance `(0.3 tts)²`, `HEDGE_MIN_SAMPLES`
20, the run-time prior standard deviations (0.7, 0.3, 0.5), the price smoothing 0.05, `OVERDUE_FRAC` 0.25.
- **A.** Lift each into config as S with an R07 variant (×0.5/×2). Cost: five keys, 100 runs.
- **B.** Lift them as S, but sweep only the two that enter VOSS's timer and placement (`0.3 tts`, `OVERDUE_FRAC`);
  state the others in the ledger (the run-time priors wash out after a few observations, the hedge threshold is the
  baseline's warm-up). Cost: 40 runs.
- **Recommendation: B.**

### 14. Hybrid-histogram limits
Rows `voss.keepalive_hist.min_samples` 10, `oob_max` 0.2 (pending V8, "check against the paper"). The repository has
no checked citation for them (`docs/validation/LITERATURE_START_COSTS.md` covers start-up costs only).
- **A.** Check Shahrad et al. (ATC 2020, §4.2): if the paper gives them, L; otherwise list each as a deviation in
  `configs/baselines.yaml` and class S. Cost: reading one section.
- **Recommendation: A.**

### 15. Trusted always-on hosts
`configs/references/trusted_hosts.yaml` runs on `configs/hardware/DC.yaml` (pending V9; not a calibrated machine) with
40 hosts per router metro (tagged assumed).
- **A.** The hosts are the reference machine (node02, NVMe bundle) and their number is the R01 pool's slot count
  divided among the three metros (D, equal capacity, guardrail 16). Cost: config change; R09 is then an upper bound at
  equal capacity.
- **B.** Keep DC and 40 per metro, stated as an assumed upper bound. Conflicts with guardrails 28-29.
- **Recommendation: A.**

### 16. Tenant template
Data file `configs/tenants.yaml` (pending V9): trace tenants take the first tenant's settings (`world/trace_load.py`);
`max_holders` is overridden by the `K` axis; `sensitivity`, `assurance_floor` and `f` are v1 (exposure, trust
scores, the v1 cover rule).
- **A.** Reduce the file to what v2 reads (`kbs_city`, the default `max_holders`) and delete the rest. Cost: code and data
  change with items 1 and 4.
- **Recommendation: A.**

## Specs and freeze

### 17. R03 pool sizes
The plan asks {100, 300, 1,000, 3,000 if V9.5 allows}. D-97: 1,000 workers do not fit one job at 28 h.
- **A.** {100, 300, 500} as D03 (`configs/experiments/R03.yaml` now). Cost: none; the paper states that the region
  map stops at 500.
- **B.** 1,000 and 3,000 with a shorter measured window (warm-up kept at 4 h, guardrail 23). Cost: a sizing run per
  size; cells with different windows in one figure.
- **Recommendation: A.**

### 18. R08 scale
The plan asks pools up to the V10 limit (about 9,000 workers at 0.1 invocations/s per worker). `R08.yaml` couples the
load to the pool (rate_mult 21 per 500 workers) at the D-97 duration, which does not fit one job above 500 workers.
- **A.** R08 is the V10 bench rerun on the frozen code (capacity per pool, no deadline metric), plus the 500-worker
  cell; delete the larger simulation cells. Cost: one bench run.
- **B.** Simulate 1,000-2,000 workers with a 4 h warm-up and a 4 h measured window. Cost: a sizing run; a shorter
  window than every other spec.
- **Recommendation: A.** The single-scheduler limit is a throughput limit (V10 outcome), which the bench measures.

### 19. R06 ablations without a mechanism
The plan's R06 lists variants that no configuration key expresses today: cover rule (`f` = 0), backup attempts off,
drop estimate off, synchronous-first (item 5), "one speed factor", "robust (worst case)" (§11.7), and "independent
failures" (no-op while item 9 is 0). `R06.yaml` has the ones that exist: homogeneous, binary, reliability-blind,
survival-blind, no warm sandboxes.
- **A.** Add a key for each remaining variant before the freeze (backup off: a detector profile without backups;
  drop estimate off: an omission model that returns the prior; one speed factor: the run-time model without the
  per-function machine factor; robust: the cover rule as a planner). Cost: four small code changes with unit tests.
- **B.** Drop them from the plan and the paper (guardrail 25).
- **Recommendation: A** for backup off and drop estimate off (they are VOSS's failure handling); B for the rest.

### 20. R07 sensitivity step
`R07.yaml` varies each swept constant VOSS reads ×0.5 and ×2 (integers rounded, quantiles to 0.90 and 0.99,
forgetting to 0.99 and 0.999), the rotation period `R` {1 h, 24 h}, and the machine mix (MilkyWay@home survey;
single-class fleets). Constants without a variant are listed with a reason in `tests/unit/test_r_specs.py`. Still
missing: deadline multiple and idempotent fraction (item 10), and "trace source fallback" (no second session or
arrival source exists).
- **A.** Accept the step and the exemptions. Cost: R07 is 51 variants × 10 seeds = 510 runs.
- **B.** One-sided steps or a smaller set. Cost: a weaker sensitivity table.
- **Recommendation: A.**

### 21. Final bundles
D-91 asks for at least three machines with the real image booted; the fleet has two (node02, node04; node01 is a
cross-check) and no node booted the real image (D-103). The plan's freeze needs final bundles (V11.5).
- **A.** Wait for the bare-metal visit (a third machine, the image boot) before tagging. Cost: calendar time.
- **B.** Freeze with the two-machine fleet and state it (and the unbooted image) in the methodology. Cost: D-91 is
  amended by a decision; reviewers may ask why.
- **Recommendation: A** if the visit is within weeks; otherwise B with the limitation stated.

### 22. Exact program
Rows `voss.planner.T_solve`, `node_limit`, `cold_penalty`, `f_from_alpha`, and every v1 objective weight in
`voss.planner.params` (`rho_mem`, `rho_ssd`, `kappa_switch`, `beta_warm`, `gamma`, `kappa_dom`, `use_exposure`,
`exposure_weight`) serve only the v1 planners `milp` (the exact program, left out of every spec) and `greedy`
(registered, used by no system).
- **A.** Rewrite the exact program as the MILP of VOSS's own objective (expected on-time rate under the holder budget,
  plan §11.6) for the offline optimality check on small instances, and delete `greedy` and every v1 weight. Cost:
  a new MILP formulation and its test.
- **B.** Delete the exact program, `greedy` and the weights; the optimality claim rests on Proposition 1's bound
  (`(1 − 1/e)` per function) and the brute-force property test. Cost: the appendix gap table goes.
- **Recommendation: B.** The brute-force test already checks the greedy against the optimum on small instances; a
  second exact solver for a different objective adds no claim.
