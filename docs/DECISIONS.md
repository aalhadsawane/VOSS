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
