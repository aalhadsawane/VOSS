# Design Decisions

Current decisions are authoritative. History (ADR-001…029, proposals 0001/0002) is summarized at the end.
Format: **Decision**, why, rejected alternatives.

## Current decisions

**D-01 Custom Python discrete-event simulator.** FaaS physics is small; solver wall time must enter simulated time;
10⁵ workers need light state; there are no TEE-capable simulators. *Rejected:* SimGrid, SimPy.

**D-02 Substrate-agnostic design; profiles are data.**
- Primary substrate: **`appliance_tpm`**, a consumer PC with TPM 2.0 booting an owner-locked, measured VOSS appliance
  per donation session. Tenant functions run in Firecracker microVMs.
- Modeled: `cvm_snp`, `coco_pool`, `drtm_hv`, `none`.
- *Why:* the available hardware is consumer Intel. Memory Guard/TME are not TEEs (no isolation from the OS, no
  attestation). Server CVMs exist only on server CPUs.
- *Rejected:* Memory Guard/TME as a TEE; SGX (deprecated on client); vetted volunteers.

**D-03 Threat model.**
- Owners may be malicious; attestation reduces them to omission/timing faults.
- Out of scope: physical attacks needing equipment, appliance 0-days, side channels, traffic analysis, orchestrator
  failure.
- The orchestrator tier is trusted for availability and accounting only. (Doc 04.)

**D-04 No blockchain.** Attested receipts written by trusted routers already make work verifiable. A chain protects
against no adversary in the model. A transparency log is parked.

**D-05 Information boundary.** `policy` never imports `world`; policies see stale views only.

**D-06 Actor model.** Every cross-node interaction is a typed message via `net.send` with geography-derived delay.
Actors never call or import each other.

**D-07 Roles.**
- Orchestrator tier (provider): orchestrator, regional routers, verifier/registrar, operational DB.
- Scheduler: a role inside one attested worker per cluster.
- Workers: volunteers.
- Tenant KBS: tenant-run.

**D-08 Scheduler fault tolerance.** Soft-state succession; instance-bound epoch appointment by the orchestrator (CAS);
worker-side fencing; roll call; checkpoints in the DB; warm standbys; planned handover; self-fence lease. No consensus
among volunteers; **rollback-immune** by construction. *Rejected:* a Raft group of volunteers (brittle at high churn,
quorum RTT on every decision).

**D-09 Progress-based failure detection.** Evidence comes from trusted or attested observers (router dispatch
watchdog, scheduler result watchdog, decision-latency SLO, outcome model with change points). Heartbeats are hints.
Owner drain/preemption notices are hints that never excuse omissions.

**D-10 Two-timescale scheduling (core novelty).** The slow loop is a robust MILP planner for trust and warm state:
- f-robust coverage, linearized by duality;
- domain caps, exposure, memory/SSD knapsack, switching cost;
- greedy planner as baseline and fallback.

The fast loop is cost-matrix greedy/flow placement over planned candidates, plus a priced cold path, hedging and
retries. The per-window invocation ILP is a baseline only. Kill criterion in doc 03 §8.

**D-11 Measure locally, simulate globally.** Calibration bundles come from the real node (doc 10); literature-only
parameters are ranges with sensitivity sweeps; optional single-box emulation validation.

**D-12 Fast-loop objective.** The `slo_miss` scalarizer: expected SLO-violation cost + ε·E[T] + λ·exposure, over
moment-matched completion distributions.

**D-13 Exposure metric.** Assurance-weighted count of distinct key holders per tenant, with sensitivity classes and
assurance floors. Results are reported as Pareto fronts, never as a single weighted number.

**D-14 Three disjoint reliability signals:**
- **survival:** session ends;
- **omission:** mid-session drops, with change points;
- **reputation:** long-run commitment behavior, rewards only.

`f = ⌈α_assumed·N⌉` makes robustness independent of the adversary's strategy.

**D-15 Worker caches.**
- Three tiers (RAM / SSD / HDD), content-addressed and digest-verified, on a PCR-sealed partition.
- Plan-pinned entries plus GDSF value-density eviction; P2P within the cluster.
- Snapshots shared only with trust-warm workers of the same snapshot class, and counted as exposure.

**D-16 Operational DB.** Private to the orchestrator tier; never on the hot path; one writer per datum; routers write
receipts. The live queue, caches and keys are deliberately not stored.

