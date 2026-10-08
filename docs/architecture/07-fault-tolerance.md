# 07 · Fault Tolerance: Omission-Tolerant Succession and Worker Failure Handling

Spec §5.5, §4.6. The threat model (doc 04) reduces malicious hosts to **omission/timing faults**, so one mechanism
set covers churn, crashes and malice.

## 1. Fault model the mechanisms must handle

| Fault | Source | Distinguishing difficulty |
|---|---|---|
| Crash / session end | Owner reboot, power loss, crash | Easy: channel and heartbeats stop |
| Graceful drain | Owner request (deadline) | Announced, but the announcement may be **fake** |
| **Black-hole / selective omission** | Malicious owner drops work but keeps heartbeats | **Heartbeats look healthy** |
| On-off defection | Builds a clean record, then omits | History is misleading |
| Delay / throttle | Malicious or overloaded host | Looks like slowness |
| Partition | Network | Zombie scheduler |
| Replay | Malicious owner | Handled by TLS (sequence numbers) |

**Principle:** *liveness signals from untrusted hosts are hints; progress observed by trusted or attested parties is
evidence.*
- **Trusted:** routers (orchestrator tier).
- **Attested:** worker agents and the scheduler code (their *hosts* are not trusted).

## 2. Progress-based detection

| Detector | Observer | Signal | Suspects |
|---|---|---|---|
| **Dispatch watchdog** | Router | `ENQUEUE` without `ACCEPTED` within `T_dispatch` | Scheduler (or cluster) |
| **Result watchdog** | Scheduler | `ACCEPTED` without `RESULT` by the predicted completion quantile (q90 + margin) | Worker |
| **Cluster stall** | Router → orchestrator | Repeated dispatch-watchdog fires for one cluster | Scheduler (grey failure / black hole) |
| **Decision-latency SLO** | Orchestrator | Scheduler's attested timestamps show placement latency > `T_decide_max` | Slow or throttled scheduler host |
| **Outcome rate** | Scheduler (omission model, doc 03 §6.4) | Omission rate and change point | Worker (on-off, selective) |
| Heartbeat/accrual | Scheduler, orchestrator | Missing heartbeats | Crash (fast path only, never sufficient alone) |

A suspected worker gets no new work, its in-flight work is hedged or retried, and it loses trust-warm eligibility. A
suspected scheduler triggers succession (§3).

## 3. Scheduler succession (soft state, no volunteer consensus)

The orchestrator is a reliable arbiter, so **no consensus among volunteers** is needed.

**Instance-bound appointment.** The orchestrator appoints scheduler *S* by atomic CAS on the cluster `epoch` in the
DB. The appointment token binds `(cluster, epoch, S's session-cert id)`. A cloned appliance with the same image but a
different session key is **not** appointed.

**Worker-side fencing.** Workers accept `DISPATCH` only from the current `(epoch, cert id)` and reject lower epochs
with `STALE`.

**Soft state = rollback-immune.** A scheduler keeps no durable state on its host:

| State | Held by | Recovery path |
|---|---|---|
| Undispatched invocations | Router pending table | Router re-sends |
| Running / queued work | Workers | **Roll call** |
| Plan (trust-warm sets, pins) | Workers (confirmed pins and keys) + DB checkpoint of the last plan | Roll call + recompute |
| Learned state (predictor, survival, omission posteriors) | DB checkpoint (orchestrator) + outcomes retained in worker memory | Checkpoint + replay |
| Work records | Routers' attested receipts | Nothing to recover |

A restarted or rolled-back appliance is a *new instance* and must be re-appointed. Its stale memory is never trusted.

**Succession list:** ranked by `S_j(H) × speed × centrality × a_j`, with failure-domain diversity and hysteresis.
Every attested worker is a candidate: the scheduler role is in the appliance image, so promotion costs no boot.
`K` warm standbys (default 1) also receive heartbeats.

**Failover sequence:**

