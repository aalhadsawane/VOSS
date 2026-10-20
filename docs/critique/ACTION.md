# VOSS: action plan after the critique register

**Purpose.** `CRITIQUE.md` lists 33 criticisms. This document decides, from a wider lens, what to do about each of them: change
phrasing, run a cheap analysis, run new experiments, or make a design change that redoes results. It also asks the questions a
serverless or systems reviewer would ask (novelty, utility, feasibility, how industry copes) and answers them as honestly as the
evidence allows. It ends with the list of items that need a major change and redone experiments, with high-level design
directions. It does **not** change code, configuration or architecture.

**Status of the claims here.** Facts about this repository are checked against the code and the committed results. Facts about
other systems come from public documentation and papers found while writing this document; they are listed in Section 9 and
should be re-verified before they are quoted in a submission. Effort estimates are mine and rough.

**Vocabulary for the decisions.**

| Class | Meaning | Touches results? |
|---|---|---|
| **T** | Text: phrasing, scoping, disclosure | No |
| **A** | Analysis of data that already exists (for example the raw logs of release `paper-runs-39066209828`) | No new simulation |
| **S** | Sweep: new runs from configuration changes only | Adds results; existing ones stay valid |
| **C** | Code and runs: a new baseline, variant or model, then runs | Adds results; may shift some existing ones |
| **M** | Major: changes the headline architecture, or invalidates results so that many experiments are redone | Yes |

Actions runners are free (public repository) and a full sweep of the 21 experiments takes about four hours of wall-clock time,
so **re-running is cheap; re-analysing, re-writing and re-validating is the real cost.**

---

## 1. The wider lens

### 1.1 What is the paper actually claiming?

1. **A formulation (the main idea).** On volunteer hardware, attestation turns malice into omission and timing faults, and what
   remains is a scheduling problem over *attested session state*: costly to establish, perishable, exposing.
2. **Mechanisms.** A slow planner (robust coverage, exposure-aware) and a fast placer (per-invocation miss probability),
   progress-based detection, epoch-fenced scheduler failover on soft state, attested receipts.
3. **Evidence.** A deterministic simulator calibrated on one laptop, ten paired seeds, 21 experiments, pre-stated hypotheses with
   negative results reported, and a partial single-machine validation (E01).

### 1.2 Novelty: what is new and what is assembled

| Element | Assessment |
|---|---|
| "Attested session state" as a scheduled resource (cost, perishability, exposure) | **New framing.** This is the paper's centre of gravity. |
| Planner with robust coverage and exposure in one objective | **New combination** of known pieces (cardinality-constrained robust optimisation, greedy provisioning). |
| Per-invocation miss-probability placement and risk-proportional hedging | Known ideas (hedged requests, cost-based placement) applied to this setting. |
| Progress-based detection, epoch fencing, soft state | Known distributed-systems patterns (leases, fencing tokens, gray-failure literature); the new part is the *argument* that attestation lets them replace consensus among volunteers. |
| Negative results (geo-clustering, MILP, caching, reputation) | Valuable and unusual. A reviewer will credit the honesty. |

**Reading.** The conceptual contribution (1) is real. The mechanisms are competent engineering around it. A reviewer will not
call it "incremental" if (1) is argued well and the evaluation is credible; they will if the evaluation looks like it tests
only the easy head of the workload on a model nobody validated.

### 1.3 Utility: who would use it, and why?

The evaluation itself says a commercial-style reference has lower latency and VOSS is cheaper per invocation only above about
20 inv/s. So the utility case is **not** "faster than Lambda". It rests on three things, none of which the paper currently argues
quantitatively:

- capacity that already exists and is otherwise idle (the provider does not buy servers for it);
- proximity to users where no datacenter or edge site exists;
- a trust model that allows donated machines at all.

The review exposed that the **supply** is narrower than the introduction says (C-08): a donor reboots into an appliance and
cannot use the machine meanwhile. The most credible supplies are therefore:

1. **Managed fleets of machines an organisation already owns** (office or lab desktops at night, spare racks, community
   clusters). The owner is an organisation, so physical-access threats (C-06), NAT (C-01), abuse (C-26) and incentives (C-25) are
   all milder.
