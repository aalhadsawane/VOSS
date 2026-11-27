# Experiment status and node schedule

Last updated: **2026-11-27 14:55 IST**
Owner: VOSS experiments. Update this file whenever node or Actions status changes.

## Current status

| Workload | Where | Completed | Running | Notes |
|---|---|---:|---|---|
| D01a | colva2 | **9/9** | no | complete, cached |
| D02_DROP | colva4 | **12/12** | no | complete, cached |
| R08 | colva4 | **10/10** | no | complete, cached |
| R06 | colva2 | **90/90** | no | complete |
| R09 | colva4 | **20/20** | no | complete |
| R05 | colva1/colva4 | **120/120** | no | complete; four shards indexed |
| R04 | all four nodes | **28/480** | 12 + 12 + 8 + 8 jobs | colva3/colva4 restarted at 8 jobs after `BrokenProcessPool` |
| V13 | colva3 | **0/6** | no | still failing at Firecracker guest boot |
| R02 | Actions | — | queued | plan job waiting; may hit 5h40 |
| R04 | Actions | partial | canceled | many shards hit 5h40; node path is primary |
| R01/R03/R07 | Actions | — | canceled | not currently scheduled |

R05 shard 0 failed with `BrokenProcessPool`/container OOM at **12 jobs**. R06
failed the same way at **20 jobs**, R09 at **12 jobs**. All are now capped at
**10 jobs**, except the two concurrent R05 shards on colva4, which use **8 jobs
each**.

## Node schedule

### colva1

| Time (IST) | Workload | Notes |
|---|---|---|
| complete | R05 | 60/60 locally |
| 13:06–28 Nov ~17:00 | R04 shard 0/4 | 120 runs, 12 jobs; HDD output |

### colva2

| Time (IST) | Workload | Notes |
|---|---|---|
| complete | R06 | 90/90 |
| 14:14–28 Nov ~18:00 | R04 shard 1/4 | 120 runs, 12 jobs; HDD output |

### colva4

| Time (IST) | Workload | Notes |
|---|---|---|
| 14:48–29 Nov ~09:00 | R04 shard 2/4 | 119 remaining, 8 jobs; restarted after failure |
| running | R05 result collection | separate process, 60 runs |

### colva3

| Time (IST) | Workload | Notes |
|---|---|---|
| 14:48–29 Nov ~00:30 | R04 shard 3/4 | 93 remaining, 8 jobs; restarted after failure |
| after R04 | V13 fix + 6 reps | still failing; needs debugging |

## Completion estimates

| Workload | Expected finish |
|---|---|
| R09 | **26 Nov, ~02:30 — complete** |
| R06 | **26 Nov, ~23:30 — complete** |
| R05 | **26 Nov, ~23:30 — complete** |
| R04 colva1 shard | 28 Nov, ~17:00 |
| R04 colva2 shard | 28 Nov, ~18:00 |
| R04 colva3 shard | 29 Nov, ~00:30 |
| R04 colva4 shard | 29 Nov, ~09:00 |
| R04 overall | **29 Nov, ~09:00** |
| Result collection and push | 29 Nov, ~12:00 |
| V13 (only if run) | 30 Nov, ~02:00 on colva3 |
| Deadline | 27 Nov, 15:00 (missed) |

**Reserve the four colvas through 29 Nov, 14:00 IST** for R04 plus result
collection. If V13 is attempted, keep **colva3 through 30 Nov, 06:00 IST**; the
other three can be released on 29 Nov.

R05, R06 and R09 are complete. R04 is behind schedule: colva3 reached 27/120 and
colva4 1/120 before `BrokenProcessPool` stopped them; both are restarted at 8
jobs. colva1/colva2 continue at 12 jobs with HDD output.

## GitHub Actions

- **R01, R02, R03, R07 dispatched** on `v2-freeze` at 13:35 IST:
  runs `45964487189` (in progress), `45964478846` (in progress),
  `45964469303` (queued) and `45964460660` (queued).
- **R04:** canceled on Actions; node shards are the R04 path. Before
  cancellation, 82 shard jobs completed, 40 were running and 39 were queued.
  Many failed at the **5h40** job limit.
- No self-hosted runners; all Actions jobs use `ubuntu-latest`.

## Disk status

colva2 is the constraint:

The colvas have an HDD tier (`/mnt/hdd2`, plus `hdd3`/`hdd4` on colva1). R04
outputs go there where the SSD is tight:

- colva1: SSD **239 GB free**; R04 shard 0 writes to `/mnt/hdd2/voss-runs`.
- colva2: SSD **40 GB free**; R04 shard 1 writes to HDD via
  `/home/voss/voss-run/hdd`.
- colva4: SSD **1.2 TB free**; R04 shard 2 stays on SSD.
- colva3: SSD **123 GB free**; R04 shard 3 stays on SSD.
- HDD capacity: about **1.5 TB free** on colva1 and **1.8 TB free** on colva2.

Keep large run outputs on HDD when the SSD is tight. Do not delete `runs/`
without a copy elsewhere.

## Capacity rules

Every active R04 container uses:

