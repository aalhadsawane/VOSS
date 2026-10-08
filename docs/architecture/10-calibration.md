# 10 · Calibration Harness and Single-Box Emulation Testbed

**Calibration node C0:**
- Intel Core i7 12th gen (Alder Lake), Intel PTT (firmware TPM 2.0);
- 128 GB DDR5;
- 1 TB NVMe SSD + 2 TB HDD;
- 2 × RTX 4060 Ti (unused: GPU functions are parked).

## 1. Principles

- **Single node, unattended, idempotent.** `tools/calibrate/run.py --suite <name>` runs probes, writes raw logs, and
  is safe to re-run. No cluster synchronization.
- **Non-destructive by default.** Anything that reboots the machine or changes BIOS settings needs an explicit flag
  and a manual step (§3.4, §3.5).
- **Outputs are data.** `tools/calibrate/ingest.py` turns raw logs into fitted distributions under
  `configs/calibration/measured/<host_fingerprint>/` (empirical quantiles + fitted lognormal + metadata), versioned
  and hashed into run manifests.
- Each probe records: harness version, kernel, Firecracker/QEMU versions, BIOS version, CPU microcode, and whether
  TME, Secure Boot and the IOMMU are on.

## 2. Capability probe (`--suite caps`)

Checks and records:
- `/dev/kvm`; CPU flags;
- **TPM:** `/dev/tpmrm0`, `tpm2_getcap properties-fixed` (vendor = INTC → PTT);
- **TME:** `dmesg | grep -i tme`, CPUID leaf 7 ECX bit 13, `MSR 0x982` if readable. TME availability varies by SKU and
  BIOS. Record and continue either way;
- Secure Boot state (`mokutil --sb-state`);
- IOMMU (DMAR in dmesg);
- disks (`lsblk`, rotational flag), free space.

Without a feature, its probes are skipped and the profile falls back to literature values flagged `assumed`.

## 3. Measurement suites

| Suite | What | How | Reps | Feeds |
|---|---|---|---|---|
| `disk` | SSD and HDD sequential/random read/write; dm-crypt and dm-verity overhead | `fio` on files on each disk (+ LUKS, verity loop devices) | 5 × each | Cache tier speeds (doc 02 §6) |
| `fc_boot` | Firecracker cold boot to init, VM memory 128–2048 MB, rootfs on SSD vs HDD, page cache cold/warm | Firecracker + jailer, official kernel; serial marker timestamps | 100 per config | L1→L3 |
| `fc_snapshot` | Snapshot create; restore (full) by memory size and tier; cold vs warm page cache (`drop_caches`) | Firecracker snapshot API | 50 per config | L2→L3, snapshot sizes |
| `qemu_vm` | QEMU VM boot (`microvm` and `q35` machines) | Serial marker | 50 | E-CS1 comparison |
| `kata` (optional) | Kata container start | `ctr`/`nerdctl` | 30 | E-CS1 |
| `sebs` | SeBS functions inside Firecracker: init time and execution vs input sizes; 1..n concurrent (interference) | Function harness in the guest | 30 per point | Function profiles, predictor priors, `speed` of C0, interference |
| `tpm` | `tpm2_quote` latency (PCRs 0–7, 10, 11), AK creation (once), seal/unseal | tpm2-tools | 200 quotes | `Tpm` resource, re-attestation cost |
| `attest_local` | End-to-end attestation round trip with a local verifier (Keylime agent + verifier on the node), excluding network | Timestamps in agent and verifier logs | 50 | Verifier CPU, quote path (the network RTT is added in simulation) |
| `tls` | TLS 1.3 handshake CPU and per-message overhead | `openssl s_time` / small bench | 1,000 | Channel costs |
| `tme` (manual) | TME on vs off: STREAM bandwidth, SeBS runtimes | Run the suite, toggle in BIOS, run again (`--phase on/off`) | 2 phases | Substrate slowdown factors |
| `appliance` (manual, `--allow-reboot`) | Reboot-to-attested: firmware → loader → UKI → dm-verity userspace → agent → quote → verifier OK | Build the appliance image (mkosi, UKI, dm-verity) on the HDD as a separate boot entry. A one-shot service logs `systemd-analyze` + attestation timestamps and reboots back to the normal OS; repeat N times | 20 boots | Session establishment cost, the core `appliance_tpm` parameter |

### 3.1 Appliance image (also the reference design of doc 04 §4)

- **Build:** `mkosi` producing a UKI and a dm-verity root; contents are a minimal kernel, Firecracker + jailer, the
  attestation agent, and a stub worker agent.
- **Disk layout:** an encrypted data partition sealed to PCR 7 + 11 (cache tiers live here).
- **Boot:** a separate UEFI boot entry, chosen once via `systemctl reboot --boot-loader-entry=voss-appliance` (or
  `efibootmgr --bootnext`), then back. The owner's normal OS stays untouched.

## 4. Single-box emulation testbed (simulator validation, optional P9b)

**Goal:** validate the simulator's *end-to-end* behavior on small scenarios run for real on one machine.

**Design** (reuses VOSS code through backend swaps; no second implementation):

| Simulator component | Emulation backend |
|---|---|
| `Kernel` (virtual time) | `RealtimeKernel` (asyncio; same `at`/`after` API) |
| `Network.send` | Loopback sockets between per-actor network namespaces with `tc netem` delays from the same geo RTT model |
| `world.lifecycle` + `execution` | `FirecrackerDriver`: real microVMs, snapshots and caches on the real SSD/HDD |
| Sessions / adversaries | A driver that kills/pauses VMs and drops messages per the same `SessionTrace` / `AdversaryTrace` |
| Attestation | Calibrated delays (real TPM quotes optional, one TPM) |
| Policies, actors | **Unchanged** |

- **Scale:** 20–40 emulated workers (128 GB is enough for many small microVMs).
- **Comparison:** run the same scenario in the simulator and in emulation. Compare end-to-end and per-component
  latency CDFs, success rate and cache level shares, and report the error (E01).

This is why the actor/message/kernel interfaces in doc 01 must stay clean: emulation is a backend swap.

## 5. Literature-only parameters

CVM classes (`cvm_snp`, `coco_pool`, `qemu_snp_ovmf`, `qemu_tdx`, severifast-like) come from
`docs/research/confidential-computing-sota.md` as `[low, high]` ranges in their substrate YAML, tagged `literature`.
Experiments sweep them (doc 06 §6).
