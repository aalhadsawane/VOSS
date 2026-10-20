# VOSS: critique and defense register

**Purpose.** This is the working document for the critique-and-rebuttal round. It lists every criticism of VOSS that came out of the
advisor-prep review of the explainer deck (marked **[U]**), every adjacent problem found while checking the code, the docs and the
manuscript (**[A]**), and every problem that appears only when two or more criticisms are combined (**[X]**). Each item states the
critique, the evidence in the repository, the best defense available today, where that defense is weak, and what would resolve it.

**Rules of this document.**

- **No code, configuration or architecture was changed to write it.** Items marked "Resolution options" are options, not actions.
  Whether any of them become a design change is the purpose of the later back-and-forth.
- Evidence cites repository paths. Numbers are from the draft-7 manuscript, `paper/`, `configs/`, `voss/` and `runs-e01/`.
- A defense is only listed if it is true of the current system. Where the honest answer is "the paper does not specify this", the
  defense says so.
- Statements about other systems (AWS Lambda, Azure, BOINC) come from public documentation and the papers cited in the manuscript.
  They should be verified against the sources before they are quoted in a submission.

**Legend.**

| Tag | Meaning |
|---|---|
| **[Design]** | A criticism of the architecture or of a mechanism of VOSS itself |
| **[Eval]** | A criticism of the evidence (simulator, workload, baselines, statistics) |
| **[Text]** | The manuscript or explainer is unclear or wrong; the system is not at fault |
| **S1** | Could change a headline claim or would need an architectural change if the critique stands |
| **S2** | Weakens a claim; needs a disclosure, an experiment or a scoped claim |
| **S3** | Clarity or minor |
| **Status** | `Open` (not yet argued), `Text fixed` (manuscript/explainer updated, design question remains), `Error fixed` |

---

## 0. Index

| ID | Title | Tags | Origin |
|---|---|---|---|
| C-01 | The scheduler is a volunteer host behind NAT: who can dial whom? | Design, S1 | U |
| C-02 | Address discovery, address changes and reconnect storms | Design, S1 | U, X(C-01) |
| C-03 | PKI: who issues which certificate, and who holds the roots | Design, S2 | U |
| C-04 | "Reliable by assumption" control plane is most of a serverless platform | Design, S1 | A, X(C-01) |
| C-05 | The verifier is in the confidentiality trust base, contradicting "never tenant secrets" | Design, S1 | A, X(C-03,C-07) |
| C-06 | Property 1 does not cover runtime physical access to RAM on consumer hardware | Design, S1 | A |
| C-07 | The tenant-operated key broker | Design, S1 | U |
| C-08 | Donation requires a reboot: the premise of "idle consumer machines" | Design, S1 | A, X(C-06) |
| C-09 | Idempotence: retries, hedges and failover assume it | Design, S1 | U |
| C-10 | At-least-once failover versus non-idempotent functions | Design, S1 | X(C-09) |
| C-11 | Exposure and assurance are arbitrary scores | Design, S2 | U, A |
| C-12 | The planning period (30 s) and horizon (60 s) are not derived or swept | Design, S2 | U |
| C-13 | Robust coverage: "no probability model" is overstated, and its value is unproven | Design, S2 | U, A |
| C-14 | The planner is keyed by tenant; the evaluation has six tenants | Design, S2 | U, X(C-21) |
| C-15 | The keep-alive baseline is weak compared with industry policies | Eval, S2 | U |
| C-16 | Solver cost: the MILP is charged about 0.1 s but takes about 4 s | Eval, S1 | U, A |
| C-17 | MILP size, growth and the planning pool cap | Design, S2 | U |
| C-18 | The fast-loop objective mixes units with assumed weights | Design, S2 | U |
| C-19 | One scheduler per cluster: capacity, failure and the global-scheduler comparison | Design, Eval, S1 | U, A |
| C-20 | Watchdog and detection constants, and adaptive adversaries | Design, S2 | U, A |
| C-21 | Workload realism: 6 tenants, 12 functions, no external I/O | Eval, S1 | A, X(C-14) |
| C-22 | Estimators are tested in a world that matches their model | Eval, S2 | A |
| C-23 | Snapshot restore: what was measured, what was assumed | Design, Eval, S2 | U |
| C-24 | Simulation-only evidence, and what E01 does and does not validate | Eval, S1 | A |
| C-25 | Economics: where is the advantage? | Design, S2 | A |
| C-26 | Supply side: sessions, incentives, abuse and responsibility | Design, S2 | A |
| C-27 | Hedging and admission definitions, and their cost | Design, S3 | U |
| C-28 | Geo-clustering: sizes, scale and confounds | Eval, S1 | U |
| C-29 | Errors found in our own text | Text, S1 | A |
| C-30 | Terminology and explanation gaps (all fixed in text) | Text, S3 | U |
| C-31 | Why is the scheduler on a volunteer host at all? | Design, S1 | X(C-01,C-04,C-17) |

Section 2 gives the cascade map (how items combine) and Section 3 a proposed order for the discussion.

---

## 1. Items

### C-01 · The scheduler is a volunteer host behind NAT: who can dial whom? `[Design] S1` — origin **U**

**Critique.** The paper states that workers sit behind NAT and therefore open *outbound* persistent TLS streams to their scheduler,
the verifier and the routers (doc 08 §2, manuscript §IV-E rule i). But the scheduler is itself a worker, appointed from the same
volunteer pool, and is equally behind a home NAT. A worker cannot open an outbound connection to a host that cannot accept inbound
ones. The paper does not say what makes the worker-to-scheduler stream (DISPATCH, plan actions, heartbeats, outcomes) possible. The
same problem applies to worker-to-worker peer-to-peer artifact transfer.

**Evidence.**
- `docs/architecture/08-state-and-protocols.md` §2: "workers sit behind NAT, so each opens outbound persistent TLS streams to its scheduler ... `relayed` workers pay a penalty."
- `voss/world/workers.py`: `relayed_frac = 0.15` (assumed). `voss/world/network.py`: each relayed endpoint adds `relay_extra_ms = 20` ms to the round trip; relays have no capacity limit and no failure model.
- The scheduler's own host is drawn from the same worker table, so it is "relayed" with probability 0.15 and directly reachable with probability 0.85. This contradicts "workers sit behind NAT".
- The manuscript's Fig. 2 and Fig. 3 draw direct arrows scheduler to worker (DISPATCH) and router to worker (INPUT).

**Defense.**
- The model has a `relayed` flag, so relaying is not ignored; 15% is a placeholder for the fraction of hosts that cannot do NAT traversal.
- Hole punching (ICE/STUN) works for most home NATs, so direct paths are the common case, and TURN-style relays cover the rest.
- The scheduler-to-router and worker-to-router streams are outbound to provider hosts that have public addresses, so the hot path (router-to-worker input and result) works without any inbound connection to a volunteer.
- The paper claims scheduling, not network traversal; a real deployment would reuse an existing NAT-traversal stack.

**Where the defense is weak.**
- The hot path *does* need worker-to-scheduler traffic for every dispatch, and the paper's own failure handling depends on it.
- "Most NATs can be punched" is true of cone NATs. Carrier-grade NAT and symmetric NAT, common in mobile and many ISP deployments, cannot be punched; relays then carry steady traffic.
- A relay that carries scheduler-worker traffic is a new component on the hot path. It must be provider-operated (volunteers are untrusted for availability), it has bandwidth cost, it adds an RTT, and it is absent from Fig. 2, Table II and the threat model.
- 20 ms per relayed endpoint is assumed, not measured, and relays are modelled as infinitely fast.

**Resolution options (not applied).** (a) Make the relay an explicit architectural component with its own cost, capacity and trust statement. (b) Run schedulers only on directly reachable hosts, which changes the succession list and shrinks the candidate pool. (c) Move the scheduler role to provider hosts and keep only workers volunteer-run (this changes the "no volunteer consensus, soft state" story). (d) Keep the design and sweep `relayed_frac` and `relay_extra_ms` to bound the impact. (e) At minimum state the assumption in the paper (done in text, see C-30).

