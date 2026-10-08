# Confidential Computing for Serverless: State of the Art (research notes)

Collected 2026-10-08 for proposal 0001. Every number is the cited authors' own measurement on their setup; treat as
calibration *starting points* and mark `# TODO verify` wherever used. Our own calibration (Roadmap P9) supersedes them.

## 1. Cold-start numbers by sandbox class

| Sandbox class | Cold start (reported) | Notes | Source |
|---|---|---|---|
| Firecracker microVM (no TEE) | ~40 ms boot (AWS microVM kernel, 1 vCPU, 256 MB) | Snapshots restore in ms | SEVeriFast §3/§6 |
| QEMU VM (no TEE), full Ubuntu | ~3.7 s boot | Generic distro boot | Wallet Fig. 1 |
| Kata VM sandbox (no TEE) | ~1 s `make-pod-sandbox` | Container-in-VM | SESAME'24 §4.1 |
| QEMU + OVMF, SEV-SNP | firmware/boot-verification ~3.2 s + pre-encryption ~0.29 s (before kernel) | OVMF dominates | SEVeriFast Fig. 10 |
| QEMU SEV-SNP CVM, full Ubuntu | ~8.3 s boot | ≥2× a VM | Wallet Fig. 1; CVM-Explained |
| CVM vs VM (SNP and TDX) | boot ">2×" a VM; VM boot +231% (SNP), +394% (TDX) | Host memory management and acceptance dominate | CVM-Explained (SIGMETRICS'25); cited in 2609.04478 |
| Knative + Confidential Containers (Kata-CC, attestation, encrypted image pulled in guest) | ~17.5 s cold, ~17.5 s "warm" (no reuse); 16 concurrent: 190 s | CVM start +4 s vs VM; in-guest image pull +3–5 s | SESAME'24 Tab. 1, §4 |
| SEVeriFast (Firecracker fork, SEV/SEV-ES/SNP) | ~4× stock Firecracker; −86…94% vs QEMU/OVMF | Minimal boot verifier (~13 KB), compressed kernel | SEVeriFast §6 |
| Wallet (SNP, VMPL + COCONUT-SVSM trustlets) | cold 2.4 s; warm/lukewarm < 10.3 ms; one-time CVM init ~12 s | Trustlets forked from zygote templates | Wallet (NSDI'26) §8 |

## 2. Component costs

| Component | Reported cost | Source |
|---|---|---|
| Remote attestation (report → verifier → secret) | ~200 ms with a local verifier; "typically < 10 ms" for the report itself | SEVeriFast §6.1; cited in 2609.04478 |
| Attestation in Wallet | cold measurement ~1.1 s (monitor + 60 MB zygote, software SHA-512); warm 0.25–0.5 ms (cached) | Wallet §3, §8.3 |
| Concurrent SEV launches on one host | Linear slowdown; 50 concurrent → ~1.8 s average each. Attributed to the single-core PSP serializing launch commands | SEVeriFast Fig. 12 |
| Memory validation (pvalidate, 256 MB) | >60 ms → <1 ms with huge pages | SEVeriFast §6.1 |
| Lazy (unaccepted) memory acceptance | ~2.5× faster boot (4 GB TDX), ~4× (64 GB); merged in Linux 6.5; SNP too | Intel patch series (Phoronix) |
| SEV (non-SNP) eager memory provisioning | ~1 s per 2 GB guest | SESAME'24 §4.2.1 |
| Execution slowdown in CVM | compute/I-O bound: single-digit %; ML inference: large under HLT idle, ~0 with idle polling; VMEXIT up to 6.8× (TDX) | 2609.04478; CVM-Explained |
| Network I/O ("CVM-IO tax", bounce buffers) | 21–28% overhead on network-heavy workloads (SEV-ES/SNP) | Li et al., ATC'23 |
| Memory per instance | No KSM/dedup across CVMs; single VM +9–20%; pages pinned | 2609.04478; SEVeriFast §7 |
| CVMs per host | ~509 (encryption-key/ASID limit in Wallet's setup) | Wallet §3.5 |

## 3. Things that do not work (or not yet) for CVMs

- **VM snapshot/restore, templating, cloning, KSM:** memory is encrypted with per-VM keys and the launch measurement
  is per instance. Kata's VM templating is explicitly unsafe for confidentiality. Lazy snapshot loading needs
  host↔guest page verification (SEVeriFast §7). **Snapshots must move inside the guest** (process-level zygotes and
  forks, as in Wallet).
- **Pre-warming with pre-attestation TEEs** (SEV, SEV-ES) is impossible, because instances bind to a guest owner at
  launch. **SEV-SNP and TDX** use guest-initiated attestation and can be pre-warmed (SESAME'24 §4.3).
- **Reset/reboot** of SNP/TDX guests terminated them before QEMU 11.0 (Red Hat blog).
- **Live migration** of SNP CVMs is generally unavailable; host maintenance means re-attestation (IONOS docs).

## 4. Industry stack to mirror (names and flows we model)

- **Confidential Containers (CoCo)**, CNCF: Kata Containers running pods in CVMs. In-guest **kata-agent**,
  **Attestation Agent** (RATS attester), **Confidential Data Hub**, and **image-rs** (pull, verify and decrypt images
  inside the guest). Lazy attestation triggers only when a secret is needed.
- **Trustee**: **KBS** (key broker, relying party), **Attestation Service**, **RVPS** (reference values). The KBS
  protocol is Request-Challenge-Attestation-Response. Usually operated by the *workload owner*, not the cloud
  provider.
- **VMMs:**
  - QEMU: SEV-SNP and TDX; the main Kata-CC path.
  - Cloud Hypervisor: SEV-SNP on KVM with IGVM firmware as of v52; TDX supported.
  - Firecracker: no upstream CVM support (SEVeriFast is a research fork of v0.26).
- **COCONUT-SVSM** (VMPL0 service module, vTPM) and **IGVM** firmware packaging. Linux 6.11 has SNP host and SVSM
  guest support; private memory uses `guest_memfd`.
- **Research systems:**
  - Wallet/Hacher (NSDI'26): VMPL trustlets.
  - SEVeriFast (ASPLOS'24): fast SNP microVM boot.
  - Reusable Enclaves (USENIX Sec'23): reset and nested attestation (SGX).
  - PIE (ISCA'21): plug-in enclaves.
  - Ditto: elastic CVM vCPUs.
  - Nested attestation for confidential serverless (ePrint 2025/727): worker reuse with sanitization.

## 5. Hardware availability (affects the motivation)

- SEV-SNP: AMD EPYC (server). TDX: Intel Xeon 4th/5th gen+ (server). No consumer SEV-SNP was found.
- Arm CCA: no public hardware as of FOSDEM 2026; data-center parts are expected 2026–27.
- So today's TEE-capable "volunteers" are owners of **server-class** machines: university labs, research groups,
  SMB and colo servers, homelab EPYC/Xeon, edge micro-datacenters.

## 5b. Consumer hardware (Ryzen / Intel Core), added for proposal 0002

- **AMD Memory Guard (TSME)** and **Intel TME/TME-MK** encrypt all RAM against *physical* attacks. The host OS sees
  plaintext and there is no attestation, so they are **not** a TEE against a malicious owner.
- **TPM 2.0** (AMD fTPM, Intel PTT; Windows 11 requires it) provides measured boot and remote attestation.
  **Keylime** (CNCF) is the industry stack (measured boot + IMA + key release + revocation). Reported quote latency is
  ~0.3–2 s and must be measured.
- **DRTM** (Intel TXT, AMD SKINIT via TrenchBoot): Linux patches are at v15 (Dec 2025); AMD DRTM needs a discrete TPM.
- **faulTPM:** voltage glitching of the AMD fTPM (Zen 2/3) with physical access (~$200, hours), so physical attacks
  are out of scope.
- **pKVM** protected guests: Arm only, experimental.
- Sources are listed in proposal 0002.

## 6. Fault-model theory

- TEE integrity can **transform Byzantine faults into crash/omission faults** for the protected code (Madsen et al.,
  "Transforming Byzantine faults using a TEE"; DISC'25 TEE paper). Trusted-counter systems (TrInc, MinBFT) stop
  equivocation. The caveat is **rollback** of persisted state across restarts.

## Sources

- SEVeriFast (ASPLOS'24): https://people.cs.vt.edu/djwillia/papers/asplos24-severifast.pdf ; https://github.com/SEVeriFast/severifast
- Wallet / Confidential Serverless Computing (NSDI'26): https://arxiv.org/html/2504.21518v3 ; https://www.usenix.org/conference/nsdi26/presentation/sabanic
- Serverless Confidential Containers (SESAME'24): https://carlossegarra.com/assets/papers/sesame24-serverlesscoco.pdf
- Confidential VMs Explained (SIGMETRICS'25): https://dse.in.tum.de/wp-content/uploads/2024/11/sigmetrics25summer-CVM-Explained.pdf
- Performance Study of Serverless Workloads in CVMs (arXiv 2609.04478): https://arxiv.org/html/2609.04478v1
- Reusable Enclaves (USENIX Security'23): https://www.usenix.org/conference/usenixsecurity23/presentation/zhao-shixuan
- Nested attestation of confidential serverless (ePrint 2025/727): https://eprint.iacr.org/2025/727.pdf
- Ditto: https://arxiv.org/pdf/2409.15542
- CVM-IO tax (ATC'23): https://www.usenix.org/system/files/atc23-li-dingji_1.pdf
- Unaccepted memory (Linux 6.5): https://www.phoronix.com/news/Linux-6.5-Unaccepted-Memory ; https://www.phoronix.com/news/Unaccepted-Memory-v2
- Confidential guest reset in QEMU: https://www.redhat.com/en/blog/confidential-guest-reset-qemu-hypervisor-design-choices-and-approach
- Cloud Hypervisor v52 (SNP on KVM, IGVM): https://newreleases.io/project/github/cloud-hypervisor/cloud-hypervisor/release/v52.0
- CoCo / Trustee architecture: https://www.redhat.com/en/blog/confidential-containers-azure-openshift-technical-deep-dive
- Kata VM templating caveat: https://github.com/superfly/kata-containers/blob/main/docs/how-to/what-is-vm-templating-and-how-do-I-use-it.md
- Arm CCA availability (FOSDEM'26): https://fosdem.org/2026/schedule/event/opencca
- Byzantine→crash with TEE: https://drops.dagstuhl.de/storage/00lipics/lipics-vol356-disc2025/LIPIcs.DISC.2025.39/LIPIcs.DISC.2025.39.pdf ; https://pure.itu.dk/en/publications/transforming-byzantine-faults-using-a-trusted-execution-environme/ ; TrInc https://www.cs.umd.edu/~dml/papers/trinc_nsdi09.pdf
- SNP attestation verification docs (VCEK, KDS): https://docs.edgeless.systems/contrast/architecture/snp
