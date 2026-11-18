# Bare-metal nodes: what runs where, how many, how long

This file is for the human who owns the nodes and for every agent session that runs on one. Each node gets its own new
agent session. All sessions follow this file and `docs/handoff/CALIBRATION_HANDOFF.md`, so their results can be compared.

## 0. Summary

| What | Where | When | Time per node |
|---|---|---|---|
| Part A: describe the node, check it is not a duplicate | every node | now | ~15 min |
| Setup: pinned Firecracker, guest kernel, base and ML guest images | every node | now | 40-75 min |
| Part B: start-up, attestation, keys, functions (no reboot) | every node | now | 3-8 h, mostly unattended |
| Part C: boot the real image 10 times (reboots, human approval) | every node with a TPM 2.0 | now | 1.5-2.5 h, human present |
| Part D: ingest, check, report, PR | every node | now | 30-60 min |
| Part E: multi-worker emulation | the one node with the most physical cores | after `v2-freeze` (later) | ~14 h unattended + 1 h |

Everything else (all simulator experiments, the decision-time benchmark) runs on GitHub Actions, not on these nodes.

## 1. Why bare metal at all

The simulator takes every cost a volunteer machine pays from a measured bundle (AGENTS.md rules 13, 28, 29): sandbox start
and restore, TPM quote, key release, each function's run time per input size, co-run slowdown, and boot of the real image.
A virtual machine hides the TPM, the disks and the CPU's frequency behaviour, so these numbers come only from bare metal.

## 2. How many nodes, and which

**At least 3 distinct nodes; 4-6 if you have them.** The reasons, each tied to a claim the paper makes:

| Claim in the paper (plan §11) | What it needs from the node set |
|---|---|
| Machines differ in speed, and the ratio differs per function (measured before: 2.4x to 5.7x between a laptop and a desktop) | ≥ 3 machine classes. With 2, a per-function ratio cannot be told apart from one scalar speed. |
| The run-time model's machine-class term (γ) transfers a run on one machine to another machine of the same class | ≥ 2 classes measured with the same functions and sizes |
| Start-up cost depends on storage: bundle fetch, sandbox boot from disk, snapshot write and restore | all three of HDD, SATA SSD, NVMe across the node set (≥ 2 required); on each node, **every** disk class it has is measured as its own tier |
| Attestation cost depends on the TPM | firmware TPM (Intel PTT or AMD fTPM) **and** a discrete TPM, if available |
| Co-run slowdown depends on core count | core counts at least 2x apart |
| Owner class M (memory encryption) | one node whose firmware can enable TME, SME or SEV; optional |

**Disks matter as much as CPUs.** A volunteer machine's start-up path reads the function bundle, the sandbox root file
system and snapshots from its own disk; an HDD can be 10-100x slower than NVMe on these. So:
- each node measures `disk`, `fc_boot` and `fc_snapshot` once per disk class it has (`nvme=`, `sata=`, `hdd=` scratch
  directories; `node_run.sh` refuses to start if a class in the spec has no directory);
- ingest writes one bundle per tier, `configs/calibration/measured/<label>_<tier>`; in the simulator a machine class is a
  (node, tier) pair, so a node with NVMe and HDD gives two classes that share the CPU and differ in storage;
- two nodes with the same CPU but different disk models are not duplicates (§3), and the node table lists every disk's
  class and model.

Machine classes in the simulator are exactly the calibrated (node, tier) pairs (plan V9.4); each class's share of the volunteer
population comes from a public hardware survey mapped to the nearest calibrated node. More distinct nodes means a smaller
part of the survey is represented badly; the paper reports that part.

`uv run python -m tools.calibrate.nodes table --branches` prints the node table, the coverage of each axis above, pairs
of nodes that are too alike, and the gaps against this section.

**Emulation (Part E)** runs on one node only: the one with the most physical cores. It needs at least 8 physical cores of
one kind (6 emulated workers with one core each plus 2 for the scheduler, routers, verifier and key services); 12 or more is
better (10 workers). It must have a TPM 2.0 and an NVMe or SATA SSD.

## 3. Node names and the duplicate check

- Scratch directories: one per disk class, on a filesystem of that disk, with ≥ 20 GB free (benchmarks write only there;
  the handoff, §2, forbids touching raw devices).
