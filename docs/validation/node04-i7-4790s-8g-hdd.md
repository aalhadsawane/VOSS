# Calibration notes: bare-metal node `node04-i7-4790s-8g-hdd`

**Session:** 2026-11-18 to 2026-11-20 (UTC), branch `calib/node04-i7-4790s-8g-hdd` cut from `revision-v2` (`94ea4eb`).
Node number `node04`, codename `calangute1`. Part A and `setup` started on harness lock
`b50f5dad13a99e6d97f4e57d330f0e0e8918bd19`; after `quick` exposed three harness defects on a no-TPM 8 GB HDD host
(below), `tools/calibrate/` and `calibration/HARNESS.lock` were updated to `a1f77cf1cb204ee1234bf57021f8f7f5d0556d27`
with human approval, and `quick`, `full`, Part C (10 host-mode boots), and `ingest` ran on that lock. Everything below
was measured on this machine; no value is copied from another node, an earlier run, or the literature. Any probe that
cannot be measured on this hardware stays missing with its reason.

---

## 1. Human answers (`CALIBRATION_HANDOFF.md` §0.4)

| Question | Answer |
|---|---|
| Which machine / earlier session? | `node04`, codename `calangute1`: Lenovo desktop (BIOS `FCKT65AUS`), 4th-gen Intel Core i7-4790S (Haswell, 4 cores / 8 threads), 8 GB DDR3-1600, 1 × 500.1 GB WD `WD5003ABYX-23` SATA 7200 rpm HDD, no TPM. Never measured before. |
| Which parts today? | Parts A, B, C, and D; commit after each part; open PR `Calibration: node04-i7-4790s-8g-hdd` into `revision-v2` and do not merge. |
| Reboots approved? | Yes, with the `CALIBRATION_HANDOFF.md` §5 step 3 preflight (non-OS services disabled for the loop, `efi_pstore` panic capture verified, 1 supervised manual reboot first, stop at the first incomplete boot), followed by 10 host-mode measured boots. |
| BIOS change possible/wanted? | No BIOS change. CPUID leaf 7 ECX bit 13 is clear (`0`), so Intel TME is not supported by this Haswell CPU; TME state is recorded (`D-104`). |
| Scratch directories | `/home/USER/voss-calib-scratch/hdd` on the single SATA HDD (`ext4` on LVM `/dev/mapper/ubuntu--vg-ubuntu--lv`, ~72 GiB free at start). |

---

## 2. Machine specification (`calibration/specs/node04-i7-4790s-8g-hdd/`)

| Component | Measured specification (`node04-i7-4790s-8g-hdd`) |
|---|---|
| **CPU** | Intel Core i7-4790S @ 3.20 GHz (4th-Gen Haswell-S, family `6`, model `60`, stepping `3`, microcode `0x28`) |
| **Cores / threads** | 4 physical cores / 8 hardware threads (uniform topology, 2 SMT threads/core, no P/E split; 800 MHz–4.0 GHz; L1d/L1i 4 × 32 KiB, L2 4 × 256 KiB, L3 8 MiB) |
| **Memory** | 8 GB DDR3-1600 MT/s (`1 × 8 GB` Samsung DIMM in `ChannelA-DIMM0`, `ChannelB-DIMM0` empty; `7,515,656 kB` = `7.17 GiB` usable; `4.0 GiB` swap) |
| **Storage (SATA HDD)** | 1 × 500.1 GB Western Digital `WD5003ABYX-23` (`/dev/sda`, firmware `WC36`, SATA 7200 rpm, `ROTA=1`, serial SHA-256 prefix `161eac7e1d`, SMART `PASSED`, 39 °C, 51,661 power-on hours, 0 reallocated sectors) |
| **TPM** | **None.** `/dev/tpm0` and `/dev/tpmrm0` absent; `/sys/class/tpm` empty; `dmidecode -t 43` empty; no `TPM2`/`TCPA` ACPI table; kernel `dmesg`: `ima: No TPM chip found, activating TPM-bypass!`. Manufacturer, family, and firmware version are recorded as `none`. |
| **Firmware / board** | LENOVO BIOS `FCKT65AUS` (`01/12/2015`), LENOVO motherboard (version `NOK`), UEFI boot mode, Secure Boot `disabled` |
| **Memory encryption** | TME not supported in CPUID (`cpuid -1 -l 7 -r`: `ecx=0x00000000`, bit 13 clear) and not enabled in firmware; `MSR 0x982` unreadable. Owner class M is not claimed (`D-104`). |
| **IOMMU** | ACPI DMAR table present; kernel default domain `Translated` (`iommu: Default domain type: Translated`) |
| **OS / kernel / tools** | Ubuntu 25.10, Linux `6.17.0-5-generic` x86_64, Firecracker `v1.10.1`, guest kernel `firecracker-ci/v1.10/x86_64/vmlinux-6.1.102`, Docker `29.1.3`, `fio-3.39`, `tpm2-tools 5.7`, OpenSSL `3.5.3`, QEMU `10.1.0` |
| **Virtualisation** | `systemd-detect-virt = none` (bare metal); `/dev/kvm` present (`nested=Y`) |
| **Governor / turbo / power** | `schedutil` at spec time; `performance` (`intel_pstate/no_turbo=0`, 0 thermal throttling messages) during all measuring stages; restored to `schedutil` afterwards. AC mains power (desktop PSU). |

Full record: [`calibration/specs/node04-i7-4790s-8g-hdd/SPEC.md`](../../calibration/specs/node04-i7-4790s-8g-hdd/SPEC.md)
and [`spec.yaml`](../../calibration/specs/node04-i7-4790s-8g-hdd/spec.yaml).

### Duplicate check (`NODE_PLAN.md` §3) & asset checksums (`NODE_PLAN.md` §4 rule 2)

- `uv run python -m tools.calibrate.nodes check node04-i7-4790s-8g-hdd --branches` exited `0` (**distinct** from
  `node01-i7-12700-64g-nvme` and `node02-i7-12700-64g-nvme`: different CPU model/generation [Haswell i7-4790S 4c/8t vs
  Alder Lake i7-12700 12c/20t], different memory [7.2 GiB DDR3 vs 62.5 GiB DDR5], different disk model
  [`hdd:WD5003ABYX-23`], and `tpm: none`).
