# VOSS: Volunteer-Oriented Serverless Scheduling

Research proof-of-concept: scheduling latency-sensitive serverless functions on **untrusted, unreliable,
geo-distributed volunteer machines**. Attestation turns malicious volunteers into merely unreliable ones; VOSS then
schedules **trust as a perishable resource** with geo-clustered, two-timescale (robust planner + fast placer)
scheduling.

The deliverable is a deterministic simulator, the VOSS scheduler, baselines and experiments, calibrated on a real
consumer node (Intel i7 12th gen, TPM 2.0). No frontend, no real multi-machine deployment, no blockchain.

## Read in this order

| Doc | What it answers |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Rules for coding agents (binding) |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Build phases with exit criteria: **start here to code** |
| [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md) | Problem, thesis, roles, layers, two-timescale scheduling, invocation flow |
| [`docs/architecture/01-simulation-core.md`](docs/architecture/01-simulation-core.md) | Kernel, determinism, actors and messages, decision clock, reproducibility |
| [`docs/architecture/02-environment-model.md`](docs/architecture/02-environment-model.md) | Workers, donation sessions, network, substrate ladders, **worker caches**, adversaries, workload |
| [`docs/architecture/03-scheduling.md`](docs/architecture/03-scheduling.md) | Orchestrator, router, **slow-loop planner (robust MILP)**, fast-loop placement, prediction |
| [`docs/architecture/04-trust-and-security.md`](docs/architecture/04-trust-and-security.md) | Threat model, substrates, attestation, key release, identity, exposure, limitations |
| [`docs/architecture/05-code-structure.md`](docs/architecture/05-code-structure.md) | Package layout, layering, types, interfaces, config, tests, recipes |
| [`docs/architecture/06-experiments.md`](docs/architecture/06-experiments.md) | RQs, hypotheses, baselines, experiment catalogue, statistics |
| [`docs/architecture/07-fault-tolerance.md`](docs/architecture/07-fault-tolerance.md) | Progress-based detection, scheduler succession, worker omission handling |
| [`docs/architecture/08-state-and-protocols.md`](docs/architecture/08-state-and-protocols.md) | Operational DB, message catalogue, worker readiness |
| [`docs/architecture/09-reputation-and-accounting.md`](docs/architecture/09-reputation-and-accounting.md) | Reliability vs reputation, attested receipts, credits |
| [`docs/architecture/10-calibration.md`](docs/architecture/10-calibration.md) | Calibration harness on the real node, single-box emulation testbed |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Current design decisions (D-01…D-22) and history |
| [`docs/TRACEABILITY.md`](docs/TRACEABILITY.md) | Research spec → design → code → phase |
| [`VOSS_research_spec.md`](VOSS_research_spec.md) | Original research brief (deviations: doc 04 §11) |
| [`docs/research/`](docs/research/), [`docs/proposals/`](docs/proposals/) | Evidence and design history (accepted) |
| [`docs/AGENT_PROMPT.md`](docs/AGENT_PROMPT.md) | Paste-ready prompt for a coding session |

## Status

Architecture final (2026-10-09). Implemented: P0 scaffold, P1 world and scenarios, P2 attested vertical slice, P3
prediction and fast loop, P4 trust and warm-state planner with cache policy, P5 geo hierarchy, P6 fault tolerance
and adversaries, P7 accounting and reputation (pilots in [`docs/pilots/`](docs/pilots/)).
Calibration (P9) waits for SSH access to node C0; until then C0 values are literature/assumed placeholders.
