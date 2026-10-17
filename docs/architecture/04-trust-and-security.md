# 04 · Trust and Security

Accepted from proposals 0001/0002 (kept in `docs/proposals/` as the design history). Evidence:
`docs/research/confidential-computing-sota.md`.

## 1. Threat model

**Assets:**
- tenant code, inputs, outputs and secrets;
- correctness of results;
- correctness of accounting (credits);
- availability.

**Adversaries:**

| Adversary | Capabilities | Neutralized by | Residual power |
|---|---|---|---|
| **Volunteer owner** (may be malicious) | Full control of power, network, firmware settings and their own OS. Can attempt to boot modified software, run the appliance in a VM, replay/delay/drop/reorder traffic, throttle, create identities, choose *when* to defect | Measured boot + TPM attestation (modified stack fails), vendor-certified TPM endorsement key (no VMs/emulated TPMs), owner-locked appliance (no shell/root), disk sealed to PCRs, IOMMU, memory encryption (Intel TME / AMD Memory Guard) against cold-boot and DIMM reads | **Omission and timing:** power off, drop, delay, throttle; lies about anything outside the attested stack |
| **Network attacker** | Observe and modify traffic | TLS terminated inside attested appliances, keys bound to attestation | Traffic metadata (sizes, timing) |
| **Other tenants** | Malicious function code | Firecracker microVM isolation (same model as Lambda) | Microarchitectural side channels (out of scope) |

**Trusted:**
- the CPU, its TPM (fTPM / PTT) and memory encryption;
- the measured VOSS appliance image (kernel, VMM, agent, scheduler code);
- each tenant's own key broker;
- the provider-run orchestrator tier, **for availability and accounting only.** It never sees tenant secrets.

**Out of scope (stated as limitations):**
- lab-grade physical attacks (fTPM voltage glitching, bus probing);
- kernel/VMM 0-days in the appliance;
- side channels and traffic analysis;
- denial of service against the orchestrator tier;
- failure of the orchestrator tier.

**Consequence used everywhere else:** to the rest of the system a malicious worker or scheduler host is an
**omission/timing-faulty node**. VOSS already tolerates those: progress-based detection, succession, hedging (doc 07).

## 2. Why not cheaper or stronger alternatives

| Alternative | Verdict |
|---|---|
| **Memory Guard / Intel TME alone** | Not a TEE: the OS sees plaintext and there is no attestation. Used only as a *component* against physical memory attacks |
| **Replicated execution + voting (2f+1)** | Triples cost; most functions have side effects or no comparable output |
| **Zero-knowledge / verifiable computation** | Orders of magnitude too slow for FaaS |
| **Vetted volunteers (old design)** | Shrinks the pool to a narrow federation (rejected as motivation) |
| **Server CVMs (SEV-SNP/TDX)** | Strongest isolation, but server CPUs only. Kept as the modeled profile `cvm_snp` |
| **DRTM measured hypervisor under the owner's OS** | Allows concurrent owner use; not deployable today (unmerged Linux, AMD needs a discrete TPM). Modeled as `drtm_hv` |
| **Blockchain ledger** | Protects against no adversary in this model; attested receipts already make work verifiable (doc 09) |

## 3. Trust substrate profiles

A **substrate profile** is data (`configs/substrates/<name>.yaml`) that tells the generic engine (doc 02 §5):

1. how a worker *establishes trust* (cost, scope);
2. how long trust lasts (*perishability*);
3. the warm-state **ladder** and its transition costs;
4. the **assurance** of hosts on this substrate;
5. execution and I/O slowdowns.

