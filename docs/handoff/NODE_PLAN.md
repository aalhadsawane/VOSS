# Bare-metal nodes: what runs where, how many, how long

This file is for the human who owns the nodes and for every agent session that runs on one. Each node gets its own new
agent session. All sessions follow this file and `docs/handoff/CALIBRATION_HANDOFF.md`, so their results can be compared.

## 0. Summary

| What | Where | When | Time per node |
|---|---|---|---|
| Part A: describe the node, check it is not a duplicate | every node | now | ~15 min |
| Setup: pinned Firecracker, guest kernel and guest image | every node | now | 30-60 min |
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
- The human gives each node a number, `node01`, `node02`, … (never the real hostname). Write the numbers down once, here:

  | Number | What the human calls it (kept outside the repository) | Assigned |
  |---|---|---|
  | node01 | | |

  Only the number goes into the repository.
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
4. **Same machine state.** Ask the human for: performance CPU governor during Part B (restore afterwards), turbo left at the
   firmware default, laptops on mains power, no other workload, no other agent session on the node. `node_run.sh` records
   governor, turbo, power, load and throttling messages before and after every stage (`env-<stage>.txt`). If the human
   refuses a setting, record that; do not work around it.
5. **Same reference.** Relative machine speed is computed against one reference node, named in `calibration/REFERENCE`
   (the human chooses; default `node01`). Every node measures the same functions at the same sizes, so ratios are defined.
6. **Same rules for gaps.** A value that cannot be measured stays missing, with the reason. Never copy a value from another
   node, an earlier run or the literature.

## 5. The session on one node, step by step, with times

| Step | Command | Expected time | Human needed |
|---|---|---|---|
| 0. Read | `AGENTS.md`, this file, `CALIBRATION_HANDOFF.md`, `CALIBRATION_DATA_CONTRACT.md` | 15 min | answers §0.4 of the handoff |
| 1. Branch | `git checkout -b calib/<label> origin/revision-v2` | 1 min | |
| 2. Part A | `bash tools/calibrate/node_run.sh spec <label> nvme=<dir> sata=<dir> hdd=<dir>` (the classes it has) | 10-15 min | name a scratch dir on every disk |
| 3. Fill gaps | add `manual` fields the script cannot see (contract §1) | 5 min | maybe |
| 4. Push spec | commit `calibration/specs/<label>/`, push `calib/<label>` | 2 min | |
| 5. Setup | `bash tools/calibrate/node_run.sh setup <label>` (asks before installing packages) | 30-60 min | approve installs |
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
| `tls`, `keys` | 1,000 handshakes, 200 key requests, `openssl speed` | 5 min |
| `fc_boot`, `fc_snapshot` | 100 boots per memory size, tier and page-cache state; 50 snapshots and restores per tier | 30-90 min per tier (HDD: upper end) |
| `sebs` | 10 functions × 5 input sizes × 30 runs; co-run at 1…cores and threads × 30; memory and snapshot size | 2-6 h |

`timeline.csv` records the start, end and duration of every suite. Report the actual total in the validation report, so
the next node's estimate is better.

**Parallel nodes.** Nodes are independent; run them at the same time if you like. Only step 4 (push the spec before Part B)
orders them. The builder session reviews and merges each node's PR.

## 6. When a session stops and asks

The rules of `CALIBRATION_HANDOFF.md` §8, plus:
- `node_run.sh` exits 3 (duplicate node), 4 (harness differs from the lock) or 5 (a suite failed): stop and tell the human.
- `assets.sha256` shows a Firecracker or kernel checksum different from another node's: stop.
- Load average above 0.5 during Part B, or throttling messages appear: tell the human, repeat the affected suite.

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

Replace `NN` and the scratch directories. Use the same text on every node.

```text
You are working on the VOSS research repository (GitHub: aalhadsawane/voss) on bare-metal Linux node nodeNN, with sudo.
Check out branch revision-v2. Read AGENTS.md, then docs/handoff/NODE_PLAN.md, docs/handoff/CALIBRATION_HANDOFF.md and
docs/handoff/CALIBRATION_DATA_CONTRACT.md, in that order, and follow them exactly. This node's number is nodeNN; choose
its label as NODE_PLAN.md §3 says. Run every measurement through tools/calibrate/node_run.sh, never suite by suite.
Push the node spec (NODE_PLAN.md §5 step 4) before Part B. Stop and ask me if node_run.sh exits 3, 4 or 5. Never
reboot, change BIOS settings, install packages or change system settings without my explicit approval in this
session. Do not reuse any number from earlier runs or other nodes. Record the time each step took.
```
