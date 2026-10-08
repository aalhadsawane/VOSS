# Proposal 0002 · Trust substrate on consumer hardware, simulation method, and the scheduler's new optimization

**Status:** ACCEPTED (2026-10-09) and folded into `docs/architecture/00`–`10` and `docs/DECISIONS.md`. Kept as design history; the architecture docs are authoritative.

**Inputs from the user:**
- Hardware will be Ryzen or Intel client CPUs (exact model to come).
- A simulation is strongly preferred.
- The scheduler's optimization is the core novelty and must be rethought.
- Remaining decisions are mine to recommend.

Each section below runs an idea → critique → revision loop.

---

## Part A · What can actually protect tenants on consumer Ryzen/Intel?

### A.1 Facts (with sources at the end)

| Feature | What it does | Protects against a malicious *owner with root*? | Attestation? |
|---|---|---|---|
| **AMD Memory Guard (TSME/SME)** | Transparently encrypts all RAM with one boot-time key held by the AMD security processor | **No.** The CPU decrypts for any software, so the OS sees plaintext. It defeats cold-boot, DIMM removal and bus snooping | No |
| **Intel TME / TME-MK** (11th/12th gen client) | Same idea; multi-key variant lets the host choose keys | **No.** TME-MK "does not enforce guest/hypervisor isolation" | No |
| **TPM 2.0** (AMD fTPM, Intel PTT; required by Windows 11, so nearly ubiquitous) | Measured boot (PCRs), quotes signed by an attestation key, endorsement-key (EK) cert chain to the vendor, sealing | **Yes, for the boot chain:** it proves *what software stack booted*, and a modified stack fails attestation | **Yes** (quote ≈ 0.3–2 s reported; measure ours) |
| **Keylime** (CNCF) | Industry stack for TPM remote attestation of nodes: measured boot + IMA runtime file integrity + payload/key release + revocation | With measured boot: yes (software tampering) | Yes |
| **DRTM:** Intel TXT / AMD SKINIT (TrenchBoot) | Late-launches a *measured* hypervisor under a running OS | Could deprivilege the owner's OS, but is research-grade: Linux patches still at v15; AMD DRTM needs a discrete TPM, not fTPM | Yes |
| SGX (client) | Deprecated on 11th gen+ client CPUs | — | — |
| SEV-SNP / TDX | True CVMs | Yes | Yes, but **server CPUs only** |

**Conclusion:** Memory Guard and TME are useful *components* (they close physical memory attacks) but are not a TEE.
On consumer hardware, protection from a malicious owner must come from **attested, owner-locked software**, rooted in
the TPM.

### A.2 Substrate options, round by round

**A-R1: "Memory Guard/TME as the TEE."**
**Critique:** fatal. A root owner reads tenant memory and forges results, and there is no attestation.
**Rejected.** (The paper should say this explicitly, because reviewers will check.)

**A-R2: Attested appliance mode.** The volunteer machine *boots into* a VOSS appliance OS when donating:
- Secure Boot with a signed unified kernel image, a read-only root (dm-verity), no owner login or shell.
- Disk encrypted with a key sealed to TPM PCRs.
- IOMMU enforced; Memory Guard or TME on.
- Remote attestation via TPM quotes (Keylime-style: measured boot + IMA runtime measurements).
- EK certificate checked against the vendor chain, so it is a real TPM and not a VM's vTPM.
- **Inside the appliance, tenant functions run in ordinary Firecracker microVMs**, because the host stack is now
  trusted. Snapshots and fast restores are back.

**Critique:**
1. **The machine is dedicated while donating** (no concurrent owner use). Owner "preemption" = rebooting back to
   their OS, so sessions are discrete donation sessions (nights, idle days, spare boxes).
2. **TCB = the whole appliance** (kernel + VMM + agent), much larger than a CVM's. Tenant escape from a microVM is
   the same risk Lambda/Firecracker accept.