2. **Dedicated spare machines of individuals** (the model's `dedicated` and `nightly` tiers).
3. Idle-triggered home PCs (the model's `idle` tier). This is the least plausible and should not carry any claim.

**Decision P1 (positioning, T):** say plainly that the target supply is (1) and (2), keep (3) out of the claims, and keep the
consumer-volunteer story as the stretch case that the substrate abstraction allows. This costs no experiment, and removes a large
fraction of the objections that a security or systems reviewer would raise.

### 1.4 Feasibility: could it be built?

- **Appliance, attestation, microVMs:** yes, with existing parts (Keylime-style attestation, Firecracker, a measured UKI image). E01
  already ran real Firecracker microVMs on a lab node.
- **Provider control plane:** yes; every serverless provider runs routers, a placement service, a registry and a database.
- **Volunteer-hosted scheduler:** feasible only with relays or reachability filtering (Section 5). This is the least
  conventional element.
- **Consumer confidentiality:** not with a TPM alone (C-06). It needs memory encryption, which most consumer CPUs lack (Intel
  deprecated SGX on 11th/12th-generation client Core processors; server TEEs are the supported path).

### 1.5 Would a serverless expert find it acceptable? (my judgement)

Likely first-round comments, in rough order of severity, and where this document puts the answer:

| Reviewer | Comment | Where handled |
|---|---|---|
| Serverless | "Functions are not idempotent; what is the contract?" | C-09/C-10, Section 6.2 |
| Serverless | "Cold-start baselines are weak: where are histogram policies, snapshots, provisioned concurrency?" | C-15, C-33 |
| Serverless | "Six tenants and twelve functions do not resemble production traces; no external I/O." | C-14, C-21, Section 6.3 |
| Serverless | "Why would anyone prefer this to cheap spot or edge capacity? You are slower." | C-25, P1 |
| Security | "TPM measured boot is not confidentiality against the machine's owner." | C-06, P2 below |
| Security | "The verifier decides who gets keys; it is in your trusted base." | C-05 |
| Distributed systems | "Why is the coordinator on an untrusted NAT-ed home machine at all?" | C-01, C-31, Section 5 |
| Methodology | "Simulation only; placeholder decision costs; confounded baselines; E01 says 'partly'." | C-16, C-24, C-28 |

**Judgement.** As written in draft 8, the paper is an interesting formulation with an honest but thin evidence base. At a top
systems venue the likely outcome is "reject, encouraging", because there is no real implementation and the workload and
scheduler-placement questions are open. With the Track 0 to Track 2 work in Section 7 it becomes a credible
design-and-simulation study for an IEEE Transactions journal (the stated target), with limits stated. It does not become an
NSDI or OSDI paper without a real deployment.

**Decision P2 (positioning, T):** state the confidentiality guarantee as conditional on memory encryption. Sensitive tenants
require a TEE-backed substrate (`cvm_snp` or a successor) through the assurance floor; TPM-only hosts serve tenants whose data
is not secret (public-data inference, rendering, transcoding) or who accept the exposure.

---

## 2. How industry accommodates each concern

| Concern | Industry practice | What it means for VOSS |
|---|---|---|
| Where does the scheduler run? | Lambda's frontend, worker-manager and placement services run in provider infrastructure; BOINC servers have public addresses; volunteers are only workers. | A provider-hosted scheduler is the norm. A volunteer-hosted one has no mainstream precedent in serverless. |
| Reaching NAT-ed machines | BOINC is client-initiated and pull-based, which is why it works behind NAT and firewalls. P2P stacks use hole punching and relays; a 2026 large-scale measurement reports about 70% hole-punching success. | Volunteers should only ever dial out to public endpoints. Relays are needed for the rest. |
| Coordinators on volunteer hosts | Skype's supernodes were volunteer machines; Skype moved all of them into Microsoft datacenters (reported 2012) for reliability, after an outage in which a large share of supernodes failed. | A direct precedent for moving a volunteer-hosted coordinator to the provider. |
| Retries and idempotence | Lambda does not retry synchronous invocations (the caller does); it retries asynchronous ones twice and the documentation tells developers to make handlers idempotent. | State an explicit contract; at-least-once with idempotent handlers is the accepted norm. |
| Key release | Azure Key Vault and Managed HSM release a key only to an attested environment under a **claims-based policy the key owner defines**; the attestation service is a provider or third-party service whose token the key vault trusts. | "Tenant-operated KBS" in practice means a *tenant-defined policy in a managed key service*, with the attestation authority trusted by choice. VOSS's KBS is that, described as if the tenant ran it. |
| Confidentiality against the machine owner | Confidential computing (TEEs with memory encryption) exists for this and is offered on server CPUs. Measured boot alone is "integrity". | VOSS's TPM-only substrate cannot claim confidentiality against a physical attacker (P2). |
| Cold starts | Fixed keep-alive timers, histogram-based policies (Azure), snapshot-based starts, provisioned concurrency. | The planner is a forecast-driven pre-provisioner; baselines should include the adaptive and snapshot-based families (C-15, C-33). |
| Scheduler availability | Provider-run replicated services with leader election (the manuscript itself cites Chubby). | The epoch-fencing protocol is the same idea, needed only because the leader would be a volunteer. |

---

## 3. Is any of this out of scope?

A concern is **in scope** if it changes what the paper's headline claims mean or what the evaluation supports. It is **out of
scope** if it is deployment engineering that every volunteer or edge system must solve and that does not interact with the
scheduling claims.

| Out of scope (state and move on) | In scope (must be answered) |
|---|---|
| PKI details, root distribution (C-03) | Who hosts the scheduler, and what that does to the hot path (C-01, C-31) |
| NAT-traversal *stack* (STUN/ICE implementation) | Whether the hot path needs inbound reachability of volunteers, and the cost of the relay if it does |
| Abuse, egress policy, legal responsibility (C-26) | Idempotence contract (C-09, C-10): it decides what "success" means |
| Billing, incentives beyond credits (part of C-25) | Threat-model scope (C-06) and the verifier's role (C-05) |
| Control-plane replication details (C-04) | Workload realism and baseline strength (C-14, C-15, C-21) |
| Snapshot demand-paging tails (C-23), beyond one sentence | Decision-latency charging (C-16) |

---

## 4. Triage of all 33 items

Priority: **P0** do before any submission; **P1** strongly recommended; **P2** nice to have or future work.

| ID | Critique | Class | Priority | Recommendation |
|---|---|---|---|---|
| C-01 | Scheduler behind NAT | C (variant) + T | **P0** | Section 5: model the relay explicitly, sweep relay parameters, add the provider-hosted variant |
| C-02 | Addressing, reconnect storms | T + S | P1 | State the rendezvous assumption; sweep `relayed_frac`/`relay_extra_ms`; reconnect cost is a later emulation item |
| C-03 | PKI | T | P2 | Done in text; out of scope |
| C-04 | Reliable control plane | T | P1 | State the provider-tier requirement from E18 data (A) |
| C-05 | Verifier in the confidentiality base | T + S | P1 | Scope the claim; sweep the KBS policy cost (`kbs_check_s` with and without a fresh quote) |
| C-06 | Physical RAM access | T (positioning P2) | **P0** | Narrow G1; require TEE substrates for sensitive tenants |
| C-07 | Tenant-run KBS | T | P1 | Describe as tenant-defined policy in a managed service (industry norm) |
| C-08 | Reboot-to-donate | T (positioning P1) + A | **P0** | Narrow the supply claim; compute the share of session time spent establishing from existing logs |
| C-09 | Idempotence | S + T | **P0** | Sweep the idempotent fraction; state the contract |
| C-10 | At-least-once failover vs non-idempotent | S + T | **P0** | Same sweep, report success per class; pick the contract |
| C-11 | Exposure/assurance scores arbitrary | S + T | P1 | Re-run E23 under two assurance tables |
| C-12 | `T_plan` unswept | S | P1 | Add `T_plan ∈ {10, 30, 60, 120}` to the paper experiments |
| C-13 | Robust coverage value; Poisson sizing | S + T | P1 | Compare with plain over-provisioning (larger `q`); reword |
| C-14 | Tenant-keyed planner; six tenants | C + S | P1 | Part of the workload extension (Section 6.3) |
| C-15 | Weak keep-alive baseline | C | **P0** | Add a histogram-style adaptive keep-alive baseline on volunteer hosts |
| C-16 | Solver cost mis-charged | S (+ M if all coefficients are refit) | **P0** | Section 6.1 |
| C-17 | MILP size, pool cap | A + T | P1 | Report instance sizes; E02-style curve from existing pilot data |
| C-18 | Fast-loop weights | S | P1 | `ε` and `λ_exp` sensitivity |
| C-19 | One scheduler per cluster | C | **P0** | Part of Section 5 |
| C-20 | Watchdog constants, adaptive adversary | S (constants); adaptive adversary P2 | P1 | Sweep the three main constants; adaptive adversary as future work |
| C-21 | Workload realism | C + S | P1 (P0 if targeting a top venue) | Section 6.3 |
| C-22 | Estimators in a matching world | S | P2 | Error injection and a misspecified world, future work or small sweep |
| C-23 | Snapshot restore definitions | T | P2 | Done |
| C-24 | E01 scope | T + later C | P1 | Reported; extend emulation to the network/session later |
| C-25 | Economics | T + A | P1 | Break-even analysis from E17 (A) and reposition (P1) |
| C-26 | Abuse, supply side | T | P2 | One scope paragraph |
| C-27 | Hedging definitions | T | P2 | Done |
| C-28 | Geo-clustering confounds | S/C | **P0** | Redesign E05 (Section 5.8) |
| C-29 | Errors in our text | T | done | Fixed in draft 8; remaining doc-03 line |
| C-30 | Terminology | T | done | |
| C-31 | Why a volunteer scheduler | C (variant) | **P0** | Section 5 |
| C-32 | Positioning of the supply (new) | T | **P0** | Decisions P1 and P2 |
| C-33 | Baseline families vs industry cold-start techniques (new) | C | P1 | With C-15 |

Notes on the two new items (added to `CRITIQUE.md`): **C-32** is the supply positioning above; **C-33** asks for snapshot-based
and provisioned-concurrency style baselines, not only keep-alive timers.

---

## 5. Where the scheduler runs

This is the one question that can change the architecture, so it gets a full analysis. The rule for the manuscript throughout:
**the volunteer-hosted scheduler is the design that was built and evaluated, and it stays in the paper as exactly that.** The
provider-hosted scheduler is added as an alternative, with its consequences and, if run, its own results. Nothing about the
volunteer-hosted design is softened or removed.

### 5.1 The two designs

- **D_v (current).** The scheduler role runs on one attested volunteer machine per cluster of 10 to 60 machines. The orchestrator
  appoints it, a router's watchdog detects its failure, and an epoch fences zombies. Scheduler state is soft.
- **D_p (alternative).** The same scheduler code (planner and placer, unchanged) runs on provider infrastructure, one instance per
  cluster or per region. Workers still dial out to it. The attested image no longer contains scheduler code.

### 5.2 The case for D_v, argued as strongly as it honestly can be

1. **Thin provider.** The provider runs routers, a verifier, a database and a registry, all of which scale with *traffic or
   fleet size*, not with the *number of clusters*. Volunteer-hosted schedulers add scheduling capacity with every cluster of donors
   without the provider provisioning anything. This is an operational argument, and it is real for a provider that wants a small
   control plane.
2. **Compute offload for the exact planner.** The exact MILP costs about 4 s of solver time per cluster per period. At 10⁵
   workers that is about 450 cores of continuous solving (Section 5.5). Volunteers would absorb it.
3. **Research value.** If the scheduler can live on an untrusted, churning host, the same pattern (attested code, soft state,
   lease and fencing, provider arbiter) applies to other coordinators on unreliable nodes (edge, vehicular, community clouds).
   The paper shows this works in simulation. That is a transferable result independent of whether it is the best deployment.
4. **No loss of trust.** The scheduler sees only metadata, and its code is attested. A volunteer-hosted scheduler decides as
   correctly as a provider-hosted one.
5. **Blast radius.** A scheduler failure affects one cluster (but so would a per-cluster provider scheduler).

**Where this case is weak:** items 1 and 5 have the same answer under D_p if schedulers are sharded per cluster; item 2 only
matters if the exact planner is used, which the paper's own decision rule demotes (H8); the only argument that survives
unchanged is item 3, which is about research value, not about the better system.

### 5.3 Networking constraints of D_v

1. **Inbound reachability.** Workers are behind NAT and dial out. The scheduler is also behind NAT. A worker's outbound stream
   to a scheduler that cannot accept inbound connections cannot be established directly.
2. **Hole punching is not reliable.** A large-scale measurement of libp2p's hole punching reports about 70% success. About 30% of
   pairs need a relay, and carrier-grade NAT is common.
3. **Address changes.** Home addresses change. A scheduler's new address must reach every router, and all workers of the cluster
   must reconnect, which makes a scheduler change a synchronised reconnect storm through relays.
4. **Relays on the hot path.** If relays carry the control streams, they add a hop and are a provider component that is absent from
   the architecture figure, the trust table and the threat model.
5. **Residential uplink.** The scheduler's uplink and jitter matter for dispatch latency; the simulator models last-mile RTT but
   not uplink contention at the scheduler.
6. **What the simulator does.** It adds 20 ms per relayed endpoint (assumed) for 15% of workers and treats the rest as directly
   reachable. That is inconsistent with "workers sit behind NAT" (C-01).

Bandwidth is **not** the problem: control traffic is about 0.46 KB/s per worker (E18 pilot), so a cluster of 30 is about
14 KB/s and 10⁵ workers is about 46 MB/s in total.

### 5.4 Solutions for D_v (high level)

| Option | Idea | Consequence |
|---|---|---|
| **S1. Provider relay / rendezvous** | Scheduler and workers both dial out to a provider-run relay that forwards encrypted streams. | Faithful to D_v. Adds a provider component and one hop. Payloads still go router to worker directly. |
| **S2. Reachability-aware appointment** | The verifier probes inbound reachability (public IPv6, port mapping, verified punch) at attestation. Only reachable hosts are eligible schedulers. | No new component. Shrinks the succession pool (potentially to about 30–70% of hosts). Adds a rank criterion. |
| **S3. Both** | S2 where possible, S1 as fallback. | Most robust D_v. |
| **S4. D_p** | Host the scheduler on the provider. | Removes the problem; see 5.7. |

Recommended for the manuscript: describe S1 as the assumed mechanism for D_v, evaluate it by making the relay explicit in the
network model with sweeps of `relayed_frac` (0, 15%, 30%, 100%) and relay overhead, and compare with D_p.

### 5.5 Greedy is enough even without volunteer compute

Using only numbers the paper reports (planning cost: greedy 8 ms, exact 4.1 s per cluster solve, period 30 s; clusters of about
30; control traffic 0.46 KB/s per worker), the provider-side cost of hosting all schedulers is:

| Workers | Clusters (÷30) | Greedy planning (cores) | Exact planning (cores) | Placement at 0.01 inv/s per worker (cores, 0.8 ms each) |
|---|---|---|---|---|
| 10³ | 33 | 0.009 | 4.6 | 0.008 |
| 10⁴ | 333 | 0.09 | 46 | 0.08 |
| 10⁵ | 3,333 | 0.9 | 455 | 0.8 |

(Per-decision placement cost is the modelled 0.2 ms + 20 µs × (invocations × hosts in the scheduler's view), about 0.8 ms for one
invocation and a cluster of 30; E01 found the real decision step 2–29% longer than modelled, so the order of magnitude is right.
A compiled implementation would be faster.)

Consequences:

- **Greedy planning is essentially free for a provider**, under one core at 10⁵ workers. The only compute saving D_v offers is
  for the exact planner, and the exact planner's benefit is not established (H8: 1.8% at medium churn, 8.1% at high churn with a
  confidence interval that includes zero, and its real solve time of 4 s is not charged by the simulator; C-16).
- So the answer to "which planner" does **not** depend on where the scheduler runs: greedy is the better default under both
  designs, because the exact planner costs hundreds of provider cores or hundreds of volunteer-hosted solves for a gain that is
  not demonstrated.
- If a provider *did* want the exact planner, D_p lets it run on provider hardware with a time budget, which volunteer hosts
  (slow, unreliable) are worse at. That is one more point for D_p.

### 5.6 Latency: D_p removes a hop

In D_v every synchronous invocation does router → scheduler → router → worker before input moves: the router waits for the
scheduler (a volunteer host, maybe behind a relay) to answer. In D_p the router and scheduler can be one regional service or sit
in one datacenter, so that round trip becomes microseconds. This is the hop inside `T_route + T_decide` (Eq. 1). The paper's
Lambda-like comparison shows VOSS 45% slower at the median at 20 inv/s (0.425 s vs 0.292 s). How much of the 133 ms is this hop
is **unknown** and can be measured (class A) from the per-invocation component logs in the release assets, then tested directly
with D_p (class C).

### 5.7 What changes in the architecture if the scheduler is provider-hosted

| Area | Change under D_p |
|---|---|
| Scheduler failover (§VII-C) | Becomes ordinary provider high availability. Epoch fencing, roll call, succession list, warm standby and zombie self-fencing are not needed against *volunteer* faults. (Leader election inside the provider is routine and trusted.) |
| Threat model | Scheduler-host adversaries disappear (black-holing or slow scheduler, fake drain by a scheduler host). Worker-side adversaries and progress detection of workers remain, which is the part with the most novelty. |
| Attested image | The scheduler code leaves the appliance. Smaller measured image, smaller code base for volunteers to trust and for the verifier to track. |
| Clusters and orchestrator | Clusters existed to bound the planner and to host one volunteer scheduler. Under D_p, cluster size is a tuning parameter. E05 (global beat clustered) says larger scheduling domains are better; a provider scheduler can be sized to hundreds of workers. Dynamic k-medoids rebalancing becomes optional. |
| Routers | A router and a scheduler can be merged into a regional front end: the ENQUEUE/DISPATCH round trip disappears. |
| Connections | Workers dial out to a public, stable endpoint. No NAT problem for the control stream, no relay, no reconnect storm on a scheduler change. |
| State and DB rule | The "hot path never touches the DB" rule becomes a performance guideline; the provider scheduler can hold state in memory with ordinary persistence. The checkpoint-every-30-s machinery becomes optional. |
| Evaluation | E15 (scheduler faults) changes meaning; E18 (scale) measures one provider service's capacity and how to shard it; E05 becomes the sizing question for scheduling domains. |
| Contribution list | The planner/placer and attested-session-state formulation stay at the centre. The "fault tolerance without volunteer consensus" contribution would become a secondary result about coordinators on unreliable nodes, presented as an option (D_v). |
| Unchanged | The planner and placer logic, estimators, exposure, receipts, key release, the information boundary rule, hedging and idempotence rules. |

### 5.8 What the current evidence can and cannot say about D_v vs D_p

- Planner and placer results (E04, E19, E20, E23, E24) are largely independent of where the scheduler runs, except through the
  `T_route + T_decide` hop and decision latency. They are expected to hold under D_p; this is a prediction to test (E-SCHED).
- Fault-tolerance results (E15, parts of E08, E14, E16) are specific to D_v.
- E05 does **not** answer the scheduler-placement question: it compares one global scheduler with clusters, where the global
  baseline plans over at most 40 hosts and at 20 inv/s is never loaded (the scheduler is modelled as a single server whose service
  time grows with the number of hosts in its view: 0.2 ms + 20 µs per host, about 0.8 ms for a cluster of 30 and 4.7 ms for the
  225 attested hosts of the global scheduler. It saturates near 1,250 inv/s for 30 hosts and near 210 inv/s for 225 hosts, and
  near 50 inv/s for 1,000 hosts; E05 runs at 20 inv/s, about 10% utilisation, so it never reaches the regime where clustering
  should pay).
- E18 shows the central decision path as the scaling limit, using placeholder decision-cost coefficients (C-16), so it cannot yet
  be read as a property of D_v.

### 5.9 The experiment that settles it (E-SCHED, high level)

Run the headline experiments with `scheduler_host ∈ {volunteer, provider}`, same code and seeds, and report: P50/P99 and the
deadline-met fraction; failover and detection (E15); provider cost; exposure. Add a load sweep (hundreds to thousands of inv/s,
thousands of workers) that finally stresses a single scheduler, and a sweep of the relay fraction for D_v. Expected outcome to
test: planner conclusions unchanged; D_p lower latency by about one router-scheduler round trip; D_v worse under high relay
fraction and during scheduler changes; D_v's advantage limited to provider compute for the exact planner.

**Feasibility from the code (my reading, to be confirmed):** the scheduler is already an actor that is attached to a host and
that the orchestrator appoints (`voss/runtime/orchlib/appoint.py`); infrastructure hosts (routers, verifier) already exist as
located nodes; a reference-cloud precedent exists for always-up provider hosts (`voss/world/reference_cloud.py`). A provider-hosted
scheduler is a host class that never has sessions or omission and an appointment that never changes. I expect a few hundred
lines and tests plus configuration. The relay model (S1) is a modification of the network model (`voss/world/network.py`).

### 5.10 How the manuscript should present it

1. **§IV and §VII keep D_v exactly as built**, with the motivation stated (thin provider, harder case, offload of the exact
   planner, transferable pattern) and the networking assumption stated (outbound-only connections through a provider relay).
2. A new **Discussion subsection, "Where the scheduler runs"**, gives D_p, the networking constraints, the compute argument of 5.5
   and the consequences of 5.7. It states plainly whether it was evaluated.
3. If E-SCHED is run, its results are a new subsection in the evaluation and the contribution list says the paper quantifies the
   trade-off. If it is not run, the text says so and calls it future work.
4. The abstract and conclusion keep volunteer-hosted scheduling as a contribution only to the extent the evidence supports it.

---

## 6. The other places where the answer may be "major"

### 6.1 Decision-latency model (C-16)

- **Problem.** The planner is charged about 0.1 s whatever the solver does; the exact planner really takes 4 s. The "place"
  coefficient also enters every experiment (E01: the real step is 2–29% longer than modelled), and E18's scaling conclusion rests
  on these placeholders.
- **Options.** (a) *Minimal:* refit only the planning coefficient, per planner, from E02 and E04 wall times; rerun E04, E23 (and the
  E02 pilot). The 8% MILP result will move. (b) *Full:* refit all coefficients from E01 and E02; rerun **all 21 experiments**,
  because the placement cost enters every latency.
- **Recommendation.** (a) now, (b) if the paper wants absolute-latency claims. Class S for (a), M for (b), with four hours of
  Actions time either way. The effort is in re-checking the manuscript's numbers and sentences (the generator will flag any claim
  that stops being supported).

### 6.2 Idempotence contract (C-09, C-10)

- **Problem.** Success under omission relies on re-dispatch, which needs idempotence; the workload is 11/12 idempotent by
  assumption.
- **Design direction.** Adopt the industry-standard contract explicitly: at-least-once execution, idempotent handlers required,
  with a provider-side idempotency-key facility as an optional extension so that retries are safe at the API boundary. For
  non-idempotent functions the platform offers at-most-once (no retry; failure reported).
- **Experiments.** Sweep the idempotent fraction (0%, 25%, 50%, 75%, 92%) and report success separately by class for E08, E14,
  E15, E16. Configuration only (S). Existing results remain valid as the 92% point.

### 6.3 Workload realism (C-14, C-21, C-33)

- **Problem.** Six tenants and 12 functions never exercise the planner's hot-set limits; no heavy tail; no external I/O.
- **Design direction.** Add a second workload family, not a replacement: hundreds of tenants and thousands of functions with
  heavy-tailed popularity (synthetic, parametrised from the published Azure trace statistics, or trace-driven), and correlated
  functions per tenant. No new algorithm is expected; the question is what the planner does with a long tail. The existing results
  stay as the "small workload" case.
- **Experiments.** Re-run E04, E19, E20, E23 on the new workload and report the unprovisioned-path share. Class C (a workload
  generator) then S. Add snapshot-based and adaptive keep-alive baselines here (C-15, C-33).

### 6.4 Threat-model narrowing (C-05, C-06)

- **Problem.** The confidentiality claim is stronger than a TPM provides against a physical attacker; the verifier is in the
  trust base in the default key-release mode.
- **Design direction.** Narrow G1 to software-level owners; make "TEE-backed substrate required for sensitive tenants" the rule,
  expressed through the existing assurance floor; present key release as tenant-defined policy at a managed key service with the
  attestation authority chosen by the tenant; describe the fresh-quote mode as the strict option.
- **Experiments.** None required. A small sweep of the key-release cost (with and without a fresh quote) shows the price of the
  strict mode (S).

### 6.5 Geo-clustering redesign (C-28)

- **Problem.** The global baseline is advantaged and unloaded.
- **Design direction.** Re-run E05 with the same planning-pool rule for both, and a load sweep that includes loads where one
  scheduler is the bottleneck; report where clustering starts to pay. This is subsumed by E-SCHED if D_p is run.

---

## 7. Plan

| Track | Content | Classes | Changes existing results? | Rough effort |
|---|---|---|---|---|
| **0. Text now** | P1/P2 positioning; C-03/04/05/07/08/23/26 scoping; verifier and KBS description; idempotence contract statement; reviewer-facing limits | T | No | 1–2 days |
| **1. Cheap sweeps** | `T_plan`, `ε`, `λ_exp`, assurance tables, watchdog constants, KBS policy cost, relay fraction, idempotent fraction, planning-coefficient refit (6.1a) | S, A | Adds; MILP rows (E04, E23) move | 2–3 days incl. manuscript updates |
| **2. Additive code** | Histogram and snapshot baselines (C-15, C-33); workload family (6.3); explicit relay model (5.4 S1) | C then S | Adds; relay model may shift all runs slightly if made the default | 4–7 days |
| **3. Scheduler placement** | `scheduler_host` switch, E-SCHED, redesigned E05, load sweep | C then S | Adds; may become the default architecture | 3–5 days plus decision |
| **4. Full refit (optional)** | 6.1b: refit all decision costs; rerun all 21 experiments | M | **Yes** | 1–2 days plus manuscript pass |

**Order.** 0 → 1 → 3 → 2. Track 3 before Track 2 because the answer to "where does the scheduler run" decides whether the
fault-tolerance section stays central, which affects how the rest of the paper is framed.

**Is it worth it?** Track 0 and 1 are clearly worth it: they remove the cheapest reviewer objections and cost days. Track 3 is
worth it because it addresses the strongest structural objection (C-31) and may even improve results; the risk is that it shows D_p
dominating D_v, which would reduce one of the three contributions. That is better learned now than from a reviewer. Track 2 is worth
it if the venue is competitive; its workload part is the most valuable single addition. Track 4 is worth it only if absolute
latencies are to be claimed.

---

## 8. The items that need a major change (and redone experiments), with directions

Only the following change architecture or force results to be redone. Directions are intentionally high level.

| # | Item | Why it is major | Design direction | Experiments redone |
|---|---|---|---|---|
| **M1** | Scheduler placement (C-01, C-02, C-19, C-28, C-31) | May change the headline architecture and the contribution list. Even as an additive variant it needs new code and a new experiment family. | Keep D_v as built. Add D_p as a host-class switch. Make the relay explicit for D_v (S1) with S2 as an optimisation. If D_p wins, present D_v as an option and D_p as the recommended deployment. | E05 redesigned; E15, E17, E18 under both; headline experiments (E04, E19, E20) under both as a check. If D_p becomes default: all 21. |
| **M2** | Decision-latency charging (C-16) | Changes the MILP results and, with a full refit, every latency. | Charge decision cost from measured runs: a fitted function of problem size per planner; refit the placement coefficient from E01/E02. | E04, E23, E02 for the minimal option; all 21 for the full option. |
| **M3** | Workload realism (C-14, C-21) | Not a change of design, but new evidence that could overturn "planning pays" for the tail. | Second workload family with many tenants and a heavy tail; correlated functions; same planner and placer. | E04, E19, E20, E23 on the new workload (existing results kept). |
| **M4** | Idempotence contract (C-09, C-10) | Changes what "success" means; may expose a large success drop under omission for non-idempotent mixes. | At-least-once with idempotent handlers as the contract; optional provider idempotency keys; at-most-once for the rest. | E08, E14, E15, E16 swept over the idempotent fraction. |
| **M5** | Baseline strength (C-15, C-33) | New baselines can narrow "planning lowers P99 by 27–57% against keep-alive". | Adaptive keep-alive (idle-time histogram) and snapshot-based start baselines on volunteer hosts. | E04, E19 (comparison rows). |

Not major: everything else in Section 4 (T, A, or small S).

**Decisions needed from you (for the back-and-forth):**

1. Positioning P1/P2: agree that the target supply is managed or dedicated machines and that confidentiality is conditional on
   memory encryption?
2. M1: build the provider-hosted variant and run E-SCHED, with D_v kept as the studied design?
3. M2: minimal refit (planning coefficient only) or full refit?
4. M3: is a competitive venue the goal (then the workload family is mandatory), or a journal where the current workload with
   disclosure may suffice?
5. M4: which contract do you prefer for non-idempotent functions?

---

## 9. Sources for external facts used here (re-verify before quoting)

- Hole-punching success about 70% (large-scale measurement, IMC 2026 paper; earlier 2022 talks 60–80%): https://arxiv.org/html/2510.27500v1 and https://probelab.io/blog/can-libp2p-punch-through-nats/
- Lambda asynchronous retries (two retries, handlers should be idempotent), synchronous invocations not retried by the service: https://docs.aws.amazon.com/lambda/latest/dg/invocation-retries.html and https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html
- Skype supernodes moved into Microsoft datacenters (2012), motive reliability after a 2010 outage: https://en.wikipedia.org/wiki/Skype
- BOINC is client-initiated, pull-based, server must be publicly reachable: https://arxiv.org/pdf/1903.01699
- Azure secure key release with claims-based policy defined by the key owner, attestation token from an expected authority: https://learn.microsoft.com/en-my/azUre/confidential-computing/concept-skr-attestation
- Intel SGX deprecated on 11th/12th-generation Core client processors, continuing on Xeon: https://www.intel.com/content/www/us/en/support/articles/000089271.html
- Lambda's provider-run frontend, worker manager and placement services (secondary write-ups; check the Firecracker NSDI paper): https://www.infoq.com/articles/aws-lambda-under-the-hood/

Not searched, from general knowledge, to verify: Lambda SnapStart uses snapshot-based starts; Azure's hybrid-histogram keep-alive is
per application.