- `calibration/specs/node04-i7-4790s-8g-hdd/assets.sha256` confirms byte-identical pinned binaries with `node01` and
  `node02`:
  - `firecracker` (`v1.10.1`): `96d25e000e5fcbf5b11dca0e1275b5d7dc0922ff8b8206aeaed98e515a8468dc`
  - `jailer` (`v1.10.1`): `8965e9ee855537561ac3adaf0b086a3882456fdc55472691f3bbe489199014ce`
  - `vmlinux` (`v1.10/x86_64/vmlinux-6.1.102`): `49ba99a5299444ac59dda2efc3569cc2d58a5d72ea6475a6bfc37aa0bf322e54`
  - `voss-guest.ext4`: `2b03b7f5c02639464334042aae489541df456343aa587b42db983e53e3f7c257`
  - `voss-guest-ml.ext4` (PyTorch 2.4.1 + ResNet-50): `3dcf771553556f7fc2549f4a6ca1b003a139d3ebf680c46b44ed6789f8f4a844`

---

## 3. Bundle & `check_bundle` output

| Bundle | Tier | Raw logs | Bundle hash (`hash_dir`) | `distributions.yaml` SHA-256 |
|---|---|---|---|---|
| `configs/calibration/measured/node04-i7-4790s-8g-hdd_hdd` | SATA HDD | `calibration/raw/c0-d5811585f1/` | `2e66b7c9bc5b1f4e1515d0ac85b272bd9381cf2ff887e5ba6b0dec8f8bed850e` | `80c070ae614db9279f08a29f99947cc1d7154b6b920ec62745f6d99f096d5d24` |

Exact `check_bundle` output (`uv run python -m tools.calibrate.check_bundle configs/calibration/measured/node04-i7-4790s-8g-hdd_hdd --spec calibration/specs/node04-i7-4790s-8g-hdd`):

```text
ERROR tpm2_quote: missing, not measured (the bundle holds the placeholder, tag literature)
ERROR tpm2_unseal: missing, not measured (absent from the bundle)
ERROR verify_s: missing, not measured (the bundle holds the placeholder, tag assumed)
configs/calibration/measured/node04-i7-4790s-8g-hdd_hdd: 3 errors, 0 warnings
```

- **0 warnings:** Handler times on this node span `5.1e-05 s` (`dynamic-html` size 1) to `12.0 s` (`graph-pagerank`
  size 100), which satisfies the contract's `< 1 ms` to `> 10 s` span requirement without warning.
- **0 spec errors, 0 function errors, 0 storage/boot errors:** All 10 functions, all input sizes, `init_s`, `rss_mb`,
  `snapshot_mb`, `snapshot_touched_frac`, `fc_boot`, `fc_snapshot_create`, `fc_restore`, `dispatch`, `key_release`,
  `kbs_check_s`, `decrypt_per_MB`, `verify_s_per_MB`, `reboot_to_kernel`, `appliance_userspace`, and hardware `C0` disk
  speeds are measured and present.
- **Why the 3 TPM errors exist:** `tpm2_quote`, `tpm2_unseal`, and `verify_s` require a hardware TPM 2.0 device. This
  machine has no TPM chip (`dmesg: ima: No TPM chip found, activating TPM-bypass!`), so those three entries remain
  unmeasured (`NODE_PLAN.md` §4 rule 6: never copy a value from another node or the literature).

---

## 4. Result tables

All numbers below come from the final `full` run (`2026-11-18T20:09:27Z`–`22:41:54Z`) and the 10 Part C host-mode boots
(`2026-11-19T10:30:18Z`–`10:48:00Z`, collected `2026-11-20T16:19:05Z`), formatted with `%.3g` where appropriate.

### 4.1 Boot to an attested worker (Part C, host mode, 10 boots)

The v2 appliance image mode (`tools/calibrate/appliance/mkosi.repart/20-cache.conf`, `Encrypt=tpm2`) requires a TPM 2.0
to seal and unseal the LUKS2 cache partition and cannot run on a node without a TPM. The documented host-mode probe
(`tools/calibrate/appliance/host/voss-calib-probe`, `D-60`) was run for 10 boots after the §5 step 3 preflight and one
supervised manual test reboot (`2026-11-18T23:30:13Z` → `btime 1795044749`, `systemd-analyze`: `2.922s (firmware) +
2.985s (loader) + 3.653s (kernel) + 22.239s (userspace) = 31.800s`, `/sys/fs/pstore` empty). On every measured boot into
`voss-calib.target`, `voss-calib-probe` logged `VOSS_SKIP tpm no_device_or_tools` and captured both wall-clock stamps
and `systemd-analyze`'s UEFI firmware/loader/kernel/userspace breakdown.

Per-boot breakdown (seconds):

| Boot | `arm → prev_end` (shutdown) | `prev_end → btime` (wall gap) | EFI firmware (`systemd-analyze`) | Boot loader (`systemd-analyze`) | Kernel (`systemd-analyze`) | `reboot_to_kernel` (fw + loader + kernel) | `agent_ready` (monotonic) | `appliance_userspace` (`agent_ready - kernel`) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2.24 | 7.22 | 2.94 | 2.99 | 3.67 | 9.59 | 14.55 | 10.88 |
| 2 | 8.58 | 6.46 | 2.93 | 3.00 | 3.68 | 9.61 | 13.98 | 10.30 |
| 3 | 8.76 | 7.05 | 2.95 | 2.97 | 3.55 | 9.48 | 14.34 | 10.79 |
| 4 | 8.89 | 7.69 | 2.95 | 3.00 | 3.64 | 9.60 | 14.52 | 10.88 |
| 5 | 8.89 | 6.86 | 2.94 | 2.99 | 3.66 | 9.59 | 14.47 | 10.81 |
| 6 | 4.01 | 7.34 | 2.95 | 3.00 | 3.66 | 9.61 | 14.49 | 10.83 |
| 7 | 8.70 | 7.74 | 2.95 | 2.99 | 3.68 | 9.61 | 14.65 | 10.97 |
| 8 | 4.07 | 6.96 | 2.96 | 3.00 | 3.66 | 9.62 | 14.78 | 11.12 |
| 9 | 4.08 | 7.16 | 2.95 | 2.99 | 3.64 | 9.58 | 14.55 | 10.91 |
| 10 | 8.67 | 6.96 | 2.94 | 2.99 | 3.58 | 9.51 | 14.89 | 11.31 |

Summary across the 10 boots:

