# Design Decisions (ADR log)

Format: **Decision** · Why · Alternatives rejected · Revisit if. Resolves the spec's "open decisions" (§15).

**ADR-001 Custom Python DES instead of SimGrid.** The FaaS-relevant physics (transfer, disk, CPU slots, fixed
delays) is small; real solver time must enter simulated time; 10⁵ peers need light state; ship fast. Resource
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

**ADR-007 Ledger is an asynchronous service model; permissioned, validators = cluster orchestrators/federation.**
Public chain is a different parameter set. Headline status: **supporting (C5)**, with the signed-log baseline
always reported. Real chain calibration optional.

**ADR-008 Control plane replicated on volunteer Tier 1/2 hosts spread over failure domains; one named residual SPOF:
a tiny provider-owned bootstrap root** (peer discovery, ledger genesis, orchestrator seeds). Costed in E15.
Modeled as replica groups, not an implemented consensus protocol.

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
signature-verification cost. **This narrows spec §3.1 #7 / §4.5:** lazy-worker verification becomes an optional
extension (`threat_model: crash_plus_lazy`, off by default, reported separately), and reputation measures
commitment-keeping/timeliness. *Revisit if* reviewers require a Byzantine-worker evaluation; the extension exists for
that.

**ADR-017 Scheduler = replicated state machine per cluster; single active leader with hot standbys (Raft-lite).**
Replicated entries: `ENQUEUE`, `ASSIGN`, `OUTCOME`, `EPOCH_CLOSE`, `CONFIG`. Followers apply entries, never re-solve
the ILP; heartbeats go to all replicas. `dispatch: committed` default, `speculative` for idempotent functions.
Safety via terms + fencing at peers. *Rejected:* active-active sharding of invocations (duplicates slot accounting,
needs conflict resolution; small clusters already bound the work); chain-based election (puts finality on the
critical path); timer-only failure model (hides geography and quorum cost). See 07.

**ADR-018 Scheduler work is recorded on the ledger and credited.** Epoch records (assignment Merkle root, leader
terms, counts) are log entries so a new leader resubmits unacked batches; chain dedupes by
`(cluster, term, epoch_id)`. The ledger is audit and reward only, never election or fencing.

**ADR-019 Reproducibility contract.** Lockfile + Dockerfile, run manifests with result hashes, `voss repro`
asserting hash equality, `replay` decision-clock mode to reproduce `measured` solver experiments, deterministic
single-threaded solver settings, no unseeded randomness. See 01 §9.

**ADR-020 Actor model with a single `net.send` for all cross-node interaction.** Geo-derived delay applies to
control messages (heartbeats, replication, election, ledger) and data alike; actors cannot call each other, which
prevents spaghetti and unrealistic zero-latency shortcuts.

**ADR-021 Clusters are small by design (tens of peers; target from E02).** ILP cost grows quickly with window ×
cluster size, scheduler hosts are slow volunteers, and a small cluster keeps quorum RTT low. Control-role overhead
(`r` of `N` peers) is reported and tuned jointly with `N_target` (E21).

*Amends:* **ADR-007** (validators run a CFT group on `ReplicationGroup`; finality derives from quorum RTT);
**ADR-008** (control plane = replica groups per 07; bootstrap root remains the one named SPOF); **ADR-014**
(adds `replay` mode).