3. **Physical attacks are out of scope:**
   - fTPM voltage glitching (faulTPM: about $200 of equipment, hours of physical access, Zen 2/3);
   - DMA through bad IOMMU configs.
4. **Firmware reference values** (PCR0 per motherboard BIOS) are hard to curate.
   *Answer:* policy = vendor-signed firmware + trust-on-first-use per machine + EK-bound identity; the residual risk
   is stated.

**Verdict:** **buildable and calibratable on the user's hardware today, with mature industry tooling (Keylime,
systemd UKI, dm-verity, Firecracker).** This becomes the **primary substrate `appliance_tpm`**.

**A-R3: DRTM measured micro-hypervisor** (TrustVisor/Flicker lineage via TrenchBoot). The owner keeps using the
machine, and VOSS VMs are protected from the owner's OS by a measured hypervisor beneath it.
**Critique:**
- It restores true cycle harvesting (concurrent use), which is very attractive.
- But deployment requires putting the owner's OS into a VM. Linux support is unmerged, and AMD needs a dTPM.
- Not buildable within this project.

**Verdict:** a modeled future substrate `drtm_hv`: same parameters as the appliance plus concurrent owner load, no
reboot cost. Discussed in the paper; not calibrated.

**A-R4: Server-class CVM** (SNP wCVM + trustlets, CoCo pools, from 0001).
**Verdict:** a modeled substrate `cvm_snp`, calibrated from literature only (§B), with sensitivity analysis. It
represents donors with server hardware.

**Converged decision (ADR to be written):** VOSS is **substrate-agnostic**. A *trust substrate profile* defines:
1. how trust is established (cost, scope);
2. how long it lasts (perishability);
3. what warm state costs;
4. what an attacker can still do.

| Profile | Trust established per | Establishment cost | Warm state | Concurrent owner use | Calibrated by |
|---|---|---|---|---|---|
| `appliance_tpm` (**primary**) | donation session (reboot) | reboot + measured boot + TPM quote + verify (tens of s; measure) | Firecracker snapshots (ms restores) | No | **Our measurements** |
| `cvm_snp` | wCVM session; key release per function per wCVM | wCVM boot 0.2–8 s + attestation; zygote ~1 s; key release RTT | zygotes and trustlets (<10 ms warm) | Yes | Literature (0001 research notes) |
| `coco_pool` | CVM shell | 3.5–17 s + attestation + in-guest image pull | tenant-bound shells | Yes | Literature |
| `drtm_hv` | DRTM launch | small (no reboot) | microVM snapshots | Yes | Modeled from the appliance + assumptions |
| `none` (reference) | — | — | microVM snapshots | Yes | Our measurements |

This makes the **user's requested cold-start comparison** (QEMU VM, Firecracker, CVMs, …) part of one experiment:
measured classes for what the user's machines can run, and literature classes for CVMs.

### A.3 Threat model v3 (replaces 0001 §1 where they differ)

**Adversary:** the volunteer owner and the network. The owner has full control of power, network, firmware settings
and their own OS. They can try to boot modified software, run the appliance in a VM, replay, delay, drop or
throttle, and create many identities.

**Neutralized:**
- Modified boot → PCR mismatch → attestation fails.
- VM or emulated TPM → no vendor EK chain → rejected.
- Memory reads → no shell or root inside the appliance; Memory Guard/TME stops cold-boot and DIMM reads.
- Forged results → only attested appliances get session keys; results are bound to them.

**Remaining power:** **omission and timing** (power off, unplug, drop, delay, throttle), lies about anything outside
the attested stack, and choosing *when* to defect.

**Out of scope:**
- Lab-grade physical attacks (glitching, bus probing);
- Kernel or VMM 0-days in the appliance;
- Side channels;
- Denial of service on the trusted orchestrator.

**Sybil:** one identity per TPM EK (per machine).

**Tenants vs tenants:** microVM isolation (the Firecracker threat model). The orchestrator is trusted for availability
and accounting; **tenant keys come from the tenant's own key broker**, wrapped to attested hosts.