**D-17 Identity = hash(TPM EK).** One identity per machine (Sybil-bounded). Reputation and credits bind to it.

**D-18 Tenant secrets.** Tenant-owned KBS releases keys wrapped to attested session keys, kept in appliance memory
only. Schedulers and the orchestrator never see them. Bundles are tenant-encrypted, so ciphertext can be cached and
forwarded freely.

**D-19 Small, diverse clusters.** Tens of workers (from E02), with failure-domain and assurance diversity, so robust
plans are feasible and the MILP stays small.

**D-20 Credits in reference work units** (throttling earns nothing), plus small credits for pinned cache donation
while responsive, and scheduler credits.

**D-21 Decision clock modes `measured | modeled | replay`;** a reproducibility contract with manifests, calibration
bundle hashes and `voss repro`.

**D-22 Parked:** workflows, GPU functions, padding, transparency log, real DRTM, multi-machine deployment.

## History (superseded or merged)

| Old | Became |
|---|---|
| ADR-001 SimGrid rejected; ADR-019 reproducibility; ADR-014 clock | D-01, D-21 |
| ADR-002, 020 | D-05, D-06 |
| ADR-005, 006 objective, hybrid placement | D-12, D-10 (the ILP moved to the slow loop) |
| ADR-007, 018, 027 ledger/chain | D-04 |
| ADR-008, 017, 022–024 control plane, Raft, succession | D-07, D-08 |
| ADR-009 reliability vs reputation | D-14 |
| ADR-010, 011 predictor, solver | Doc 03 §6, D-10 (HiGHS) |
| ADR-016, 026 crash-only / vetted honest | Replaced by D-03 (malicious owners + attestation) |
| ADR-021 small clusters | D-19 |
| ADR-025 worker crash tolerance | D-09 + doc 07 §4 |
| ADR-028 DB private | D-16 |
| ADR-029 worker readiness | Doc 08 §5 |
| Proposals 0001, 0002 | Accepted into docs 00–10 |

## Implementation decisions (coding phase)

**D-23 `ACCEPTED` is sent when the worker receives `DISPATCH`** (P2). Doc 00 §6 draws it after `INPUT`; with
multi-MB payloads on residential downlinks that makes the router's dispatch watchdog (`T_dispatch` = 1 s, doc 07 §2)
fire spuriously. The watchdog tests scheduler progress, so the worker acknowledges the dispatch itself; payload
arrival is accounted as `net_in` (input wait). *Rejected:* raising `T_dispatch` (slows real stall detection).

**D-24 Sessions already running at t = 0 skip their boot delays** (P2). Their establish ops keep the TPM quote and
verifier round trip but drop `delay`/`psp` steps, so a run does not start with every worker rebooting. Caches still
start empty; analyses may drop a warm-up window.

**D-25 Latency attribution with overlap** (P2). Trust and artifact fetch overlap the slot wait (doc 08 §5). The time
from `DISPATCH` receipt until slot, key and artifacts are all ready is split as trust first, then fetch (counted in
`startup`), and the remainder is `wait`; payload arrival after start-up is `net_in`. Components therefore always sum
exactly to end-to-end latency (doc 05 §7 invariant).

**D-26 Per-invocation execution noise is a precomputed matrix** (P2). Common random numbers (doc 01 §3) only need the
same draws for the same `(invocation, attempt)` in every system; a vectorized `noise_matrix` from one named stream
gives that without creating a generator per attempt (a measurable cost at 10⁵ invocations). Ladder delays use a
per-worker-session stream.

**D-27 Admission rejects only overload** (P3). Doc 03 §5.4 rejects a sync invocation when no candidate has
`pMiss < 1 − ε`. Without a warm plan, every cold function then has `pMiss ≈ 1` (deadline = k × warm latency), so it
would be rejected forever and its caches would never warm. Rejection (sync) or deferral (async) therefore also
requires overload: even the shortest slot wait exceeds the remaining budget. Cold-start misses are admitted.

**D-28 Wall-clock columns are metadata** (P3). Columns ending in `_wall_s` (e.g. solver wall time) are logged but
excluded from the result hash, so `modeled` and `replay` runs hash identically across machines; `measured` runs
are reproduced through `replay` of their charged latencies (doc 01 §7).

**D-29 Decisions serialize on the scheduler host** (P3). A decision is computed on the view at its start and takes
effect after its charged latency; decisions queue behind each other (`busy_until`), so decision latency includes
queueing on a busy scheduler. Async/filler invocations wait in a window (`placer.window_s`) logged as `batch_wait`.

