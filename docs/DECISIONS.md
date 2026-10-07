# Design Decisions (ADR log)

Format: **Decision** · Why · Alternatives rejected · Revisit if. Resolves the spec's "open decisions" (§15).

**ADR-001 Custom Python DES instead of SimGrid.** The FaaS-relevant physics (transfer, disk, CPU slots, fixed
delays) is small; real solver time must enter simulated time; 10⁵ workers need light state; ship fast. Resource
models are behind narrow interfaces. *Rejected:* SimGrid (heavy integration, binding limits), SimPy (generator
style hurts determinism/profiling for little gain). *Revisit if* reviewers require it; do the optional SimGrid
micro-scenario cross-check (P9).

**ADR-002 World/observe/policy separation; policy never imports world.** Enforces "no future information"
mechanically and makes every policy a pure, testable function. *Rejected:* convention-only discipline.

**ADR-003 Precomputed traces for churn, arrivals, network, control faults.** Common random numbers across compared
systems; real traces plug in via the same schema. Invocation true runtime is drawn from a per-invocation stream.

**ADR-004 Single `CostMatrix` consumed by all placers.** Isolates algorithm effects from input effects; makes
min-cost-flow vs. ILP vs. greedy a fair comparison.

**ADR-005 Primary objective = expected SLO-violation cost with `ε·E[T]` regularizer** (spec §8.1), implemented as
one scalarizer among several; P99 is an evaluation metric only. Completion distribution by moment-matched shifted
lognormal; approximation stated in the paper.

**ADR-006 Hybrid placement: fast-path greedy for sync SLO, windowed ILP/flow for async/filler and
rebalancing/prewarm planning.** Answers "ILP in the loop vs. on the side" as a configurable axis; E02 sets the
default window and cluster size.

**ADR-007 (superseded by ADR-027)** Ledger as an asynchronous service model; permissioned, validators = cluster orchestrators/federation.**
Public chain is a different parameter set. Headline status: **supporting (C5)**, with the signed-log baseline
always reported. Real chain calibration optional.

**ADR-008 (superseded by ADR-022/023/024)** Control plane no longer relies on volunteer replica groups or a bootstrap root;
the provider-run orchestrator tier is the single named centralized component.

**ADR-009 Reliability (survival model) and reputation have disjoint inputs.** Churn/preemption → survival only;
verification/commitment → reputation only. Avoids double counting; ablation `reputation_includes_failures`
demonstrates the effect.

**ADR-010 Default predictor: hierarchical Bayesian linear regression in log space with forgetting and a conformal
calibration wrapper.** Gives a distribution, cold-start priors and cheap online updates; compared against EWMA, GBQ,
kNN. Heavy tails handled via Student-t scale and conformal scaling.

**ADR-011 ILP solver: SciPy HiGHS MILP default, OR-Tools CP-SAT as second solver; matching via SciPy
`linear_sum_assignment`.** Few dependencies, time limits supported. Slot-expansion handles queue coupling; `y`
(start-up sharing), memory packing and domain caps are the constraints that justify integer programming.

**ADR-012 Backstop provider pool: ablation only.** Not in default config.

**ADR-013 No real testbed in the POC.** Only a Firecracker/SeBS calibration microbenchmark (P9); stated as a threat
to validity.

**ADR-014 Decision clock has `measured` and `modeled` modes.** Measured for E02 (solver tail behavior), modeled for
sweeps (reproducible and fast). Both logged.

**ADR-015 Workflows (SeBS-Flow) parked.** Secondary evaluation; add only after core results.

## Added after design review

**ADR-016 Fault model is crash-fault tolerant, not Byzantine, for all nodes.** Workers, schedulers, routers,
orchestrators and validators may crash, be preempted, drain, or be partitioned; none is assumed to lie (a scheduler
never writes false records to the chain). Consequences: CFT consensus for validators, term/fencing for safety, no
signature-verification cost. **This narrows spec §3.1 #7 / §4.5:** lazy-worker verification is dropped (see ADR-026: vetted
honest volunteers; only an optional canary audit remains), and reputation measures
commitment-keeping/timeliness. *Revisit if* reviewers require a Byzantine-worker evaluation; the extension exists for
that.

**ADR-017 (superseded by ADR-024)** Raft-lite replicated-log schedulers: kept only as the `raft_group` baseline.