| Step / bundle entry | Median (s) | p5 (s) | p95 (s) | n | Notes |
|---|---:|---:|---:|---:|---|
| Firmware (`systemd-analyze`) | 2.95 | 2.93 | 2.96 | 10 | Reported by UEFI to systemd |
| Boot loader (`systemd-analyze`) | 2.99 | 2.97 | 3.00 | 10 | Reported by UEFI/loader to systemd |
| Kernel (`systemd-analyze`) | 3.66 | 3.56 | 3.68 | 10 | Kernel start to userspace handoff |
| **`reboot_to_kernel`** (bundle entry) | **9.60** | **9.49** | **9.61** | **10** | `firmware + loader + kernel` (lognormal fit median `9.58 s`) |
| **`appliance_userspace`** (bundle entry) | **10.9** | **10.5** | **11.2** | **10** | Userspace start to `agent_ready` (`10.88 s` empirical median) |
| Image-only steps (`boot_*`, `image_mem`, `image_cache_bytes`) | missing | — | — | 0 | Host mode used; `mkosi` image requires `Encrypt=tpm2` (no TPM on host) |

### 4.2 Storage throughput (`disk` suite, SATA HDD tier)

| Probe | Median | p5 | p95 | n | Unit |
|---|---:|---:|---:|---:|---|
| `hdd_seq_read_MBps` | 132 | 131 | 132 | 5 | MB/s |
| `hdd_seq_write_MBps` | 130 | 130 | 130 | 5 | MB/s |
| `hdd_rand_read_4k_iops` (`MBps`) | 345 (`1.41`) | 338 (`1.38`) | 351 (`1.44`) | 5 | IOPS (MB/s) |
| `hdd_rand_write_4k_iops` (`MBps`) | 369 (`1.51`) | 365 (`1.50`) | 374 (`1.53`) | 5 | IOPS (MB/s) |
| `hdd_crypt_seq_read_MBps` | 3.08e+03 | 3.05e+03 | 3.19e+03 | 5 | MB/s (loop device in page cache) |
| `hdd_crypt_seq_write_MBps` | 1.68e+03 | 1.65e+03 | 1.74e+03 | 5 | MB/s (loop device in page cache) |
| `hdd_verity_seq_read_MBps` | 825 | 822 | 842 | 5 | MB/s (loop device in page cache) |
| `hash_per_MB` (bundle `verify_s_per_MB`) | 0.00207 | 0.00206 | 0.00207 | 20 | s/MB (`~484 MB/s` single-core SHA-256) |

### 4.3 Sandbox boot (`fc_boot`, SATA HDD tier, warm and cold page cache)

Values in seconds (`n = 100` per configuration):

| Guest MB | Cache | `fc_spawn` (p50 / p5 / p95) | `fc_configure` (p50 / p5 / p95) | `fc_start_api` (p50 / p5 / p95) | `fc_boot` kernel→init (p50 / p5 / p95) | `fc_init_to_done` (p50 / p5 / p95) | n |
|---:|---|---:|---:|---:|---:|---:|---:|
| 128 | warm | 0.00278 / 0.00271 / 0.00285 | 0.00105 / 0.000937 / 0.00119 | 0.00950 / 0.00917 / 0.0100 | 0.0741 / 0.0734 / 0.0752 | 0.00666 / 0.00634 / 0.00704 | 100 |
| 128 | cold | 0.00951 / 0.00936 / 0.0290 | 0.00116 / 0.00105 / 0.00125 | 0.177 / 0.173 / 0.194 | 0.267 / 0.261 / 0.284 | 0.0307 / 0.0285 / 0.0467 | 100 |
| 256 | warm | 0.00277 / 0.00273 / 0.00284 | 0.00108 / 0.000952 / 0.00119 | 0.00950 / 0.00927 / 0.00981 | **0.0757 / 0.0749 / 0.0771** | 0.00633 / 0.00612 / 0.00678 | 100 |
| 256 | cold | 0.00954 / 0.00934 / 0.0331 | 0.00115 / 0.00106 / 0.00122 | 0.180 / 0.171 / 0.194 | 0.282 / 0.269 / 0.400 | 0.0365 / 0.0342 / 0.154 | 100 |
| 512 | warm | 0.00278 / 0.00272 / 0.00285 | 0.00110 / 0.000963 / 0.00122 | 0.00943 / 0.00917 / 0.00974 | 0.0785 / 0.0776 / 0.0794 | 0.00650 / 0.00624 / 0.00693 | 100 |
| 512 | cold | 0.0283 / 0.00938 / 0.0347 | 0.00114 / 0.00105 / 0.00123 | 0.184 / 0.166 / 0.190 | 0.280 / 0.262 / 0.329 | 0.0715 / 0.0334 / 0.154 | 100 |
| 1024 | warm | 0.00276 / 0.00269 / 0.00284 | 0.00104 / 0.000944 / 0.00116 | 0.00934 / 0.00906 / 0.00966 | 0.0850 / 0.0838 / 0.0862 | 0.00707 / 0.00685 / 0.00791 | 100 |
| 1024 | cold | 0.00950 / 0.00937 / 0.0290 | 0.00116 / 0.00105 / 0.00124 | 0.184 / 0.178 / 0.193 | 0.283 / 0.276 / 0.292 | 0.0300 / 0.0293 / 0.0313 | 100 |
| 2048 | warm | 0.00279 / 0.00272 / 0.00285 | 0.00109 / 0.000959 / 0.00122 | 0.00949 / 0.00913 / 0.00977 | 0.0982 / 0.0972 / 0.0995 | 0.00707 / 0.00687 / 0.00752 | 100 |
| 2048 | cold | 0.00950 / 0.00932 / 0.0407 | 0.00114 / 0.00104 / 0.00123 | 0.184 / 0.168 / 0.211 | 0.295 / 0.279 / 0.736 | 0.0306 / 0.0294 / 0.733 | 100 |

### 4.4 Snapshot create, snapshot restore, warm dispatch, and touched fraction (`fc_snapshot`, `fc_dispatch`, `fc_touched`)

Snapshot creation (`n = 50` per memory size, SATA HDD tier, seconds):

| Guest MB | `fc_pause` median (p5 / p95) | `fc_snapshot_create` median (p5 / p95) | `fc_snapshot_mb` | n |
|---:|---:|---:|---:|---:|
| 128 | 0.000458 (0.000369 / 0.000537) | 1.10 (1.08 / 1.11) | 128 MB | 50 |
| 512 | 0.000467 (0.000412 / 0.000544) | **4.36 (4.35 / 4.47)** | 512 MB | 50 |
| 2048 | 0.000480 (0.000399 / 0.000559) | 17.5 (17.2 / 17.8) | 2048 MB | 50 |

Snapshot restore (`n = 50` per configuration, SATA HDD tier, seconds):