**Cascades.** C-02, C-04, C-19, C-24 (E01 did not emulate the network), C-26.

**Status.** Open. Text updated to state the assumption; the design question is open.

---

### C-02 · Address discovery, address changes and reconnect storms `[Design] S1` — origin **U**, cascade of C-01

**Critique.** The paper never says how components find each other: how a router learns the current scheduler's address, how a worker
learns which scheduler to connect to, what happens when a home IP changes, and whether this lookup sits on the hot path.

**Evidence.**
- Failover diagram (`docs/architecture/07-fault-tolerance.md`): the orchestrator pushes "scheduler address" to routers after an appointment. Workers learn the new scheduler from `EPOCH_INSTALL` sent by the successor. How the successor reaches the workers (which are NAT-ed) is not specified.
- Identity is `hash(EK)` and the session certificate, not an IP address, so a reconnect with a new IP keeps the identity. The paper does not describe reconnection, resume or the messages lost during the gap.
- The operational database stores `scheduler_cert_id` and an epoch; whether it stores an address is not stated. The paper says the hot path never touches the database; the routers' cached scheduler address is the thing that would go stale.
- How a client reaches a router (DNS, anycast, SDK-embedded list) is not specified.
- Workers open streams to "routers" (plural). Which routers, and how many? If a worker must hold a stream to every router that may route to its cluster, router and worker populations multiply (every router terminates streams from thousands of workers); if only to one router, the others need a path to reach it. Not specified.

**Defense.**
- Persistent outbound streams from workers mean a worker's address does not matter to anyone else; the worker dials out and re-dials after a change. Address churn is therefore a reconnect problem, and reconnects already exist because the same machinery handles crashes.
- Orchestrator pushes keep routers' scheduler table fresh; the database is read only on failover, not per invocation.
- The dispatch watchdog (1 s) and result watchdog already turn any lost message into a retry or spill.

**Where the defense is weak.**
- A scheduler change forces *every* worker of the cluster (up to 30 by default, 60 at most) to reconnect to a new volunteer host. This is a synchronized reconnect storm through relays, during which no dispatch can happen. The measured failover time (2.7 s for crashes) comes from the simulator, which models message delay only, not connection setup, NAT mapping or handshakes (`tls_handshake_cpu_s = 1 ms`, marked "TODO verify").
- Home IP changes are frequent for many ISPs. Each change drops the TLS stream to the scheduler; the paper does not say whether the in-flight work is lost or resumed.
- The scheduler's address is the one piece of hot-path state that is not "born where it lives": it is created by the orchestrator and consumed by routers.

**Resolution options (not applied).** Specify a rendezvous/registry for addresses (and state it is off the invocation path but on the failover path); specify reconnect and resume semantics; model connection setup in `net.send`; measure a failover end to end in the emulation testbed (E01 follow-up).

**Cascades.** C-01, C-03, C-04, C-24.

**Status.** Open.

---

### C-03 · PKI: who issues which certificate, and who holds the roots `[Design] S2` — origin **U**

**Critique.** "Attested TLS" is not a standard term. The paper says every channel is TLS with the session certificate, but does not say who the certificate authority is, how its root is distributed, how revocation reaches peers, or what certificates routers, the orchestrator and the tenant key brokers use.

**Evidence.** `docs/architecture/04-trust-and-security.md` §5: the verifier issues `SESSION_CERT(identity, session pubkey, assurance, expiry)` after checking the quote; mutual TLS then uses it. Revocation: "a failed re-quote revokes the certificate, and the verifier notifies the scheduler and routers." Nothing on provider-component certificates, tenant KBS certificates, root distribution, certificate transparency or clock synchronization.

**Defense.** Implicitly the verifier is a private CA for the worker population. Provider components and tenant KBS can use ordinary web PKI. Revocation by notification works because routers and schedulers are the only parties that must reject a revoked worker. Expiry at `min(session end, last quote + T_valid)` bounds the damage of a missed revocation.

**Where the defense is weak.** None of this is written down. "Notifies the scheduler and routers" is a push to parties behind NAT (C-01). Tenant KBS must trust the verifier's root, which couples C-05. A worker's session key is generated inside the appliance, which is good, but the TLS peer (a worker or scheduler) must validate a certificate whose validity depends on the verifier's clock.

**Resolution options.** State the PKI explicitly (private CA operated by the verifier, roots pinned in the image and in each KBS). Text clarified in the explainer; paper change limited to stating this assumption.

**Cascades.** C-05, C-02.

**Status.** Text fixed (assumption stated); design question open.

---

### C-04 · "Reliable by assumption": the control plane is most of a serverless platform `[Design] S1` — origin **A**, cascade of C-01/C-02

**Critique.** VOSS offloads many functions to a provider control plane that is assumed reliable: routers with pending tables, the orchestrator with an epoch CAS, the verifier, the operational database, the artifact registry, and (needed by C-01) relays. The "no consensus among volunteers" result holds because a single reliable arbiter exists. That arbiter and its siblings are the hard part of a production FaaS control plane. The paper evaluates how the volunteer tier behaves, not whether the assumed tier can be built or scaled.

**Evidence.** `manuscript/sections/overview.tex` (provider control plane "assumed reliable"); Table II; scalability experiment E18 where decision latency grows to tens of seconds at 3·10⁴ workers and "the limit lies in the central decision path". Routers hold the only copy of an undispatched invocation (soft-state rule iv), so a router failure loses queued work; router replication is not specified.

**Defense.** Every existing serverless provider already runs these tiers and treats them as reliable; the research question is the volunteer tier. The control plane handles only metadata (no payloads go through the scheduler), which is cheap. E18 shows control traffic per worker is flat.

**Where the defense is weak.** The advantage over simply running the data plane in the cloud depends on how big the provider tier is relative to the volunteer tier (see C-25). The pending table in each router is a single point of loss for undispatched invocations. E18's saturation indicates the provider-side decision path is already the limit at 10⁴–10⁵ workers, and the paper leaves its cause unisolated.

**Resolution options.** State the provider tier's capacity requirement; sketch router replication; isolate the E18 bottleneck.

**Status.** Open.

---

### C-05 · The verifier is in the confidentiality trust base, contradicting "never tenant secrets" `[Design] S1` — origin **A**

**Critique.** Fig. 2 and Table II say the provider control plane is "trusted for availability and accounting, never for tenant secrets". But the default key-release rule (doc 04 §6) is: the tenant's KBS accepts session certificates issued by the VOSS verifier for approved measurements, with a fresh quote only as an optional stricter mode. In the default mode, a compromised or malicious verifier can issue a certificate for any machine, including one with an owner-controlled session key, and the KBS will release the key. The verifier ("appraisal") is therefore trusted for confidentiality.

**Evidence.** `docs/architecture/04-trust-and-security.md` §6 and the manuscript's §V-C ("policy (for instance, accept certificates for appliance measurements at or above a version, optionally with a fresh quote)"). Table II lists the verifier as "trusted for availability, accounting, appraisal".

**Defense.** With the stricter mode the KBS checks the quote itself against its own reference values, and then the verifier is not trusted. A tenant may choose the mode by policy. The provider is, in any case, trusted to run the verifier honestly in the same sense that a cloud provider's attestation service is trusted.

**Where the defense is weak.** The claim in Fig. 2 and the abstract-level framing is unconditional. The stricter mode costs a fresh quote (about 0.5 s on the calibration TPM, which sits in `T_prov`) and the simulator does not state which mode it uses; the planner prices key release with a calibrated constant (`kbs_check_s`, not measured). The explainer and the manuscript currently over-state.

**Resolution options.** Scope the claim: "the control plane is not trusted for tenant secrets *if* the tenant uses direct quote verification; otherwise the verifier is trusted for confidentiality". State which mode the simulation uses and charge its cost.

**Cascades.** C-03, C-07.

**Status.** Text fixed (claim scoped); design question open.

---

### C-06 · Property 1 does not cover runtime physical access to RAM on consumer hardware `[Design] S1` — origin **A**

