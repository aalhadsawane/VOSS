# VOSS experiment handover

Prepared: **2026-11-27 15:10 IST** for the 18:00 IST machine handover.
This is the read-this-first file. It records what completed, where every result
lives, what can continue elsewhere, and what was cleaned up.

## Short answer

- **Finished:** D01a, D02_DROP, R05, R06, R08, R09.
- **Partial:** R04, **28 of 480 runs**.
- **Not started on colvas:** R01, R02, R03, R07; they are on GitHub Actions.
- **V13:** 0/6, never passed the Firecracker guest boot.
- **All colva experiment processes and containers are stopped.**
- **All large run data has been moved to the HDD tier.**
- **GitHub Actions is cloud-only and can continue; it does not need the colvas.**

## Completed runs

| Spec | Completed | Where the raw runs are | Summary in git? |
|---|---:|---|---|
| D01a | 9/9 | colva2 HDD | no; collect later |
| D02_DROP | 12/12 | colva4 HDD | no; collect later |
| R05 | 120/120 | colva1 HDD (60) + colva4 HDD (60) | no; collect later |
| R06 | 90/90 | colva2 HDD | no; collect later |
| R08 | 10/10 | colva4 HDD | yes, `node-R08` |
| R09 | 20/20 | colva4 HDD | yes, `node-R09` |
| R04 | 28/480 | colva3 HDD (27) + colva4 HDD (1) | no; incomplete |
| V13 | 0/6 | none | no |

R08 and R09 summaries are the only new node summaries already produced. The
other collectors were stopped for the handover; their raw Parquet logs are
complete and can be summarised later with `experiments.collect`.

## Data locations

HDD roots differ by machine:

| Machine | HDD root | VOSS data |
|---|---|---|
| colva1 | `/mnt/hdd2/voss-runs/colva1` | `R05/` (60 runs, 45 GB) |
| colva2 | `/mnt/hdd2/voss-runs/colva2` | `D01a/` (9, 7 GB), `R06/` (90, 65 GB) |
| colva3 | `/mnt/hdd2/voss-runs/colva3` | `R04/` (27 runs, 17 GB) |
| colva4 | `/mnt/hdd1/voss-runs/colva4` | `R04/` (1, 643 MB), `R05/` (60, 45 GB), `R08/` (10, 7.3 GB), `R09/` (20, 20 GB), `D02_DROP/` (12, 7.8 GB), `results/node-R08`, `results/node-R09` |

The repositories remain at:

- colva1, colva2, colva4: `/home/voss/voss-run`
- colva3: `/home/voss/voss-v13`

No run directory was deleted. The move is physical; the original SSD paths are
now absent on the machines where data was moved.

## What can continue on another machine

1. **GitHub Actions (no colva needed).** R01, R02, R03 and R07 are on
   `v2-freeze`. They are currently queued for runner capacity, not running on a
   colva.
   Runs:
   - R01 `45964487189`
   - R02 `45964478846`
   - R03 `45964469303`
   - R07 `45964460660`

2. **R04 can resume elsewhere.** Copy the HDD `R04` directories to the target
   machine, keep the `manifest.json` files, and run the same shards. The sweep
   cache skips any run with a manifest. Resume with 8 jobs, not 12; colva3 and
   colva4 failed with `BrokenProcessPool` at 11–12 jobs.
   Remaining: 93 runs on shard 3 and 119 on shard 2, plus all of shards 0 and 1.

3. **D01a, D02_DROP, R05, R06 can be summarised anywhere.** Copy the raw run
   directories to a machine with the repository, then run:
   `python -m experiments.collect <SPEC> --runs <HDD path> --dst results/<name>`.
   This is I/O-heavy: R06 is about 65 GB and took hours. Run it after the
   sweeps, not beside them.

4. **R08 and R09 analysis can start now**; their summaries are in `node-R08` and
   `node-R09`.

5. **V13 cannot move to a colva.** It needs node02-class hardware, a TPM quote
   and Firecracker assets. It never produced a rep; do not report it.

## Reproducing the numeric environment

Reported runs require the numeric canary `c72c6744cad261c1`. On a colva the
known-good pattern is an Ubuntu 24.04 container with:

```text
NPY_DISABLE_CPU_FEATURES="X86_V4 X86_V3 AVX512_ICL AVX512_SPR AVX2 FMA3"
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
```

Check it before a sweep:

```bash
python -c "from voss.core.numerics import canary, EXPECTED_CANARY; print(canary(), EXPECTED_CANARY)"
```

A host run without the container did **not** reproduce the canary and is
diagnostic only.

## Capacity lessons

- **8 jobs** is the safe setting after the `BrokenProcessPool` failures; 12 is
  borderline on a 62 GB host and failed on colva3/colva4.
- Use **48 GB** container memory and CPUs `2-17`; leave CPUs 0–1 for sshd.
- Never run 20 jobs on a 62 GB colva; that caused the global OOM and loss of
  login.
- Mount the HDD **before** creating the container. A bind mount added after
  container creation is masked by `rprivate` propagation and the container
  writes to the SSD directory instead. colva2 was recreated for this reason.

## Handy commands

```bash
dssh colva1 'hostname'                    # working connection wrapper
dssh colva2 'hostname'
dssh colva3 'hostname'
dssh colva4 'hostname'

# inspect HDD data
dssh colva4 'du -sh /mnt/hdd1/voss-runs/colva4/*'

# resume R04 on a machine with the data copied
python -m experiments.sweep R04 --shard 3/4 --jobs 8 --out <runs-parent>

# summarise completed raw runs
python -m experiments.collect R06 --runs <runs-parent> --dst results/node-R06
```

Use `dssh`, not raw interactive `sshpass`. Never reboot colva1; it is the lab
jump host.

## Cleanup performed

- Stopped and killed `experiments.sweep` and `experiments.collect` on all four
  colvas.
- Stopped and removed the VOSS Docker containers (`noble` on colva1/2/4,
  `voss-r04` on colva3).
- Moved completed and partial run data to the HDD tier; no VOSS run data remains
  on the SSDs.
- Copied R08/R09 summaries to `results/node-R08` and `results/node-R09` and
  pushed them on `results/node-2026-11-27`.
- Stopped remote opencode servers and the colva4 tmux session.
- Killed V13 work; no V13 process remains.
- Did not reboot any machine.

## Open items

1. R04: 452 runs remain; resume from HDD with 8 jobs.
2. R01/R02/R03/R07: watch GitHub Actions; cancel or rerun as needed.
3. D01a/D02_DROP/R05/R06: collect summaries and commit them.
4. V13: needs node02 and a Firecracker boot fix; not covered by the colva data.
5. Paper tables/figures: R08/R09 can be filled; R04 and R01–R03/R07 remain.