The 0001 insight still holds: **attestation turns malicious volunteers into omission/timing-faulty volunteers.**

---

## Part B · Simulation methodology (no TEE simulators exist)

**B-R1: "Simulate everything from literature numbers."**
**Critique:** reviewers distrust models with no local grounding, and the CVM numbers vary 100× across papers.

**B-R2: "Real testbed only."**
**Critique:** heterogeneous machines, synchronization scripts, churn emulation and malicious hosts make it impractical,
and scale is limited. (The user's concern exactly.)

**B-R3 (converged): "Measure locally, simulate globally."**
- **The simulator (our DES) stays the experiment engine.** Geo latency, churn, adversaries, clusters, scheduling and
  10³–10⁵ workers are all simulated and fully reproducible.
- **Single-node calibration harness** (`tools/calibrate/`): scripted, unattended, one machine at a time, no cluster
  sync. It measures on the user's Ryzen/Intel box and emits distributions (CSV + YAML with a hardware fingerprint):

| Measured locally | Feeds |
|---|---|
| Firecracker cold boot, snapshot restore (mem and size sweep), QEMU VM boot, Kata boot (optional) | `none` / `appliance_tpm` ladder; cold-start comparison |
| Appliance: reboot-to-attested time (firmware → UKI → dm-verity → agent → TPM quote → verifier OK) | Session trust-establishment cost |
| `tpm2_quote` latency (p50/p99, 100+ runs); IMA measurement overhead; verifier check time | Re-attestation and freshness costs |
| Memory Guard/TME on vs off (if BIOS allows): STREAM bandwidth, SeBS runtimes | Execution slowdown factor |
| dm-verity read overhead; image pull and decompress | Lifecycle ladder |
| SeBS function runtimes vs input size, interference at 1..n concurrent | Predictor ground truth, reference speed |

- **Literature-only parameters** (CVM profiles) get **ranges, not points**. Every headline conclusion is checked
  with a sensitivity sweep across the range. Results report "robust within range" or "flips at X".
- **Optional validation (P9b):** a mini-testbed of the 2–3 machines the user owns, with geo latency emulated by
  `tc netem` and a scripted churn trace, running one small scenario. Compare its end-to-end latency CDFs with the
  simulator's on the same scenario and report the error. It is small, automatable and good for credibility.
- **Reproducibility:**
  - Simulation results are bit-reproducible from manifests.
  - Calibration is re-runnable by script, and the raw calibration data is versioned.
  - The paper reports the calibration hardware.

**Critique of B-R3:** distributed contention effects (many hosts booting, router load) are never measured for real.
*Answer:* those come from network and queue models (standard practice). The mini-testbed checks the end-to-end shape.

---

## Part C · The scheduler's optimization, rethought (core novelty)

### C.0 What changed for the scheduler

The old optimization was "place each invocation to minimize expected SLO misses, given latency predictions and
churn risk". Four new facts change its structure:

1. **Trust is expensive to establish:**
   - attestation, and a key release from the tenant's broker (a geographic round trip);
   - code load into an attested sandbox;
   - for CVMs, zygotes.
2. **Trust is perishable:**
   - It dies with churn (session end, reboot, power-off).
   - Attestations go stale and must be refreshed.
   - Keys released to a host stay exposed there for the session.
3. **Trust has a security cost:** every host that ever receives tenant *t*'s key widens *t*'s exposure surface
   (physical attacks and 0-days are out of scope, but not impossible).
4. **Some hosts are strategic adversaries:**
   - Their failures are not independent random churn: they may behave well, then omit when it hurts most (on-off
     attacks).
   - A purely stochastic risk model is exploitable.

### C.1 Ideation and critique rounds

**S-R1: add terms to the per-assignment cost matrix** (exposure penalty, adversary-inflated failure probability).
**Critique:**
- Exposure is a property of the **set of distinct hosts holding a key**: adding one host costs a lot, reusing it is
  free. That is a coverage-type function, not additive per invocation.
- Robustness to *f* adversarial hosts is a **worst case over subsets**.
- Per-pair additive costs cannot express either. They over-penalize repeated use of a key holder or miss the set
  effect entirely.

**Revision:** decisions about *which hosts hold which tenants' trust* need set variables.

**S-R2: put set variables in the per-window invocation ILP** (key-holder `y[t,j]`, a top-*f* robustness constraint
per window).
**Critique:**
- A window holds tens of invocations, so "robust per window" is statistically meaningless.
- Key-holder state lives for a whole session (hours), so it is not a per-window decision.
- Solving a set-coupled ILP on the request path adds latency to every invocation.

**Revision:** separate the timescales.

**S-R3 (converged): two-timescale, trust-aware scheduling.**

| Loop | Timescale | Decides | Method |
|---|---|---|---|
| **Slow loop: Trust & Warm-state Planning (TWP)** | every `T_plan` (10–60 s) + on events (join, leave, suspicion, demand shift) | Which hosts are **trust-warm** for which tenants (key released, code loaded, snapshot/zygote ready), how many warm units per runtime/function, per-host traffic caps, re-attestation timing, prewarm actions | **Robust MILP** (small: hosts × tenants/runtimes in one cluster), seconds of budget, warm-started from the previous plan |
| **Fast loop: invocation placement** | per invocation (sync) or tiny window (async/filler) | Which trust-warm host runs it, whether to hedge, when to take the cold path | Cost-matrix greedy / min-cost flow (existing machinery), constrained by TWP's candidate sets and caps |

This also settles the long-standing "ILP in the loop vs on the side" question in a principled way:
- the **combinatorial, set-coupled, robust part is slow and goes to the MILP**;
- the **latency-critical part is per invocation and polynomial**.

### C.2 Slow-loop formulation (sketch, for the paper)

**Inputs per cluster:**
- Attested hosts `J`, each with: memory budget `M_j`; survival over the horizon `S_j(H)` (survival model); estimated
  omission rate `p_j` (outcome-based); assurance `a_j ∈ [0,1]` (substrate profile, attestation freshness, TCB/firmware
  policy, age); failure domain `d(j)`.
- Tenants `T`, each with: demand forecast quantile `q_t`; sensitivity weight `σ_t`; runtime `r(t)`; code size.
- Existing state: `y0[t,j]` (trust-warm now), `z0[r,j]`.

**Variables:**
- `y[t,j] ∈ {0,1}`: tenant *t* trust-warm on *j* for the horizon. Releasing a new key is an action that pays the
  key-release latency, now and off the request path.
- `z[r,j] ∈ ℤ≥0`: warm units of runtime/snapshot class *r* on *j*.
- `c[t,j] ≥ 0`: capacity of *j* devoted to *t*.

**Objective (minimize), all terms exposed for Pareto sweeps:**

```
  Σ_t  ColdCost_t · E[demand of t not covered by healthy warm capacity]     # latency/SLO term
+ Σ_j  donor(j) · (Σ_r m_r z[r,j] + Σ_t m_code_t y[t,j])                     # donor memory/CPU
+ Σ_t  σ_t · Σ_j (1 − a_j) · y[t,j]                                          # exposure surface (key holders, assurance-weighted)
+ Σ_t,j  switch_cost · max(0, y[t,j] − y0[t,j])                              # churn of the plan (stability)
```

**Constraints:**
- **f-robust coverage (adversarial).** Coverage must survive the loss of *any* `f` hosts:
  `Σ_j c[t,j]·S_j(H)·(1−p_j) − max_{|F|≤f} Σ_{j∈F} c[t,j] ≥ q_t`.
  The max of the *f* largest is linearized exactly by LP duality: `f·θ_t + Σ_j π[t,j]`, with `π[t,j] ≥ c[t,j] − θ_t`,
  `π ≥ 0`.
- **Correlated failure:** `Σ_{j∈D} c[t,j] ≤ κ · Σ_j c[t,j]` for every failure domain `D`.
- **Coupling:** `c[t,j] ≤ cap_j · y[t,j]` and `y[t,j] ≤ z[r(t),j]` (a warm runtime is needed).
- **Memory:** `Σ_r m_r z[r,j] + Σ_t m_code_t y[t,j] ≤ M_j`.
- **Freshness:** hosts whose attestation expires inside `H` without a scheduled re-attestation get `c = 0`, or a
  re-attestation action is added.

**Size:** one cluster has ~30 hosts × (tens of hot tenants + a few runtimes), so about 10³ binaries. Seconds with
HiGHS, run off the request path. Long-tail tenants are not planned and take the cold path.

**Why this is genuinely an integer program** (answers old RQ16):
- set coverage (`y`);
- knapsack memory;
- robust top-*f* coverage;
- domain caps.

Min-cost flow cannot express these. A **greedy planner** (rank hosts by `S·(1−p)·a / memory`, add until robust
coverage holds) is the baseline the MILP must beat.

### C.3 Fast loop (deltas from doc 03)

- **Candidates for invocation *i* of tenant *t*:** trust-warm hosts `{j : y[t,j]=1}` with remaining cap `c[t,j]`, plus
  the **cold path**: any attested host, paying key release (broker RTT), code load, snapshot/zygote creation and an
  **exposure increment** (`σ_t(1−a_j)` if `j` is new for *t*).
- **Cost** (existing `C(i,j)` from 03 §7) gains the trust state in `T_startup` (trust-warm vs trust-cold) and an
  exposure term for cold-path hosts.
- **Hedging becomes the adversary defense:** for sync invocations with `pMiss > θ`, send a tied duplicate to a
  second trust-warm host in a *different failure domain*, under a hedge budget. Attested results make hedging
  integrity-safe; only idempotency limits it.
- **Retries prefer trust-warm hosts** (a retry on a trust-cold host pays the whole trust cost again).

### C.4 Risk model: stochastic churn + strategic adversaries

**R-R1: one omission probability per host from history.**
**Critique:** on-off attackers build a clean history, then defect; newcomers have no history.

**R-R2 (converged): hybrid.**
- **Stochastic part:** survival `S_j` (sessions) and outcome-based omission rate `p_j`, with change-point
  detection (a sudden rise in omission resets trust-warm eligibility).
- **Adversarial part:** the planner assumes *any* `f = ⌈α·N⌉` hosts may defect *regardless of history*, for an
  assumed adversary fraction `α`. This gives a guarantee that does not depend on modeling the adversary's strategy,
  which is exactly what reviewers ask for.
- **Progress-based detection** (0001 Round 5) shortens how long a defector can hurt.

**Critique:** `f`-robustness is conservative in small clusters (for N=30, α=10%, f=3, each hot tenant needs ≥ 4 warm
hosts).
**Answer:** that cost is the **price of robustness**, and the evaluation plots it (latency vs `α`, and vs exposure).
Sensitive or low-volume tenants can opt down (`f=0`).

### C.5 The trilemma the scheduler navigates (paper framing)

| Push toward | Gains | Costs |
|---|---|---|
| **Concentrate** trust on few hosts | Low exposure, high warm-hit, low donor memory | Fragile to churn and to targeted omission |
| **Spread** trust across many hosts and domains | Robust to *f* defectors and correlated churn | More exposure, more donor memory, more cold key releases |
| **Stay cold** (no planning) | Zero idle cost, minimal exposure | High latency (every first touch pays trust establishment) |

VOSS's planner picks the point on the **latency × exposure × robustness** surface per tenant sensitivity class. The
headline figures are the Pareto frontiers vs baselines.

### C.6 Router and orchestrator deltas

- **Cluster summaries** carry, per hot tenant: trust-warm capacity, robust coverage slack, and the assurance mix.
- **Router:**
  - prefers clusters where the tenant is trust-warm;
  - spilling to a trust-cold cluster costs key release + exposure, so spillover becomes a priced decision;
  - the router also detects stalled clusters from missing progress.
- **Orchestrator:** cluster formation adds **assurance and failure-domain diversity**, so every cluster can satisfy
  f-robust plans. Small clusters keep the slow-loop MILP tractable, so geo-clustering still enables the optimizer.

### C.7 Baselines and ablations for the scheduler

- **Planning:** none (reactive cold path); a static per-function keep-alive TTL; greedy planner; MILP without
  `f`-robustness; MILP without exposure; MILP without the domain cap; oracle-demand MILP (analysis only).
- **Placement:** existing baselines (random, least-loaded, po2, warm-first, latency-aware, …), each given the same
  trust-warm sets.
- **Adversaries:** none; random omission at rate *p*; black-hole; on-off (good for *k* hours, then defect); targeted
  at hot tenants (only possible through metadata leakage, so the padding knob is evaluated); colluding domain (whole
  ASN).
- **Ablations:** no hedging; no progress-based detection (heartbeat only); no change-point reset; `f=0`; `σ=0`.

---

## Part D · Research-paper perspective (step back, critique the whole)

**P-R1: positioning.** "Confidential serverless on volunteers."
**Critique:** confidential-serverless *mechanisms* exist (Wallet, PIE, Reusable Enclaves, SEVeriFast), all single-node.
Volunteer computing handles integrity by replication. Edge FaaS schedulers ignore trust. A mechanism paper would be
incremental.
**Revision:** position as a **scheduling** paper: *trust as a schedulable, perishable resource.*

**P-R2: one-sentence thesis.**
*Attested execution turns malicious volunteers into merely unreliable ones; what remains is a scheduling problem in
which trust is costly to establish, perishes with churn, and carries exposure. VOSS solves it with geo-clustered,
two-timescale, robust trust-and-warm-state planning plus risk-aware placement.*

**P-R3: contributions (pruned to avoid dilution).**

| | Contribution | Status |
|---|---|---|
| **C1** | Problem and model: substrate profiles (trust cost, perishability, exposure) + omission/timing adversaries + churn | Foundation |
| **C2 (headline)** | Two-timescale trust-aware scheduler: robust MILP planner for trust and warm state (f-robust coverage, exposure, domain caps) + risk-aware fast placement and hedging | Headline |
| **C3** | Omission-tolerant soft-state succession for attested schedulers (progress-based detection, rollback-immune) | Supporting |
| **C4** | Measured characterization: cold start and trust establishment across Firecracker, QEMU, Kata, TPM appliance (measured) and CVM classes (literature) | Headline (empirical) |
| **C5** | Viability map across substrate × churn × adversary fraction × load × cluster size | Headline (results) |

**P-R4: reviewer attack list and responses.**

| Attack | Response |
|---|---|
| "Measured boot is not a TEE." | Correct, and we don't claim it is. The threat model is software-capable owners; physical attacks are excluded and discussed; a CVM profile is included for server donors |
| "Simulation-only." | Local calibration harness + mini-testbed validation with reported error + sensitivity ranges for literature parameters |
| "Your adversary is a strawman." | The `f`-robust guarantee is strategy-independent; canonical strategies (incl. on-off and colluding domain) are evaluated |
| "Volunteers won't reboot into an appliance." | Model donation sessions (nights/idle/spare boxes); the DRTM and CVM profiles cover concurrent use; report how session length changes viability |
| "Exposure is an ad-hoc metric." | It is a transparent proxy (assurance-weighted key-holder count). We show Pareto curves rather than one weighted optimum |
| "MILP is overkill." | It is only in the slow loop; compared against a greedy planner and against no planning; kill criterion below |
| "The orchestrator is trusted." | Only for availability and accounting; tenant secrets go through tenant-owned brokers |

**P-R5: kill criteria** (decide after pilots; report negative results honestly):
- If the MILP planner beats the greedy planner by < 5% P99 across regimes, the greedy planner becomes the method and
  the MILP an upper-bound reference.
- If the exposure term barely moves the Pareto front, demote it to a sensitivity study.
- If `appliance_tpm` session costs make volunteers unviable at realistic session lengths, that is a viability-map
  result: report it and lean on the `cvm_snp` / `drtm_hv` profiles.

**P-R6: scope control (ship fast).**
- **Must:** the `appliance_tpm` profile (measured), the `cvm_snp` profile (literature), the `none` reference, the
  slow-loop MILP + greedy planner, fast placement + hedging, three adversaries (random omission, black-hole, on-off),
  progress-based detection, geo clusters, succession.
- **Should:** `coco_pool`, colluding-domain adversary, the mini-testbed.
- **Could:** `drtm_hv`, padding, workflows.

---

## Part E · Decisions (resolved by recommendation) and what I still need

| # | Decision | Resolution |
|---|---|---|
| Q1 | Isolation inside the trusted substrate | `appliance_tpm`: Firecracker microVMs per function. `cvm_snp`: trustlets (modeled), with CoCo as the baseline |
| Q2 | TEE | **Primary: TPM-attested appliance on consumer Ryzen/Intel** (+ Memory Guard/TME against physical memory attacks). Server CVM (SNP) modeled; TDX as sensitivity |
| Q3 | Key release | Tenant-owned key broker (Keylime/KBS-style), keys wrapped to attested hosts |
| Q4 | Blockchain | Stays removed; attested results give verifiable receipts |
| Q5 | Motivation | **Broadens back to consumer machines.** TPM 2.0 is on nearly every Windows-11-era PC; donation is session-based. Server donors via CVM profile |
| Q6 | Calibration hardware | The user's Ryzen/Intel box via the single-node harness; CVM numbers from literature with ranges |
| Q7 | Adversaries | Random omission, black-hole, on-off, colluding domain, throttling, fake owner signals, replay. Sybil bounded by TPM EK |

**Still needed from you (small):**
1. The exact machine(s): CPU model and whether it is a PRO/vPro part; fTPM/PTT vs discrete TPM; whether BIOS exposes
   Memory Guard/TME. This decides what the harness can measure.
2. Is the **donation-session (reboot into appliance)** framing acceptable as the primary consumer story, with
   concurrent-use DRTM as discussed future work?

**After your answer:** refactor all architecture docs to the converged design (one PR, merged), update the roadmap and
ADRs, and replace 09 with threat model v3.

## Sources

- AMD Memory Guard/TSME scope and the 2026 Ryzen 9000 change: https://www.techspot.com/news/112791-amd-quietly-disabled-ram-encryption-consumer-ryzen-cpus.html ; https://hackmag.com/news/amd-tsme
- Intel TME / TME-MK: https://intel.com/content/www/us/en/architecture-and-technology/total-memory-encryption-security-paper.html ; https://docs.enclaive.cloud/confidential-cloud/technology-in-depth/intel-tdx/technology/history/tme-mktme ; https://www.kicksecure.com/wiki/Dev/confidential_computing
- Keylime: https://www.cncf.io/blog/2021/07/06/ibm-implements-remote-attestation-on-linux-with-a-hardware-root-of-trust-using-keylime/ ; https://documentation.suse.com/sle-micro/html/SLE-Micro-all/cha-security-attestation.html
- TrenchBoot / DRTM: https://lists.infradead.org/pipermail/kexec/2025-April/032671.html ; https://lkml.iu.edu/hypermail/linux/kernel/2512.2/03047.html ; https://groups.google.com/g/trenchboot-devel/c/T9d0pez3ItE
- TPM quote latency: https://arxiv.org/pdf/2609.20909 ; https://arxiv.org/pdf/2303.16463 ; https://lkml.iu.edu/hypermail/linux/kernel/1702.1/04615.html
- faulTPM: https://arxiv.org/pdf/2304.14717
- pKVM status (Arm only): https://docs.kernel.org/virt/kvm/arm/pkvm.html ; https://lwn.net/Articles/1053007/
- Earlier sources: `docs/research/confidential-computing-sota.md`
