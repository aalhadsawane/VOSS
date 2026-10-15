# Validation notes (P9)

Status of the calibration against hardware, as of 2026-10-15. Section references are to `docs/architecture/10-*.md`.

## What was measured, and on what

One machine: a Lenovo laptop (board `LNVNB161216`), **Intel Core i3-7020U** (2 cores / 4 threads, 2.3 GHz), 3.9 GB RAM,
one 1 TB **spinning disk**, TPM 2.0, Ubuntu 26.04 (kernel 7.0), VT-x, no TME, no AMD-V. It is **not** the i7 node "C0" of
doc 10. Its bundle is `configs/calibration/measured/laptop-b9212a4528/` (`calibration_hash` in run manifests: `b1b5c3c73db6b2f2fd148f2d8117b731684b5127c345ac700b18935ebea2888f`);
raw logs are in `calibration/raw/laptop-b9212a4528/`. Because the machine has no SSD, its only disk tier (`hdd`) fills
the `ssd` role of `tools/calibrate/mapping.yaml` (`ingest --tier hdd`, D-62), so the entries named `fc_boot`,
`fc_restore` and `fc_snapshot_create` are **HDD** numbers.

Run path: `tools/calibrate/laptop/voss-calib-auto.sh` (one command, systemd service, three rounds; D-60, D-61).

## Measured versus the placeholder bundle

| Entry | Placeholder (tag) | Measured p50 | Reading |
|---|---|---|---|
| `tpm2_quote` | 0.25 s (literature) | 0.51 s | This TPM is 2x the literature figure; spread is tight (p90 0.52 s). |
| `verify_s` | 0.01 s (assumed) | 0.040 s | `checkquote` plus Ed25519 signature, 4x the assumption; still small against the quote. |
| `verify_s_per_MB` | 0.0007 (literature) | 0.0037 | 270 MB/s single-core SHA-256 on a 2017 mobile core. |
| `fc_boot` | 0.15 s (literature) | 0.15 s (warm, 256 MB) | Matches. Cold page cache from the HDD: 1.45 s (10x). |
| `fc_restore` | 0.02 s (literature) | 0.007 s (load API, warm) | Faster than assumed when warm; **cold from the HDD 0.64 s** (api) / 1.1-1.5 s (to first response). |
| `fc_snapshot_create` | 0.2 s (literature) | 6.7 s (512 MB) | HDD write-bound (one sample per size: 2.8 s at 128 MB). Not a per-invocation cost. |
| `reboot_to_kernel` | 15 s (assumed) | 21 s | 9 clean boots: firmware+loader ~20 s plus kernel ~1 s; the ~10 s shutdown comes on top, see note 1. |
| `appliance_userspace` | 4 s (assumed) | 30.7 s | A general Ubuntu userspace with a minimal target, not a purpose-built appliance; **an upper bound**, see note 2. |
| `dispatch`, `drtm_launch`, `kbs_check_s`, `tme_*`, `snapshot_touched_frac` | assumed / literature | not measured | Placeholder values stay; the bundle tags them so. |

Note 1. `reboot_to_kernel` is firmware plus loader plus kernel time taken from wall-clock stamps (`btime -
journal end of the previous boot`, +/- 1 s; GRUB gives systemd no firmware time). One further sample was rejected for a
clock step (the machine's hardware clock was in local time, +5.5 h, until the install switched it to UTC; D-61). Shutdown
(about 10 s) is reported separately in the raw records (`shutdown`, `firmware_loader`, `reboot_cmd_to_kernel`).

Note 2. The design's appliance is a UKI with a dm-verity root and a minimal userspace. The host-mode probe boots a
minimal systemd target on the machine's own kernel and initrd (kernel 0.9 s + initrd 4.1 s + userspace 22 s on this
HDD), so `appliance_userspace` (30.7 s) and `appliance_attested` (44.4 s, of which `tpm2_quote` plus key creation is
about 14 s) overstate what a purpose-built image would need, and understate nothing. They bound the cost from above.

## Not measured

- **SeBS functions** `graph-mst`, `graph-bfs`, `dna-visualisation`, `image-recognition` (the first two hit a guest bug
  fixed after the run; the last needs more RAM than the laptop has). Six functions are measured; the rest keep their
  placeholder profile. Decision: not rerun, the paper does not depend on them.
- **QEMU `q35`** (the Firecracker kernel has no virtio-pci) and all but one **QEMU `microvm`** boot (1.7 s).
- **TME** (the CPU has none), **SSD tier**, **CVM paths** (no SEV/TDX hardware).
- **E01** (simulator versus a real small cluster) needs the P9b emulation testbed, which is parked.

## What this validates, and what it does not

The simulator's start-up and trust-establishment costs were within a factor of 2-4 of this machine for the TPM and
verification paths, equal for warm Firecracker boot, and far off (10x to 30x) where the HDD or a full OS userspace
dominates. Those differences are properties of the laptop's storage and OS, so they say which parameters the
sensitivity sweeps must cover (cold-start tier, appliance reboot time), not that the placeholders were wrong for the
intended C0 (NVMe, minimal image). Re-ingest on the i7 node would replace this bundle without code changes.