```mermaid
sequenceDiagram
    participant R as Router
    participant S as Scheduler (epoch 7)
    participant O as Orchestrator + DB
    participant N as Successor (attested worker)
    participant W as Workers
    R->>S: ENQUEUE(inv2)
    Note over S: host crashes OR black-holes (heartbeats continue)
    R->>R: dispatch watchdog fires (no ACCEPTED) → re-send / spill sync invocations
    R->>O: STALL(cluster, epoch 7)
    O->>O: CAS epoch 7→8, holder = N (cert-bound)
    O->>N: APPOINT(epoch 8, membership, plan + learned-state checkpoint, reputation)
    O->>R: scheduler address push
    N->>W: EPOCH_INSTALL(8) + ROLL_CALL
    W-->>N: running/queued work, confirmed pins and keys, retained outcomes, cache inventory
    N->>N: rebuild view; replay outcomes; re-plan (warm-started from checkpoint)
    R->>N: re-send pending (dedupe by inv_id)
    N->>W: DISPATCH(epoch 8)
```

**Other paths:**
- **Planned handover** on drain notice or decision-latency degradation: the old scheduler flushes its checkpoint, then
  the CAS happens. A *fake* drain by a malicious scheduler host just causes a clean handover, which is harmless.
- **Zombie:** a scheduler that cannot reach the orchestrator for `lease_s` stops dispatching (self-fence). Workers
  fence it anyway.
- **Whole-cluster loss:** the orchestrator reassigns the workers and the router spills over.

## 4. Worker failure handling

| Mechanism | Design |
|---|---|
| Predictive watchdog | Fires at the predicted completion quantile; the scheduler probes the worker, and without a reply it re-places the work |
| **Risk-proportional hedging** | Tied duplicate on another failure domain when `pMiss > θ` (doc 03 §5.4), under a budget. Attested results make hedges integrity-safe |
| Retry | Exclude the failed worker; prefer trust-warm candidates; retry budget per invocation |
| **Storm control** | A per-cluster retry token bucket plus router spillover during regional waves |
| **Fake signals** | Drain or preemption notices only make the scheduler *more conservative* (stop new dispatch, shorten predicted life). They never excuse an omission in the omission model or reputation |
| Suspicion | Change point or watchdog streak → suspected: no new work, trust-warm eligibility revoked, re-planned |
| Session end | All `K`/L3/L4 state lost; disk caches survive as ciphertext; the worker rejoins after re-attestation |

## 5. Failure matrix

| Failure | Detected by | Recovered by | Lost / delayed |
|---|---|---|---|
| Worker session ends mid-invocation | Channel close / watchdog | Retry / hedge | That attempt (counted as wasted work) |
| Worker black-holes | Result watchdog, omission model | Hedge, retry, suspicion, re-plan | Attempts until detection |
| Worker on-off | Change point | Eligibility reset, re-plan | Bounded by detection delay |
| Scheduler crash | Keepalive + router stall | Succession + roll call | Delay for undispatched invocations |
| Scheduler black-hole | Router stall, decision SLO | Succession | Delay ≈ `T_dispatch` + appointment |
| Scheduler partitioned | Self-fence, `STALE` | Fencing | Possible duplicates (at-least-once, counted) |
| Colluding domain | Many watchdogs at once | Domain caps keep coverage; re-plan | Bounded by the robust plan |
| Orchestrator tier | — | Out of scope (assumed reliable) | — |

## 6. Parameters and metrics

| Parameter | Default |
|---|---|
| `T_dispatch` | 1 s |
| `T_spill` (sync) | 1.5 s |
| Watchdog quantile | q90 + 20% |
| `T_decide_max` | 200 ms |
| Change point | CUSUM `h=5` |
| Hedge θ / budget | 0.2 / 10% |
| Warm standbys `K` | 1 |
| `T_ckpt` | 30 s |
| `lease_s` | 5 s |

**Metrics:**
- time-to-detect (per fault type) and false-suspicion rate;
- failover time and invocations delayed/lost/duplicated;
- P99 inside fault windows;
- hedge waste;
- re-plan churn.

**Hypotheses:**

| ID | Hypothesis |
|---|---|
| H-FT1 | Progress-based detection bounds black-hole impact; heartbeat-only detection does not |
| H-FT2 | Succession without volunteer consensus keeps cluster unavailability low at high churn |
| H-FT3 | Risk-proportional hedging recovers most of the P99 lost to omission at < 10% extra work |
