# Emulation runbook (plan V13, handoff Part E)

How to run the multi-worker emulation on the node and compare it with the simulator. **No emulation run has been
performed yet**: this file is the procedure the bare-metal session follows, written before the first run. Nothing here
is a result.

Companion documents: `docs/handoff/CALIBRATION_HANDOFF.md` Part E (what the session does), `docs/handoff/
CALIBRATION_DATA_CONTRACT.md` §7 (what it delivers), `docs/architecture/10-calibration.md` §4 (the design), and
`docs/DECISIONS.md` D-136 (what is isolated and what is not).

## 0. What a run is

One emulation run is **one scenario × one system × one repetition**, executed in real time:

- 6 emulated workers (the handoff's 6-10), each one **process tree** of real Firecracker microVMs, pinned to its own
  physical P-core, under its own cgroup v2 memory limit, in its own network namespace with the scenario worker's own
  access link injected by `tc netem` (one-way last-mile delay, up and down bandwidth);
- **real sandboxes**: the measured functions run in the guest, and boot, snapshot and restore are real Firecracker
  operations (the same `tools/calibrate/fc.py` the calibration bundle was measured with);
- a **real `tpm2_quote` at every session start** on the machine's TPM, with one attestation key created per run;
- the **scheduler, routers, verifier, registry and key services** as actors on the coordinator process, pinned to
  cores no worker may use, with their decision time charged from the wall clock (`decision_clock.mode=measured`,
  scale 0). They are not separate OS processes: D-136 says why and the report says it too;
- **arrivals and session ends from the scenario file** `configs/emu/s1_central.yaml` (2 h, six workers, `voss` and
  `fixed_keepalive`, seeds 1-3).

The emulator and the simulator run the **same scenario file**, so a pair shares its scenario hash. The builder produces
the simulator side from the same file with `--emit-sim-spec` (step 3 below).

## 1. Prerequisites

| What | Requirement | Check |
|---|---|---|
| Machine | node02, bare metal (not a VM), Linux, x86_64 | `systemd-detect-virt` prints `none` |
| Cores | 8 physical P-cores for 6 workers + 2 provider cores; one kind only | `bash tools/emu/preflight.sh` |
| Memory | 32 GB or more (6 workers × 4 GB cgroup limit plus the provider roles and page cache) | `free -g` |
| KVM | `/dev/kvm` readable by the user running the run | `ls -l /dev/kvm` |
| Root | netns, `tc`, cgroups and pinning need it | `sudo -n true` |
| Kernel modules | `sch_netem`, cgroup v2 with the memory controller | `modprobe -n sch_netem`; `/sys/fs/cgroup/cgroup.controllers` |
| TPM | `/dev/tpmrm0` (Intel PTT on node02) and `tpm2-tools` | `tpm2_getcap properties-fixed` |
| Assets | `~/voss-calib/assets/{firecracker,vmlinux,voss-guest.ext4}` | `ls ~/voss-calib/assets` |
| Storage | 50 GB free under `/var/tmp` (snapshots and VM memory files) | `df -h /var/tmp` |
| Traced inputs | `data/traces/boinc-rosetta/hosts.parquet` (the fleet survey), `data/traces/ookla-fixed-2024q1/links.parquet` (the worker links the injected delay and bandwidth come from), `data/traces/seti09/sessions_dev.parquet` (the session trace: since the freeze it is the only session model) | `ls data/traces` |
| Code | `revision-v2` at the commit that carries this harness; no local edits | `git status --short` (empty) |

Build the assets exactly as in the calibration visit (handoff Part B): `tools/calibrate/guest/fetch_assets.sh` and
`tools/calibrate/guest/build_rootfs.sh`. The emulation uses the same images as the bundle, which is the point. The
traced inputs are the release assets the calibration visit already fetched; `--dry-run` names the first file that is
missing.

## 2. Commands

Everything below runs from the repository root on the node, as root (`sudo -E`), with the repository's venv
(`.venv/bin/python`; `uv run` also works but may try to sync as root).

```sh
# 0. the read-only audit; paste its output into the report
bash tools/emu/preflight.sh | tee ~/voss-calib/preflight-v13.txt

# 1. the harness's own checks, then the plan without touching anything
uv run python -m tools.emu.preflight configs/emu/s1_central.yaml
uv run python -m tools.emu.run configs/emu/s1_central.yaml --system voss --rep 1 --dry-run

# 2. six runs: 2 systems x 3 repetitions, 2 h each (about 12 h of machine time)
for s in voss fixed_keepalive; do
  for r in 1 2 3; do
    sudo -E .venv/bin/python -m tools.emu.run configs/emu/s1_central.yaml \
      --system "$s" --rep "$r" --out runs-emu/node02-i7-12700-64g-nvme/ || break 2
  done
done

# 3. the simulator side of the same scenario (the builder can also run this on GitHub Actions)
uv run python -m tools.emu.run configs/emu/s1_central.yaml --system voss --rep 1 \
  --out /tmp/unused --emit-sim-spec runs/emu-s1_central-spec.yaml
uv run python -m experiments.runner runs/emu-s1_central-spec.yaml --out runs

# 4. the side-by-side table and the report draft
uv run python -m tools.emu.compare --emu runs-emu/node02-i7-12700-64g-nvme --sim runs/emu-s1_central
```

Each run writes `runs-emu/<host_label>/<system>/rep<i>/`: the simulator's own tables (`invocations`, `attempts`,
`events`, `samples`, `cache`, ...), `manifest.json` (config, scenario hash, code commit, result hash) and `emu.json`
(host, layout, isolation command count, per-worker self-check and OOM counters, TPM statistics, kernel lag). The
`--out` root is the host label of `NODE_PLAN.md` §3, never the real hostname.

