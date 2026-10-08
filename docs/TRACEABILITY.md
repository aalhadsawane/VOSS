# Traceability: research spec → design → code → phase

The spec (`VOSS_research_spec.md`) is the original research brief. Deliberate deviations are listed in doc 04 §11.

| Spec | Requirement | Design doc | Module(s) | Phase |
|---|---|---|---|---|
| §3.1 #1–3 | Owner preemption, diurnal/correlated, heavy-tailed availability | 02 §2 (donation sessions) | `world/sessions` | P1 |
| §3.1 #4 | Heterogeneity, sandbox variance | 02 §1, §5; 10 | `world/hardware`, `substrate`, `lifecycle` | P1–P2, P9 |
| §3.1 #5 | Stale state | 01 §5, 08 §5 | `observe/*` | P2 |
| §3.1 #6 | Donor costs | 02 §6, 03 §4.2 | `world/cache`, `policy/plan` | P2, P4 |
| §3.1 #7 | Untrusted participants | 04 (attestation; malicious → omission) | `runtime/verifier`, `tenant_kbs`, `world/adversary` | P2, P6 |
| §3.1 #8 | Newcomers | 03 §6, 09 §2 | predictors, reputation probation | P3, P7 |
| §3.2 | Serverless concerns | 02 §4–8, 03 §5 | Cold starts and keep-alive: ladder + caches + planner. Images: P2P content-addressed. Scale-to-zero: plan `w=0`. Concurrency/sizing/timeouts: execution. Semantics: `idempotent` gates hedge/retry. Bursts: admission + spillover. Multi-tenancy: microVMs + Jain. Versioning: cache invalidation. Billing: credits vs reference cloud. Drain: sessions. Control plane: 07. **Workflows parked (D-22)** | P2–P8 |
| §4.2 | Supply tiers, filler | 02 §1 (nightly/idle/dedicated), 03 §5.4 | `world/workers`, `policy/admission` | P1, P3 |
| §4.3 | Onboarding, probation, calibration | 04 §5, 09 §2, 10 | verifier, reputation, harness | P2, P7, P9 |
| §4.4 | Reliability vs reputation | 09 §1 (three disjoint signals) | `policy/survival`, `omission`, `reputation` | P3, P7 |
| §4.5 | Verifiable work ledger | 09 §3 (attested receipts, **no chain**) | `runtime/router`, `accounting` | P7 |
| §4.6 | Departure modes, drain | 02 §2, 07 §4 | `world/sessions`, scheduler | P1, P6 |
| §5.1–5.4 | Hierarchy, dynamic clusters | 03 §2–3 | `policy/route`, `orchestrate`, runtime actors | P5 |
| §5.5 | Control-plane fault tolerance | 07 | `runtime/succession`, `fault_driver` | P6 |
| §6 C1–C6 | Contributions | 00 §1, 06 §3 | — | P10 |
| §7 | microVM lifecycle, keep-alive, snapshots, P2P images | 02 §5–6, 03 §4 | `world/lifecycle`, `cache`, `policy/cache_value`, `plan` | P2, P4 |
| §8.1–8.4 | Objective, inputs, prediction, scalarization | 03 §5–6, 08 §5 | `policy/cost`, `predict` | P3 |
| §8.5 | Where integer programming is needed | 03 §8 | `policy/plan/milp`, `place/*` | P3–P4 |
| §8.6 | Cluster size × solve time × latency | 06 E02 | decision clock | P4 |
| §9 | Methodology, validation, reproducibility | 01 §1, §8; 10 | harness, manifests | P0, P9 |
| §10–12 | RQs, baselines, experiments | 06 | `experiments/*` | P8–P10 |
| §13 | Metrics | 06 §2 | `metrics/schema` | P2+ |
| §14 | Principles | AGENTS.md, 05 §7–8 | linters, invariants | P0 |
