# Part C: host-mode appliance boots (node01, 2026-11-14 → 2026-11-16)

The real appliance image (mkosi UKI + dm-verity root + TPM-sealed cache partition) could not be built on this host:
Ubuntu 22.04 ships systemd 249, which has no `systemd-repart` binary and cannot parse the `Verity=` keys in
`tools/calibrate/appliance/mkosi.repart/`; the distribution's mkosi is 12. The handoff (`CALIBRATION_HANDOFF.md` §5)
explicitly allows the laptop helper instead, so this node ran the host-mode probe: the same reboot + TPM attestation
round in a minimal one-shot target on the machine's own kernel, with wall-clock stamps (±1 s). The image-only steps
(`boot_firmware`, `boot_loader`, `boot_quote`, `boot_verify`, `boot_first_tls`, `boot_total`, `image_mem`) are therefore
missing; they are not estimated.

## What completed

- `appliance run 10` started 2026-11-14T14:15:53Z (15 s later the first reboot).
- 5 of 10 boots completed: `arm-0001.epoch` … `arm-0005.epoch`, `complete-0001` … `complete-0005`.
- Boots 1 and 2 are clean: firmware+loader 20.44 s / 20.21 s, userspace-to-agent 17.28 s / 6.45 s,
  kernel-to-verified 23.85 s / 11.59 s.
- Boots 3 and 4 are **incomplete** (`boot_incomplete` in the bundle): the gap between `prev_end` and `btime` is
  63,763 s and 85,650 s, so the machine was down/hung between arming and booting. This is the kernel panic and the
  manual recovery, not a boot measurement.
- Boot 5 is within the harness's 600 s sanity bound but its firmware+loader is 187.69 s, about 9× the clean boots;
  it is the recovery boot and is reported as an outlier, not as a representative value.
- The loop was stopped at 5/10: `STOP` was created after the panic, the driver was disabled, and the default target
  was restored to `graphical.target`.

## Files

`probe-000*.log` are the raw host-mode probe logs; `arm-*.epoch` and `complete-*` are the loop's arm/complete stamps.
The parsed records are in `calibration/raw/c0-584bb563fe/appliance/20261116T082510/records.jsonl`.