`tools.emu.compare` writes `runs-emu/<host_label>/report/{compare.md,report.md,pairs.csv,cdf-*.pdf}`. `report.md` is
the draft of `docs/validation/emulation-<host_label>.md`: fill in the machine, the code revision, the preflight output
and one sentence per disagreement, then commit it with the runs.

## 3. What is real and what is simulated

| Real on the node | Modelled (the same code both sides run) |
|---|---|
| Firecracker boot, snapshot, restore, and the measured function in the guest | Every actor message: delay, bandwidth, loss, TLS handshake and per-message cost (`voss.world.network`) |
| The TPM quote at every session start (and its latency) | Attestation beyond the quote (verifier check, certificate), key release and key-service work |
| Worker cores, memory limit and network namespace, and the injected link (self-checked with a ping inside the namespace) | The volunteer machines other than node02, their availability and their owners |
| Arrivals and session ends (from the scenario), the policy code and its measured decision time | Wide-area propagation delay (peer-dependent, so it stays in the model) |

The injected link shapes traffic the worker's own processes generate; it is **not** added on top of the modelled
delays, which would count the same link twice. Both sides therefore see the scenario's links exactly once, which is
what makes the comparison meaningful.

**Load.** The measured functions run in 25 µs to 0.17 s on node02, so a single node can serve only a few tens of
invocations per second; the scenario asks for 20/s, which the simulator puts at roughly 15-20% slot utilisation. The
emulation is a **timing validation at low load**, not the R01 operating point, and the report must say so. If
`emu.json` shows `kernel_max_lag_s` above about 0.5 s, or the emulation's deadlines met are far below the simulator's
while its queues are saturated, the node cannot serve the offered load: stop, report it, and let the builder lower
`scenario.load.rate` in the scenario and re-run **both** sides. Never change one side alone.

## 4. When a step fails

| Symptom | Cause and what to do |
|---|---|
| `preflight.sh` reports `[FAIL] no /dev/tpmrm0` | Firmware TPM (Intel PTT) disabled. Ask the human to enable it in the firmware; do not run with `--no-tpm` (that is not a V13 run). |
| `[FAIL] sch_netem missing` | `linux-modules-extra-$(uname -r)` is not installed. Ask before installing. |
| `[FAIL] /sys/fs/cgroup not writable` | Not root, or cgroup v1. Run as root; if the host boots cgroup v1, stop and report (the harness needs cgroup v2). |
| `preflight: N workers x 1 core(s) + 2 provider core(s) need 8 P core(s)` | The machine has fewer P-cores than the scenario asks for. Lower `emu.workers` **and** `scenario.workers` together (they must be equal) and say so in the report. |
| `ip netns exec ...: Cannot open network namespace` during a run | A session end removed the namespace while a sandbox was being spawned; the harness retries once. If it repeats, the run is invalid: keep `emu.json`, report it. |
| `TPM quote failed` | The TPM is busy or the AK was lost. Re-run the repetition from scratch (`--force`); a run with a failed quote is not a run. |
| `RuntimeError: emulation backend failure` | A real action (boot, restore, execute) failed twice. Keep the directory, note the worker and function from `emu.json`/stderr, and report it. |
| `free disk under ... is 12.3 GB: aborting` | Snapshots filled the work dir. Delete `emu.workdir/fc` and `emu.workdir/snap` (only those: they are regenerated) and re-run. |
| `... already has a manifest` | The run exists. `--force` overwrites it; do not overwrite a run you have not compared yet. |
| A run is much slower than 2 h | The emulator is not keeping up: check `kernel_max_lag_s` in `emu.json` and §3's load note. |
| `compare` reports "no simulator run with label ... and seed ..." | The simulator runs are missing or carry no `label`. Re-run step 3 and pass the `runs/emu-s1_central` directory. |
| `compare` reports "scenario hashes differ" | The two sides were generated from different scenario files or seeds. Do not compare them; regenerate both from `configs/emu/s1_central.yaml`. |

Never fill a gap with an estimate. A failed repetition is reported as failed.

## 5. The session trace, and what to say in the report

Since the freeze cleanup (checklist 2.9) there is no synthetic session model: sessions come from
`data/traces/seti09/sessions_dev.parquet`, where every worker replays one SETI@home host's week of availability
(V9.2). Six workers therefore follow six real hosts, and how many sessions start and end inside the 2 h window is
whatever those hosts did — possibly very few. `emu.json` records the attested sessions and the backend counters record
every session end; the report states both, and it does not claim that the run exercised session churn that the trace
did not contain. If the window contains no session end, say so and re-run a repetition rather than editing the
scenario: the seed chooses the hosts, the file stays as the builder prepared it.

The fleet is one class (node02 itself), so `survey` only weights classes and has no effect on this run (D-107). No
machine class file is involved: `configs/hardware/` no longer exists.

## 6. What to deliver

1. `runs-emu/<host_label>/<system>/rep<i>/` for the six runs (tables, manifest, `emu.json`).
2. `runs-emu/<host_label>/report/` from `tools.emu.compare`.
3. `docs/validation/emulation-<host_label>.md`: the human's answers from the handoff §0.4, the preflight output, the
   side-by-side table with the spread over the three repetitions, and one sentence for every disagreement larger than
   the spread. Do not tune anything to make the two agree; a disagreement is the finding.
4. A PR into `revision-v2` titled `Emulation: <host_label>`.
