# 09 · Threat Model: Vetted, Honest, Crash-Prone Volunteers (and No Blockchain)

> **Superseded in progress:** proposal [`0001-confidential-voss`](../proposals/0001-confidential-voss.md) replaces this vetted-honest model with malicious hosts on confidential VMs.

Decision record: ADR-016 (crash-only), ADR-026 (vetted membership), ADR-027 (no blockchain).

## 1. The assumption

> **VOSS runs on a closed federation of vetted volunteers.** Every volunteer is admitted by a vetting step that ties
> the node to an accountable real-world identity. Admitted nodes are **honest but unreliable**: they crash, are
> preempted by their owners, drain, churn and are heterogeneous, but they do not deliberately forge results,
> reports or accounting records. The orchestrator tier is operated by the platform provider and is trusted.

Vetting is **out of scope of the implementation** (the simulator stubs `identities`), but it is part of the system
design and must be stated in the paper. Examples of vetting sources: institutional (`.edu`/organizational) email,
research identifiers (e.g., ORCID), verified professional profiles, or an existing consortium membership. Rules: one
identity per human, revocable, reputation bound to the identity (so rejoining after a crash keeps history, and
creating fresh identities is gated by vetting, which removes Sybil and whitewashing as first-order problems).

## 2. Why not stay open and tolerate malicious nodes? (the three alternatives, all rejected)

| Mechanism | What it would give | Why it does not fit ephemeral FaaS |
|---|---|---|
| **1. TEE / confidential microVMs** | Host cannot tamper with or read function state; attestable | Requires TEE-capable hardware on every volunteer (not the commodity assumption), and confidential-VM boot is reported around ~2 s versus ~20 ms for a plain Firecracker microVM (`# TODO verify`). For functions that run for milliseconds to seconds, start-up would dominate and destroy the latency premise |
| **2. Replicated execution + majority vote (2f+1)** | Tolerates up to f lying workers | Triples the cost; most serverless benchmark functions have **no comparable result** (they write to object storage, call APIs, or have side effects), so there is nothing to vote on, and duplicate side effects break idempotency; nondeterminism breaks equality |
| **3. Zero-knowledge / verifiable computation** | Cryptographic proof of correct execution | Proof generation is orders of magnitude slower than the function itself (`# TODO verify`); infeasible for latency-sensitive work |

Therefore the project scopes the problem the way most distributed schedulers do (Borg, Kubernetes, Mesos assume
non-Byzantine components): **tolerate crashes, not lies**, and obtain honesty from admission control instead of
from per-invocation cryptography or redundancy.

## 3. Why the assumption is defensible in the paper

1. **It matches the problem's novelty.** The paper's challenge is unreliability, geography, heterogeneity and cold
   starts, not adversaries. Crash-fault tolerance is the standard model for production control planes.
2. **Vetted federations are a real deployment class** (campus/lab machines, research-institution grids, consortium
   or community clouds; analogues such as WLCG/EGI-style certificate-vetted sites, PlanetLab and Grid'5000 style
   institutional testbeds; `# TODO verify` before citing). Here identity is accountable and misbehavior has
   real-world cost (removal, institutional consequences).
3. **Incentives are non-monetary credits and reputation**, so the payoff from cheating a vetted identity is low and
   the cost (ban) is high.
4. **It is explicit.** We state the scope and list what it excludes (§6), and we keep the optional audit extension
   (§5) so reviewers see what a stronger model would cost.

Suggested paper paragraph: *"We target a federated deployment in which volunteers are vetted at admission (for example
by institutional email or research identity). Nodes may crash, be preempted or churn at will but are assumed not to
behave maliciously; we therefore provide crash-fault tolerance for workers and schedulers, not Byzantine tolerance.
Open deployments with anonymous volunteers require additional mechanisms (trusted hardware, redundant execution or
verifiable computation), which we discuss as future work and which, in the serverless regime, face the
latency and side-effect obstacles of Section X."*

## 4. Do we still need a blockchain? **No: removed.**

What a blockchain provides: tamper-evident, agreed-upon records among writers who do not trust each other or a
single operator. Who writes our records, and do they need that?

| Record | Writer | Trust situation | Chain needed? |
|---|---|---|---|
| Work done (`invocation_log`) | Routers (provider, trusted) | One administrative domain | No |
| Assignments, epochs, roles | Orchestrator | Provider, trusted | No |
| Worker/scheduler reports | Vetted honest nodes | Honest by assumption | No (a lying reporter is excluded by the assumption; a lying scheduler *could* only matter if nodes were malicious) |
| Credits | Orchestrator batch job over the above | Provider | No |