**Critique.** Property 1 says an attested owner "can neither run other code nor read or modify the image's memory". Measured boot plus a TPM quote shows which software booted. It does not stop an owner with physical access from reading RAM while the appliance runs: cold-boot attacks, DMA attacks (unless an IOMMU is correctly configured), bus probing, or a modified hypervisor hosting a genuine image if the TPM could be proxied. Memory encryption (Intel TME/MKTME, AMD SME/SEV) would address part of this, and the threat model "trusts the CPU, its TPM and memory encryption", but the calibration laptop has no TME and most consumer CPUs do not enable it. Boot-time attestation is also a point-in-time check (the paper acknowledges stale evidence), and a later runtime compromise of the appliance (a bug, excluded as out of scope) is not detected until the next re-quote.

**Evidence.** `manuscript/sections/trust.tex` §V-A (assumptions, out-of-scope list); `docs/validation/README.md` ("no TME"); Table V: `appliance_tpm` assurance base 0.80 (an assumed policy parameter), `cvm_snp` 0.95 (literature). Goal G1: "A malicious owner learns no tenant secret and forges no result."

**Defense.** The out-of-scope list names physical attacks. The assurance base of 0.80 for the TPM appliance is lower than 0.95 for confidential VMs precisely because it is a weaker substrate, and the exposure objective limits how many hosts hold a key. Keylime-style attestation is a standard industry mechanism. Memory-encryption hardware exists on newer consumer and workstation CPUs and the substrate framework lets VOSS run on confidential VMs when available.

**Where the defense is weak.** G1 and the abstract state the guarantee without the qualifier. "Physical attacks" in the out-of-scope list is illustrated by voltage glitching of a firmware TPM, which sounds exotic; cold-boot and DMA are not exotic against a machine the owner physically controls. The paper's central claim (a hostile owner becomes merely unreliable) is true for software-level adversaries; for an owner with physical access it is true only where memory encryption or equivalent is present. Assurance values are policy numbers (C-11), so they do not quantify this gap.

**Resolution options.** Scope G1 and Property 1 to software-level owners, or require memory encryption for sensitive tenants (an assurance floor that only TME/SEV hosts meet). State the residual in the abstract's caveats.

**Cascades.** C-05, C-08, C-11.

**Status.** Open. Text scoped to avoid over-claiming.

---

### C-07 · The tenant-operated key broker `[Design] S1` — origin **U**

**Critique.** Each tenant "runs" a key broker service. Serverless tenants are developers who deliberately do not run infrastructure. A tenant-run KBS must be always on, reachable from every volunteer worker, fast (its RTT is added to `T_prov` on the cold path), and DoS-resistant; if it is down, no new host can be provisioned for that tenant. If the provider ran the KBS instead, the provider would hold the keys, contradicting "never tenant secrets" (C-05).

**Evidence.** `docs/architecture/04-trust-and-security.md` §6; `configs/tenants.yaml` places each tenant's KBS in a different city (Frankfurt, Washington, Singapore, San Francisco, London, Zurich), so key-release RTT differs per tenant. Table II lists the KBS as "Runs on: tenant".

**Defense.** This follows the Confidential Containers / RATS relying-party model, where the secret owner runs the key broker. A tenant can use a managed KBS (a cloud key service) and does not have to operate hardware. KBS availability matters only for cold provisioning; the planner provisions ahead of demand, so most invocations never touch the KBS (that is the point of the slow loop).

**Where the defense is weak.** "Tenant runs the KBS" is stated plainly and read as a burden. The paper does not discuss managed or delegated KBS, what a tenant does when the KBS is unavailable, or how KBS failure interacts with planning (a KBS outage silently lowers the number of provisionable hosts). The simulation never fails or slows a KBS.

**Resolution options.** Describe three deployment options (tenant-run, third-party managed, provider-hosted inside a TEE); model KBS faults; state the trust consequences.

**Status.** Text fixed (clarified); design question open.

---

### C-08 · Donation requires a reboot: the premise of "idle consumer machines" `[Design] S1` — origin **A**, cascade of C-06

**Critique.** A donating machine reboots into the appliance. While the appliance runs, the owner cannot use the machine (Table V: "Owner uses machine: no"; doc 04 §10 limitation 3). Reaching an attested worker takes about 65 s after power-on (see C-29) plus about 10 s shutdown of the owner's operating system, and the owner must reboot again to get their desktop back. This is a very different supply than "idle desktops": it is dedicated or scheduled donation (the model's `nightly`, `idle` and `dedicated` tiers). An "idle-triggered" tier would require two reboots per session, which nobody does when the machine becomes idle for ten minutes.

**Evidence.** `manuscript/sections/overview.tex` ("A volunteer machine reboots into the attested appliance"); `docs/architecture/02-environment-model.md` (tiers, session processes); `docs/validation/README.md` (reboot and appliance timings). The paper's introduction says consumer machines are "idle most of the day" without saying that using them needs an exclusive reboot.

**Defense.** Nightly and dedicated spare machines are realistic for a volunteer program (a spare PC, a machine donating overnight). The measured 65 s and 76 s (with shutdown) are small against sessions of hours. A purpose-built image (UKI, minimal userspace) would be faster than the host-mode laptop probe, which the paper states is an upper bound.

**Where the defense is weak.** The introduction oversells the supply; the idle-triggered tier in the model implicitly assumes short sessions that do not exist under this mechanism. The fraction of a session consumed by establishment is never reported. E01 skipped the session boot (rule 14), so no emulation evidence exists either.

