# Development log (plan V11.3)

Development split only; nothing here is a reported result (guardrail 31). At most five iterations, each with one
written hypothesis about a cause of misses or cost, one change, and a rerun of `D01`'s central cell (`D01a`). Bug
fixes found on the way are listed separately: they are not the iteration's change, and baselines get them too.

Local runs below: 500 workers, `churn_seti`, development split of every trace, bundle `i7_12700_64g_full-b4f89a4def`,
`K` = 8, rate_mult 21, seed 1, 2 simulated hours with a 10-minute warm-up (`D01a`'s settings except the horizon and
warm-up), one run per row on a 4-core machine. They are short and single-seed: they show the mechanism, the `D01a`
rerun measures it.

## Iteration 1: key churn in provisioning

**Observation (D01a, run 43758102523, 24 h measured).** VOSS released keys 1,571 times per hour, pre-released keys
58 and the autoscaler 110, with mean holders 3.4 against 5.8 for pre-released keys.

**Hypothesis.** Holders change almost every period because the provisioning objective is a sample average over
failure scenarios re-drawn every period: workers of near-equal value rank differently each round, and the current
holders win only exact ties.

**Evidence (local run, code of `revision-v2` at e39a793).** 2,217 of 2,590 key drops after the warm-up were planned
releases (373 were session ends), and 1,801 of 2,338 key releases went to a (key, worker) pair that had held that key
before: holders oscillate. Logging the busiest function's round: the chosen holders were the workers alive in 32 of
the 32 sampled scenarios; the current holders were alive in 29-31, with unit values within 0.02 of each other.
Common random numbers (scenario uniforms fixed per worker across rounds) did not reduce releases: 1,469 per hour
against 1,275, so sampling noise alone is not the whole cause; swaps of near-zero gain are taken whatever their source.

**Change (D-100).** Algorithm 1 also runs from the current holders and keeps that result unless the plain greedy's
on-time rate, less what its new holders lose while they prepare (`gain × prep / H`, `prep` from the measured startup
model), is larger. No new constant. Bound: `F ≥ (1 − max prep / H) · F(greedy)`; the median `prep / H` of
non-holders was 0.27 in the local run (H = 60 s). Over 200 rounds the plain greedy was never better than the kept
allocation by more than 0.003% of its value (median −0.04%: the incumbent's completion was usually the better of the
two).

**Result (local, 2 h).** Both rows include the two bug fixes below.

| System | Code | Deadlines met | Mean holders | Key releases / h | Episodes |
|---|---|---|---|---|---|
| voss | before the change | 0.945 | 3.47 | 1,306 | 115 |
| voss | swap rule | 0.958 | 5.52 | 356 | 68 |
| trusted_hosts | `revision-v2` | 0.699 | 0.94 | 1,102 | 277 |
| trusted_hosts | swap rule | 0.680 | 4.08 | 97 | 281 |
| prereleased_keys | `revision-v2` | 0.922 | 6.22 | 231 | 103 |

The trusted hosts lose 0.019 here: their misses are dominated by one function that misses on every host (tr0135,
7,454 misses in both runs), and the change moved mean network time from 0.16 to 0.23 s, which the provisioning model
does not include (it scores run time and deadline probability, not the distance to the router). Whether this holds
over 24 h is for the `D01a` rerun to show.

**Rerun.** `runs/requests/experiment/d01a-iter1.yaml` (9 runs, 9 shards). Result: pending.

## Bug fixes found in iteration 1 (apply to every system)

**Run-time model load term (all systems).** The predictor's load covariate was queue length per slot. With queues
of up to 2,700 per slot (eviction-aware placement), `x'Σx` gave σ up to 70 and `exp(σ²)` overflowed in
`LogDist.var`, and the completion model returned NaN (the RuntimeWarnings of the D01a logs). Queued work runs beside a
new invocation only up to the worker's slots, so the covariate is now `min(busy + queued, slots) / slots`. Local
effect on voss: deadlines met 0.925 → 0.945, no warnings in any run afterwards.

**`eviction_aware` was not the published algorithm (D-101).** It ranked workers by predicted failure probability and
used load only to break ties. Zhang et al. (SOSP 2021) balance load with min-worker-set (§5.2, Algorithm 1) and stop
sending to a machine warned of eviction; they do not rank machines by eviction probability. The old rule sent 48% of
attempts to one worker (11 workers in all), with a mean wait of 3.5 s, p99 wait 23 s and 29% timeouts: deadlines met
0.279 in the local run. As published (with the load fix): 0.711, p99 latency 1.2 s, mean wait 0.010 s; almost all
its misses are late completions (28.9% of invocations late, under 0.01% lost) on slower workers (mean run time
0.159 s against 0.092 s for on demand), since the ring ignores speed. It stays below on demand (0.825, measured before
the load fix) here; that is the policy's behaviour, not a defect.
