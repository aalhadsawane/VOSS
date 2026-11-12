# Handoff: bare-metal calibration and emulation for VOSS v2

**Who this is for:** a new agent session with shell and sudo access on a bare-metal Linux machine, working with a human who is
physically able to approve reboots. You have no memory of earlier sessions. Everything you need is in this file and the files
it names.

**What you deliver:** measured costs of every step a volunteer machine performs (Parts A-D), and later a multi-worker emulation
run that checks the simulator (Part E). The exact fields and acceptance checks are in
`docs/handoff/CALIBRATION_DATA_CONTRACT.md`. Read it before measuring anything.

**What you do not do:** change the simulator (`voss/`), the scheduler, experiment specs or the paper. If the harness
(`tools/calibrate/`, `tools/emu/`) has a bug that blocks a measurement, fix only that, in its own small PR with a test.

---

## 0. Start here

1. Clone `aalhadsawane/voss`, check out `revision-v2`, create `calib/<host_label>` from it (the label is chosen in Part A).
   Your PRs go **into `revision-v2`**, never `main`.
2. Read, in this order:
   - `AGENTS.md` (rule 14: never run a reboot or BIOS-dependent suite without the human's explicit approval in this session);
   - `docs/REVISION_PLAN.md` §1 (what was wrong with the old calibration: F1-F3) and §V1 (what the harness now measures);
   - `docs/handoff/CALIBRATION_DATA_CONTRACT.md`;
   - `tools/calibrate/README.md`, `tools/calibrate/laptop/README.md`, `docs/architecture/10-calibration.md`;
   - `docs/validation/i7-12700-64g.md` (a worked example from an earlier session; its numbers are **not** reused, its method is).
3. Check that the harness changes of plan phase V1 are merged on `revision-v2`:
   `uv run python -m tools.calibrate.run --dry-run --suite all` must list the probes `guest_entropy_wait`, `image_mem`,
   `fn_rss`, `snap_size` and the per-step boot probes. If it does not, stop and tell the human: the builder session has not
   finished V1.
4. Ask the human, and write the answers at the top of your report:
   - which machine this is and whether an earlier session already measured it (then everything is re-measured; nothing old is kept);
   - which parts to run today (A-D calibration, or E emulation);
   - whether reboots are approved today, and how many (Part C needs 10 or more);
   - whether a BIOS change (memory encryption on/off) is possible and wanted;
   - a scratch directory on each storage device.

## 1. Machines wanted

At least three, chosen to differ in what moves a cost. One session per machine.

| Role | Example | Why |
|---|---|---|
| Low-end laptop, hard disk | the Intel i3-7020U laptop measured before | slowest start-up path; small memory |
| Desktop, NVMe, firmware TPM | the Intel i7-12700 desktop measured before | fast path; many cores for co-run and emulation (Part E runs here) |
| Mid-range laptop or desktop, SATA SSD, **discrete TPM** or AMD firmware TPM | whatever the human can provide | TPM quote time is not portable across TPM implementations |

More machines are welcome if they differ in CPU family, TPM implementation, storage class or memory size. Do not measure two
machines with the same CPU, board, BIOS and memory as two data points; say so and stop.

## 2. Safety and data rules

- Never format, partition or write to a raw block device. Benchmarks write files in the scratch directories only. List before
  you delete; delete only what you created.
- Ask the human before: installing packages, any reboot, any BIOS change, changing kernel parameters, CPU governors, sysctls or
  services. Record each change and undo it at the end.
- No secrets, keys, serial numbers, MAC or IP addresses, or real hostnames in the repository. Hash identifiers
  (first 10 hex digits of SHA-256). `tools/calibrate/report.py pack` scrubs text files; grep the result before `git add`.
- Pack every raw result directory as `.tar.zst` with a SHA-256 file before any cleanup, and keep a copy outside the repository.
- Report failures and skipped probes with the reason. Never fill a gap with an estimate. A missing value stays missing.
- A quiet machine: no other workload during timing runs; note the CPU governor, turbo state, power source (laptop on mains) and
  ambient conditions you can observe (fan state, thermal throttling messages in `dmesg`).
- If `systemd-detect-virt` is not `none`, stop: a virtual machine is not a calibration target.

## 3. Part A: describe the machine

1. Choose `<host_label>`: CPU family, memory, main storage, e.g. `i3-7020u-4g-hdd`. Never the real hostname.
2. `bash tools/calibrate/spec.sh <host_label> <scratch on device 1> [<scratch on device 2> ...]`
   writes `calibration/specs/<host_label>/SPEC.md` and `spec.yaml`.
3. Check the spec contains every field of contract §1 (physical cores and threads, memory, each disk's type, model class and
   capacity, TPM manufacturer, family and firmware version, firmware type and version, Secure Boot state, memory-encryption
   state, kernel). Add by hand what the script cannot see, marked `manual`.
4. `uv run python -m tools.calibrate.run --suite caps` and keep its output.

## 4. Part B: start-up, crypto, functions (no reboot)

Setup (ask before installing): packages listed in `tools/calibrate/README.md`; then
```sh
sh tools/calibrate/guest/fetch_assets.sh ~/voss-calib/assets
sudo env DOCKER="sudo docker" SUDO="sudo" sh tools/calibrate/guest/build_rootfs.sh ~/voss-calib/assets
bash tools/emu/preflight.sh | tee ~/voss-calib/preflight.txt
```
Run a 10% smoke pass first (`--quick`), read its output for errors and implausible values, then the full pass, once per
storage tier:
```sh
A="--set firecracker=$HOME/voss-calib/assets/firecracker --set kernel=$HOME/voss-calib/assets/vmlinux \
   --set rootfs=$HOME/voss-calib/assets/voss-guest.ext4 --set sebs_rootfs=$HOME/voss-calib/assets/voss-guest.ext4"
uv run python -m tools.calibrate.run --suite all --sudo $A --set ssd_dir=<scratch> [--set hdd_dir=<scratch>] --quick
uv run python -m tools.calibrate.run --suite all --sudo $A --set ssd_dir=<scratch> [--set hdd_dir=<scratch>]
```
Suites in `all`: `disk`, `tpm`, `attest_local`, `tls`, `fc_boot`, `fc_snapshot`, `sebs`. (`qemu_vm` is no longer needed.)

**Function measurements need special care (the old ones were wrong, plan F2).**
- Before the full `sebs` run, check `guest_entropy_wait` in the smoke output: it must be under 50 ms for every guest. If it is
  not, the guest is blocking for randomness; fix the entropy device before continuing (plan V1 step 1) and tell the human.
- Every function in `tools/calibrate/guest/functions/` must be measured: handler time at each input size, initialisation time,
  resident memory, snapshot size, and co-run slowdown at 1, 2, …, physical cores, and at the thread count.
- After the run, compare each function's run time at its reference input with the published SeBS value
  (`check_bundle.py` prints the ratio). For any function more than 10x away, find out why (read the guest function, time the
  handler by hand inside one guest) and write the explanation in the report. Do not accept an unexplained value.
- Record the CPU governor and whether turbo was on; run the co-run levels twice and report both.

## 5. Part C: boot the real image (reboots; needs approval each session)

Goal: the time from power-on to an attested worker, per step, on the real locked image, not a sum of steps measured on the
installed system.
1. Build: `uv run python -m tools.calibrate.run --suite appliance --set step=build` (mkosi; unified kernel image, dm-verity root,
   encrypted cache partition sealed to the TPM, attestation agent, Firecracker).
2. Show the human exactly what the next step changes (one extra UEFI boot entry; the installed system is untouched) and get a
   clear "yes".
3. Arm and run at least 10 boots: `--suite appliance --set step=arm --allow-reboot --boots 10`, or the laptop helper
   `bash tools/calibrate/laptop/voss-calib.sh appliance run 10`. Then `--set step=collect`.
4. Steps that must have their own timestamp (contract §3): firmware, boot loader, kernel start, initial RAM disk, dm-verity
   setup, TPM unseal of the cache partition, services up to the agent, agent start, TPM quote, verifier round trip, certificate
   issued, first mutual-TLS connection. Firmware and loader times come from the EFI loader time variables, not from
   `systemd-analyze` (it raced on one machine before). A step that cannot be separated is reported as merged with its
   neighbour, by name; it is never estimated.
5. Also from inside the booted image: resident memory when idle (`image_mem`) and the size of the cache partition.
6. Remove the boot entry afterwards and confirm with the human that the machine boots its normal system.

Optional, only if the human can change the BIOS setting: `--suite tme --phase off`, toggle, `--suite tme --phase on`. This tells
whether the machine belongs to owner class M (memory encrypted) and what that costs.

## 6. Part D: ingest, check, report

```sh
uv run python -m tools.calibrate.ingest --raw calibration/raw --host <host_label>            # main tier
uv run python -m tools.calibrate.ingest --raw calibration/raw --host <host_label>_hdd --tier hdd   # if a second tier exists
uv run python -m tools.calibrate.check_bundle configs/calibration/measured/<bundle>
```
`check_bundle` must pass with no errors; every warning needs a sentence in the report.

Write `docs/validation/<host_label>.md`:
- the human's answers from §0.4; date; harness commit;
- the machine spec table;
- per-step tables: boot to attested worker, sandbox boot, snapshot create, snapshot restore, key release and bundle decryption;
  median, 5th and 95th percentile, n;
- function table: run time by input size, initialisation, memory, snapshot size, ratio to the SeBS value, explanation where needed;
- co-run slowdown table by concurrency level;
- everything skipped or failed, and why;
- every change made to the machine and its reversal.

Commit: spec files, bundle(s), scrubbed raw data (or checksums and location if larger than 50 MB), the report. Open a PR into
`revision-v2` titled `Calibration: <host_label>`. Do not merge it yourself; the builder session reviews it against the contract.

## 7. Part E: multi-worker emulation (second visit, on the largest machine)

Do this only when the human says the builder has tagged `v2-freeze` and prepared the emulation (plan V13). Purpose: run the
real scheduler against real sandboxes and compare with the simulator on the same scenario.

Setup, as provided by `tools/emu/` on `revision-v2` at that time:
- 6-10 emulated workers on this one machine. Each worker is a process tree with its own pinned physical cores (use only cores of
  one kind on hybrid CPUs; never share a core between workers), a memory limit, and its own network namespace with injected
  delay and bandwidth limits matching the simulator scenario.
- Sandboxes are real Firecracker microVMs running the measured functions. A session start performs a real TPM quote on the
  machine's TPM. Ending a session kills the worker's process tree and removes its namespace.
- The scheduler, routers, verifier and key services run as processes on the same machine on separate cores.
- Arrivals and session ends come from the scenario file the builder provides
  (`configs/emu/<name>.yaml`); do not edit it.

Run:
1. `bash tools/emu/preflight.sh`; fix what it reports (ask before system changes).
2. For each system in the scenario list (the VOSS scheduler and the fixed keep-alive baseline), 3 repetitions of the 2-hour
   scenario: `uv run python -m tools.emu.run <scenario> --system <name> --rep <i> --out runs-emu/<host_label>/`.
3. The matching simulator runs are produced by the builder on GitHub Actions; you only run
   `uv run python -m tools.emu.compare --emu runs-emu/<host_label> --sim <path the builder gives>`.
4. Report `docs/validation/emulation-<host_label>.md`: share of deadlines met, key holders, mix of start-up levels, latency
   distribution, for emulation and simulator side by side, with the spread over repetitions; every disagreement larger than the
   spread, stated plainly. Do not tune anything to make them agree.
5. PR into `revision-v2` titled `Emulation: <host_label>`.

## 8. When to stop and ask the human

- Any reboot, BIOS change, package install, or system setting change.
- A probe fails twice for the same reason.
- A measured value is more than 10x away from the earlier worked example or from the published value and you cannot explain it.
- The machine is shared or shows other load.
- Anything in this file conflicts with what you see in the repository.

## 9. Message to paste into the new session

```text
You are working on the VOSS research repository (GitHub: aalhadsawane/voss) on a bare-metal Linux machine with sudo.
Check out branch revision-v2 and read docs/handoff/CALIBRATION_HANDOFF.md from top to bottom, then
docs/handoff/CALIBRATION_DATA_CONTRACT.md. Follow them exactly. Start with section 0: ask me the questions in 0.4
before you measure anything. Never reboot, change BIOS settings, install packages or change system settings
without my explicit approval in this session. Do not reuse any number from earlier calibration runs.
```