**Resolution options.** Restrict claims to nightly/dedicated supply, or add a supply-side analysis (session length versus 65 s setup), or consider a non-reboot substrate (a measured hypervisor launched under the owner's OS, the `drtm_hv` profile, already in the model with an assurance of 0.75, "assumed").

**Cascades.** C-06, C-26, C-24.

**Status.** Text fixed (disclosed); design question open.

---

### C-09 · Idempotence: retries, hedges and failover assume it `[Design] S1` — origin **U**

**Critique.** Hedging runs two copies of an invocation, and retrying re-executes it. Both are unsafe for functions with side effects (a "like" counter, writing a record, sending an email). Most real serverless functions are not idempotent unless the developer arranges it. The paper's success numbers rely on re-dispatch after an omission.

**Evidence.**
- `voss/policy/hedge.py`: only idempotent invocations are hedged. `voss/policy/retry.py`: retry only if the function is idempotent or the failure never reached execution (pre-execution failures).
- `configs/functions.yaml`: 11 of 12 functions are marked `idempotent: true`; only `dna-visualisation` is not. These flags are *our assumption*, not a measured SeBS property. All synchronous functions in the catalogue are idempotent.
- The manuscript's RQ4 conclusion "detection and re-dispatch carry success" is measured on this mix.

**Defense.** For a non-idempotent function the policy does the safe thing: it does not retry or hedge after the request reached a worker, so the failure is reported (at-most-once). That is the same contract as a synchronous Lambda invocation, where the *client* retries. AWS retries asynchronous invocations (at least once) and tells developers to write idempotent handlers. Pure-compute, object-store and idempotent-key functions (the SeBS style) are a large and natural class.

Concretely, when a worker accepts an invocation and returns nothing, the result watchdog fires at the predicted 90th-percentile completion time times 1.2 (at least 3 s), the scheduler probes the host, marks it suspected, and re-places the invocation only if it is idempotent; otherwise the invocation is reported as failed. The router's dispatch watchdog (1 s) covers the earlier step, when the scheduler never acknowledged the enqueue; nothing has executed then, so re-sending is always safe.

**Where the defense is weak.** (a) The paper does not say that the evaluation workload is 92% idempotent or how many non-idempotent functions would break the success numbers. A non-idempotent function that lands on a host which then omits is a hard failure, and under 20% omitting owners that is a large share of such calls. (b) Churn is far higher than datacenter failure rates, so the at-least-once-and-hope approach that works in a datacenter does not transfer. (c) If the platform requires idempotent functions, that is a product constraint that should be in the problem statement.

**Resolution options.** State the requirement; sweep the idempotent fraction; report success separately for idempotent and non-idempotent functions; consider an idempotency-key service (provider-run) so retries are safe at the API boundary.

**Cascades.** C-10, C-13 (what "robust coverage buys"), C-27.

**Status.** Text fixed (assumption stated); design question open.

---

### C-10 · At-least-once failover versus non-idempotent functions `[Design] S1` — origin **X (C-09 × failover)**

**Critique.** The failover protocol says a partitioned scheduler "can therefore cause only duplicate work, which is within at-least-once semantics", and routers "re-send pending (dedupe by id)". Duplicate work is acceptable only for idempotent functions. For a non-idempotent function the same sequence executes the side effect twice. The retry policy treats non-idempotent functions at-most-once, the failover protocol treats everything at-least-once. The two disagree.

**Evidence.** Manuscript §VII-C; `docs/architecture/07-fault-tolerance.md` "Zombie" and re-send paths; `voss/policy/retry.py` versus doc 07's duplicate-work statement.

**Defense.** Dedupe by invocation id at routers and workers can suppress most duplicates; a partitioned scheduler is fenced after a lease period (5 s) and workers reject lower epochs. The window is small.

**Where the defense is weak.** Dedupe at the router does not undo an execution that already happened on a worker; a window of up to 5 s of dispatching by a zombie scheduler can still start executions.

**Resolution options.** Either declare at-least-once platform semantics (and so require idempotence, C-09), or make failover resolve in-flight non-idempotent invocations at-most-once (fail rather than resend).

**Status.** Open.

---

### C-11 · Exposure and assurance are arbitrary scores `[Design] S2` — origin **U**, **A**

**Critique.** Exposure `E_t = Σ (1 − a_j)` counts key-holding hosts weighted by an "assurance" in [0,1]. Assurance is a product of a substrate base (0.80 for the TPM appliance, 0.95 for confidential VMs, 0.75, 0.0) and a firmware factor. These numbers are policy parameters, not measurements. The paper itself says exposure is "a transparent proxy, not a probability", and then reports results ("the knee saves 25% of exposure for 1.6% more P99") that depend entirely on those values. Exposure is also linear in the number of holders; the risk model could just as well be convex (one leak is the whole breach).

**Evidence.** Manuscript §V-D and Table V; `docs/architecture/04-trust-and-security.md` §8 and D-69.

**Defense.** The paper says so openly and reports a Pareto front instead of one weighted number. A transparent proxy lets a deployer plug in their own risk numbers. Counting key holders is a standard way to express attack surface.

**Where the defense is weak.** The explainer's first draft described exposure as "a probability-like security price"; a reader will take 0.8 as a probability. Without an empirical basis a reader cannot tell whether a 25% reduction of exposure means anything. The objective weights `λ`, `σ` and the placer's `λ_exp` set the exchange rate between exposure and latency with no justification.

**Resolution options.** Replace "assurance" by an explicit list of attack-surface features for each substrate; show results under at least two assurance tables; define a threshold-based risk model (breach if any holder is compromised, each independently with probability p).

**Status.** Text fixed (plain definition, caveat stated); design question open.

---

### C-12 · The planning period (30 s) and horizon (60 s) are not derived or swept `[Design] S2` — origin **U**

**Critique.** `T_plan = 30 s` and `H = 2·T_plan` look arbitrary. There is no link to function duration statistics (for example the Azure trace) and no sweep in the paper.

**Evidence.** `voss/core/config.py`: `T_plan = 30.0`, `horizon_factor = 2.0` ("assumed"). The only sweep is the E02 pilot (`docs/pilots/E02.md`), outside `make paper`, which tried `T_plan ∈ {15, 60}` (not 30) with planning pools of 10 to 80 hosts on the placeholder calibration. For a 40-host pool the P99 was 1.371 s [1.277, 1.474] at 15 s and 1.499 s [1.379, 1.621] at 60 s (overlapping intervals). Doc 03 §1 gives the range "10–60 s".

**Defense.** The value is constrained from both sides by quantities the paper does measure or assume: it must be longer than provisioning latency (a key release round trip of 0.1–0.5 s, microVM boot of 0.15–1.5 s, artifact fetch of seconds) so that a plan can complete, and shorter than typical session length (tens of minutes to hours) so the plan tracks session churn. The pilot shows the result is insensitive in that range. Plans are re-solved only on material change.

**Where the defense is weak.** The constraint argument is not in the paper. The pilot did not test 30 s and is not in `paper/`. Insensitivity might be an artifact of the 6-tenant workload (C-21) where demand is stable. The 60 s horizon interacts with survival estimates (Weibull scale 7200 s) and the arrival forecast (EWMA constants 60 s and 900 s).

**Resolution options.** Add a `T_plan` sweep (10, 30, 60, 120 s) to the paper experiments; state the derivation.

**Status.** Text fixed (origin of the value stated); open.

---

### C-13 · Robust coverage: "no probability model" is overstated, and its value is unproven `[Design] S2` — origin **U**, **A**

**Critique.** The coverage constraint removes the `f_t` largest allocations (worst case) *and* weights every remaining allocation by `e_j = S_j(H)(1−p_j)`, where `S_j` and `p_j` are statistical estimates. It is a hybrid, so "makes no probabilistic assumption about adversaries" is true only of the removed `f_t` hosts. The measured value of the constraint is also thin: the `f = 0` ablation changes success by only 0.11 percentage points (H2 inconclusive), and the benefit appears as tail latency (P99 1.43 s versus 2.05 s) in exchange for more exposure (13 → 24).

**Evidence.** Manuscript Eq. (5), §IX-D, §IX-E, Table XXII, Fig. 11. Default `f_t = ⌈0.1·N⌉` equals the assumed adversary fraction α in the experiments with 10% omitting owners, which is the ground truth the design was tuned on.

The coverage target `q_t` is also sized with a Poisson model (concurrent runs are Poisson with mean arrival rate × service time, an M/G/∞ system), while the simulated arrivals are a Markov-modulated Poisson process with 4× bursts. A burst is exactly when the real concurrency exceeds the Poisson quantile, so realized coverage falls below 95% in bursts (the paper says so). Real traces are over-dispersed relative to Poisson, so the same mismatch would exist in practice.

**Defense.** The worst-case part is the useful guarantee against an adversary with a clean record; estimates only discount expected failures. The latency benefit is real and significant in E08. The paper reports H2 honestly and describes the constraint's value as "tail latency, not success".

**Where the defense is weak.** `f = ⌈0.1 N⌉` presupposes knowing α. The only demonstrated benefit is latency, and E23 shows it is paid for with exposure; a non-robust plan with more warm capacity might give the same latency without enlarging the key-holder set. Not tested.

**Resolution options.** Compare robust coverage with simply over-provisioning (a larger `q_t` quantile); state the α dependence; reword the "no probability model" sentence.

**Cascades.** C-09, C-11, C-12.

**Status.** Text fixed (wording); open.

---

### C-14 · The planner is keyed by tenant; the evaluation has six tenants `[Design] S2` — origin **U**, cascade into C-21

**Critique.** Keys are per tenant, so key provisioning (`y_tj`) and its coverage requirement are decided per tenant, ranked by `demand × cold penalty`. Warm sandboxes and snapshots are per function. A reader can ask whether a hot tenant boosts a cold function, and whether industry keeps warm state per function or per application.

**Evidence.** `voss/policy/plan/greedy.py`: `_trust_sets` iterates tenants by `rate × cold_penalty`; `_warm_state` then iterates *functions* by `benefit / memory` and places warm units only on hosts already holding that function's tenant key (`for j in np.flatnonzero(y[fn_tenant[f]])`). So hotness of a tenant decides who holds the key; hotness of the function decides which functions get warm units; a cold function of a hot tenant is *not* boosted, but it may be placed on key-holding hosts cheaply. Industry practice varies: Azure's published policy works per application, OpenWhisk and commercial platforms per function or container.

**Defense.** Tenant-level provisioning is forced by the security model (the unit of secret is the tenant). Function-level warm choice is made by value density, so tenant hotness only gates *where* a function may be warm.

**Where the defense is weak.** With thousands of tenants most are cold and fall to the unprovisioned path (key release plus fetch plus boot per invocation); the design optimizes the head of a heavy-tailed distribution. The experiment has six tenants and 12 functions (`configs/tenants.yaml`, `configs/functions.yaml`), so the hot-set limit (top 20 tenants and 50 functions) never binds. The tail the limit creates is untested.

Correlated demand is a second gap. In a CRUD-style application, several functions of one tenant rise and fall together. Tenant-level provisioning suits this, but the arrival forecast treats each function independently (an EWMA per function) and the simulated functions are independent Zipf-ranked streams, so the correlation that would let a tenant-level signal help is neither exploited nor tested.

**Resolution options.** Evaluate with hundreds of tenants and a heavy-tailed popularity (Azure-like); report the cold-path share; add correlated functions per tenant.

**Cascades.** C-21, C-12.

**Status.** Text fixed (rationale and workload size stated); open.

---

### C-15 · The keep-alive baseline is weak compared with industry policies `[Eval] S2` — origin **U**

**Critique.** The "keep-alive TTL" baseline is a fixed 600 s per-function timer (`warm_ttl_s = 600`). Production policies are more adaptive: Azure's published hybrid-histogram policy uses per-application idle-time histograms to choose pre-warming and keep-alive windows, and FaasCache treats keep-alive as caching. The headline claims "planning lowers P99 by 27–57% against keep-alive" are against a classical TTL, not against these.

**Evidence.** `voss/policy/plan/baselines.py`, `voss/core/config.py`; manuscript §III cites the histogram work and FaasCache but does not implement them as baselines.

**Defense.** Histogram policies target the idle-time distribution of long-lived functions on trusted servers; they do not model session loss, provisioning or exposure, so on volunteer hosts they would face the same churn cost. The simulated "Lambda-like" and "Azure-like" references use per-function keep-alive of 10 and 20 minutes, matching public descriptions of their defaults.

**Where the defense is weak.** A histogram baseline adapted to volunteer hosts is a natural, reviewer-expected comparison. Without it the advantage of the planner over *adaptive keep-alive* is unquantified.

**Resolution options.** Add a histogram-based keep-alive baseline on volunteer hosts; or scope the claim to "fixed TTL".

**Status.** Text fixed (baseline described exactly); open.

---

### C-16 · Solver cost: the MILP is charged about 0.1 s but takes about 4 s `[Eval] S1` — origin **U**, **A**

**Critique.** The paper says "nothing is free" and charges the decision latency of planner, placer, router and orchestrator to the simulated clock. In the paper's runs the planner's latency is *modelled* as `0.02 + 5·10⁻⁵ × (number of program variables)` seconds (`voss/core/config.py`, `decision_clock.mode = modeled`), about 0.07 to 0.17 s for the program sizes in the paper. The same formula charges greedy and MILP. The measured MILP wall time is about 4.1 s per cluster (Table XX), and the greedy planner's is 8 ms. So in E04 and E23 the MILP's 4 s of real solve time is charged as roughly 0.1 s of simulated time, while the plan it produces is already 4 s stale in a real system. The coefficient is marked "TODO verify: refit from E02 measured runs", which was never done. The paper does say the coefficients are placeholders.

**Evidence.** `voss/core/config.py` (`DecisionClockConfig.coeffs`), `voss/runtime/schedlib/planner_mixin.py:46`, `configs/base.yaml` (`decision_clock: {mode: modeled}`), `configs/experiments/E04.yaml` (no override), Table XX "Solve (s)" (wall-clock, informational, not hashed). In E02 (the pilot with a measured clock) a pool of 80 hosts took 17–24 s per solve, longer than `T_plan = 15 s`.

**Defense.** The modelled clock keeps results machine-independent, which is a reproducibility feature. The comparison that matters (MILP not clearly better than greedy, H8 inconclusive) is, if anything, conservative towards the MILP: charging it correctly would lower its apparent benefit, not raise it. The MILP is only a reference.

**Where the defense is weak.** The abstract and §VI describe a "robust MILP" solved every period, and H1 reports MILP results against no planning and keep-alive; those numbers carry an unrealistically low latency charge. It is not stated in the paper that the 4.1 s is *not* what the simulated clock charged. The E01 comparison found the real decision step is 2–29% longer than the modelled one, so the modelled coefficients are not accurate even for the cheap placer.

**Resolution options.** Refit the coefficients from E02/E01 measured data; rerun E04 and E23 with the measured clock in replay mode; state in the paper what is charged. (This would be a code or configuration change and is not applied.)

**Cascades.** C-17, C-12, C-24.

**Status.** Text fixed (the charge is now stated); open.

---

### C-17 · MILP size, growth and the planning pool cap `[Design] S2` — origin **U**

**Critique.** "4.1 s per cluster" lacks the instance size. The MILP has `y_tj` and `c_tj` for each (tenant, host), `s_fj` and `w_fj` for each (function, host), plus the auxiliary variables of the cardinality constraint. MILP is NP-hard; solve time can grow steeply with the number of hosts.

**Evidence.** The planning pool is capped at `max_plan_workers = 40` hosts (`voss/core/config.py`, `voss/runtime/schedlib/planning.py`: "previous holders first, then by capacity × assurance"). Hot set: at most 20 tenants and 50 functions. So at most 800 `y`, 800 `c`, 2000 `s`, 2000 `w` plus `θ, π` auxiliaries: about 5·10³ variables, of which 10³–3·10³ are integer (manuscript §VI-D). Inputs per host: survival, omission probability, assurance, failure domain, slots, memory, snapshot space, cache inventory; per tenant: demand quantile, sensitivity, assurance floor, robustness; per function: memory, snapshot size, warm benefit, units demanded. Output: `y, s, w, c`. E02 pilot (`docs/pilots/E02.md`): median solve 0.3–1.1 s for 10 hosts, 1.5–2 s for 20, 4.7–5.0 s for 40 and 17–24 s for 80. Greedy is a few sorted passes over the same inputs (8 ms). Learned history is held in the scheduler's memory (one regression per function with per-worker offsets, Weibull and Beta parameters per host, arrival bins) and checkpointed to the database every 30 s; there is no per-(function, worker) history table.

**Defense.** The cap and the small clusters (target 30, between 10 and 60) exist to keep the program small. Solve time is bounded by a time limit; on timeout the incumbent or greedy plan is used.

**Where the defense is weak.** A cap that drops hosts from consideration changes the problem: with the cap, a "global" scheduler plans over only 40 of its hosts (C-28). The solver runs on a volunteer scheduler host whose speed divides the (modelled) cost. The paper's phrase "4.1 s per cluster" does not say any of this.

**Resolution options.** Report instance sizes and a solve-time curve in the paper; decide whether the cap is part of the method.

**Status.** Text fixed (inputs, outputs, size and growth stated); open.

---

### C-18 · The fast-loop objective mixes units with assumed weights `[Design] S2` — origin **U**

**Critique.** `J = w·P_miss + ε·E[T] + λ_exp·x` adds a probability, a time and an exposure score. `ε = 0.05 /s` (one second of latency costs five points of miss probability), `λ_exp = 1`, `w = 1` or `0.3` are assumed constants. `P_miss` depends on moment-matched log-normal completion times whose trust, start-up and network parts are calibrated constants, not learned. The paper explains it in words but a reader meeting it first sees symbols.

**Evidence.** Manuscript Eq. (3), Table VIII, Table IX; E03 compares scalarizers (expectation, quantile, CVaR, tardiness) but not the weights.

**Defense.** The scalarisation is an expected-cost decision whose first term is the actual objective; the other terms break ties and encode exposure. Weights are swept in E19/E23 for the exposure term.

**Where the defense is weak.** The exchange rate between latency, miss probability and exposure is a policy choice presented as a default; sensitivity of the headline results to `ε` is not shown.

**Resolution options.** Add an `ε` and `λ_exp` sensitivity; state the exchange rates as policy parameters with a justification.

**Status.** Text fixed (symbols and units explained); open.

---

### C-19 · One scheduler per cluster: capacity, failure and the global-scheduler comparison `[Design, Eval] S1` — origin **U**, **A**

**Critique.** One volunteer host runs both loops for 10–60 workers. The paper compares this against a single global scheduler (E05) and concludes clustering does not pay. But (a) the question "could one scheduler scale at all?" is not answered at the sizes where it matters; (b) clustering is introduced for scalability, which E05 does not stress; (c) "global" can mean provider-hosted, which changes the trust story.

**Evidence.** See C-28 for the experiment details. E18 reports that decision latency is the scaling limit, yet E05 runs 600 workers (about 225 attested) at 20 inv/s. The scheduler's load per decision is modelled as `a + b·work` with work independent of population (candidates `K = 12`).

**Defense.** The paper restricts its claim to "no population in which geo-clustering wins at the scale we simulate". The scalability result is reported honestly.

**Where the defense is weak.** The design's main structural element (clusters of tens, one scheduler each, orchestrator rebalancing) is supported by an experiment in which its alternative is not stressed, and its cost in exposure is large. Whether the global scheduler is volunteer-hosted or provider-hosted is not stated.

**Resolution options.** See C-28.

**Cascades.** C-01, C-04, C-28.

**Status.** Open.

---

### C-20 · Watchdog and detection constants, and adaptive adversaries `[Design] S2` — origin **U**, **A**

**Critique.** The dispatch watchdog (1 s), spill (1.5 s), result watchdog (`q90 × 1.2`, at least 3 s), heartbeat period (2 s) and silence limit (7 s) are assumed. Intercontinental RTT plus residential last mile plus a relay (C-01) can exceed 300 ms, so a 1 s dispatch watchdog is aggressive and a false suspicion has costs. Conversely, a slow-and-low adversary that stays just inside the thresholds is never caught (slow scheduler detection already takes 14 s), and the adversary menu is fixed (black hole, random omission, on–off, throttle, fake notices, colluding domain). Also, "black hole" is a networking term for a node that silently drops what it receives.

**Evidence.** Manuscript Tables XI and XIII; "an adaptive adversary that learns the scheduler could do worse" (threats to validity).

**Defense.** Detection error is bounded by the CUSUM and the robust coverage; progress evidence is hard for a host to fake because routers and attested workers observe it; false positives only reduce a host's eligibility.

**Where the defense is weak.** No sweep of the watchdog constants; no adaptive adversary; a false-positive rate is never reported.

**Status.** Text fixed (terms explained); open.

---

### C-21 · Workload realism: 6 tenants, 12 functions, no external I/O `[Eval] S1` — origin **A**, cascade of C-14

**Critique.** The evaluated workload has six tenants and 12 SeBS-style functions with Zipf popularity and a bursty arrival process. Public traces (the Azure study the paper cites) show tens of thousands of functions, extremely heavy-tailed popularity, many functions invoked rarely, timer and queue triggers. Functions here never call external services (object stores, databases) and so never expose the volunteer's residential location to a data store; there are no function chains. The hot-set cap is never reached.

**Evidence.** `configs/tenants.yaml` (six tenants), `configs/functions.yaml` (12 functions, execution parameters "assumed ... TODO verify"), `voss/world/workload.py` (Zipf, Poisson or two-state MMPP).

**Defense.** The functions are modelled on the published SeBS suite; the paper says workload sizes are assumed; the claim is about mechanisms. Workflows are discussed as an extension.

**Where the defense is weak.** The head-of-distribution result (planning pays) is what a six-tenant workload would show; the question for a volunteer platform is what happens for the long tail. Missing external I/O removes a latency source that is arguably worse on residential links.

**Resolution options.** A trace-driven workload (the Azure traces are public) with hundreds of tenants; add function-initiated I/O.

**Cascades.** C-14, C-12, C-19.

**Status.** Text fixed (disclosed); open.

---

### C-22 · Estimators are tested in a world that matches their model `[Eval] S2` — origin **A**

**Critique.** Session lengths in the simulator come from Weibull, log-normal or schedule-based families and the survival estimator fits a Weibull per tier, which is exact for the Weibull regimes; execution times are generated from the same function catalogue the estimator uses as its prior. The E03 pilot note says predictors "are indistinguishable here because the simulated truth equals the profile prior and workers are only speed-scaled". Prediction-error injection is "not part of the paper's experiments". The scheduler also assumes start-up costs, network times and declared speeds exactly.

**Evidence.** `docs/pilots/README.md` (E03), manuscript §VI-C and §X-B, `voss/world/sessions.py`.

**Defense.** The paper states this limitation. The planner's robustness constraint is designed not to depend on the omission estimator being right.

**Where the defense is weak.** The entire "history versus forecast" story is exercised on well-specified models; misspecification (non-stationary churn, correlated sessions) is where real systems fail.

**Resolution options.** Error-injection sweeps; a misspecified-world test (different session family than the estimator).

**Status.** Open.

---

### C-23 · Snapshot restore: what was measured, what was assumed `[Design, Eval] S2` — origin **U**

**Critique.** The explainer must explain "restore snapshot, warm/cold" and "boot microVM". The questions: are snapshots demand-paged (mmap or userfaultfd), do they live on remote storage, and what does "warm" mean?

**Evidence.**
- Calibration (`tools/calibrate/suites/fc_snapshot.py`): snapshot files are *local* (on the host's SSD or HDD); "warm" means the file is in the OS page cache, "cold" means it was evicted from the page cache first (file-scoped `posix_fadvise` since D-72), so the next read comes from disk. The measured restore is the Firecracker `/snapshot/load` call (7 ms warm, 0.64 s cold HDD) and the time to the first console echo (1.1–1.5 s cold HDD).
- Firecracker maps the memory file lazily (page faults) or through a userfaultfd handler; the harness uses the default file backend. A real function then touches more pages, adding faults; the model scales disk reads "in proportion to memory touched" using `snapshot_touched_frac`, a placeholder that was not measured.
- Snapshots in VOSS are per host, tied to a snapshot class (CPU model, kernel, VMM version), contain *decrypted* tenant memory, and are shared only with other provisioned hosts of the same class. They are not on remote storage; remote loading would mean network latency on every restore.
- "Boot microVM" is a Firecracker microVM boot from a root file system (0.15 s warm cache, 1.45 s cold HDD). "Reboot to kernel" is the whole *host machine* rebooting (firmware, boot loader, kernel start; 21 s), a different thing.

**Defense.** The restore figure is end-to-end to first response and so includes a page-fault cost for the minimal touched set; the placeholder for the touched fraction is flagged in the bundle; the paper reports the numbers as measured with their definitions.

**Where the defense is weak.** The tail cost of demand-paging a real function after restore is not measured; heterogeneity of consumer CPUs fragments snapshot classes (reducing sharing); snapshot creation (6.7 s for 512 MB on HDD) is a host cost not charged to any invocation.

**Status.** Text fixed (definitions added); open.

---

### C-24 · Simulation-only evidence, and what E01 does and does not validate `[Eval] S1` — origin **A**

**Critique.** E01 now exists (merged, `docs/validation/E01.md`, `runs-e01/`) and the manuscript does not yet use it. It deserves a plain reading. Setup: i7-12700 node, 16 donor slices (two slots each), five functions, 10-minute runs, seeds 1–3, four scenarios plus one kept for the record. Real: Firecracker boot, snapshot restore and creation, function execution. Not real: the network (kept as a model; `netns` and `netem` were dropped in D-72 as validating nothing about the model), attestation, key release, queueing, TPM, session boot, the hard-disk tier, scale beyond 16 workers. Result: all five scenarios are "partly" close (none "close"): success within 0.6 points, start-level mix identical (TV 0.00), median latency within 6–23%, but latency distribution shape differs (KS 0.20–0.51), light-load P99 error is +270% to +314% (simulator higher), and at 100 inv/s the emulated tail is heavier in one seed (2.6 s versus 0.17 s).

**Defense.** E01 shows that the start-up and execution pieces agree to the order of magnitude and that the policy code behaves the same on the real clock. Differences are largest where the P99 is the five slowest requests of about 530. Cut-offs were fixed before the runs.

**Where the defense is weak.** The parts of VOSS the paper's headline claims depend on (network, NAT, session establishment, key release, scheduler failover timing, omission detection at scale) are exactly the parts E01 did not run. The "partly" verdict means the simulator is not validated to the standard the paper's absolute latencies would need. Real-time operation also uses `measured` decision cost with scale 0, a different decision clock from the paper.

**Resolution options.** Report E01 in the paper with this scope; plan an emulation of the network and the session boot; emulate failover.

**Cascades.** C-01, C-02, C-08, C-16.

**Status.** Text fixed (E01 now reported with its limits); open.

---

### C-25 · Economics: where is the advantage? `[Design] S2` — origin **A**

**Critique.** In the paper's own comparison a commercial-style reference has lower latency at all loads and VOSS is cheaper per invocation only above about 20 inv/s, with volunteer credits excluded from the cost. A reader will ask what the platform gives its users: lower provider cost at scale, proximity to users, or use of otherwise wasted hardware? And what do volunteers get? Credits concentrate (Gini 0.93).

**Evidence.** Manuscript §IX-G, §IX-F (credits). Table XXV.

**Defense.** The paper says that VOSS "never has lower latency" than a trusted, always-on, nearby fleet; the contribution is a design that makes volunteer hardware viable when such a fleet is not available, and the evaluation shows where. Cost is reported excluding credits and the paper says so.

**Where the defense is weak.** The motivation (volunteers close to users) predicts better latency, and the evaluation says the opposite. No payment or incentive model exists; credits are not money.

**Status.** Open.

---

### C-26 · Supply side: sessions, incentives, abuse and responsibility `[Design] S2` — origin **A**, cascade of C-08

**Critique.** Volunteers run tenant code on home networks. Tenant code can send traffic from the volunteer's IP address (abuse complaints, blocklisting, legal exposure) and consume uplink. There is no egress policy, no abuse process, no energy compensation, and no description of what happens to a volunteer's machine integrity when it runs arbitrary code in microVMs (isolation bugs are out of scope). Identity is a TPM-bound hash, which is good against Sybils but ties a person's hardware to the platform.

**Evidence.** Doc 04 §7 (identity), §10 (limitations). Nothing on egress or abuse.

**Defense.** These are deployment issues common to every volunteer or edge platform; the paper's claim is scheduling under the trust and churn model.

**Where the defense is weak.** A reviewer in systems or security will ask; a statement of scope is the minimum.

**Status.** Text fixed (scope sentence); open.

---

### C-27 · Hedging and admission definitions, and their cost `[Design] S3` — origin **U**

**Critique.** "Hedge" and "admission" are used without definition. Hedging runs a duplicate on another failure domain when the best placement has a high miss probability and takes the first result (the other is cancelled); wasted work is bounded by a 10% budget. Admission control rejects a synchronous invocation (or defers an asynchronous one) when every candidate would miss with probability at least 0.95 and even the shortest slot wait exceeds the remaining budget. Hedging requires idempotence (C-09). A hedge on a different failure domain doubles donor energy for that call.

**Evidence.** `voss/policy/hedge.py`, `voss/policy/admission.py`, manuscript §VI-E, Table XXII (always hedge 10.6% extra attempts, risk-proportional 1.8%; P99 −13% with interval [−32%, +1%]).

**Status.** Text fixed (definitions added); open only through C-09.

---

### C-28 · Geo-clustering: sizes, scale and confounds `[Eval] S1` — origin **U**

**Critique.** What exactly was compared? How large were the clusters, how many nodes did the single scheduler manage, at what arrival rate? Could one scheduler scale?

**Evidence.** `configs/experiments/E05.yaml`, `configs/pilot.yaml`, `docs/pilots/README.md`:
- 600 workers per run (about 225 of them attested, the rest unattested or off), 15 simulated minutes, 20 invocations per second, 10 seeds.
- Populations: Europe only, EU plus North America, world. Systems: one global scheduler, static regions, static k-means, dynamic clusters. Cluster size target 30 (between 10 and 60); k-medoids on RTT. Resulting counts (Table XXIII): about 10 clusters in Europe, 7 for EU plus North America, 6 to 7 for the world.
- With the global scheduler, all attested hosts are in one cluster but the planner pool is capped at 40 (`max_plan_workers`), so the planner provisions keys on at most 40 of about 225 hosts. This is the main reason the global scheduler's exposure is 12–14 while k-means gives 54–63.
- The decision cost model does not grow with population (placer work is candidates times components, `K = 12`), so a single scheduler is never slowed by 225 hosts or 20 inv/s.

**Defense.** The paper restricts the claim to the simulated scale and reports the exposure cost. Dynamic clusters give a small advantage in some regimes (E06).

**Where the defense is weak.** The global baseline is advantaged by the pool cap (fewer key holders), by a cost model that does not scale with population, and by a load too small to stress a scheduler. H7's "refuted" verdict is therefore about "global scheduler at 20 inv/s and 225 hosts against clusters of about 22 hosts". The explainer's first draft said clusters were compared against "one global scheduler" without any of this. Also unresolved: whether the global scheduler is a volunteer host (C-19).

**Resolution options.** A load and population sweep in which the global scheduler's decision time grows; remove the pool cap for the global baseline or apply the same cap to clusters; state the confound.

**Cascades.** C-17, C-19, C-21.

**Status.** Text fixed (sizes and confounds stated); open.

---

### C-29 · Errors found in our own text `[Text] S1` — origin **A**

1. **Time to an attested worker was mislabelled.** The paper (abstract-level numbers in §I, §II-A, §IV-D, §VIII-B, §IX-A, Fig. 1) said "reboot to an attested worker from a powered-off machine takes 44 s, of which 21 s is firmware and kernel start". The harness measures `appliance_attested` as the time from *kernel start* to the verifier's acceptance (`/proc/uptime` stamps; `tools/calibrate/appliance/host/voss-calib-probe`), so it excludes the firmware and boot-loader phase. From the raw boots (`calibration/raw/laptop-b9212a4528/appliance`, 9 boots): firmware plus loader plus kernel 21 s, kernel start to attested 44.4 s, so **power-on to attested is 65.1 s (range 63.8–66.4)**, and **76.3 s** from the reboot command including the owner OS shutdown. All are host-mode, HDD, and include about 14 s of TPM key creation plus quote, so they are upper bounds for a purpose-built image. The qualitative conclusion (three to four orders of magnitude above a snapshot restore) is unchanged. Manuscript and generator corrected.
2. **Doc 03's decision table** still says "Robust MILP (default) or greedy" for the slow loop; the paper and E04 use greedy as the default. (Docs only; left for the later change round since this document does not edit design docs.)
3. **"Control plane never trusted for tenant secrets"** is only true in the stricter key-release mode (C-05).
4. **"Cold path"** was used without a definition. In the paper it means placement on a host that is not provisioned for the tenant (no key, nothing warm); the explainer now calls it the "unprovisioned path" and separates it from the per-invocation "hot path" (C-30).
5. **MILP solve time** is quoted without noting it is wall-clock and not what the simulated clock charged (C-16).
6. **Number of tenants** was not stated, hiding that the hot-set cap is never reached (C-14).
7. **The global-scheduler planner cap** was not stated next to the geo-clustering result (C-28).

**Status.** Items 1, 3–7 fixed in the manuscript; item 2 left for the design-doc round.

---

### C-30 · Terminology and explanation gaps (all fixed in text) `[Text] S3` — origin **U**

Gaps the advisor-prep review found, and what the manuscript and explainer now say:

| Gap | What was unclear | Now |
|---|---|---|
| tenant | Could be read as a microVM | The customer who writes and deploys functions; the provider runs VOSS |
| secret / key | Not a standard serverless term | A tenant-held decryption key for the tenant's code bundles and snapshots (and what they contain) |
| liveness signal | Used before it is defined | Periodic "I am alive" heartbeats from a host |
| omission, delay | Used without definition | Omission: a host accepts work and never returns the result; delay: it returns it too late |
| drain | Unclear | The owner announces they will leave by a deadline |
| black hole | Not standard here | A host that keeps heartbeating but silently drops accepted work (networking usage of the term) |
| hot path / cold path | Both used loosely | Hot path: the per-invocation request path; unprovisioned path: placement on a host without the key or warm state |
| set-valued | Jargon | "Decisions about groups of hosts" |
| uncovered demand | Unexplained | Slots of forecast demand not covered by provisioned hosts, with a price |
| value density | Unexplained | Start-up time saved per megabyte kept warm |
| budgets bind | Unexplained | A host's memory or disk is used up |
| history, forecast | Not standard | Learned from past outcomes; extrapolated to the next minute |
| priced | Unexplained | Expressed in seconds of expected delay |
| TPM quote, warm/cold, reboot to kernel | Not explained | Defined in the trust-cost slides (see C-23, C-29) |

### C-31 · Why is the scheduler on a volunteer host at all? `[Design] S1` — origin **X (C-01 × C-04 × C-17)**

**Critique.** The scheduler role runs on a volunteer worker. Everything in §VII that is new (progress detection of schedulers, epoch fencing, soft state with roll call, succession lists, warm standbys, zombie self-fencing) exists *because* the scheduler can crash, stall or be partitioned like any volunteer. A provider-hosted scheduler per cluster would remove all of it, would not be behind NAT (C-01, C-02), would be one datacenter hop from the routers, and would not need to be re-appointed when a home machine reboots. The paper's justification is implicit: provider cost and scalability. But the default planner is the greedy one (8 ms per solve), and the placer's work per decision is bounded by `K = 12` candidates, so scheduling a cluster of tens of workers costs a provider a tiny fraction of a core.

**Evidence.**
- Manuscript §IV-B ("the scheduler is a role"), §VII-C; Table II lists the scheduler as "trusted for correct placement (attested code), not for availability".
- Greedy planning: 8 ms per cluster per 30 s (Table XX); the MILP, the only expensive version, is a reference (H8 inconclusive, 4.1 s wall).
- Back of envelope with the paper's numbers: at 10⁵ workers and clusters of about 30, there are about 3,300 clusters; greedy planning every 30 s costs about 3,300 × 8 ms / 30 s ≈ 0.9 core; the MILP would cost 3,300 × 4.1 s / 30 s ≈ 450 cores. The placer is on the per-invocation path and scales with the invocation rate, not with the worker count.
- E15: scheduler failures cost 2.7 s (crash) to 14 s (slow) of degraded service; E18: the centralized decision path, not message volume, limits scale.

**Defense.**
- Offloading scheduling to volunteers removes the provider's per-cluster compute and state, which is what makes the MILP version plausible (450 cores) and keeps the provider tier "stateless-ish" (soft state).
- Locality: the scheduler sits inside the cluster, so worker-to-scheduler latency is intra-region; a provider scheduler would be in the nearest datacenter, which for many clusters is further than a neighbour volunteer.
- Attested code means a volunteer-hosted scheduler cannot decide wrongly; the paper's contribution includes showing that fault tolerance for the *remaining* omission and timing faults is cheap.
- Research framing: the paper studies how far the volunteer tier can be pushed.

**Where the defense is weak.**
- If greedy is the method, the compute argument disappears (under one core for 10⁵ workers).
- Locality is a hop-count argument that is not evaluated, and it is contradicted by the NAT/relay path to the volunteer (C-01).
- The architectural complexity (and the failure modes in C-02, C-10) is paid for a saving the paper does not quantify. A comparison "provider-hosted scheduler" versus "volunteer-hosted scheduler" on latency, failover cost and provider cost is the experiment that would settle it. Not run.
- The decision to keep a scheduler role at all is the largest single contributor to the fault-tolerance section.

**Resolution options (not applied).** (a) Add a provider-hosted scheduler variant as a baseline (same code, different host class). (b) State the cost argument with numbers. (c) Keep the volunteer scheduler only for the MILP variant. (d) Drop the volunteer scheduler and keep the rest of the design.

**Cascades.** C-01, C-02, C-04, C-10, C-17, C-19, C-20.

**Status.** Open. This is the item most likely to change the architecture if it is accepted.

---

## 2. Cascade map

Several items interact so that one answer changes another. The combinations below are where a design change, if any, is most likely to be forced.

1. **Plumbing chain: C-01 → C-02 → C-03 → C-04 → C-31 → C-19 → C-24.** If schedulers cannot be dialled, either a relay is on the hot path (cost, trust, an RTT, a new failure mode), or schedulers must be restricted to reachable hosts, or the role moves to the provider. The deepest form of the question is C-31: if the scheduler can be provider-hosted at negligible cost (greedy planning is under one core for 10⁵ workers), most of the NAT, failover and fencing machinery is optional. Each option changes a result that depends on the scheduler's location: failover time (2.7–14 s), the global-vs-clustered comparison, E18 scaling. E01 did not test any of this.
2. **Semantics chain: C-09 → C-10 → C-27 → C-13.** Retries, hedges and failover all lean on idempotence. If the platform must require idempotent functions, that is a product constraint. If it must not, success under omission falls and "detection and re-dispatch carry success" needs re-measurement; robust coverage's role (latency only) may shrink further.
3. **Trust chain: C-05 + C-06 + C-07 + C-11 + C-08.** The verifier is a confidentiality dependency in the default key-release mode; physical RAM access defeats Property 1 on consumer hardware without memory encryption; the key broker is a tenant burden; the exposure score that is meant to express all of this is a set of arbitrary numbers; and the machine needs an exclusive reboot. Together they narrow the honest claim to "software-level adversaries, scheduled or dedicated donors, with a stated KBS mode".
4. **Scale and realism chain: C-14 + C-21 + C-28 + C-17 + C-19.** Six tenants never hit the hot-set cap; the global baseline has a pool cap that hides its cost; the decision cost model does not grow with population; the scalability experiment shows the central decision path is the limit. The geo-clustering and "planning pays" conclusions are about a small head-of-distribution workload.
5. **Time-constant chain: C-12 + C-16 + C-17 + C-20.** `T_plan` (30 s) is not swept; the MILP's real solve (4–24 s) can approach it, but is charged about 0.1 s; watchdogs (1–3 s) are assumed against RTTs that grow with relays; plan staleness interacts with the 60 s horizon and 2–60 s failover. A single mis-set constant can flip which components appear to pay.
6. **Supply chain: C-08 + C-26 + C-25.** If donation is a scheduled, exclusive reboot, the supply looks like dedicated spare machines, whose economics against always-on cloud hosts (C-25) are what the commercial-reference comparison measures.
7. **Evidence chain: C-24 + C-22 + C-16.** E01's scope (start-up and execution only), well-specified estimator worlds, and a modelled decision clock mean the simulator's absolute and relative results are validated least exactly where the design is least conventional.

---

## 3. Suggested order for the back-and-forth

1. **C-01/C-02/C-31** (plumbing and the role of the volunteer scheduler). It is the one most likely to force an architectural decision, and C-19, C-24 and E18 depend on it.
2. **C-05/C-06/C-07** (trust claims). Decide how the headline claim is worded, and whether KBS mode and memory encryption are requirements.
3. **C-09/C-10** (idempotence). Decide the product contract.
4. **C-16 + C-12 + C-17** (time constants and solver cost). Decide whether to rerun E04/E23 with a measured or refitted decision clock.
5. **C-14/C-21/C-28** (workload and scale). Decide whether a trace-driven many-tenant experiment is needed before submission.
6. The remaining items (C-11, C-13, C-15, C-18, C-20, C-22, C-23, C-25, C-26) are mostly new experiments or scoped claims.

For each item the outcome will be one of: **accept** (design change, with a decision entry), **rebut** (the defense stands, with the argument recorded), or **scope** (the claim is narrowed and the limitation written down).
