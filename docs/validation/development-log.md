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
in a 2 h run of `revision-v2` before iteration 1, 41 for pre-released keys). The cause, found in iteration 3, was not
the release order: the key service freed places at the certificate's original expiry (see there).

## Iteration 3: equal budgets, run seed, why hedged leads without adversaries, the audit's cost, network transfer

Local runs: 500 workers, K = 8, rate_mult 21, bundle `i7_12700_64g_full-b4f89a4def` (D01's), 1 h after a 10-minute
warm-up, seeds 1 and 2, `voss` and `hedged` failure handling with VOSS provisioning, no adversaries or 20% dropping
owners. "Before" is `revision-v2` at 6a148c8 (iteration 2). 24 h evidence: D02_DROP run 44056777206 and D02_FORGE run
44056798787 (seed 1), from their raw logs.

### (1) The holder budget was exceeded (bug fix, D-107; guardrail 16)

The tenant key service freed a holder's place at the expiry the session certificate had when the key was released.
Re-quotes (every 600 s) extend a certificate (900 s validity) while the worker keeps the key in RAM for the session
(doc 04 §6), so every 15 minutes each holder's place was freed although it still held the key, and the budget admitted
more holders. The violations are not message races: at each violation the holder the key service had already let go
dropped its key 25 s to 75 min later (34 violations in a 2 h VOSS run: 22 planned releases, 12 session ends). Now a
place frees only on the worker's `KeyDrop` or the verifier's `RevokeSession` (also sent when a certificate expires
without a re-quote). Every system uses this key service.

Hard test: `test_holder_budget_holds_across_certificate_requotes` runs each of the ten provisioning presets for
1,500 s with K = 2; on the old key service it fails for `prereleased_keys` and `exact_program`, now all pass. In 2 h
local runs the violations fell to 0 (VOSS, pre-released keys, fixed keep-alive).

Cost of the honest budget (1 h, mean of 2 seeds):

| System | Dropping owners | Deadlines met before → after | Mean holders | Keys with a violation per run | Key requests refused |
|---|---|---|---|---|---|
| voss | 0 | 0.944 → 0.917 | 5.09 → 4.08 | 22.5 → 0 | 367 → 1,215 |
| voss | 20% | 0.942 → 0.930 | 4.79 → 4.01 | 22.0 → 0 | 363 → 1,129 |
| hedged | 0 | 0.918 → 0.909 | 5.18 → 4.30 | 22.5 → 0 | 355 → 1,293 |
| hedged | 20% | 0.926 → 0.881 | 5.14 → 4.22 | 22.0 → 0 | 375 → 1,543 |

Every system lost deadlines, because every system had been running with more holders than K. Mean holders stay
below 8 because the key service now counts a worker that left without notice until its certificate is revoked (up to
900 s); those requests are refused. The results of D01a, D02 and the earlier iterations were all run with the
exceeded budget.

### (2) Failure scenarios from the run seed

Provisioning drew its failure scenarios from master seed 0 for every run, so the run seed did not reach them. They now
come from `rng.stream("plan.scenarios", t)` of the run (AGENTS.md rule 9). A convention test fails on any literal
master seed under `voss/` outside `voss/core`.

### (3) Why hedged leads without adversaries (D02_DROP, 24 h: hedged 0.984, VOSS 0.966)

Not the backups. VOSS made 251,889 backup attempts (22,654 answered first) against hedged's 127,646 (7,753), and
62,276 backups or retries were refused by the deadline-fit check. The gap of 16,274 misses (30,019 against 13,745)
comes entirely from two network-bound functions: tr0006 (deadline 0.27 s, execution 4 ms, 12,190 more misses) and
tr0018 (4,272 more); every other function together has slightly fewer misses under VOSS. For Singapore-routed
invocations of tr0006 the Frankfurt scheduler's round trip leaves almost no slack, and the share met depends on the
holder's access link: worker 193 misses 8%, worker 319 misses 79%. Under hedged, 193 got tr0006's key at t = 1,650 s and
kept it for 22.4 of the 24 measured hours; 319 held it too but was rarely chosen (116 invocations). Under VOSS, 193 got
the key only at t = 70,111 s (6.6 h), and 319 served 13,264 invocations. Both runs use the same provisioning; the
choice among Asian workers is arbitrary because provisioning's deadline probability includes only run time and warm
dispatch, so every worker looks the same for a function whose time is network, and the swap rule (D-100) then keeps
the early choice. The detectors are not involved: no Asian holder was ever suspected in either run.

**Change tried, rejected.** The deadline probability with the cost model's network term: router-worker round trip
(distance estimate corrected by the scheduler's observed round trip to that worker) plus transfers, as a mix over the
routers the function's invocations came through. Over the same 8 local runs (after the budget fix) it changed deadlines
met by +0.004 (VOSS, no adversaries), −0.021 (VOSS, 20%), −0.020 (hedged, none) and +0.018 (hedged, 20%), and did not
reduce tr0006's misses (895 with it against 821 before, VOSS seed 1). It is not committed. Placing holders per
region is the open design question this leaves: a function's holders serve every router, and one deadline probability
per worker cannot say which region a holder is good for.

### (4) The 5% audit (D02_FORGE, 24 h: p 1% 0.981, p 5% 0.964, class-P share 5%, forge_p 0.5)

The same mechanism, not audit load. Misses: 16,696 at 1%, 31,424 at 5%; tr0006 accounts for 13,723 of the 14,728
difference (4,574 against 18,297). At 1% worker 193 held tr0006's key for 22.3 h, at 5% not at all. Forged answers were
27 and 12, both negligible. Audit attempts do compete for holder slots, but the pool is under 1% busy and slot waits
are near zero, so they did not cost deadlines here; the 1.5 points are which holders the run happened to keep. One seed
per cell cannot separate the audit rate from that choice.

### (5) Network transfer under the per-size mapping (#117, now D-106)

On the first per-size mapping (node02 NVMe bundle, D01 central cell, 1 h, seed 1) VOSS met 61.4% of synchronous
deadlines and pre-released keys 60.0%. 84% of the late synchronous invocations were of one function, tr0143
(thumbnailer at size 16,000): its late invocations spent a median 0.88 s (mean 1.70 s) in dispatch and input transfer
against 0.13 s of execution and 0.07 s mean slot wait, on 99% warm sandboxes. The profile's size had been taken as a
16 MB input; at 2.75 invocations/s that is about 350 Mbit/s into 8-15 home downlinks (worker 459 received 36% of it),
with median input times of 0.43-0.51 s on the best links and 2.4-7.6 s on the worst. Neither cores (pool 2.9% busy),
long co-located functions (85% of the busy time on tr0143's top holders, yet near-zero slot wait), sandbox eviction
nor placement (pre-released keys did no better) were the cause. D-106 (owner's decision) now carries the bytes a
client sends and includes the transfer in the deadline. What remains true: provisioning and the per-function
utilisation count cores only, and the cost model's `bytes / down` ignores other transfers on the same link, which the
simulator shares.
