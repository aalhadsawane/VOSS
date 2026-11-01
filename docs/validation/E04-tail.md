# E04 tail breakdown: why the planner's P99 gain concentrates in seeds 2, 8, 10

Context: `docs/PLAN-ROUND4.md` section 2b ("Tail breakdown of the slowest 1% of requests in E04 seeds 2, 8, 10"). Analysis only; no repository code
was changed. Scripts and raw run outputs live under `/tmp/claude-0/tail/` (not committed).

## Commands

```
# 14 runs of configs/experiments/E04.yaml (keepalive_ttl and plan_greedy x {churn_high 2,8,10,3,7; churn_med 2,8}),
# built with experiments.runner.points() so the overrides are exactly those of the sweep:
uv run --frozen python /tmp/claude-0/tail/run.py          # writes /tmp/claude-0/tail/runs/<system>_<regime>_<seed>/ (Parquet + manifest)
uv run --frozen python /tmp/claude-0/tail/gen.py          # regenerates the scenarios (sessions, workers, arrivals) into /tmp/claude-0/tail/scenarios/
uv run --frozen python /tmp/claude-0/tail/analyze.py      # tables 1-5
uv run --frozen python /tmp/claude-0/tail/win2.py; ... win3.py; ... extra.py   # tables 6-8
```
Equivalent single cell with the CLI: `uv run --frozen voss run configs/pilot.yaml --set horizon_s=900 --set scenario.workers=200
--set scenario.load.rate=10 --set voss.planner.name=keepalive_ttl --set scenario.regime='"churn_high"' --set seed=10 --set label=keepalive_ttl --out <dir>`
(the runner is what I actually used; the CLI line is the same override list, not run separately). The whole batch took 70 s on 4 cores.

Definitions follow `experiments/analysis/common.py::latency_metrics`: synchronous = `slo_class == 0`, `outcome == ok`, `t_arrive >= 60 s`;
"tail" = sync requests with e2e >= that run's P99. Latency components are the logged columns of `invocations`
(`route, retry, batch_wait, decide, net_in, wait, trust, startup, exec, net_out`); they sum to `e2e` exactly (max gap 0.0 in every run).
`wait` is the time queued for a worker execution slot; `trust` is key release; `startup` is the sandbox start-up by level.

## 1. Reproduction check

All 14 P99s equal `paper/tables/E04.csv` (max abs difference 4.4e-16, i.e. identical). All 14 result hashes equal the E04 rows of
`paper/run-hashes.csv` (matched by config-hash prefix). **No mismatch.**

| regime | seed | keepalive_ttl P99 (s) | plan_greedy P99 (s) | ratio |
|---|---|---|---|---|
| churn_high | 2 | 5.275 | 1.503 | 3.5 |
| churn_high | 8 | 4.894 | 1.490 | 3.3 |
| churn_high | 10 | 11.819 | 2.134 | 5.5 |
| churn_high | 3 | 1.453 | 1.265 | 1.15 |
| churn_high | 7 | 1.518 | 1.339 | 1.13 |
| churn_med | 2 | 2.887 | 1.309 | 2.2 |
| churn_med | 8 | 3.618 | 1.520 | 2.4 |

Sample size caveat: the tail is only 26-52 requests per run (1% of 2.5-5.2k sync requests after warm-up).

## 2. What the tail is made of (mean seconds per tail request)

