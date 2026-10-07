# Traceability: spec → design → phase

| Spec | Requirement | Module(s) | Doc | Phase |
|---|---|---|---|---|
| §3.1 #1–3 | Owner preemption, diurnal/correlated, heavy-tailed availability | `world/availability` | 02 §2 | P1 |
| §3.1 #4 | Heterogeneity, microVM variance | `world/worker`, `lifecycle` | 02 §1, §5 | P1–P2 |
| §3.1 #5 | Stale state | `observe/statestore` | 01 §5 | P2 |
| §3.1 #6 | Donor costs | `world/lifecycle` accounting, `cost.donorCost` | 02 §5, 03 §7 | P2–P3 |
| §3.1 #7 | Untrusted participants → **vetted honest volunteers** (09, ADR-026) | `identities` stub, `reputation`, optional `canary` | 09, 04 §1 | P5–P6 |
| §3.1 #8 | Newcomers | probation, predictor priors | 03 §5, 04 §1 | P3, P5 |
| §3.2 | Serverless concerns (all items; see notes below) | `world/*`, `policy/keepalive`, `policy/cost`, `runtime/worker_agent` | 02 §4–6, 03 §4, §10 | P2–P8 |
| §4.2 | Tiers, filler | `worker.tier`, scheduler filler | 02 §1, 03 §4 | P5 |
| §4.3 | Onboarding, probation, calibration | `worker.benchmark`, reputation | 02 §1, 04 §1 | P1, P5 |
| §4.4 | Reputation vs. reliability | `reputation`, `survival` | 03 §6, 04 §1 | P5 |
| §4.5 | Verification, ledger → **router-written work log + credits, no blockchain** (ADR-027) | `accounting`, `opdb` | 04 §2–3, 08 §3 | P6 |
| §4.6 | Departure modes, drain | `availability`, scheduler reaction | 02 §2, 04 §5 | P1, P5 |
| §5.1–5.4 | Hierarchy, dynamic clusters | `route`, `orchestrate`, `runtime/*` | 03 §1–4 | P4 |
| §5.5 | Control-plane FT; scheduler as volunteer-hosted SPOF | `succession`, `scheduler`, `opdb`, `faults` | 07 | P2 (appointment, no failover), P7 |
| §4.5 | Scheduler work tracked (added) | `invocation_log` rows carry epoch/scheduler; `scheduler_roles` | 07 §7, 08 §3 | P6–P7 |
| §8.2 | Worker readiness / time-to-start as ILP input | `WorkerState`, cost model `ready_at` | 08 §5, 03 §7 | P3 |
| §9 | Reproducibility | manifest, `voss repro`, lockfile, Docker | 01 §9 | P0 |
| §7 | MicroVM lifecycle, snapshot compat, P2P images | `world/lifecycle` | 02 §5 | P2, P5, P9 |
| §8.1 | Objective and scalarizations | `cost`, `scalarize` | 03 §7 | P3 |
| §8.3 | Predictors | `policy/predict` | 03 §5 | P3 |
| §8.5 | MCF vs ILP vs greedy | `policy/place` | 03 §8 | P3 |
| §8.6 | Cluster size × solve × latency | decision clock, E02 | 01 §6, 06 §4 | P3–P4 |
| §9 | Methodology, validation, reproducibility | scenario, manifest, E01 | 01, 06 §6 | P1, P9 |
| §11 | Baselines and ablations | registry, configs | 06 §3 | P3–P8 |
| §12 | Experiments | `experiments/` | 06 §4 | P8–P10 |
| §13 | Metrics | `metrics/schema`, analysis | 06 §2 | P2+ |
| §14 | Principles | AGENTS.md, import-linter, invariants | 05 | P0 |
| §6 H1–H10 | Hypotheses | E02–E20 | 06 §4 | P10 |

## §3.2 serverless concerns: where each is handled

Cold start ladder, keep-alive, image distribution: lifecycle model + keep-alive policies (P2, P5). Scale-to-zero:
`ttl=0` plus prewarm (P5). Concurrency, sizing/OOM, timeouts: execution model (P2). Semantics: `idempotent` flag
gates retry/hedge (P1, P3). Bursts, admission, backpressure: scheduler admission and router spillover (P3–P4).
Multi-tenancy: interference model; Jain index across functions (P8). Versioning: lifecycle invalidate (P5). Cost and
billing: reference-cloud $/GB-s vs. VOSS credits (P6, P8). Observability: StateStore staleness (P2).
Control-plane FT and drain: 04 (P5, P7). **Function composition/workflows: justified exclusion, parked
(ADR-015)**; external state is modeled as a storage endpoint.