**D-30 The MILP is bounded by construction** (P4). With exposure fixed costs, robust top-f coverage and warm-state
benefits the full MILP took 20-35 s with large gaps on 200 workers. Three bounds keep it tractable, each a choice the
greedy planner already makes implicitly: a *planning pool* of at most `max_plan_workers` live workers (previous
holders first, then capacity × assurance; P5 clusters bound it further); *candidate* workers per tenant (previous
holders plus the best by the greedy score, 3× what robust coverage needs); and `fn_snaps` = warm units + 1 snapshot
copies per function. The solver gets a node limit and the greedy plan as a competing incumbent; the better objective
is kept (status `greedy_incumbent:*`), so the MILP is never worse than greedy (P4 exit test). An unchanged input
signature (workers, hot set, demand buckets) reuses the previous plan (status `reused`).

**D-31 The planner runs beside the fast loop** (P4). A plan is computed on the view at its start and applied after its
charged latency (decision clock kind `plan`), but it does not hold the scheduler's `busy_until`: the slow loop runs
on its own core, so placements are not delayed by a solve. Its actions are diffed against the workers' confirmed
state (heartbeat `pinned`, cache inventory), not against the previous plan.
**D-32 Clusters plan for their region's demand** (P5). With priced spillover (doc 03 §3) a cluster that receives no
traffic for a tenant never becomes trust-warm for it, so it keeps paying the trust-cold penalty and keeps receiving
no traffic: in the first multi-cluster pilot one cluster served 80% of the world and `nearest` routing beat `score`.
Routers therefore count every invocation against its *home* cluster (nearest by RTT, whatever it was routed to);
the orchestrator forwards these rates each period (`HOME_DEMAND`), and the arrival forecaster plans for
max(local, home) per tenant and function. In equilibrium local ≈ home, so nothing is double counted. *Rejected:*
routing exploration (wastes cold starts), dropping the trust-cold term (removes priced spillover).

**D-33 Cluster cards carry measured in-cluster overhead** (P5). `E[completion_c(f)]` in the routing score is
execution (the same in every cluster up to speed) plus the cluster's overhead. Cards report an EWMA of decision time
plus slot wait as measured by the scheduler (excluding the router hop, which `rtt` already counts, and trust and
start-up, which the trust-warm and warm-function terms price), decaying to a prior when idle so stale values cannot
lock traffic out. The health penalty applies only above the unhealthy threshold θ (doc 03 §2). *Rejected:* the
scheduler's mean service time (reflects each cluster's function mix, not its quality).

**D-34 Hard per-worker migration budget** (P5 exit: bounded migrations). Dwell time and a cap per period bound
rebalancing moves but not structural ones (merge/split). The orchestrator also enforces `max_moves_per_h` (default
3) per worker over a sliding hour, across sessions: merges wait until every member is eligible, splits move only
eligible members (and only if at least `min_size` remain eligible). A property test drives the trigger policy
through random churn and summaries and checks the bound in every one-hour window.

**D-35 Moves are explicit and fenced by cluster** (P5). The orchestrator moves a worker with `ASSIGN(cluster)`; the
worker accepts `EPOCH_INSTALL` and `DISPATCH` only for its assigned cluster (an install that arrives before the
`ASSIGN` is held) and answers others with `STALE(cluster)`. The source scheduler gets the worker in `MEMBERSHIP.moved`
and drops it from its view without retrying its in-flight copies: they still report to the scheduler that
dispatched them. *Rejected:* treating a move as a loss (needless retries and duplicate execution).

**D-36 Spillover withdraws the invocation** (P5). On spillover (no `ACCEPTED` within `T_spill`) the router sends
`WITHDRAW` to the previous cluster's scheduler, which forgets the invocation and cancels any copies already
dispatched; an `ASSIGNED` that still arrives from a cluster the router spilled away from is cancelled. Otherwise
both clusters could run it and the router could pair an input with the wrong attempt.

**D-37 P2P sources must beat the registry** (P5, fixes P4). Residential uplinks are often slower than the registry, so
the nearest peer is not the fastest source (a 175 MB bundle at 6 Mbps up takes ~230 s). Source hints rank peers by
expected pull time (RTT + bytes / min(peer uplink / (1 + busy), target downlink)) and keep only peers faster than the
registry estimate; snapshots, which the registry does not serve, keep the fastest eligible peers.