**ADR-018 (superseded by ADR-027/028)** Scheduler work recorded on the ledger and credited. Epoch records (assignment Merkle root, leader
terms, counts) are log entries so a new leader resubmits unacked batches; chain dedupes by
`(cluster, term, epoch_id)`. The ledger is audit and reward only, never election or fencing.

**ADR-019 Reproducibility contract.** Lockfile + Dockerfile, run manifests with result hashes, `voss repro`
asserting hash equality, `replay` decision-clock mode to reproduce `measured` solver experiments, deterministic
single-threaded solver settings, no unseeded randomness. See 01 §9.

**ADR-020 Actor model with a single `net.send` for all cross-node interaction.** Geo-derived delay applies to
control messages (heartbeats, appointment, roll call, checkpoints) and data alike; actors cannot call each other, which
prevents spaghetti and unrealistic zero-latency shortcuts.

**ADR-021 Clusters are small by design (tens of workers; target from E02).** ILP cost grows quickly with window ×
cluster size, scheduler hosts are slow volunteers, and a small cluster keeps quorum RTT low. Control-role overhead
(`r` of `N` workers) is reported and tuned jointly with `N_target` (E21).

**ADR-022 Roles and lingo are fixed: orchestrator, scheduler, worker.** The orchestrator is provider-run (cloud),
not a volunteer, assumed reliable, and includes the front-door routers, operational DB (private to the tier); failure of
this tier is out of scope and named as the centralized component (spec §5.5 requires naming it). A scheduler is a
role on a worker; any eligible worker can be promoted.

**ADR-023 Operational DB is cloud-hosted and orchestrator-owned.** Holds membership, epochs and succession lists,
scheduler checkpoints, function registry, global reputation, work log (see ADR-028). Never on the invocation critical path;
modeled with cloud-region latency and availability 1.0. Costs reported.

**ADR-024 Scheduler fault tolerance = succession with soft state, no consensus among volunteers.** Orchestrator
arbitrates epochs (CAS, Kubernetes-lease style); workers fence by epoch; scheduler state is a cache rebuilt by
roll call (Mesos-style reconciliation) plus checkpoint in the cloud DB; routers retain pending invocations until
the worker's `ACCEPTED`; workers keep results and outcomes on a direct path; successors are ranked by survival ×
speed × centrality with failure-domain diversity; hazard-triggered proactive handover. *Why not Raft among
volunteers:* needs a simultaneous majority and a majority to reconfigure, brittle at high churn, quorum RTT on every
decision. *Rejected:* active-active sharding; chain-based election. See 07.

**ADR-025 Worker crash tolerance:** predictor-driven per-invocation watchdogs and hedging under a budget, accrual
detector, push signals as known availability, storm control, crash-recover rejoin.

*Amends:* **ADR-007** **ADR-014** (adds `replay` mode); **ADR-016** (honesty now justified by vetting, ADR-026).

**ADR-026 Volunteers are vetted at admission and assumed honest but unreliable.** Admission (institutional email,
research ID, consortium membership; out of implementation scope, stubbed as `identities`) ties each node to an
accountable identity; reputation binds to it. Rationale: TEE/confidential microVMs (~2 s boot vs ~20 ms,
`TODO verify`), 2f+1 voting (no comparable result for side-effecting functions) and ZK proofs (too slow) are all
infeasible for ephemeral FaaS. Limitations and critics: 09 §6. Only optional extension: known-answer `canary_audit`.

**ADR-027 No blockchain (public or private).** With vetted honest writers and a trusted provider, a chain protects
against no actor in the threat model and never proved correct execution anyway. Work is recorded in an append-only
`invocation_log` in the orchestrator's DB, credits are derived from it. A provider-signed Merkle transparency log is
the parked alternative if volunteer-facing auditability is needed. Consequences: C5 becomes an accounting/incentive
layer, RQ10 and H7 are reframed (09 §4, §7).

**ADR-028 The DB is private to the orchestrator tier; hot path never touches it; one writer per datum; routers write
the work log.** Workers and schedulers use messages (08 §3.3); `APPOINT` embeds snapshots; DB writes from schedulers
are epoch-fenced; the live queue and per-worker pending jobs are intentionally not stored (recoverable from routers
and workers).

**ADR-029 Worker readiness (time-to-start) is an explicit ILP input.** The scheduler computes per-core `ready_at` from
heartbeat `WorkerState`, predictor residuals conditioned on elapsed time, queued jobs, in-flight dispatches and
staleness; it forms the slot ladder and feeds `T_wait` + `T_startup` (with image-pull overlap) into the cost matrix
(08 §5).