| Profile | Trust established | Establishment cost (seed values, replaced by calibration) | Warm ladder | Owner may use machine concurrently | Assurance base | Source |
|---|---|---|---|---|---|---|
| **`appliance_tpm`** (primary) | Per **donation session** (boot into appliance) | Reboot + firmware + measured boot + TPM quote + verifier: **tens of seconds** (measured in doc 10) | Firecracker: artifacts → snapshot → warm VM | No | 0.80 | **Measured** on our i7 node |
| `cvm_snp` | Per wCVM session; key per function per wCVM | wCVM boot 0.2–8 s + attestation; zygote ~1 s | zygote → loaded function → trustlet (<10 ms) | Yes | 0.95 | Literature (ranges) |
| `coco_pool` | Per CVM shell | 3.5–17 s + attestation + in-guest image pull | tenant-bound shells | Yes | 0.95 | Literature |
| `drtm_hv` | Per DRTM launch | Small (no reboot) + quote | Firecracker ladder | Yes, with interference | 0.75 | Appliance values + assumption |
| `none` | — | — | Firecracker ladder | Yes | 0.0 (no security) | Measured |

Assurance bases are **policy parameters for the exposure metric**, not measured truths. Experiments sweep them.

## 4. Primary substrate: the attested VOSS appliance

**Image:**
- Unified kernel image (UKI) signed for Secure Boot, booted via shim.
- dm-verity read-only root.
- Firecracker + jailer, the **worker agent**, and the latent **scheduler role** (same image, so every attested
  worker is a scheduler candidate).
- No owner login. Kernel lockdown, IOMMU on, IMA on.
- Data partition encrypted with a key sealed to the expected PCRs. It holds the worker caches (doc 02 §6).

**Donation session:**
1. The owner chooses "donate" (scheduled or idle-triggered) and reboots into the appliance.
2. The agent attests (§5).
3. The worker becomes schedulable.
4. The session ends on owner reboot (abrupt), an owner drain request (graceful, deadline), or power loss.
5. Trust is lost with the session: keys and warm VMs vanish. Disk caches survive *as ciphertext* and are re-used
   next session after re-attestation.

## 5. Attestation (Keylime-style, modeled)

```mermaid
sequenceDiagram
    participant A as Worker agent (appliance)
    participant TPM as TPM (fTPM / PTT)
    participant V as Verifier + Registrar (orchestrator tier)
    participant S as Scheduler (attested)
    A->>V: REGISTER(EK cert, AK public)  [first session only]
    V->>V: validate EK cert chain → vendor root; bind identity = hash(EK)
    V->>A: nonce
    A->>TPM: quote(PCRs 0-7, 11, IMA PCR 10; nonce)
    TPM-->>A: signed quote + event log
    A->>V: ATTEST(quote, event log, IMA log, session pubkey)
    V->>V: verify signature, replay event log, check policy (firmware allow-list or TOFU, Secure Boot state, UKI digest, IMA allow-list)
    V-->>A: SESSION_CERT(identity, session pubkey, assurance, expiry)
    A->>S: mutual TLS with SESSION_CERT  (S holds its own SESSION_CERT + appointment token)
    loop every T_reattest
        V->>A: nonce
        A->>V: fresh quote + IMA delta
    end
```

- **Session key pair** is generated inside the appliance and bound into the quote (nonce || hash(pubkey)). Every
  channel (router, scheduler, KBS, peers) uses TLS with this certificate, so there is no untrusted OS on the path
  (the appliance *is* the OS) and the network sees ciphertext.
- **Perishability:** a session certificate expires at `min(session end, last_quote + T_valid)`. Periodic re-quotes
  (`T_reattest`) extend it. A failed re-quote revokes the certificate, and the verifier notifies the scheduler and
  routers.
- **Costs in the model:** quote latency (measured `tpm2_quote`), verifier CPU (ms), and the network RTT to the
  verifier's region. Reboot-to-attested time is measured end to end (doc 10).

## 6. Tenant secrets: key release

- Each tenant runs a **key broker (KBS)** with a policy: accept SESSION_CERTs issued by the VOSS verifier for
  appliance measurements ≥ policy version, plus a fresh quote (optional, stricter).