| system | regime/seed | n tail | e2e P99 | wait | trust | startup | exec | net in+out | other (route, decide) | tail with wait >= 50% of e2e |
|---|---|---|---|---|---|---|---|---|---|---|
| keepalive_ttl | high/2 | 29 | 5.27 | **9.10** | 0.00 | 0.63 | 0.53 | 0.10 | 0.09 | 90% |
| plan_greedy | high/2 | 29 | 1.50 | 0.38 | 0.00 | 0.07 | 1.19 | 0.15 | 0.28 (incl. retry 0.21) | 21% |
| keepalive_ttl | high/8 | 26 | 4.89 | **12.23** | 0.03 | 0.63 | 0.61 | 0.12 | 0.10 | 81% |
| plan_greedy | high/8 | 26 | 1.49 | 0.38 | 0.00 | 0.05 | 1.40 | 0.11 | 0.07 | 15% |
| keepalive_ttl | high/10 | 41 | 11.82 | **16.86** | 0.03 | 1.05 | 0.59 | 0.10 | 0.09 | 93% |
| plan_greedy | high/10 | 41 | 2.13 | 2.00 | 0.00 | 0.08 | 0.48 | 0.10 | 0.10 | 93% |
| keepalive_ttl | high/3 | 52 | 1.45 | 0.01 | 0 | 0.03 | 1.48 | 0.16 | 0.08 | 0% |
| plan_greedy | high/3 | 52 | 1.27 | 0.00 | 0 | 0.00 | 1.27 | 0.19 | 0.09 | 0% |
| keepalive_ttl | high/7 | 52 | 1.52 | 0.01 | 0 | 0.00 | 1.84 | 0.12 | 0.05 | 0% |
| plan_greedy | high/7 | 52 | 1.34 | 0.00 | 0 | 0.00 | 1.41 | 0.10 | 0.06 | 0% |
| keepalive_ttl | med/2 | 29 | 2.89 | **5.61** | 0.03 | 0.55 | 0.50 | 0.09 | 0.08 | 86% |
| plan_greedy | med/2 | 29 | 1.31 | 0.24 | 0.00 | 0.08 | 1.21 | 0.17 | 0.08 | 10% |
| keepalive_ttl | med/8 | 26 | 3.62 | **7.20** | 0.01 | 1.72 | 0.47 | 0.11 | 0.08 | 65% |
| plan_greedy | med/8 | 26 | 1.52 | 0.12 | 0.00 | 0.34 | 1.47 | 0.08 | 0.05 | 8% |

(Tail means can exceed the P99 because the tail is every request at or above it; e.g. keepalive seed 10 reaches 29.6 s.)
Routing, decision, batch-wait, retry and network are never the cause: each is <= 0.3 s mean in every tail. The slow tail in the bad
seeds is queueing for an execution slot. In the two normal seeds nobody queues; the tail is pure execution time (graph-pagerank etc.).

## 3. Counterfactual: P99 with a component removed (per request, then P99)

| regime/seed | system | actual | no `wait` | no `trust+startup` | neither |
|---|---|---|---|---|---|
| high/2 | keepalive_ttl | 5.27 | 1.76 | 5.12 | 1.57 |
| high/2 | plan_greedy | 1.50 | 1.33 | 1.45 | 1.32 |
| high/8 | keepalive_ttl | 4.89 | 2.47 | 4.25 | 1.65 |
| high/8 | plan_greedy | 1.49 | 1.43 | 1.44 | 1.38 |
| high/10 | keepalive_ttl | 11.82 | 1.71 | 10.20 | 1.37 |
| high/10 | plan_greedy | 2.13 | 1.30 | 2.10 | 1.20 |
| med/2 | keepalive_ttl | 2.89 | 1.53 | 2.71 | 1.45 |
| med/2 | plan_greedy | 1.31 | 1.26 | 1.26 | 1.24 |
| med/8 | keepalive_ttl | 3.62 | 2.31 | 2.47 | 1.64 |
| med/8 | plan_greedy | 1.52 | 1.47 | 1.43 | 1.40 |

Removing slot-queueing alone takes keepalive_ttl to 1.7-2.5 s (within 0.4-1.1 s of greedy); removing key release plus start-up alone
barely moves it in seeds 2, 8(high), 10. Removing both leaves keepalive 0.2-0.3 s above greedy (execution speed, table 8).

## 4. Start level, trust, retries of the tail requests