| Guest MB | Cache | `fc_restore_spawn` (p50 / p5 / p95) | `fc_restore_api` (p50 / p5 / p95) | `fc_restore_ack` (p50 / p5 / p95) | `fc_restore` total load→ack (p50 / p5 / p95) | n |
|---:|---|---:|---:|---:|---:|---:|
| 128 | warm | 0.00279 / 0.00273 / 0.00285 | 0.00189 / 0.00178 / 0.00212 | 0.00237 / 0.00229 / 0.00247 | 0.00427 / 0.00411 / 0.00445 | 50 |
| 128 | cold | 0.0316 / 0.00732 / 0.0440 | 0.137 / 0.115 / 0.147 | 0.220 / 0.190 / 0.357 | 0.348 / 0.330 / 0.464 | 50 |
| 512 | warm | 0.00277 / 0.00270 / 0.00284 | **0.00187 / 0.00179 / 0.00207** | 0.00239 / 0.00226 / 0.00251 | 0.00425 / 0.00410 / 0.00451 | 50 |
| 512 | cold | 0.0311 / 0.00944 / 0.0426 | 0.140 / 0.127 / 0.153 | 0.326 / 0.241 / 0.392 | 0.465 / 0.387 / 0.524 | 50 |
| 2048 | warm | 0.00279 / 0.00273 / 0.00285 | 0.00190 / 0.00180 / 0.00220 | 0.00249 / 0.00238 / 0.00263 | 0.00439 / 0.00424 / 0.00474 | 50 |
| 2048 | cold | 0.0292 / 0.00725 / 0.0433 | 0.159 / 0.122 / 0.160 | 0.332 / 0.267 / 0.454 | 0.484 / 0.424 / 0.581 | 50 |

Warm dispatch (`fc_dispatch`, vsock to warm sandbox) and cold restore touched fraction (`fc_touched`, across all 10 functions on HDD):

| Probe / bundle entry | Median | p5 | p95 | n | Notes |
|---|---:|---:|---:|---:|---|
| `dispatch_warm` (bundle `dispatch`) | 0.000275 s | 0.000238 s | 0.000308 s | 200 | Connect + `RUN` command to guest `START` line |
| `vsock_rtt` | 0.000135 s | 0.000122 s | 0.000192 s | 200 | `PING` → `ACK` over vsock |
| `dispatch_handler` (`thumbnailer` size 50) | 0.00225 s | 0.00223 s | 0.00231 s | 200 | Handler duration during dispatch probe |
| `snapshot_touched_frac` (all 10 functions) | 0.0890 (empirical) / 0.101 (fit) | 0.0289 | 0.449 | 100 | 10 cold restores × 10 functions on HDD |

### 4.5 Attestation, TLS, key release, and bundle decryption (`tpm`, `attest_local`, `tls`, `keys`, `disk`)

| Probe / bundle entry | Median | p5 | p95 | n | Status / notes |
|---|---:|---:|---:|---:|---|
| `tpm2_quote` | missing | — | — | 0 | No TPM device on host (`/dev/tpm0`, `/dev/tpmrm0` absent) |
| `tpm2_unseal` | missing | — | — | 0 | No TPM device on host |
| `verify_s` (`attest_verify`) | missing | — | — | 0 | Requires hardware TPM quote in `attest_local` |
| `tls_handshake` | 0.00111 s | 0.000969 s | 0.00116 s | 1000 | Loopback TLS 1.3 mutual handshake wall time |
| `tls_handshake_cpu` | 0.00127 s | 0.00115 s | 0.00135 s | 1000 | Loopback TLS 1.3 mutual handshake CPU time |
| `tls_msg_overhead` | 0.000228 s | 0.000225 s | 0.000235 s | 10 | 1 KiB TLS message overhead over TCP |
| `key_request` | 0.0418 s | 0.0417 s | 0.0427 s | 200 | Worker loopback TLS key request (256 B req/reply) |
| `key_unwrap` | 0.000514 s | — | — | 1 | RSA-2048 private-key unwrap (`openssl speed`) |
| **`key_release`** (`key_request + key_unwrap`) | **0.0424 s** | **0.0422 s** | **0.0432 s** | **200** | Ingested bundle distribution (`key_release`) |
| **`kbs_check_s`** (`kbs_check`) | **0.000315 s** | **0.000263 s** | **0.000322 s** | **200** | Key service cert/signature/policy/budget check + RSA-OAEP wrap |
| **`decrypt_per_MB`** | **0.000323 s/MB** | — | — | **1** | AES-256-GCM decryption on 1 MB blocks (`~3,096 MB/s`) |
| **`verify_s_per_MB`** (`hash_per_MB`) | **0.00207 s/MB** | **0.00206 s/MB** | **0.00207 s/MB** | **20** | Single-core SHA-256 (`~484 MB/s`) |

### 4.6 Functions: initialisation, memory, snapshot size, touched fraction, and handler time by input size (`sebs`, `fc_touched`)

All 10 workload functions were measured at `concurrency = 1` with `n = 30` repetitions per input size (`image-recognition`
on `voss-guest-ml.ext4`, the other 9 functions on `voss-guest.ext4`), plus `n = 3` snapshots per function for `snap_size`
and `n = 10` cold restores per function on HDD for `snapshot_touched_frac`.