The only party a chain would protect volunteers from is the **provider** altering credits, which is a transparency
question, not a correctness one. And the spec itself notes that a chain never proves the work was done correctly
(§4.5): its real value was only tamper-evidence. Under our model it would add finality latency, fees, validator
infrastructure and a "who runs validators" question, for no gain. **Decision: no blockchain; no private chain.**

**What replaces it:** an append-only **work log in the operational DB** (`invocation_log`, written by routers) plus a
derived `credits` table (08 §3). The spec's "centralized append-only log" baseline *becomes* the design.

**Feasible alternative if volunteer-facing auditability is ever required (parked):** a provider-signed
**transparency log** (Merkle-tree append-only log with signed tree heads, as in Certificate Transparency) lets
volunteers verify their credits without consensus or a chain. Cheap and optional; not built in the POC.

**Impact on the research framing (see §7):** C5 becomes an *incentive and accounting layer* (reputation + credits
from router-observed ground truth, supporting contribution); RQ10 becomes "what does accounting cost and how
complete is it under failures"; H7 becomes "accounting is off the critical path and adds negligible latency"
(true by construction, tested by invariant). The "what does the chain buy" question is answered honestly: nothing
under this threat model.

## 5. Residual faults and the optional audit extension

The honest assumption does not cover **honest-but-faulty** behavior: silent data corruption, misconfiguration,
over-declared envelopes, clock skew, or a vetted insider gaming credits. Mitigations, cheapest first:

| Fault | Handling |
|---|---|
| Over-declared envelope / slow delivery | Reputation (`ENVELOPE_SHORT`), survival and predictor learn actual behavior (03 §6) |
| Transfer corruption | Content digests on images, payloads, results (cheap, always on) |
| Lazy or fake results, credit gaming | **Optional extension `canary_audit` (off by default):** the orchestrator injects known-answer, deterministic, side-effect-free *canary invocations* to a small fraction (~1%, `# TODO measure`) of workers and checks output and plausibility of reported time. Works where majority voting cannot (no replication of real side-effecting work); detects statistically, not per-invocation. Cost = the canary fraction of capacity, reported in E13 |
| Insider credit gaming | Credits are non-monetary; ban by identity; plausibility check of reported `exec_s` against the predictor |

This replaces the earlier `crash_plus_lazy` replicated-verification extension (replication has the side-effect
problem above).

## 6. Honest critique and limitations (put in threats to validity)

| Critic | Response / what we do |
|---|---|
| "A closed vetted pool is not the open volunteer computing you motivated." | True: the target is a *federated/institutional* volunteer pool. The paper should frame motivation accordingly (idle institutional and community hardware) and say that vetting trades pool size for trust |
| "Honest nodes make this a plain cluster scheduler." | The difficulty is churn, owner preemption, correlated availability, geography, heterogeneity and cold starts, none of which depend on adversaries; that is the paper's contribution |
| "A vetted insider can still cheat." | Credits non-monetary, identity-bound bans, optional canary audits; stated as a limitation |
| "Why no blockchain, your spec had one." | It protected only against an untrusted operator, which is not our threat model; a transparency log is the cheap alternative. Chains are future work for open deployments, where they still would not prove correct execution |
| "Silent corruption isn't crash-stop." | Out of scope except for digests and the optional canaries |

**No stronger feasible alternative exists** for the open setting in the serverless regime (all three mechanisms in §2
fail on latency, cost or side effects); the only genuinely useful addition is the cheap canary audit, which we include
as an optional extension rather than a default.

## 7. Deviations from the research specification

The research spec (`VOSS_research_spec.md`) is unchanged; these are the decisions of the design docs that depart
from it. Each should be reflected in the paper's scope.

| Spec | Spec says | Design decision | ADR |
|---|---|---|---|
| §3.1 #7, §4.5 | Untrusted participants; verify before anchoring | Vetted honest nodes; crash-fault only; optional canary audit | 016, 026 |
| §4.5, C5, RQ10, H7 | Tamper-evident blockchain ledger, anchoring, settlement | **No blockchain.** Router-written work log + derived credits in the orchestrator's DB | 027 |
| §5.5 | No SPOF on volunteer-hosted components; orchestrator redundant | Orchestrator tier is provider-run and assumed reliable (named, costed); volunteer scheduler made crash-tolerant by succession | 022, 024 |
| §5.1 | Cluster orchestrator, router, scheduler | Router lives in the orchestrator tier (regional front doors) | 022 |