| system | regime/seed | tail L0/L1/L2/L3 | all-sync L3 share | tail trust-cold | all-sync trust-cold | tail attempts>1 | tail `retry`>0 s | tail resend/spill |
|---|---|---|---|---|---|---|---|---|
| keepalive_ttl | high/2 | 2/1/2/24 | 96.7% | 0 | 0.0% | 3 | 0 | 0 |
| plan_greedy | high/2 | 0/2/2/25 | 98.5% | 0 | 0.1% | 3 | 3 | 3/3 |
| keepalive_ttl | high/8 | 3/1/1/21 | 97.0% | 2 | 0.2% | 5 | 0 | 0 |
| plan_greedy | high/8 | 0/1/1/24 | 98.0% | 0 | 0.4% | 0 | 0 | 0 |
| keepalive_ttl | high/10 | 3/5/3/30 | 97.2% | 3 | 0.2% | 5 | 0 | 0 |
| plan_greedy | high/10 | 0/1/0/40 | 98.1% | 0 | 0.2% | 0 | 0 | 0 |
| keepalive_ttl | high/3 | 0/1/1/50 | 99.6% | 0 | 0.0% | 0 | 0 | 0 |
| plan_greedy | high/3 | 0/0/0/52 | 99.4% | 0 | 0.0% | 0 | 0 | 0 |
| keepalive_ttl | high/7 | 0/0/0/52 | 99.7% | 0 | 0.0% | 0 | 0 | 0 |
| plan_greedy | high/7 | 0/0/0/52 | 99.2% | 0 | 0.1% | 0 | 0 | 0 |

At least 70% of the slow requests in the bad seeds (24/29, 21/26, 30/41) were served from an already warm L3 sandbox; they were slow
because they queued, not because they started cold. Trust-cold starts: 0-3 tail requests per run, about 0.1-0.4% of all sync requests
for both systems. Retries/hedges/failures are not a factor (no retry delay in keepalive tails; the 3 greedy resends in seed 2 add about 2 s each, which is why that greedy tail has retry 0.21 s mean).

## 5. Timing: one episode per run

