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

**Rerun.** `runs/requests/experiment/d01a-iter1.yaml` (9 runs, 9 shards, run 43823178136): shards 1-8 finished in
0.8-1.7 h, shard 0 (`eviction_aware`) hit the job limit, so the run published nothing; the cause is the
min-worker-set bug fixed in iteration 2. D01a is rerun after iteration 2.

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

## Iteration 2: backups for half of all invocations; forged answers counted as correct

**Observations (D02_DROP run 43824761074, D02_FORGE run 43824844566; 500 workers, K = 8, rate_mult 21, seed 1).**
(1) VOSS made 1.48-1.50 attempts per invocation at every level of dropping owners, 1.50 even with none, against
1.05 for hedged requests; under 20% dropping owners hedged met 0.976 of deadlines and VOSS 0.959. (2) Every audit
p = 0 cell of D02_FORGE had deadline_met 0.979166 and p99 2.364 s, the values of the no-adversary run, for every
class-P share and forge probability.

**(2) Forging was applied; the metric did not see it.** A local run with the D02_FORGE override (100 workers, class-P
share 0.2, 30 minutes) had 20 forging workers and 480 `adv_forge` events, and 462 invocations were answered with a
forged result (47 of 1,486 synchronous, 415 of 4,573 asynchronous). The audit runs after the answer, so with p = 0
nothing changes in timing, and `deadline_met` counted a forged answer as met. Change: `metrics.mark_wrong` marks an
invocation whose answer came from a forged result (an `adv_forge` event of the answering worker for it); `classify`
returns `wrong` for it, so it is a miss; the summary reports `forged_results` (forged results produced after the
warm-up) and `wrong_answers` (forged answers returned, every class). `tests/integration/test_audit.py` fails if
forgers have no effect on these or on deadlines met. D02_FORGE needs its summaries recomputed (the logs are in the
release; no rerun is needed).

**(1) Hypothesis.** The watchdog timer fires too early: VOSS requests a backup when an attempt passes the predicted
q95 of its completion, so with a calibrated timer about 5% of first attempts should get one.

**Evidence.** Local run (code of `revision-v2` at ff91045, 1 h after a 10-minute warm-up, no adversaries), first
attempts that answered, realised parts against the terms of the timer:

| Part (mean, s) | sync realised | sync timer term | async realised | async timer term |
|---|---|---|---|---|
| dispatch (with input wait) + reply network | 0.085 + 0.058 = 0.143 | 0.057 | 0.106 + 0.058 = 0.164 | 0.083 |
| queue wait on the worker | 0.000 | 0.001 | 0.087 | 0.079 |
| key and start-up | 0.007 | 0.013 | 0.018 | 0.092 |
| execution | 0.097 | 0.099 (5.1% above its q95) | 0.299 | 0.305 (5.2% above its q95) |
| first attempts past the timer | 74.7% | | 53.0% | |
| ... if the network term were exact | 6.3% | | 9.8% | |

