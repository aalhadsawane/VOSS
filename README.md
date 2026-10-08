# VOSS: Volunteer-Oriented Serverless Scheduling

Research proof-of-concept: a simulator-based scheduling framework for latency-sensitive, ephemeral serverless
invocations on heterogeneous, geo-distributed, owner-preemptible volunteer machines.

> Paper: *A Scheduling Framework for Serverless Computing over Heterogeneous, Geo-Distributed, Unreliable
> Volunteer-Based Edge Resources.*

This is **not a real platform**. No frontend, no real networking, no blockchain (see 09). The deliverable is a
deterministic simulator, the VOSS scheduler running inside it, baselines, and experiment results.

> **⚠ Design under revision (2026-10-08):** the threat model is changing to *malicious, unreliable volunteers running
> tenant code in confidential VMs*. See [`docs/proposals/0001-confidential-voss.md`](docs/proposals/0001-confidential-voss.md).
> Until it is accepted and the docs are refactored, only Roadmap **P0–P1** may be implemented; hold P2+.

## Read in this order

| Doc | What it answers |
|---|---|
| [`VOSS_research_spec.md`](VOSS_research_spec.md) | What must be true and answered (research source of truth) |
| [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md) | Scope, principles, layers, invocation flow |
| [`docs/architecture/01-simulation-core.md`](docs/architecture/01-simulation-core.md) | Kernel, determinism, ground truth vs. observed state, decision latency |
| [`docs/architecture/02-environment-model.md`](docs/architecture/02-environment-model.md) | Workers, churn, network, microVM lifecycle, workloads |
| [`docs/architecture/03-scheduling.md`](docs/architecture/03-scheduling.md) | Router, orchestrator, cluster scheduler, prediction, cost, ILP/flow/greedy |
| [`docs/architecture/04-reputation-and-accounting.md`](docs/architecture/04-reputation-and-accounting.md) | Reputation, router-written work log, credits, drain |
| [`docs/architecture/05-code-structure.md`](docs/architecture/05-code-structure.md) | Package layout, dependency rules, interfaces, config |
| [`docs/architecture/06-experiments.md`](docs/architecture/06-experiments.md) | Metrics, runner, baselines, experiment catalogue, validation |
| [`docs/architecture/07-fault-tolerance.md`](docs/architecture/07-fault-tolerance.md) | Scheduler succession, worker crash tolerance |
| [`docs/architecture/08-state-and-protocols.md`](docs/architecture/08-state-and-protocols.md) | What the cloud DB stores and who accesses it, message catalogue, worker readiness (time-to-start) for the ILP |
| [`docs/architecture/09-threat-model.md`](docs/architecture/09-threat-model.md) | Vetted honest volunteers, why no blockchain, critique, deviations from the spec |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Build phases with exit criteria (start here to code) |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Design decisions and why (cite in the paper) |
| [`docs/TRACEABILITY.md`](docs/TRACEABILITY.md) | Spec section → module → phase |
| [`docs/proposals/0001-confidential-voss.md`](docs/proposals/0001-confidential-voss.md) | **Active redesign proposal** (CVMs, malicious hosts) |
| [`docs/research/confidential-computing-sota.md`](docs/research/confidential-computing-sota.md) | Confidential-computing SOTA notes and numbers |
| [`AGENTS.md`](AGENTS.md) | Rules for coding agents working in this repo |
| [`docs/AGENT_PROMPT.md`](docs/AGENT_PROMPT.md) | Paste-ready prompt to start a coding agent |

## Ground rules (one-liners)

Crash-fault model only (no Byzantine nodes) · orchestrator (provider-run) / scheduler (a role on a worker) / workers, scheduler failover by succession · all node-to-node
traffic pays geo-derived network delay · every run is reproducible from a manifest with one command.

## Status

Design phase complete; implementation starts at Phase 0 in the roadmap.