- The human gives each node a number, `node01`, `node02`, … and a codename (the owner's name for the machine). The
  owner decided that the codename may go into the repository (2026-11-18); IP addresses, user accounts, cluster
  services and real hostnames that differ from the codename do not. Every node is listed here:

  | Number | Codename | Label(s) | Status |
  |---|---|---|---|
  | node01 | anjuna2 | `node01-i7-12700-64g-nvme` | retired (2026-11-18). Parts A, B, ML and topup merged (#101); Part C failed three times (a hung shutdown, then a kernel panic in interrupt context, with another user's filesystem watchdog daemon running on the node); no boot data, so its bundle lacks `reboot_to_kernel` and `appliance_userspace` and serves only the same-model comparison with node02 |
  | node02 | colva3 | `node02-i7-12700-64g-nvme` (`_nvme`, `_hdd`) | complete (#86): all ten functions, 10 boots, topup; `fn_input_gen` only after `inputs` (optional) |
  | node04 | calangute1 | `node04-i7-4790s-8g-hdd` | in progress: Part A complete; Haswell i7-4790S (4c/8t), 8 GB DDR3, one 500 GB SATA HDD, no TPM; distinct CPU class from node01/node02 |

  The next node takes the next free number. Add its row in the node's own PR.
- The node's **label** is `nodeNN-<cpu>-<memory>g-<main storage>`, lower case, e.g. `node03-i5-8250u-8g-ssd`,
  `node01-i7-12700-64g-nvme`. `node_run.sh` refuses any other form. All files of the node live under
  `calibration/specs/<label>/`, `configs/calibration/measured/<label>[_hdd]/` and `docs/validation/<label>.md`.
- Part A ends with `nodes check <label> --branches`, which compares this node with every node already pushed on an
  `origin/calib/*` branch:
  - **duplicate** (same CPU model, memory within 25%, same disk models, same TPM kind): the session stops, pushes the
    spec only and tells the human. Measuring it would count one machine twice. The human decides whether it adds anything;
    if not, the node is dropped.
  - **similar** (same CPU model with other memory or other disks, or the same disk models, or three of the CPU, memory,
    disk-class and TPM checks): continue, and say in the report what differs. A node whose only difference is its disks
    still adds a storage data point; measure all its tiers.
- Push the spec (step 4 of §5) before Part B, so nodes measured in parallel see each other.

## 4. Consistency rules (so results from different sessions are comparable)

1. **Same harness.** `calibration/HARNESS.lock` holds the git tree hash of `tools/calibrate/`. `node_run.sh` stops if the
   checked-out harness differs or has local edits. If the harness has a bug, the session stops and tells the human; the
   fix goes into `revision-v2` through the builder session, the lock is updated, and every node re-runs the suites the fix
   touches.
2. **Same assets.** Firecracker v1.10.1 and guest kernel `firecracker-ci/v1.10/x86_64/vmlinux-6.1.102` (pinned in
   `tools/calibrate/guest/fetch_assets.sh`); the guest image is built by the same script. `node_run.sh setup` writes their
   checksums to `calibration/specs/<label>/assets.sha256`; Firecracker and kernel checksums must be equal on all nodes.
3. **Same order and sample counts.** `node_run.sh` runs the suites of Part B one at a time in a fixed order with the sample
   counts of `CALIBRATION_DATA_CONTRACT.md`. Do not run suites by hand, change counts or skip suites.
4. **Same machine state, for every measuring stage.** `quick`, `full`, `ml`, `topup` and `inputs` all run under the Part B
   conditions: performance CPU governor (restore afterwards), turbo left at the firmware default, laptops on mains power,
   background services stopped, no other workload, no other agent session on the node, and a 1-minute load average below
   0.5 when the stage starts. A stage that only re-measures a few probes is no exception: node02 measured its ML stage at
   a load average of 10 to 17 (the image build's writeback and services left running), and its `image-recognition` came
   out 13 to 19% slower than node01's, while every other function matched within about 4%. `node_run.sh` refuses to
   start a measuring stage without the performance governor, and waits up to 30 minutes for the load average to fall
   below 0.5 before it stops (exit 6). It records governor, turbo, power, load, TME state and throttling messages before
   and after every stage (`env-<stage>.txt`). If the human refuses a setting, record that; do not work around it.
5. **Same reference.** Relative machine speed is computed against one reference node, named in `calibration/REFERENCE`
   (the human chooses; `node02` since node01 retired, because node02 is complete). Every node measures the same functions at the same sizes, so ratios are defined.
6. **Same rules for gaps.** A value that cannot be measured stays missing, with the reason. Never copy a value from another
   node, an earlier run or the literature.
7. **No other users' work on the node.** node01 was a shared machine: another user's filesystem watchdog daemon and
   workload processes ran there, and its reboots (Part C) hung or panicked. Before the first measuring stage, and again
   before Part C, list every process and service that does not belong to the operating system or to this session:
   `ps -eo uid,user,pid,etime,comm --sort=uid | awk '$1 >= 1000'`, `loginctl list-users`, `systemctl list-units
   --type=service --state=running` (look for cluster, storage, filesystem and watchdog daemons, container runtimes and
   GPU jobs), `crontab -l` for each user and `ls /etc/cron.d`. Show the list to the human and stop what they approve;
   record each in the report and restore it afterwards. `node_run.sh` refuses a measuring stage (exit 6) while any
   process or service manager of another login user (UID 1000 or above) runs; a user the human approves is passed as
   `VOSS_ALLOW_USERS="name ..."` and is recorded in `env-<stage>.txt`. A node that other people need while it is measured
   is not suitable; tell the human.

## 5. The session on one node, step by step, with times

| Step | Command | Expected time | Human needed |
|---|---|---|---|
| 0. Read | `AGENTS.md`, this file, `CALIBRATION_HANDOFF.md`, `CALIBRATION_DATA_CONTRACT.md` | 15 min | answers §0.4 of the handoff |
| 1. Branch | `git checkout -b calib/<label> origin/revision-v2` | 1 min | |
| 2. Part A | `bash tools/calibrate/node_run.sh spec <label> nvme=<dir> sata=<dir> hdd=<dir>` (the classes it has) | 10-15 min | name a scratch dir on every disk |
| 3. Fill gaps | add `manual` fields the script cannot see (contract §1) | 5 min | maybe |
| 4. Push spec | commit `calibration/specs/<label>/`, push `calib/<label>` | 2 min | |
| 5. Setup | `bash tools/calibrate/node_run.sh setup <label>` (asks before installing packages; builds both guest images, the ML one with PyTorch) | 40-75 min | approve installs |
| 6. Smoke | `bash tools/calibrate/node_run.sh quick <label> nvme=<dir> sata=<dir> hdd=<dir>` | 20-60 min | `sudo -v` |
| 7. Read smoke output | errors, implausible values (`%.3g` formatting) | 15 min | |
| 8. Part B | `bash tools/calibrate/node_run.sh full <label> nvme=<dir> sata=<dir> hdd=<dir>` | 3-8 h; +30-60 min per extra disk class | `sudo -v` once |
| 9. Part C | handoff §5: build image, 10 boots, collect | 1.5-2.5 h | yes, for every reboot |
| 10. Part D | `node_run.sh ingest <label> <each tier measured>`, report | 30-60 min | |
| 11. PR | `Calibration: <label>` into `revision-v2`; do not merge | 5 min | |

Where the time of Part B goes (rough, from the sample counts; the real durations land in `timeline.csv`):

| Suite | Work | Typical |
|---|---|---|
| `caps`, `disk` | capability probe; `fio` sequential and random read/write on every tier | 10-20 min per tier |
| `tpm`, `attest_local` | 200 quotes, 50 unseals, 50 verifications (a discrete TPM is slower) | 5-20 min |
| `tls`, `keys` | 1,000 handshakes, 200 key requests, 200 key service checks, `openssl speed` | 5 min |
| `fc_boot`, `fc_snapshot` | 100 boots per memory size, tier and page-cache state; 50 snapshots and restores per tier | 30-90 min per tier (HDD: upper end) |
| `fc_dispatch` | 200 dispatches to one warm sandbox over vsock | 2-5 min |
| `sebs` | 10 functions × 5 input sizes × 30 runs; co-run at 1…cores and threads × 30; memory and snapshot size | 2-6 h |
| `fn_inputs` | 10 functions × every input size × 30 input builds, one guest alone | 10-30 min |
| `fc_touched` | 10 functions × 10 cold restores and first invocations, per tier | 10-20 min per tier (HDD: up to 1 h) |
| `tme --phase on` | only when the firmware has TME enabled: STREAM, 4 functions alone | 10 min |

`timeline.csv` records the start, end and duration of every suite. Report the actual total in the validation report, so
the next node's estimate is better.

**Parallel nodes.** Nodes are independent; run them at the same time if you like. Only step 4 (push the spec before Part B)
orders them. The builder session reviews and merges each node's PR.

## 5a. Harness versions: what a node measured on an older harness re-runs

`calibration/HARNESS.lock` names the harness every node must run. When a builder fix changes it, this table says what
a node measured on the older harness runs again; everything else it measured stays valid.

| Lock | Change | A node measured on the previous lock runs |
|---|---|---|
| `570e04bc` | node01's fixes: guest memory 4,096 MB for `dynamic-html` and `dna-visualisation`; 50 snapshot creates; `fn_rss` per co-run level; `snap_size` 3 times, also on NVMe-only nodes | everything (earlier locks were never used for a bundle) |
| `1de5d147` | separate ML guest image (`voss-guest-ml.ext4`, PyTorch + ResNet-50) used only by `image-recognition`; `setup` builds both images | `git pull` (the lock check needs the new harness), then `bash tools/calibrate/node_run.sh ml <label> <tier>=<dir> ...` (builds the ML image, measures `image-recognition` alone, about 1-1.5 h), then `ingest` again. Nothing else. |

| `f1e2fb16` | every bundle entry the simulator reads now has a probe: `dispatch_warm` over vsock (`fc_dispatch`), `kbs_check` (`keys`), `snapshot_touched_frac` (`fc_touched`), `fn_input_gen` (`fn_inputs`), `tpm2_unseal` 50 times under its contract name, `hash_per_MB` 20 times, `tme_state` and `tme --phase on` when TME is enabled; guest runner with a vsock listener; `ingest` reads only this node's fingerprint and leaves out `quick` runs; measuring stages check governor and load | `git pull`, then `bash tools/calibrate/node_run.sh topup <label> <tier>=<dir> ...` (copies the new guest runner into the existing images, then runs only the probes above, about 30-90 min, HDD at the upper end), then `ingest` again. Nothing else: the fio, boot, snapshot, quote, key-request and `sebs` results of lock `1de5d147` stay valid, and `ingest` now also reads the node's fio speeds for its own tier, which were already measured. |
| `82e4f794` | `check_bundle` no longer demands the TME on/off factors (D-104: memory encryption is not modelled); the placeholder bundle drops them | `git pull` only; nothing is re-measured. A node on `f1e2fb16` that already ran `topup` runs `ingest` again. |
| `bda72fa0` | the console reader matches the guest's `VOSS_GEN` lines: `fn_inputs` on lock `82e4f794` ran but recorded nothing | `git pull`; a node that already ran `topup` on `82e4f794` runs `bash tools/calibrate/node_run.sh inputs <label> <tier>=<dir> ...` (about 40 min, `fn_inputs` alone, Part B conditions), then `ingest`. A node that has not run `topup` yet runs it as before. |
| `b50f5dad` | measuring stages refuse to start while another login user's processes or service manager run (§4 rule 7) | `git pull` only; nothing is re-measured. |

The guest image is no longer a human choice: every node measures all ten functions. A node that still has to run Part
C boots (fewer than 10 completed) does that separately, with the human's approval; `topup` does not reboot.

## 6. When a session stops and asks

The rules of `CALIBRATION_HANDOFF.md` §8, plus:
- `node_run.sh` exits 3 (duplicate node), 4 (harness differs from the lock), 5 (a suite failed) or 6 (governor not
  `performance`, or load average not below 0.5): stop and tell the human.
- `assets.sha256` shows a Firecracker or kernel checksum different from another node's: stop.
- Load average above 0.5 during any measuring stage, or throttling messages appear: tell the human, repeat the
  affected suite.

## 7. After all nodes are merged (builder session)

1. `uv run python -m tools.calibrate.nodes table` → the paper's machine table (CPU, memory, every disk's class and
   model, TPM) and the coverage statement.
2. Plan V9.4: map the hardware survey onto the calibrated nodes; report the unrepresented share.
3. Plan V5: class priors γ from the measured per-function ratios between nodes.
4. Check that speed ratios between nodes are function-dependent (the claim of §2); if they are not, the paper says so.

## 8. Part E later

Only after the human says `v2-freeze` exists. On the emulation node: handoff §7. Time: setup 1 h; 2 systems × 3 repetitions
× 2-hour scenario = 12 h unattended; comparison and report 1 h.

## 9. Message to paste into each node's new session

Replace `NN` and `<codename>`. The session starts with no memory of earlier ones; the message and the files it names
are its whole context.

```text
You are working on the VOSS research repository (GitHub: aalhadsawane/voss) on a bare-metal Linux machine with sudo.
This node is nodeNN, codename <codename>. Check out branch revision-v2 (the long-lived v2 branch; never push to main,
never force-push).

What this is: VOSS runs serverless functions on volunteer machines. Its results come from a simulator whose costs must
be measured on real machines (AGENTS.md guardrails 28-29: no invented costs). Your job is to measure this machine with
the calibration harness and deliver its bundle as a PR. Read, in this order, and follow exactly: AGENTS.md,
docs/handoff/NODE_PLAN.md, docs/handoff/CALIBRATION_HANDOFF.md, docs/handoff/CALIBRATION_DATA_CONTRACT.md. Derive the
node's label from its hardware (NODE_PLAN.md §3) and add its row to the node table there in your PR.

Why this node: node01 (anjuna2) and node02 (colva3) are both Intel i7-12700. The paper needs other CPU classes to show
that the speed ratio between machines depends on the function. Run Part A and `nodes check <label> --branches` first;
if it reports a duplicate, push the spec only and stop.

Lessons from the earlier nodes, already in the documents; do not skip them:
- Run every measurement through tools/calibrate/node_run.sh (stages spec, setup, quick, full, ingest), never suite by
  suite. The harness must match calibration/HARNESS.lock; exit 4 means it does not: stop.
- Every measuring stage runs under the Part B conditions (NODE_PLAN.md §4 rule 4): performance governor, background
  services stopped, load average below 0.5. node02 once measured under load and one function came out 13-19% slow.
- No other user's work on the node (§4 rule 7): node01 had another user's filesystem watchdog daemon running, and its
  reboots hung and panicked. List other users' processes, service managers, cluster/storage/watchdog daemons, container
  and GPU jobs and cron entries, show me the list, and stop what I approve. node_run.sh exits 6 while they run.
- setup builds two guest images; the second has PyTorch for image-recognition. All ten functions are measured.
- Part C (boot to an attested worker) needs reboots: follow the preflight of CALIBRATION_HANDOFF.md §5 step 3 (non-OS
  services and watchdogs disabled for the loop, a panic capture via pstore or netconsole, one reboot by hand with me
  watching, stop at the first incomplete boot). If the image mode cannot be built (Ubuntu 22.04 lacks systemd-repart),
  use the documented host mode and report the image-only steps as missing.
- Memory encryption (TME) is not modelled (decision D-104): record the TME state; do not change the BIOS for it.
- A value that cannot be measured stays missing, with the reason. Never copy a number from another node, an earlier
  run or the literature.

Ask me first, every time, before: any reboot, any BIOS change, installing packages, changing the governor, stopping or
disabling a service, or any other system setting. Restore every change afterwards and list it in the report. Push the
node spec (NODE_PLAN.md §5 step 4) before Part B. Stop and ask me if node_run.sh exits 3, 4, 5 or 6, if load average
stays above 0.5, or if throttling appears.

Deliver: the bundle(s) from `node_run.sh ingest <label> <tiers>`, `check_bundle` output, and
docs/validation/<label>.md (machine table, every result table, what was skipped and why, every change to the machine
and its reversal, the time of every step from timeline.csv). Open the PR "Calibration: <label>" into revision-v2 and do
not merge it. Do not put IP addresses, user names or other people's service names in the repository.
```