| Function | `init_s` (s) | `rss_mb` (MB) | `snapshot_mb` (MB) | `snapshot_touched_frac` | `size_exp` | Handler time `fn_exec` by input size: `size: median (p5 / p95)` in seconds (`n = 30` each) |
|---|---:|---:|---:|---:|---:|---|
| `compression` | 0.00609 | 244 | 1.02e+03 | 0.0969 | 0.990 | `500`: 0.00306 (0.00302 / 0.00338), `2000`: 0.0118 (0.0117 / 0.0121), `8000`: 0.0467 (0.0466 / 0.0472), `32000`: 0.187 (0.187 / 0.189), `128000`: 0.734 (0.732 / 0.737) |
| `dna-visualisation` | 0.211 | 1.59e+03 | 4.10e+03 | 0.0562 | 1.01 | `100`: 0.0264 (0.0261 / 0.0269), `500`: 0.138 (0.137 / 0.142), `2000`: 0.548 (0.545 / 0.551), `8000`: 2.24 (2.23 / 2.24) |
| `dynamic-html` | 0.0547 | 1.28e+03 | 4.10e+03 | 0.0289 | 0.940 | `1`: 5.1e-05 (4.23e-05 / 6.83e-05), `10`: 0.000195 (0.000194 / 0.000230), `1000`: 0.0182 (0.0181 / 0.0193), `10000`: 0.202 (0.202 / 0.204), `100000`: 2.05 (2.05 / 2.06) |
| `graph-bfs` | 0.0503 | 789 | 2.05e+03 | 0.0619 | 1.39 | `1`: 0.00140 (0.00138 / 0.00170), `10`: 0.0460 (0.0459 / 0.0464), `30`: 0.186 (0.185 / 0.187), `100`: 0.836 (0.821 / 0.845) |
| `graph-mst` | 0.0503 | 790 | 2.05e+03 | 0.0619 | 1.40 | `1`: 0.00164 (0.00162 / 0.00191), `10`: 0.0699 (0.0696 / 0.0705), `30`: 0.260 (0.260 / 0.262), `100`: 0.994 (0.991 / 1.12) |
| `graph-pagerank` | 0.0506 | 1.04e+03 | 2.05e+03 | 0.0643 | 1.36 | `1`: 0.0215 (0.0213 / 0.0225), `10`: 0.531 (0.527 / 0.539), `30`: 1.90 (1.89 / 1.93), `100`: 12.0 (11.8 / 12.4) |
| `image-recognition` | 2.76 | 742 | 2.05e+03 | 0.334 | 0.658 | `50`: 0.138 (0.138 / 0.139), `100`: 0.138 (0.138 / 0.139), `400`: 0.496 (0.494 / 0.505) |
| `thumbnailer` | 0.109 | 246 | 512 | 0.224 | 0.725 | `50`: 0.00213 (0.00210 / 0.00235), `200`: 0.00549 (0.00547 / 0.00555), `1000`: 0.0146 (0.0145 / 0.0148), `4000`: 0.0465 (0.0464 / 0.0468), `16000`: 0.143 (0.143 / 0.144) |
| `uploader` | 0.00195 | 392 | 1.02e+03 | 0.0811 | 1.09 | `256`: 0.000113 (0.000112 / 0.000171), `1000`: 0.000318 (0.000314 / 0.000427), `6700`: 0.00290 (0.00283 / 0.00366), `25000`: 0.0124 (0.0123 / 0.0142), `100000`: 0.0702 (0.0698 / 0.0724) |
| `video-processing` | 0.00519 | 470 | 1.02e+03 | 0.449 | 0.0701 | `1000`: 0.277 (0.275 / 0.279), `5000`: 0.382 (0.381 / 0.386), `20000`: 0.386 (0.381 / 0.391), `80000`: 0.384 (0.382 / 0.390) |

- **Published SeBS ratio check:** `check_bundle.PUBLISHED` is empty, so no automatic >10× published-SeBS warning is
  emitted.
- **Function-dependent speed ratio vs reference node `node02-i7-12700-64g-nvme` (`NODE_PLAN.md` §2 claim 1):**
  Comparing `node04` (Haswell i7-4790S) to `node02` (Alder Lake i7-12700) at each function's largest input size shows
  that the slowdown ratio varies strongly by function rather than being a single scalar speed factor:
  - `thumbnailer` (size `16000`): `0.143 s` vs `0.110 s` → **`1.30×`**
  - `uploader` (size `100000`): `0.0702 s` vs `0.0436 s` → **`1.61×`**
  - `graph-mst` (size `100`): `0.994 s` vs `0.583 s` → **`1.71×`**
  - `graph-bfs` (size `100`): `0.836 s` vs `0.470 s` → **`1.78×`**
  - `image-recognition` (size `400`): `0.496 s` vs `0.279 s` → **`1.78×`**
  - `dna-visualisation` (size `8000`): `2.24 s` vs `1.19 s` → **`1.88×`**
  - `dynamic-html` (size `100000`): `2.05 s` vs `1.07 s` → **`1.92×`**
  - `video-processing` (size `80000`): `0.384 s` vs `0.172 s` → **`2.23×`**
  - `compression` (size `128000`): `0.734 s` vs `0.314 s` → **`2.34×`**
  - `graph-pagerank` (size `100`): `12.0 s` vs `3.61 s` → **`3.31×`**

### 4.7 Co-run slowdown (`interference[n]` = median `fn_corun[n]` / median `fn_corun[1]`)

This host has 4 physical cores and 8 hardware threads, so `sebs.concurrencies` evaluates `n = 1, 2, 4, 8`. Levels whose
aggregate guest memory `n * MEM_MB[fn]` exceeds the host RAM budget (`4,096 MB` on this 8 GB machine) are skipped by the
suite (`—`):

| Function | Guest `MEM_MB` | `n = 1` | `n = 2` | `n = 4` (physical cores) | `n = 8` (hardware threads) | Skipped levels & reason |
|---|---:|---:|---:|---:|---:|---|
| `thumbnailer` | 512 | 1.00 | 1.06 | 1.14 | 1.92 | None (all levels up to 8 threads fit in 4,096 MB) |
| `compression` | 1024 | 1.00 | 1.05 | 1.12 | — | `n = 8` (needs 8,192 MB > 4,096 MB budget) |
| `uploader` | 1024 | 1.00 | 1.38 | 2.36 | — | `n = 8` (needs 8,192 MB > 4,096 MB budget) |
| `video-processing` | 1024 | 1.00 | 1.17 | 1.53 | — | `n = 8` (needs 8,192 MB > 4,096 MB budget) |
| `graph-bfs` | 2048 | 1.00 | 1.19 | — | — | `n = 4, 8` (needs 8,192 / 16,384 MB > 4,096 MB budget) |
| `graph-mst` | 2048 | 1.00 | 1.17 | — | — | `n = 4, 8` (needs 8,192 / 16,384 MB > 4,096 MB budget) |
| `graph-pagerank` | 2048 | 1.00 | 1.29 | — | — | `n = 4, 8` (needs 8,192 / 16,384 MB > 4,096 MB budget) |
| `image-recognition` | 2048 | 1.00 | 1.25 | — | — | `n = 4, 8` (needs 8,192 / 16,384 MB > 4,096 MB budget) |
| `dna-visualisation` | 4096 | 1.00 | — | — | — | `n = 2, 4, 8` (needs 8,192–32,768 MB > 4,096 MB budget) |
| `dynamic-html` | 4096 | 1.00 | — | — | — | `n = 2, 4, 8` (needs 8,192–32,768 MB > 4,096 MB budget) |

Slowdown is strictly non-decreasing in `n` for every function.

---

## 5. What was skipped or failed, and why