```text
--memory=48g --memory-swap=48g
--cpuset-cpus=2-17 --cpus=12
--jobs 12
nice -n 10
```

colva1 and colva2 additionally mount the HDD tier; their R04 output does not
count against the SSD. colva3 uses `--cpus=11` and 11 jobs. Never run 20 jobs on
a 62 GB node. Completed runs are identified by `manifest.json`; do not delete
`runs/`.

## Remote control

- opencode server on **colva4**, port **4096**, tmux session `opencode`.
  Password is kept out of this file.
- All sweeps are detached from SSH and survive laptop sleep.

## Update log

- **2026-11-25 17:50 IST:** recovered from OOM reboot; restarted R05 as four
  shards, R06/R09 capped at 12 jobs; R04 placed on nodes; opencode server
  restarted on colva4. Actions R04 found to be timing out at the 5h40 limit.
- **2026-11-25 17:55 IST:** canceled Actions R04 to release the queue for R02;
  node-side R04 remains the primary R04 path.
- **2026-11-25 21:15 IST:** R05 shard 0, R06 and R09 all hit container OOM at
  12/20 jobs. Restarted them at 10 jobs with 40 GB limits. R05 shard 1 moved
  from colva2 to colva4 alongside shard 2. Pruned 58 GB of unused Docker images
  on colva2; disk is still tight for R04.
- **2026-11-25 22:25 IST:** R06 is 20/60 and running clean at 10 jobs; R09 is
  8/20 and running clean; R05 shard 0 is running with 0 manifests so far. colva2
  has 52 GB free. V13 is still 0/6 and not running. R04 remains at risk: colva2
  cannot fit its 120-run shard, and colva3 still needs Docker/repo setup.
- **2026-11-26 02:35 IST:** R09 completed 20/20. R05 shard 0 and R06 both hit
  container OOM again at 10 jobs; R05 has only 1/30 in shard 0. Restarted R05 as
  four 6-job shards and R06 at 8 jobs. R05/R06 now finish around 15:00 on 26 Nov,
  which pushes R04 past its 15:00 deadline on 27 Nov; R04 is no longer
  achievable without a different allocation.
- **2026-11-26 12:50 IST:** R09 complete. R06 is **73/90** with 17 remaining,
  finishing around 20:15. R05 is **60/120**: shards 0 and 2 completed; shards 1
  and 3 failed with `BrokenProcessPool` and were restarted alone at 6 jobs,
  finishing around 01:20 on 27 Nov. colva2 is down to 27 GB free. R04 at 120 runs
  per node now finishes after 21:15 on 27 Nov, so the 15:00 deadline is missed.
- **2026-11-26 15:10 IST:** R06 is **81/90** with 9 remaining. R05 remains
  **60/120**; shards 1 and 3 are still running at 6 jobs, now expected around
  23:15. colva2 has 53 GB free. Colva3 is being set up with a Docker R04
  container so its idle capacity is used for the fourth R04 shard.
- **2026-11-26 15:55 IST:** colva3 Docker R04 container is up, its numeric
  canary matches, and R04 shard 3/4 is running with 11 jobs. The shard finishes
  around 19:20 on 27 Nov; the other R04 shards finish on 28 Nov, so R04 misses
  the 27 Nov 15:00 deadline. dssh was fixed for colva1 and now has a one-shot
  jump fallback for colva2/3/4; all node checks use dssh again.
- **2026-11-26 23:30 IST:** R05 finished **120/120** and R06 finished **90/90**;
  R09 was already complete. R04 shard 3/4 is running on colva3 and shard 2/4 on
  colva4. colva1 and colva2 are idle because their 120-run R04 shards do not fit
  in 28 GB and 40 GB free respectively; completed R05/D01a/R06 results need to
  be moved off before those shards start. V13 remains 0/6.
- **2026-11-27 13:10 IST:** used the HDD tier. colva1 R04 shard 0 writes to
  `/mnt/hdd2/voss-runs`; colva2 R04 shard 1 writes through a bind mount at
  `/work/hdd`. All four R04 shards are now running. Expected R04 completion is
  about 14:05 on 28 Nov; V13 remains 0/6.
- **2026-11-27 13:40 IST:** dispatched **R01, R02, R03 and R07** to GitHub
  Actions on `v2-freeze`; all four have completed their plan job and are queuing
  sweeps under the 40-job limit. colva2's R04 container was raised to 48 GB and
  12 CPUs; colva1/colva2 R04 output stays on HDD. Node result collection is
  running for D01a, D02_DROP, R05, R06, R08 and R09.
- **2026-11-27 14:55 IST:** R04 is **28/480**. colva3 stopped at 27/120 and
  colva4 at 1/120 with `BrokenProcessPool`; both restarted at **8 jobs**.
  colva1/colva2 continue at 12 jobs. R08 and R09 summaries are collected;
  D01a/R05/R06 collection is still running. Expected R04 completion is **29 Nov
  ~09:00**, result push ~12:00. Reserve all colvas through **29 Nov 14:00**; keep
  colva3 through **30 Nov 06:00** only if V13 is attempted.
