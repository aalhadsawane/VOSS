# node01 Part C failure log (host-mode appliance boots)

Machine: `node01-i7-12700-64g-nvme` (ASUS PRIME Z790-P WIFI, i7-12700, 64 GB, 2×NVMe, Intel PTT).
This file records every Part C attempt, including the crashes, so the same procedure is not repeated blindly. No
number from these failed attempts is used by the calibration bundle.

## Summary

| Attempt | Date (UTC) | Completed | Valid boots | Invalid boots | Archive |
|---|---|---|---|---|---|
| 1 | 2026-11-14/16 | 5/10 | 1, 2, 5 (5 is a 187.7 s outlier) | 3, 4 | `~/voss-calib-backups/node01-partC-old-20261116/` — raw SHA-256 `99b252a8…`, logs `7e3150ba…` |
| 2 | 2026-11-17 | 3/10 | 1, 3 | 2 (host down 5 h 31 m 44 s) | `~/voss-calib-backups/node01-partC2-partial-20261117/` — `f06e1975…` |
| 3 | 2026-11-17/18 | 2/10 | 1 | 2 (host down 11 h 30 m 22 s); console showed a kernel panic | `~/voss-calib-backups/node01-partC3-partial-20261118/` — `970a689e…` |

Ten complete boots were never obtained. Part C is **not** in the calibration bundle.

## Attempt 3 detail (the guard run)

Before this attempt every non-voss UID was killed and a `voss-calib-guard.service` was installed. It ran on every normal
boot before the driver and killed every UID ≥ 1000 except voss (1027) every second, so pfs and nectar could not start a
workload. `ps` showed only voss (and root/system) before the loop started.

| Boot | Arm (UTC) | Kernel start (UTC) | Arm→kernel gap | Status | Agent ready | Quote done | Verified |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-17 18:04:58.996 | 2026-11-17 18:05:26 | 20.1 s | ok | 6.46 s | 10.00 s | 10.03 s |
| 2 | 2026-11-17 18:09:34.445 | 2026-11-18 05:39:57 | 41,422.3 s (11 h 30 m 22 s) | **invalid** | 7.03 s | 10.03 s | 10.06 s |

The human was at the node with a monitor when it failed and saw a **kernel panic attributed to an interrupt**. The
machine did not return until a manual power-cycle; boot 2's gap is the time it was down. The STOP file was written at
2026-11-18 11:13 IST (05:43 UTC); the driver was disabled and the host-mode units were uninstalled.

## Persistent evidence (what the machine stored)

- `/sys/fs/pstore` is **empty**. The EFI pstore backend is registered, but no crash record was written.
- No `Kernel panic`, `panic - not syncing`, `Fatal exception in interrupt`, `NMI watchdog` failure, `hard LOCKUP`,
  `soft lockup`, `Oops` or `BUG:` record appears in the persistent journal (`/var/log/journal`), `kern.log` or
  `syslog` for the failed boot. The only `NMI` lines are the normal `ACPI: LAPIC_NMI` and
  `NMI watchdog: Enabled` boot messages.
- The journal for the failed boot ends at the reboot; it contains no stack trace. The panic was printed to the console
  and was not persisted before the machine went down.
- `last`/`journalctl --list-boots` show the failed boot and the long gap; they cannot show the panic text.

## What this rules out

- **Not pfs/nectar or another user workload.** Attempt 3 removed them completely with the guard, and the panic still
  happened. The earlier pfs theory was wrong.
- **Not the probe or the arming script.** The probe completed on every boot that reached userspace; the driver armed
  the next boot normally. The panic happens on the host, around the reboot/boot boundary.
- **Not a calibration-number or bundle problem.** The failed boots are archived outside the repository and are not
  ingested.

The remaining likely cause is a host-level kernel/firmware/driver panic in interrupt context (this ASUS board, the
NVIDIA driver, the 5.15 kernel and the rapid reboot cycle are the untested variables). The exact stack is unavailable,
so no further diagnosis is claimed.

## If it is ever retried

Do **not** retry the same unattended loop on this node. If a future session must try, it needs a way to capture the
panic before the machine dies:

- a serial console or `netconsole` (the only reliable way to capture an interrupt-context panic here);
- `pstore`/`ramoops` configured and verified to retain a record; the EFI pstore backend was empty;
- the node booted with the same kernel/BIOS and without the NVIDIA driver if possible, one boot at a time, attended;
- the human present at every reboot.

A different node with a reliable reboot path is the safer route.

## Data status and rerun time

- Part A, Part B, ML and the topup probes are stored and pushed; none of their data was lost.
- Part C has **no valid 10-boot dataset**; attempts 1–3 are archived for evidence only and must be redone.
- `fn_input_gen` is still missing: the topup `fn_inputs` ran but the host ignored `VOSS_GEN`; the parser fix is
  committed on the branch (`6ac78d2`, lock `40541bbe`) but `fn_inputs`/`topup` has **not** been re-run. That re-run does
  not need a reboot and should take about 40–45 min.
- Estimated rerun on a host with a working shutdown/reboot path: **10 host-mode boots ≈ 50–60 min**, plus collect and
  ingest ≈ 10 min, so **about 1 h–1 h 15 min** for Part C. If the `fn_input_gen` re-run is also needed, add
  **~45 min** (total ≈ 1 h 45 min–2 h). On this node the loop has failed three times, so the estimate assumes a
  different/repaired host.