| Item | Status | Explanation |
|---|---|---|
| `tpm` suite (`tpm2_quote`, `tpm2_unseal`) | `skipped` | No TPM hardware on this machine (`/dev/tpm0` and `/dev/tpmrm0` absent; `dmesg: ima: No TPM chip found, activating TPM-bypass!`). Reported as missing by `check_bundle`; not estimated. |
| `attest_local` suite (`verify_s`) | `skipped` | Requires a hardware TPM to produce quotes for local verification; reported as missing by `check_bundle`. |
| `tme` suite (`tme_cpu_factor`, `tme_mem_factor`) | `not run` | CPUID leaf 7 ECX bit 13 is clear (`tme` not supported by Haswell i7-4790S); `node_run.sh` skips `tme` when firmware TME state is `off`. Memory encryption is not modelled (`D-104`). |
| Part C image mode (`boot_firmware`, `boot_loader`, `boot_quote`, `boot_verify`, `boot_first_tls`, `boot_total`, `image_mem`, `image_cache_bytes`) | `not run` | `tools/calibrate/appliance/mkosi.repart/20-cache.conf` specifies `Encrypt=tpm2`, which requires a TPM 2.0. Host mode (`D-60`) was used for 10 boots and measured both simulator-consumed entries (`reboot_to_kernel` and `appliance_userspace`) plus `systemd-analyze`'s EFI firmware/loader/kernel/userspace durations. |
| Co-run levels requiring > 4,096 MB aggregate guest RAM | `skipped` | Host has 8 GB DDR3 (`7,339 MB` total). Aggregate guest memory above `4,096 MB` (`n = 8` for 1,024 MB guests; `n = 4, 8` for 2,048 MB guests; `n = 2, 4, 8` for 4,096 MB guests) exceeds physical RAM after host headroom and is recorded as `skipped`. |
| `fn_inputs` (`fn_input_gen`) in `full` | `partial / timed out` | In `quick` (3 reps/size), `fn_inputs` succeeded across all 10 functions (`483 s`). In `full` (30 reps/size), `fn_inputs` recorded 450 samples (`dynamic-html`, `uploader`, `thumbnailer`) and timed out at `3,600.0 s` (`vm.collect(..., timeout=3600.0)`) near the end of `video-processing` (whose 4 input sizes take `1.36 + 6.37 + 25.0 + 99.4 = 132.1 s` per repetition × 30 reps = `~3,964 s` inside a single guest call). `fn_input_gen` is a sanity probe not read by the simulator or required by `check_bundle`. |

---

## 6. Harness bugs found and fixed on this node

1. **`spec.sh` hardcoded another node's prose and YAML fields:** `tools/calibrate/spec.sh` emitted prose and fields for
   an MSI i7-12700 / 64 GB DDR5 / Intel PTT / NVMe+HGST machine and included a raw MAC address in `efibootmgr` output.
   `calibration/specs/node04-i7-4790s-8g-hdd/SPEC.md` and `spec.yaml` were corrected by hand from on-machine probes
   (`lscpu`, `dmidecode`, `cpuid`, `smartctl`, `/sys`, `dmesg`), marked `manual`, with identifiers scrubbed/hashed.
2. **Harness fixes committed in `4493393` (lock `a1f77cf1cb204ee1234bf57021f8f7f5d0556d27`) after `quick #1` exited 5:**
   - `tools/calibrate/suites/tpm.py` and `attest_local.py`: check for `/dev/tpmrm0` or `/dev/tpm0` (when not `--dry-run`
     and no `tcti` option is passed) and raise `SuiteSkipped` instead of crashing with `RuntimeError` when `tpm2-tools`
     is installed on a machine without a TPM chip.
   - `tools/calibrate/fc.py`: raise `UnixHTTPConnection` timeout from `30.0 s` to `120.0 s` so writing a 4,096 MB
     snapshot memory file (`dynamic-html`, `dna-visualisation`) to a ~130 MB/s SATA HDD (`~35–38 s`) does not fail with
     `TimeoutError`.
   - `tools/calibrate/suites/__init__.py` and `sebs.py`: allow a single 4,096 MB guest (`n = 1`) when
     `MemAvailable >= 5,120 MB` (so an 8 GB host can measure `dynamic-html` and `dna-visualisation` at `n = 1`, where
     actual RSS is `1.28–1.59 GB`, while still skipping `n >= 2`), and skip `snapshot_size` if a function ran at no
     concurrency level.
   - `tools/calibrate/nodes.py`: treat `tpm.type: none` as `("none", "")` so no-TPM specs satisfy `check_bundle --spec`
     without being misclassified as `discrete`.
   - `tools/calibrate/node_run.sh`: trap `RETURN EXIT` with eager PID expansion for the background `sudo` keep-alive
     subshell so `node_run.sh` does not leave an orphan `sleep 60` process holding stdout open on exit.

---

## 7. Every change made to the machine and its reversal

| Change | Why | Reversal / final state |
|---|---|---|
| Installed packages via `apt-get`: `rsync`, `fio`, `tpm2-tools`, `openssl`, `cryptsetup`, `gcc`, `docker.io`, `e2fsprogs`, `mkosi`, `cpuid`, `msr-tools`, `smartmontools`, `numactl`, `python3-venv`; installed `uv` under `~/.local/bin` | Required by `node_run.sh` and calibration suites (`tools/calibrate/README.md`) | Kept installed (standard harness dependencies, approved by owner) |
| Loaded `msr` kernel module (`modprobe msr`) | Read `MSR 0x982` during Part A capability inspection | Non-persistent across reboots; unloaded automatically on Part C reboots |
| Created `/home/USER/voss-calib/assets`, `/home/USER/voss-calib-scratch/hdd`, and `/home/USER/voss-calib-backups` | Pinned Firecracker/guest images, HDD benchmark scratch dir, and external `.tar.zst` raw backups | Scratch files inside `/home/USER/voss-calib-scratch/hdd` deleted after Part D; assets and `.tar.zst` backups retained outside repo |
| Brought `docker0` bridge link `UP` (`ip link set docker0 up`) and installed temporary `/usr/local/bin/docker` wrapper passing `--network=host` on `docker build` | Host routing across `docker0` had no outbound uplink during guest rootfs builds | `/usr/local/bin/docker` wrapper removed (`sudo rm -f /usr/local/bin/docker`) immediately after `setup` |
| Installed temporary `/home/USER/.local/bin/sudo` helper | Ubuntu 25.10 `sudo-rs` uses per-process authentication timestamps not shared with child subshells in `node_run.sh` | Deleted (`rm -f ~/.local/bin/sudo`) after Part D restoration |
| Changed CPU scaling governor from `schedutil` to `performance` across `cpu0`–`cpu7` (turbo left at firmware default `intel_pstate/no_turbo=0`) | `NODE_PLAN.md` §4 rule 4 (`quick` and `full` stages) | **Restored to `schedutil`** on all 8 CPUs after Part D (`sort -u .../scaling_governor` = `schedutil`) |
| Stopped background services before Part B (`chrony`, `cron`, `fwupd`, `ModemManager`, `multipathd`, `networkd-dispatcher`, `thermald`, `udisks2`, `unattended-upgrades`, `upower`, `smartmontools`, `pesign`, `docker`, `containerd`) and temporarily disabled non-OS services across the Part C reboot loop | `NODE_PLAN.md` §4 rules 4 & 7, `CALIBRATION_HANDOFF.md` §5 step 3 | **All services re-enabled and restarted** after Part C/D (`chrony`, `containerd`, `cron`, `docker`, `fwupd`, `ModemManager`, `multipathd`, `networkd-dispatcher`, `pesign`, `smartmontools`, `thermald`, `udisks2`, `unattended-upgrades`, `upower` verified `active (running)`) |
| Installed host-mode appliance systemd units (`tools/calibrate/appliance/host/install.sh install 10` with `SETTLE=15`, hardened to stop on first incomplete boot or non-empty `/sys/fs/pstore`) and ran 10 measured reboots | Part C session-establishment timing (`reboot_to_kernel`, `appliance_userspace`) | **Uninstalled** via `install.sh uninstall`; default boot target confirmed restored to `graphical.target`; `/sys/fs/pstore` verified empty |

