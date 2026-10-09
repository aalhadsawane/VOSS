# Calibration harness (doc 10, ROADMAP P9)

Measures node **C0** and turns the raw logs into a hashed calibration bundle that the simulator reads instead of the
literature placeholders. The node is reached over **SSH**; the coding agent never runs on it.

```
local repo ──rsync tools/calibrate──▶ C0 ~/voss-calib ── python3 -m tools.calibrate.run --suite … ──▶ raw/
local repo ◀──────────rsync raw/──────────── C0                    (stdlib-only Python 3.10+ on the node)
python -m tools.calibrate.ingest --raw calibration/raw   →   configs/calibration/measured/<fingerprint>/
```

## Safety rules

- **Non-destructive by default.** Everything except `appliance` (reboots) and `tme` (BIOS toggle) is safe to re-run.
- `appliance --set step=arm` needs `--allow-reboot`; `tme` needs `--phase on|off` after the owner changed the BIOS.
  **Never pass these flags without the user's explicit approval** (AGENTS.md rule 14). The harness never installs a
  reboot loop: `remote.py --boots N` reboots once, waits for SSH, and repeats.
- `--sudo` is needed only for cold page-cache runs (`drop_caches`) and dm-crypt/dm-verity loop devices.
- Every run writes `meta.json` (harness, kernel, VMM versions, BIOS, microcode, TME/Secure Boot/IOMMU state).

## One-time setup on C0

1. Packages: `python3 (≥ 3.10) rsync fio tpm2-tools openssl cryptsetup qemu-system-x86 gcc docker.io e2fsprogs`
   (and `mkosi` for the appliance).
2. Assets: `tools/calibrate/guest/fetch_assets.sh ~/voss-assets` (pinned Firecracker + jailer + CI kernel) and
   `tools/calibrate/guest/build_rootfs.sh ~/voss-assets [--with-ml]` (guest ext4 with the SeBS-equivalent functions).
3. Scratch directories on each disk, e.g. `/mnt/nvme/voss` (SSD) and `/mnt/hdd/voss` (HDD).

## Runs (from the local repo)

```sh
H="--host user@c0 --identity ~/.ssh/c0"
A="--set firecracker=$HOME/voss-assets/firecracker --set kernel=$HOME/voss-assets/vmlinux \
   --set rootfs=$HOME/voss-assets/voss-guest.ext4 --set sebs_rootfs=$HOME/voss-assets/voss-guest.ext4"
D="--set ssd_dir=/mnt/nvme/voss --set hdd_dir=/mnt/hdd/voss"
python -m tools.calibrate.remote $H --suite caps                        # what the node can do
python -m tools.calibrate.remote $H --suite all --sudo $A $D --quick     # smoke (10% reps)
python -m tools.calibrate.remote $H --suite all --sudo $A $D             # full: disk, tpm, attest_local, tls, fc_*, qemu_vm, sebs
python -m tools.calibrate.ingest --raw calibration/raw                   # → configs/calibration/measured/<fp>/
python -m experiments.ecs1_measured --raw calibration/raw                # E-CS1 measured table
```

Manual suites, only with approval: `--suite tme --phase on|off` (twice, around a BIOS change by the owner) and
`--suite appliance --set step=build`, then `--suite appliance --set step=arm --allow-reboot --boots 20`, then
`--set step=collect`.

## Suites

| Suite | Measures | Feeds |
|---|---|---|
| `caps` | KVM, CPU flags, TPM vendor (INTC = PTT), TME (dmesg, CPUID, MSR), Secure Boot, IOMMU, disks | which suites can run |
| `disk` | fio seq/rand read/write per tier, dm-crypt and dm-verity, SHA-256 | hardware C0, `verify_s_per_MB` |
| `fc_boot` | spawn → API, `InstanceStart` → guest init by memory, tier, page cache | `fc_boot` |
| `fc_snapshot` | snapshot create, restore (load API and to first response) by memory, tier, page cache | `fc_snapshot_create`, `fc_restore` |
| `qemu_vm` | microvm and q35 boot to init | E-CS1 |
| `sebs` | SeBS-equivalent functions: init, exec vs size, 1-8 concurrent guests | function profiles |
| `tpm` | `tpm2_quote`, AK creation, `tpm2_checkquote`, PCR-policy unseal | `tpm2_quote` |
| `attest_local` | quote → checkquote → certificate signature | `verify_s` |
| `tls` | TLS 1.3 handshake and per-message overhead | channel costs |
| `tme` (manual) | STREAM-style triad and a SeBS subset, TME on vs off | `tme_*_factor` |
| `appliance` (manual) | reboot → UKI → dm-verity userspace → agent → quote → verified | `reboot_to_kernel`, `appliance_userspace` |

`mapping.yaml` says which probe becomes which bundle entry. Entries without data keep the placeholder value and tag.
Kata (`kata` in doc 10) and the Node.js function variants are not covered yet.

## Testing without the node

`--dry-run` prints every command. `tpm` and `attest_local` run against a software TPM:
`swtpm socket --tpm2 --server type=tcp,port=2321 --ctrl type=tcp,port=2322 --flags not-need-init,startup-clear`
and `--set tcti=swtpm:port=2321`. `disk` and `tls` run anywhere with `fio`/`openssl`.