| system | regime/seed | tail arrival time, 10th / median / 90th pct (s) | share of tail in best 30 s bin | share in best two 60 s bins | distinct workers (top worker's share) | tail tenants |
|---|---|---|---|---|---|---|
| keepalive_ttl | high/2 | 804 / 890 / 895 | 72% (bin 870) | 90% | 6 (15/29) | t-ml 16, t-graph 5 |
| keepalive_ttl | high/8 | 470 / 492 / 517 | 58% (bin 480) | 100% | 6 (19/26) | t-ml 18, t-graph 6 |
| keepalive_ttl | high/10 | 184 / 208 / 220 | 46% (bin 210) | 100% | 5 (12/41) | t-ml 37, t-media 4 |
| keepalive_ttl | med/2 | 585 / 715 / 769 | 59% | 76% | 6 | t-graph 13, t-ml 8 |
| keepalive_ttl | med/8 | 468 / 505 / 539 | 38% | 89% | 9 | t-ml 14 |
| plan_greedy | high/2, 8 | spread over 60-860 s (best 2 bins 41%, 35%) | 14%, 12% | - | 8-9 | t-graph (graph-pagerank/mst execution) |
| plan_greedy | high/10 | 61 / 68 / 150 | 83% (bin 60) | 95% | 5 (34/41) | t-ml 33 |
| normal seeds 3, 7, both systems | | spread over 130-815 s | 10-14% | 31-38% | 3-6 | t-graph (graph-pagerank) |

In the bad seeds the whole keepalive tail is a single 40-120 s episode, almost entirely image-recognition (tenant t-ml, a sync
function with a high-sensitivity tenant). It is not a city-wide shock or a start-up burst:

* **No shock occurred.** In the scenarios for these seeds no session ends with `reason=shock` in [0, 900] s. Only 4-8 of 200 workers' sessions end in the
  window at all (seed 2: 8; seed 8: 5; seed 10: 4, all listed by worker in `scenarios/*/sessions.parquet`), and `churn_med` seed 8 has none. The nearest relevant loss
  is seed 10 worker 36 (a t-ml key holder in keepalive, session end 846.8 s), which is after the episode (183-220 s). Seed 2: worker 179 (a holder) ends at 859.9 s,
  inside the 870 s episode, but only 1 of the 4-5 holders; waits had been 2-7 s since t = 780 s before that.
* **Arrival burst only in seed 10.** t-ml/image-recognition is 52% of all sync arrivals in seed 10 (2137 of ~4.1k; 2.4/s average, 2.9/s in the window 160-180 s); in seeds 2 and 8 it is
  228 and 272 arrivals (about 6-8 per 20 s, no burst). So load alone does not explain seeds 2 and 8.

## 6. The mechanism: too few key-holding workers, and their slots are full of long asynchronous jobs

t-ml key holders (from `key_release` / `key_dropped` events), image-recognition requests and waits in the keepalive episode:

| regime/seed | window (s) | key holders, keepalive_ttl (slots) | key holders, plan_greedy (slots) | mean wait of image-recognition in window: keepalive / greedy |
|---|---|---|---|---|
| high/2 | 860-900 | 5 (24) | 20 (141) | 7.9 s / 0.0 s (20-s bin 880) |
| high/8 | 460-540 | 2 (21) | 11-14 (99-120) | 21.3 s (bin 480) / 0.0-0.45 s |
| high/10 | 140-240 | 5-6 (30-36) | 13-17 (69-105) | up to 9.6 s (max 28.7 s) / 0.0 s |

* The keepalive_ttl planner makes no key placement decisions: keys exist only where an earlier invocation caused a release. In seed 10 t-ml
  had keys on workers 67, 195, 189, 36, 170 by t = 55 s and on no new worker until 213 s; the 3 L0 trust-cold requests in the tail (t = 213 s; trust 0.3-0.5 s, start-up 7.7-7.9 s)
  are the moment worker 6, the first non-holder, was finally used. Greedy releases keys to 7 workers at 33.7 s, to 2 more at 63.7 s, to 4 at 153.6 s, and so on every ~30 s (58 key_release/key_dropped events vs 6 for keepalive for that tenant).
* The holders' slots are occupied by long jobs of other tenants. FIFO `Slots` (`voss/world/resources.py`) does not prioritise sync over async. Example seed 8, worker 37 (6 slots): from t = 465 s all 6 slots run
  `dna-visualisation` (async, ~6 s of reference work), with 14-29 invocations queued (mostly more dna-visualisation, 2-7 sync); the 30 image-recognition requests
  sent to it waited 10 s on average. Seed 10, worker 67 (3 slots, speed 0.5): 2 slots on dna-visualisation and 5-9 queued, 5-8 of those sync. Seed 2, worker 168: video-processing holds all 3 slots.
  The scheduler's wait estimate is `max(0, occupancy - slots + 1) * svc_s / slots` with `svc_s` a scheduler-wide mean (`voss/policy/cost/components.py`), so it cannot see that the occupants are 6 s jobs; I did not
  test why the placer still prefers these queues over a trust-cold worker (it picks trust-cold in only 0-3 tail requests); that is open.
* Async work suffers as well in keepalive: mean `wait` of async/filler invocations is 2.5-4.4 s (seeds 10, 8, 2) vs 0.1-0.2 s under greedy; sync requests waiting > 5 s: 24 / 18 / 79 (seeds 2 / 8 / 10) vs 0 for greedy.
  Overall share of sync requests with wait > 1 s: 3.4% / 2.2% / 5.4% vs 0.2% / 0.2% / 1.1%.
* In seed 10 greedy has the same problem for 15 s right after warm-up (worker 189 with 3 s of wait at t = 60-75 s, 93% of its tail is `wait`) before its first key placements for t-ml reach the other workers; its P99 there is 2.13 s versus 11.82 s.

## 7. Exposure / memory cost of the planner's advantage

Mean over t >= 60 s from `cache.parquet` (keepalive_ttl -> plan_greedy): key holders 41.6 -> 86.4 (seed 2), 44.0 -> 87.7 (8), 43.4 -> 77.4 (10), 34.3 -> 66.5 (seed 3), 24.8 -> 76.3 (7);
warm RAM 72.6 -> 124.2 GB, 96.0 -> 116.0, 74.2 -> 117.8, 47.0 -> 54.2, 45.6 -> 71.7; exposure 9.5 -> 18.5, 9.2 -> 18.5, 9.3 -> 16.7, 8.1 -> 14.6, 5.4 -> 15.8; SSD snapshots 17.4 -> 46.4 GB (seed 2), 18.5 -> 37.7, 19.0 -> 46.2.
Greedy roughly doubles key holders and exposure and holds 1.1-1.7x more warm RAM, in the good and bad seeds alike; the difference between the bad and normal seeds is not the size of the planner's
advantage in these averages but whether a demand pattern lands on few holders.

## 8. The two normal seeds (3 and 7)

No queueing in either system (sync wait > 1 s: 0.0%), zero trust-cold tail requests, ~99.5% L3. t-ml is only 240 / 465 sync requests and is not in the tail; the tail is graph-pagerank execution time.
Greedy's 8-12% gain there comes from execution: mean worker speed of the workers serving sync requests is 0.74 -> 0.83 (seed 3) and 0.90 -> 0.99 (seed 7); graph-pagerank mean exec 0.59 -> 0.56 s and 0.64 -> 0.55 s.
That is a placement effect (more candidate holders, so faster workers can be chosen), not a start-up or key effect, and not placement "away from workers about to leave" (the logs show
no departures near these tails; this was not otherwise tested).

## Conclusion

For seeds 2, 8, 10 (and churn_med 2, 8) the keepalive_ttl tail is slot queueing, not cold starts and not key releases: 65-93% of the slow requests spend over half their latency in `wait`, the mean `wait` is
9-17 s (5.6-7.2 s in churn_med), and removing it alone cuts keepalive P99 from 5.3 / 4.9 / 11.8 s to 1.8 / 2.5 / 1.7 s (greedy: 1.5 / 1.5 / 2.1 s). The queue forms on the 2-6 workers that hold the key
of the tenant under load (t-ml / image-recognition), because their FIFO slots are filled by 6-s asynchronous jobs. The planner's advantage is that it places keys, plus warm state, ahead of demand on 11-20 workers,
so the same requests find free slots.

Answering the candidate explanations:

* (a) Avoiding key releases (trust-cold starts): **no, as a rate**. Trust-cold is 0.0-0.4% of sync requests for both systems and 0-3 of 26-41 tail requests. Releasing keys *earlier and on more workers* is what helps, as capacity: that is
  explanation (b)-like, but it is key-holder capacity, not saved release latency (`trust` is 0.0-0.03 s mean in the tails).
* (b) More warm sandboxes/snapshots: **partly and confounded**. Keepalive's tail requests were already L3-warm (73-83%); greedy has 1.1-1.7x warm RAM and ~2x key holders, but the logs cannot separate
  "more key holders" from "more warm sandboxes" because the planner supplies both; a keepalive run with the same key-holder count would be needed (not run).
* (c) Placement away from departing workers: **no**. Only 4-8 sessions end in the 900-s window and none in the tail episodes except one holder in seed 2 (1 of 5).
  Placement matters only in the normal seeds, where greedy lands sync work on faster workers (~10% execution gain).
* (d) Recovery after correlated losses: **no**. The scenarios for these seeds contain no shock sessions in [0, 900] s.
* Something else, the actual cause: **head-of-line blocking at a small key-holder set** (FIFO slots shared by sync and long async jobs, wait estimate blind to job length), triggered by a concentrated demand for one
  high-sensitivity tenant (seed 10: a real image-recognition surge; seeds 2 and 8: ordinary demand landing on 2-5 holders).

Consequences for the paper's argument: the headline gain is a tail-episode effect (one 40-120 s episode decides each of those P99s, from about 30 requests), not a smooth per-request advantage; it is a capacity-provisioning
effect that a keepalive baseline with key pre-placement or a sync-priority slot queue might remove. These two alternatives were not tested here. `provisioned_keys` in the Round 4 system list is the right control.