- **Trust-cold → trust-warm** for tenant *t* on worker *j*:
  1. The worker requests `KEY(t)` from *t*'s KBS over TLS.
  2. The KBS checks the certificate (and the quote if required) and returns the key wrapped to the session pubkey.
  3. The key is cached in appliance **memory only**, for the session.
- **Cost:** RTT to the KBS location + policy check. This is the "trust" term of cold paths in the cost model, and the
  planner pays it proactively for trust-warm sets (doc 03 §4).
- **The scheduler never sees tenant keys.** The orchestrator never sees tenant keys.
- Tenant code bundles in registries and P2P caches are **encrypted with the tenant key**: any worker may store or
  forward ciphertext, but only trust-warm workers can use it.

## 7. Identity, Sybil, reputation binding

- **Identity = hash of the TPM endorsement key**: one per physical machine (or TPM). Creating identities costs
  machines, and whitewashing costs a machine.
- Identity-bound records: reliability statistics, reputation, credits (doc 09).
- Privacy note: the EK is a stable hardware identifier, visible to the orchestrator (stated).

## 8. Exposure (the security cost the scheduler optimizes)

- **Exposure of tenant *t*** over a horizon = `E_t = Σ_{j ∈ KeyHolders(t)} (1 − a_j)`: the assurance-weighted
  number of distinct hosts holding *t*'s key or decrypted artifacts.
- **Host assurance** `a_j = a_substrate × f_fresh(time since last quote) × f_policy(firmware known-good vs TOFU)`.
  It lies in [0,1] and is configurable. *Implementation note (D-69):* the verifier computes `a_j = a_substrate × f_policy`; staleness is handled by certificate expiry (a host whose certificate expires inside the planning horizon is not provisioned), not by a continuous `f_fresh` factor.
- **Tenant sensitivity class** `σ_t ∈ {low, medium, high}` weights exposure in the planner (doc 03 §4). High-sensitivity
  tenants also get an assurance floor (`a_j ≥ a_min`).
- Exposure is a **transparent proxy**, not a probability of compromise. Results are shown as Pareto fronts
  (latency × exposure × robustness), never as one weighted number.

## 9. Attested receipts (accounting integrity)

- A worker returns `RESULT` over its attested TLS channel with a receipt:
  `{inv_id, attempt, worker_id, session_cert_id, epoch, exec_s, ref_work_units, digest(output)}` signed by the
  session key.
- The router verifies and logs it (doc 09). A host cannot claim work it did not do; it can only *not* do work
  (omission).
- Credits use **reference work units**, not elapsed time, so throttling earns nothing.

## 10. Limitations to state in the paper

1. Physical attacks with equipment (faulTPM-class) and appliance 0-days are excluded.
2. Firmware reference values are hard to curate across motherboards. The policy uses vendor-signed firmware plus
   trust-on-first-use, and the residual risk is stated.
3. Under `appliance_tpm` the owner cannot use the machine during a donation session.
4. The orchestrator tier is trusted for availability and accounting (not confidentiality).
5. Traffic-analysis metadata (sizes and timing) may reveal hot tenants. An optional padding knob is evaluated.

## 11. Deviations from the original research spec

| Spec | Spec says | Design | Decision |
|---|---|---|---|
| §3.1 #7, §4.5 | Untrusted participants; verify results, chain anchoring | Malicious owners neutralized by attestation; results verifiable via attested receipts | D-03, D-04 |
| §4.5, C5, RQ10, H7 | Tamper-evident blockchain ledger | **No blockchain**; attested receipts in the orchestrator DB | D-04 |
| §7 | microVM lifecycle, Linux/KVM everywhere | Same, **inside the attested appliance**; substrate profiles add CVM classes | D-02 |
| §5.5 | No volunteer-hosted SPOF; orchestrator redundant | Orchestrator tier is provider-run and assumed reliable; scheduler crash/omission-tolerant via succession | D-07, D-08 |
| §8 | Per-cluster ILP for invocation placement | **ILP moves to the slow planner** (trust and warm state); fast placement is greedy/flow | D-10 |
