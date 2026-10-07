# VOSS: Volunteer-Oriented Serverless Scheduling

Research proof-of-concept: a simulator-based scheduling framework for latency-sensitive, ephemeral serverless
invocations on heterogeneous, geo-distributed, owner-preemptible volunteer machines.

> Paper: *A Scheduling Framework for Serverless Computing over Heterogeneous, Geo-Distributed, Unreliable
> Volunteer-Based Edge Resources.*

This is **not a real platform**. No frontend, no real networking, no real blockchain. The deliverable is a
deterministic simulator, the VOSS scheduler running inside it, baselines, and experiment results.

## Read in this order

| Doc | What it answers |
|---|---|
| [`VOSS_research_spec.md`](VOSS_research_spec.md) | What must be true and answered (research source of truth) |
| [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md) | Scope, principles, layers, invocation flow |
| [`docs/architecture/01-simulation-core.md`](docs/architecture/01-simulation-core.md) | Kernel, determinism, ground truth vs. observed state, decision latency |
| [`docs/architecture/02-environment-model.md`](docs/architecture/02-environment-model.md) | Peers, churn, network, microVM lifecycle, workloads |
| [`docs/architecture/03-scheduling.md`](docs/architecture/03-scheduling.md) | Router, orchestrator, cluster scheduler, prediction, cost, ILP/flow/greedy |
| [`docs/architecture/04-trust-and-control-plane.md`](docs/architecture/04-trust-and-control-plane.md) | Reputation, ledger (incl. scheduler work), rewards, drain; optional verification extension |
| [`docs/architecture/05-code-structure.md`](docs/architecture/05-code-structure.md) | Package layout, dependency rules, interfaces, config |
| [`docs/architecture/06-experiments.md`](docs/architecture/06-experiments.md) | Metrics, runner, baselines, experiment catalogue, validation |
| [`docs/architecture/07-scheduler-replication.md`](docs/architecture/07-scheduler-replication.md) | Replicated volunteer-hosted schedulers: failover, fencing, hosting, on-chain scheduler records |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Build phases with exit criteria (start here to code) |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Design decisions and why (cite in the paper) |
| [`docs/TRACEABILITY.md`](docs/TRACEABILITY.md) | Spec section → module → phase |
| [`AGENTS.md`](AGENTS.md) | Rules for coding agents working in this repo |
| [`docs/AGENT_PROMPT.md`](docs/AGENT_PROMPT.md) | Paste-ready prompt to start a coding agent |

## Ground rules (one-liners)

Crash-fault model only (no Byzantine nodes) · schedulers are replicated volunteer-hosted actors · all node-to-node
traffic pays geo-derived network delay · every run is reproducible from a manifest with one command.

## Status

Design phase complete; implementation starts at Phase 0 in the roadmap.