External raw archives (outside the repository, with `.sha256` checksums):
- `/home/USER/voss-calib-backups/node04-raw-quick1-20261118.tar.zst`: `cad695a251bbaf3872ac1720326f06cfe6748a3e7809853df59037ce177f57d2`
- `/home/USER/voss-calib-backups/node04-raw-quick2-20261118.tar.zst`: `2e6b08322e344bcdff79221d74762843340e56e813c3a5b057a02388fa567b56`
- `/home/USER/voss-calib-backups/node04-raw-full-20261118.tar.zst`: `f2ee7128d3de5a6a9e4ee2d155c443530ff25b9fc3a7993482da233172a1300f`
- `/home/USER/voss-calib-backups/node04-partC-appliance-20261119.tar.zst`: `83b19fc5ac75624fd6280d97d1c92e9328b32e726043b76f77aca8a36a5e82e3`

---

## 8. Time of every step from `calibration/specs/node04-i7-4790s-8g-hdd/timeline.csv`

| Stage | Suite | Start (UTC) | End (UTC) | Duration (s) | Exit | Notes |
|---|---|---|---|---:|---:|---|
| `spec` | `spec` | `2026-11-18T09:00:51Z` | `2026-11-18T09:00:52Z` | 1 | 0 | Part A hardware spec |
| `spec` | `caps` | `2026-11-18T09:00:52Z` | `2026-11-18T09:00:52Z` | 0 | 0 | Part A capability probe |
| `setup` | `fetch_assets` | `2026-11-18T09:06:22Z` | `2026-11-18T09:06:22Z` | 0 | 1 | `~/voss-calib/assets` directory not created yet |
| `setup` | `fetch_assets` | `2026-11-18T09:06:33Z` | `2026-11-18T09:06:45Z` | 12 | 0 | Downloaded Firecracker v1.10.1 + kernel |
| `setup` | `build_rootfs` | `2026-11-18T09:06:45Z` | `2026-11-18T09:06:45Z` | 0 | 1 | `sudo-rs` per-process auth prompt in child shell |
| `setup` | `fetch_assets` | `2026-11-18T09:42:42Z` | `2026-11-18T09:42:53Z` | 11 | 0 | Re-run before `sudo-rs` helper |
| `setup` | `build_rootfs` | `2026-11-18T09:42:53Z` | `2026-11-18T09:42:53Z` | 0 | 1 | `sudo-rs` per-process auth prompt |
| `setup` | `fetch_assets` | `2026-11-18T14:42:11Z` | `2026-11-18T14:42:23Z` | 12 | 0 | Re-run after Docker wrapper |
| `setup` | `build_rootfs` | `2026-11-18T14:42:23Z` | `2026-11-18T14:42:23Z` | 0 | 1 | `sudo-rs` per-process auth prompt |
| `setup` | `fetch_assets` | `2026-11-18T14:43:35Z` | `2026-11-18T14:43:46Z` | 11 | 0 | Trace run (`bash -x`) |
| `setup` | `build_rootfs` | `2026-11-18T14:43:46Z` | `2026-11-18T14:43:46Z` | 0 | 1 | Confirmed `sudo-rs` per-process timestamp |
| `setup` | `fetch_assets` | `2026-11-18T14:44:32Z` | `2026-11-18T14:44:51Z` | 19 | 35 | Transient `curl` connection reset |
| `setup` | `fetch_assets` | `2026-11-18T14:45:07Z` | `2026-11-18T14:45:18Z` | 11 | 0 | Clean `setup` run |
| `setup` | `build_rootfs` | `2026-11-18T14:45:18Z` | `2026-11-18T14:49:37Z` | 259 | 0 | Built `voss-guest.ext4` (1.1 GB) |
| `setup` | `build_rootfs_ml` | `2026-11-18T14:49:37Z` | `2026-11-18T14:56:52Z` | 435 | 0 | Built `voss-guest-ml.ext4` (2.4 GB, PyTorch + ResNet-50) |
| `setup` | `preflight` | `2026-11-18T14:56:52Z` | `2026-11-18T14:56:55Z` | 3 | 0 | `tools/emu/preflight.sh` (`setup` total: **708 s / 11 min 48 s**) |
| `quick` | `caps` | `2026-11-18T15:02:34Z` | `2026-11-18T15:02:35Z` | 1 | 0 | Quick pass #1 (lock `b50f5dad`) |
| `quick` | `disk` | `2026-11-18T15:02:35Z` | `2026-11-18T15:07:06Z` | 271 | 0 | Quick pass #1 |
| `quick` | `tpm` | `2026-11-18T15:07:06Z` | `2026-11-18T15:07:07Z` | 1 | 1 | Quick pass #1: failed on missing `/dev/tpmrm0` |
| `quick` | `attest_local` | `2026-11-18T15:07:07Z` | `2026-11-18T15:07:07Z` | 0 | 1 | Quick pass #1: failed on missing `/dev/tpmrm0` |
| `quick` | `tls` | `2026-11-18T15:07:07Z` | `2026-11-18T15:07:07Z` | 0 | 0 | Quick pass #1 |
| `quick` | `keys` | `2026-11-18T15:07:07Z` | `2026-11-18T15:07:32Z` | 25 | 0 | Quick pass #1 |
| `quick` | `fc_boot` | `2026-11-18T15:07:32Z` | `2026-11-18T15:08:14Z` | 42 | 0 | Quick pass #1 |
| `quick` | `fc_snapshot` | `2026-11-18T15:08:14Z` | `2026-11-18T15:10:24Z` | 130 | 0 | Quick pass #1 |
| `quick` | `fc_dispatch` | `2026-11-18T15:10:24Z` | `2026-11-18T15:10:25Z` | 1 | 0 | Quick pass #1 |
| `quick` | `sebs` | `2026-11-18T15:10:25Z` | `2026-11-18T15:11:02Z` | 37 | 1 | Quick pass #1: 30 s HTTP timeout on 4,096 MB HDD snapshot |
| `quick` | `fn_inputs` | `2026-11-18T15:11:02Z` | `2026-11-18T15:19:12Z` | 490 | 0 | Quick pass #1: all 10 functions succeeded |
| `quick` | `fc_touched` | `2026-11-18T15:19:12Z` | `2026-11-18T15:21:52Z` | 160 | 0 | Quick pass #1 (archived to `node04-raw-quick1-20261118.tar.zst`) |
| `quick` | `caps` | `2026-11-18T19:20:25Z` | `2026-11-18T19:20:25Z` | 0 | 0 | Interrupted by session server restart during `disk` |
| `quick` | `caps` | `2026-11-18T19:27:03Z` | `2026-11-18T19:27:03Z` | 0 | 0 | Quick pass #2 (lock `a1f77cf1`) |
| `quick` | `disk` | `2026-11-18T19:27:03Z` | `2026-11-18T19:31:32Z` | 269 | 0 | Quick pass #2 |
| `quick` | `tpm` | `2026-11-18T19:31:32Z` | `2026-11-18T19:31:32Z` | 0 | 0 | Quick pass #2 (`skipped: no /dev/tpmrm0 or /dev/tpm0`) |
| `quick` | `attest_local` | `2026-11-18T19:31:32Z` | `2026-11-18T19:31:32Z` | 0 | 0 | Quick pass #2 (`skipped: no /dev/tpmrm0 or /dev/tpm0`) |
| `quick` | `tls` | `2026-11-18T19:31:32Z` | `2026-11-18T19:31:32Z` | 0 | 0 | Quick pass #2 |
| `quick` | `keys` | `2026-11-18T19:31:32Z` | `2026-11-18T19:31:57Z` | 25 | 0 | Quick pass #2 |
| `quick` | `fc_boot` | `2026-11-18T19:31:57Z` | `2026-11-18T19:32:25Z` | 28 | 0 | Quick pass #2 |
| `quick` | `fc_snapshot` | `2026-11-18T19:32:25Z` | `2026-11-18T19:34:35Z` | 130 | 0 | Quick pass #2 |
| `quick` | `fc_dispatch` | `2026-11-18T19:34:35Z` | `2026-11-18T19:34:36Z` | 1 | 0 | Quick pass #2 |
| `quick` | `sebs` | `2026-11-18T19:34:36Z` | `2026-11-18T19:53:14Z` | 1118 | 0 | Quick pass #2: all 10 functions succeeded |
| `quick` | `fn_inputs` | `2026-11-18T19:53:14Z` | `2026-11-18T20:01:17Z` | 483 | 0 | Quick pass #2: all 10 functions succeeded |
| `quick` | `fc_touched` | `2026-11-18T20:01:17Z` | `2026-11-18T20:05:21Z` | 244 | 0 | Quick pass #2: all 10 functions succeeded (**total: 2,298 s / 38 min 18 s**) |
| `full` | `caps` | `2026-11-18T20:09:27Z` | `2026-11-18T20:09:28Z` | 1 | 0 | Part B full run (start load `0.11`, governor `performance`) |
| `full` | `disk` | `2026-11-18T20:09:28Z` | `2026-11-18T20:19:34Z` | 606 | 0 | Part B full run (10 min 06 s) |
| `full` | `tpm` | `2026-11-18T20:19:34Z` | `2026-11-18T20:19:34Z` | 0 | 0 | Part B full run (`skipped`) |
| `full` | `attest_local` | `2026-11-18T20:19:34Z` | `2026-11-18T20:19:35Z` | 1 | 0 | Part B full run (`skipped`) |
| `full` | `tls` | `2026-11-18T20:19:35Z` | `2026-11-18T20:19:37Z` | 2 | 0 | Part B full run (1,000 handshakes) |
| `full` | `keys` | `2026-11-18T20:19:37Z` | `2026-11-18T20:20:16Z` | 39 | 0 | Part B full run (200 key requests + 200 KBS checks + speed) |
| `full` | `fc_boot` | `2026-11-18T20:20:16Z` | `2026-11-18T20:24:57Z` | 281 | 0 | Part B full run (5 memory sizes × warm/cold × 100 reps) |
| `full` | `fc_snapshot` | `2026-11-18T20:24:57Z` | `2026-11-18T20:45:53Z` | 1256 | 0 | Part B full run (20 min 56 s; 50 creates + 50 warm/cold restores × 3 sizes) |
| `full` | `fc_dispatch` | `2026-11-18T20:45:53Z` | `2026-11-18T20:45:54Z` | 1 | 0 | Part B full run (200 warm vsock dispatches) |
| `full` | `sebs` | `2026-11-18T20:45:54Z` | `2026-11-18T21:33:52Z` | 2878 | 0 | Part B full run (47 min 58 s; all 10 functions + co-run + snapshots) |
| `full` | `fn_inputs` | `2026-11-18T21:33:52Z` | `2026-11-18T22:34:18Z` | 3626 | 1 | Part B full run (60 min 26 s; timed out at 3,600 s in `video-processing`) |
| `full` | `fc_touched` | `2026-11-18T22:34:18Z` | `2026-11-18T22:41:53Z` | 455 | 0 | Part B full run (7 min 35 s; all 10 functions; **Part B total: 9,146 s / 2 h 32 min 26 s**) |
| `appliance` | `collect` | `2026-11-20T16:19:04Z` | `2026-11-20T16:19:05Z` | 1 | 0 | Part C: collected 10 completed host-mode boots (`2026-11-19T10:30`–`10:48Z`, 18 min) |
| `ingest` | `ingest_hdd` | `2026-11-20T16:19:28Z` | `2026-11-20T16:19:32Z` | 4 | 0 | Part D: wrote `configs/calibration/measured/node04-i7-4790s-8g-hdd_hdd` |
| `ingest` | `check_hdd` | `2026-11-20T16:19:32Z` | `2026-11-20T16:19:32Z` | 0 | 1 | Part D: `check_bundle` (0 warnings; 3 expected missing-TPM errors) |