Only the network term is wrong (the router's `net_in` includes the wait for the input; see below). It is the cost
model's router-to-worker round trip, estimated from distance (doc 03, "no jitter and no measurement"), but the timer
runs from the dispatch at the scheduler (one node, Frankfurt) to the outcome back there. Asynchronous invocations are
not all backed up: in the 2 h iteration-1 run 51% of them got a backup (38% of synchronous ones), about the share that
overran.

**Change, step 1 (scheduler round trip).** The timer's network became the scheduler-worker round trip, the one the
scheduler last observed to that worker (dispatch to `ACCEPTED`, sent on receipt), or its distance estimate before
the first exchange. Overruns fell to 44.2% (sync) and 28.4% (async) only.

**The missing term.** A second local run (30 minutes, step 1 applied) logged the legs of every first attempt at the
scheduler. The observed round trip matched the two network legs exactly (sync: dispatch 0.0543 s + outcome 0.0544 s
= 0.1087 s against an observed 0.1090 s; async 0.1022 s against 0.1030 s), and the worker's time was wait 0.000 +
trust 0.000 + start-up 0.007 + **input wait 0.038 (sync) / 0.052 (async)** + execution. The input reaches the worker
from the router, which sends it when the scheduler's `ASSIGNED` arrives; 87% (sync) and 92% (async) of first attempts
waited for it, 0.043 s and 0.056 s when they did. Without the input wait the overruns would have been 14.5% and 5.9%.
The timer's model had no such term: its time to start is the worker's queue, key and start-up only.

**Change, step 2 (D-102).** Execution starts no earlier than the input arrives: `(rtt(S, R) + rtt(R, W) − rtt(S, W)) /
2` after the worker receives the dispatch, plus the input transfer, from the scheduler's distance estimates for the
router legs. The timer's time to start is the larger of that and the cost model's time to start; its network is the
scheduler round trip; the output transfer, which goes to the router, is not in the span. The mean and the budget of the
deadline-fit check stay the router's. No new constant, no margin.

**Result (local, 1 h, one seed each).** Overruns of first attempts that answered:

| Dropping owners | Code | sync | async |
|---|---|---|---|
| 0 | `revision-v2` | 74.7% | 53.1% |
| 0 | step 1 | 44.2% | 28.4% |
| 0 | steps 1 + 2 | 11.7% | 10.3% |
| 20% | `revision-v2` | 75.4% | 49.2% |
| 20% | steps 1 + 2 | 13.4% | 11.5% |

The remaining excess over 5% is not decomposed further; candidates are the router legs, which are still distance
estimates, and network jitter, which the completion model does not include.

| System | Dropping owners | Code | Deadlines met | Attempts per invocation | p99 (s) | Episodes |
|---|---|---|---|---|---|---|
| voss | 0 | `revision-v2` | 0.947 | 1.453 | 0.762 | 42 |
| voss | 0 | iteration 2 | 0.939 | 1.097 | 0.759 | 43 |
| voss | 20% | `revision-v2` | 0.914 | 1.424 | 0.768 | 48 |
| voss | 20% | iteration 2 | 0.925 | 1.114 | 0.737 | 57 |
| hedged | 0 | `revision-v2` | 0.948 | 1.052 | 0.768 | 32 |
| hedged | 0 | iteration 2 | 0.948 | 1.052 | 0.768 | 32 |
| hedged | 20% | `revision-v2` | 0.936 | 1.057 | 0.776 | 47 |
| hedged | 20% | iteration 2 | 0.944 | 1.053 | 0.759 | 35 |

(With step 1 only, VOSS met 0.939 at alpha 0 and 0.962 at 20%, with 1.25 attempts per invocation.)

**Does VOSS depend on early backups? Yes, in these runs.** With a nearly calibrated timer VOSS starts a backup for
about 10% of invocations instead of 45% and meets 0.008 fewer deadlines without dropping owners (0.947 → 0.939); under
20% dropping owners it gains 0.011 (0.914 → 0.925) but stays below hedged requests (0.944), which back up 5% of
invocations after the function's observed 95th-percentile latency, to any worker and without a deadline-fit check. The
early backups of `revision-v2` were acting as hedges: about half of all invocations ran twice. This is a design point
for the owner, not something this iteration settles: VOSS restricts a backup to a key holder in another failure domain
that fits the remaining deadline, and with K = 8 holders that restriction is what the timer change exposes. One seed and
1 h per cell; the D02_DROP rerun measures it over 24 h.

## Bug fix found in iteration 2

**`eviction_aware` piled work onto full workers (D01a rerun, shard 0 slow).** The min-worker-set of #97 counted a
worker's total slots as its usable resources, so a function's set stopped at its home worker even when that worker was
full: locally, 874 invocations queued on one worker at t = 2,400 s (2,227 in all), and wall time per simulated hour
grew from 238 s to 873 s over the first five hours. Usable resources are now the free slots (not busy, queued or
dispatched), the paper's usable resources of a VM: queued work stayed at 0 in every 10-minute sample of 6 simulated
hours, at 29-64 s of wall time per 10 simulated minutes. Deadlines met over those 6 hours: 0.680 (p99 1.02 s,
1.39 attempts per invocation).

**Known, not changed:** the holder budget invariant reports 9 holders for a budget of 8 in short runs (16 violations
in a 2 h run of `revision-v2` before iteration 1, 41 for pre-released keys): a new holder is counted before the
released one has dropped its key.
