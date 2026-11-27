# Experiment status and handover snapshot

Last updated: **2026-11-27 15:10 IST**
Status: **stopped and archived for machine handover.**
Read `docs/handoff/HANDOVER.md` first for the full guide.

## Machine state

- **No VOSS experiment process is running on any colva.**
- VOSS Docker containers are stopped and removed: `noble` on colva1/colva2/colva4
  and `voss-r04` on colva3.
- Remote opencode servers and the colva4 tmux session are stopped.
- All run data is moved to the HDD tier; no VOSS run data remains on the SSDs.
- R08/R09 summaries are committed on `results/node-2026-11-27`; raw run data is
  on the HDDs.
- No machine was rebooted. **colva1 must not be rebooted; it is the lab jump
  host.**
- **No colva reservation is needed from now on.** The machines can be handed to
  the other user.

## Completed results

| Spec | Completed | Raw data location | Summary in git |
|---|---:|---|---|
| D01a | 9/9 | colva2 HDD `D01a/` | no; collect later |
| D02_DROP | 12/12 | colva4 HDD `D02_DROP/` | no; collect later |
| R05 | 120/120 | colva1 HDD `R05/` + colva4 HDD `R05/` | no; collect later |
| R06 | 90/90 | colva2 HDD `R06/` | no; collect later |
| R08 | 10/10 | colva4 HDD `R08/` | `results/node-R08` |
| R09 | 20/20 | colva4 HDD `R09/` | `results/node-R09` |
| R04 | 28/480 | colva3 HDD `R04/` (27) + colva4 HDD `R04/` (1) | no; incomplete |
| V13 | 0/6 | none | no |

R05, R06, D01a and D02_DROP are complete but their collectors were stopped at
15:10; the raw Parquet logs are intact. `experiments.collect` can summarise
them later; R06 is about 65 GB and takes hours.

## HDD data roots

| Machine | Root |
|---|---|
| colva1 | `/mnt/hdd2/voss-runs/colva1` |
| colva2 | `/mnt/hdd2/voss-runs/colva2` |
| colva3 | `/mnt/hdd2/voss-runs/colva3` |
| colva4 | `/mnt/hdd1/voss-runs/colva4` |

Nothing was deleted. The data was moved off the SSDs, not copied, except the
small `results/` trees.

## R04

- colva3 stopped at **27/120** and colva4 at **1/120** with
  `BrokenProcessPool`.
- colva1 and colva2 had not completed a run when the handover stopped them.
- R04 is archived but **not complete**; do not report it as a result.
- Resume on another machine with 8 jobs after copying the HDD `R04` trees; the
  `manifest.json` cache skips completed runs.

## GitHub Actions

R01, R02, R03 and R07 were dispatched on `v2-freeze` and are cloud-only; they do
not use the colvas. At handover they had completed their plan jobs and were
waiting for runner capacity:

- R01 `45964487189`
- R02 `45964478846`
- R03 `45964469303`
- R07 `45964460660`

These can continue after the machine handover. Watch or cancel them from any
machine with `gh`.

## V13

V13 is **0/6** and still fails at Firecracker guest boot. It needs node02-class
hardware, the measured calibration bundle, a live TPM quote and the Firecracker
assets. It is not runnable on the colvas and no emulation result exists.

## Handover tips

- Use `dssh`, not raw interactive `sshpass`.
- A reported run needs numeric canary `c72c6744cad261c1`.
- Run inside the Ubuntu 24.04 container with
  `NPY_DISABLE_CPU_FEATURES="X86_V4 X86_V3 AVX512_ICL AVX512_SPR AVX2 FMA3"`.
- Use 8 jobs, 48 GB memory, CPUs `2-17`; 20 jobs caused the earlier global OOM.
- Mount the HDD **before** creating the container; a later bind mount is masked
  inside the container.
- Do not delete `runs/`; `manifest.json` is the resume cache.
