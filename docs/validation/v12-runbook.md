# V12 held-out runbook (prepared; no held-out run has started)

Prepared on branch `v2/V12-requests` from `revision-v2` at `b7b5921`. The `d01a-cleanup` request and the first
version of this runbook landed in PR #138; this update travels with draft PR #136, which holds the held-out R01-R09
request files and the R08 bench request. **No `r0*` request file may land on `revision-v2` before the `v2-freeze` tag**
(`docs/FREEZE_CHECKLIST.md` 5.4). The D01a cleanup run 45138203406 started by `workflow_dispatch` and failed before
any simulation because the D01a spec's calibration override no longer resolves against the fleet (§5 step 2); no
held-out run has started.

The D-135 pipeline is in `revision-v2` (`experiments/merge_results.py`): each shard collects its own summary and
hashes, the publish job merges them, and the release carries the merged files plus one raw-log run from every 100th
shard (shards 0, 100, 200).

## 1. Runs

| Spec | Systems | Grid cells | Seeds | Runs | Shared with R01 | Distinct new |
|---|---|---|---|---|---|---|
| R01 | 8 | 15 (`K` 5 × load 3) | 10 | 1,200 | — | 1,200 |
| R02 | 8 | 1 (central cell) | 10 | 80 | 80 | 0 |
| R03 | 9 | 18 (pool 3 × load 3 × notice 2) | 10 | 1,620 | 0 | 1,620 |
| R04 | 4 | 12 (alpha 3 × strategy 4) | 10 | 480 | 0 | 480 |
| R05 | 1 | 12 (class-P 2 × forge_p 2 × p 3) | 10 | 120 | 0 | 120 |
| R06 | 9 | 1 | 10 | 90 | 10 | 80 |
| R07 | 89 | 1 | 10 | 890 | 10 | 880 |
| R08 | 1 | 1 | 10 | 10 | 10 | 0 |
| R09 | 2 | 1 | 10 | 20 | 10 | 10 |
| **Total** | | | | **4,510** | **120** | **4,390** |

Counted from the current specs with `experiments.sweep.plan()` and compared by config hash: the 120 shared points are
R02's 80 central-cell runs plus 40 repeats of the same 10 `voss` central-cell runs in R06-R09 (so the 120 duplicates
cover 80 distinct R01 configs).

**Distinct held-out runs: 4,390. Total including verification repeats: 4,408** (4,390 + 18 reruns, §4). The sweep as
written executes **4,510** points: `experiments/sweep._one` caches only under `runs/<spec>/<hash>`, and each job
starts from a fresh checkout, so the shared cells run again under R02/R06/R07/R08/R09. D-135 publishes only a raw
sample, not every run's raw directory, so the shared cells can no longer be seeded from the release: **4,510
executions is the operational count** (4,528 with verification). The 4,390 distinct configs remain the reporting
count.

## 2. Shard plan

### 2.1 Assumptions

- One shard = one `sweep` job of `experiment.yml`, timeout **340 min** (20,400 s).
- Measured per-run wall time: the 66 runs of `results/*/summary.parquet` (D01a and D02, 500 workers, `K` = 8,
  `rate_mult` 21, 28 h): mean **5,152 s (86 min)**, p50 5,250 s, p90 7,149 s, max 7,899 s (132 min).
- Wall time scales with arrivals (D-97: 130 M events at `rate_mult` 30 in 114 min), so rate-30 cells are assumed
  1.43× the rate-21 wall.
- 10% for the post-freeze code (D-113 plans without the caps; the D01a cleanup measures it) and 10% for co-running
  processes on one runner.
- 8 min per job for checkout, `uv sync` and the trace fetch; **2 min per run** for the new per-shard
  `experiments.collect` step (estimate; the D01a cleanup and the first R01 shard measure it).
- A shard's wall is the pool's list schedule (runs start as workers free), not `sum(runs)/jobs`: a 5-run shard on 4
  workers takes two run-times, not 1.25. The table below is a bootstrap over the measured per-run distribution
  (within system, scaled by `rate_mult`, with the margins), taking the maximum over the shards of each spec.

### 2.2 Shard counts

| Spec | Runs | Shards | Runs per shard |
|---|---|---|---|
| R01 | 1,200 | 240 | 5 |
| R02 | 80 | 27 | 2-3 |
| R03 | 1,620 | 232 | 6-7 |
| R04 | 480 | 160 | 3 |
| R05 | 120 | 40 | 3 |
| R06 | 90 | 20 | 4-5 |
| R07 | 890 | 237 | 3-4 |
| R08 | 10 | 5 | 2 |
| R09 | 20 | 7 | 2-3 |
| **Total** | **4,510** | **968** | |

The counts are the `--jobs 3` layout: 3 runs per shard on R02/R04/R05 (one round on 3 workers), 4-5 on R06, 3-4 on
R07, 5 on R01 and 7 on R03. The **256-job matrix limit** sets the minimum runs per shard for the two large specs: R01
cannot have more than 256 shards, so it needs 5 runs per shard; R03 needs 7. R06 (20 shards) and R07 (237) are under
the cap, and their 4-5 and 3-4 runs per shard stay under 340 min even at 3 jobs (R06 is the closest at p99 337). With
D-135 the release-asset limit no longer constrains the shard size.

### 2.3 Runner memory, `--jobs` and the timeout

Measured peak RSS is **4.5-4.8 GB per 28 h run** (`resource.getrusage` in the manifest), and the standard
GitHub-hosted runner has **16 GB**:

- **`--jobs 4` is not assumed safe on 16 GB**: 4 × 4.8 = 19.2 GB, over the runner. `nproc` on the 4-vCPU runner is 4,
  so the workflow's `--jobs "$(nproc)"` as written would run 4 processes and can be OOM-killed. The D01a cleanup is
  the empirical gate (last bullet).
- **`--jobs 3` fits memory** (3 × 4.8 = 14.4 GB, 90% of 16 GB) but not the timeout for R01 and R03:

| Spec | Shards | Runs/shard | `--jobs 3` mean | `--jobs 3` p99 | `--jobs 6` mean | `--jobs 6` p99 |
|---|---|---|---|---|---|---|
| R01 | 240 | 5 | 232 min | **367 min** | 172 min | 246 min |
| R02 | 27 | 2-3 | 132 min | 173 min | 132 min | 173 min |
| R03 | 232 | 6-7 | 284 min | **426 min** | 195 min | 299 min |
| R04 | 160 | 3 | 140 min | 173 min | 140 min | 173 min |
| R05 | 40 | 3 | 152 min | 173 min | 152 min | 173 min |
| R06 | 20 | 4-5 | 238 min | 337 min | 133 min | 177 min |
| R07 | 237 | 3-4 | 187 min | 301 min | 148 min | 175 min |
| R08 | 5 | 2 | 133 min | 171 min | 133 min | 171 min |
| R09 | 7 | 2-3 | 139 min | 173 min | 139 min | 173 min |

At `--jobs 3`, R02 and R04-R09 are safe (p99 171-337 min; R06 is the closest at 337), but **R01 has a 59% chance
that one of its 240 shards exceeds 340 min** (p99 367) and **R03 is certain to** (p99 426, three rounds of 3+3+1
runs at the rate-30 wall). R03 against the 256-job cap: 232 shards of 7 fit the cap, but 6 runs per shard would need
270 shards, over it. So **R03 cannot run at `--jobs 3` on 16 GB within the 340-min timeout and the matrix limit**.
These are per-job limits; the number of concurrent jobs does not change them.

- `--jobs 4` on a ~20 GB runner removes R01's risk (p99 308) but not R03's: p99 380, an 89% chance of one timeout.
- **`--jobs 6` on a 32 GB runner is the safe configuration for the whole sweep** (6 × 4.8 = 28.8 GB, under 32): every
  spec's p99 is at most 299 min, with at least 41 min of headroom. `nproc` on an 8-core runner is 8 (38.4 GB), so the
  sweep step must pass **`--jobs 6` explicitly**; this is a one-line workflow change, not something a request file can
  set.
- **Memory gate.** `d01a-cleanup.yaml` runs the 9 D01a points in **2 shards of 5 and 4**, so each shard starts up to
  4 processes on the 16 GB runner; its peak RSS and completion decide `--jobs 4` versus the split fallback. If it
  passes with headroom, use `--jobs 4` on 16 GB for R01 and the rate-21 specs (R03's timeout still needs 6 jobs on
  the 32 GB runner); if it fails, use `--jobs 3` for R02/R04-R09 and move R01 and R03 to the 32 GB runner (the
  split-R01/R03 fallback).

### 2.4 Release contents (D-135)

Each shard runs `experiments.collect` on its own runs and uploads only `results/partial-<i>` (a summary and a hash
row per run, a few MB); the publish job merges the parts with `experiments.merge_results` and commits one
`summary.parquet` and `hashes.csv` for every run. The release carries those two files plus one raw-log run from
every 100th shard: shards 0, 100 and 200, so at most 3 raw runs per spec and 16 in all (~11 GB), each under 2 GiB.
The old 2 GiB/1,000-asset limit and the ~3 TB full-log download are gone; the publish job moves a few MB of
summaries and ~11 GB of raw samples, not terabytes. The raw sample is a reproduction exhibit, not the archive: every
run is reproducible from its committed config hash, scenario hash and seed (D-135).

### 2.5 Trigger and launch

The push trigger takes only the **first** changed request file of a push
(`git diff --name-only ... | sort | head -1`), so a push of several request files silently skips the rest. The
`workflow_dispatch` path does work on `revision-v2` through the API even though the workflow file is not on `main`
(run 45138203406 was started that way). After the freeze, with the R01-R09 request files on `revision-v2`, launch
**all nine in one batch**:

```
for s in 01 02 03 04 05 06 07 08 09; do
  gh workflow run experiment.yml --ref revision-v2 \
    -f request=runs/requests/experiment/r$s.yaml
done
```

This puts all nine specs in the 40-job queue at once. The push trigger stays as the fallback: if the merge push
itself starts the first file (`r01`), cancel that run before the batch (or let it run and dispatch only `r02`-`r09`);
do not run `r01` twice. A single spec can be relaunched the same way, without a push.

The R08 decision-timing bench (`runs/requests/bench/r08-decision.yaml`) is different: `bench-decision.yml` has only a
push trigger and no `workflow_dispatch`, so it must be **one push after the freeze** (its own commit, or the #136
merge if the bench file lands with it). Its `fit` job writes `configs/calibration/provider/<cpu-label>/decision.yaml`
on a `bench/run-<id>` branch; merge that branch.

## 3. Wall clock

| Configuration | Total job-hours | At 40 concurrent jobs (planning) | At 20 concurrent jobs (fallback) | Timeout verdict |
|---|---|---|---|---|
| `--jobs 3`, 16 GB | 3,407 | 85 h = 3.5 days | 170 h = 7.1 days | R01 and R03 fail |
| `--jobs 4`, ~20 GB | 2,931 | 73 h = 3.1 days | 147 h = 6.1 days | R03 fails (89%) |
| **`--jobs 6`, 32 GB** | **2,633** | **66 h = 2.7 days** | **132 h = 5.5 days** | all pass |

The owner's GitHub plan is **Pro** and the repository is public: **40 concurrent jobs** (20 on Free, 60 on Team),
shared with every other workflow in the account. **40 is the planning assumption**; the 20-job column is the
conservative fallback. 40 concurrent jobs × 4 runs/shard = up to 160 runs in flight (the exact peak is 40 × 3 = 120
with `--jobs 3`, and 40 × 6 = 240 on the 5- and 7-run shards with `--jobs 6`).

The recommended 6-job configuration at 40 jobs: **2.7 days expected**, 72 h = 3.0 days conservative (every run at its
system's p90), 3.0-3.3 days with a 10% tail for the last wave. If the D01a cleanup shows the frozen code 20% slower,
3.3 days expected and 3.6 days conservative; R03's worst shard rises to ~326 min, still under 340. The 3-job
configuration is not a full fallback: it is 3.5 days at 40 jobs *and* cannot run R01/R03.

The per-spec mean and p99 in §2.3 are shard (job) times, not makespans, and do not change with concurrency. If a spec
runs alone, its makespan is `ceil(shards/40) × its mean shard`: R01 17.2 h, R03 19.5 h, R04 9.3 h, R07 14.8 h; R02,
R05, R06, R08 and R09 are one wave (2.2-2.5 h). Run one at a time, largest first, the sum is ~72 h; interleaving all
specs in one 40-slot queue gives the 66 h figure.

## 4. Verification plan

`verify.yml` is one job, no matrix, 340 min, and `experiments/verify.py` reruns the sample **sequentially** in that
job. At the measured wall time, 2 runs = 172 min mean and 264 min even at the slowest measured run; 3 runs at p90 =
357 min, over the timeout. So 2 is the largest sample that always fits a rate-21 spec. R01 and R03 contain rate-30
cells where one run can take ~190 min, so their sample is 1 run per job, dispatched twice.

| Spec | Runs | `frac` | Runs per job | Jobs | Reruns | Salt |
|---|---|---|---|---|---|---|
| R01 | 1,200 | 0.0008 | 1 | 2 | 2 | run id |
| R02 | 80 | 0.025 | 2 | 1 | 2 | run id |
| R03 | 1,620 | 0.0006 | 1 | 2 | 2 | run id |
| R04 | 480 | 0.0041 | 2 | 1 | 2 | run id |
| R05 | 120 | 0.0166 | 2 | 1 | 2 | run id |
| R06 | 90 | 0.0222 | 2 | 1 | 2 | run id |
| R07 | 890 | 0.0022 | 2 | 1 | 2 | run id |
| R08 | 10 | 0.2 | 2 | 1 | 2 | run id |
| R09 | 20 | 0.1 | 2 | 1 | 2 | run id |
| **Total** | | | | **11** | **18** | |

`experiments/verify.sample` picks `max(1, ceil(frac × n))` runs, so each `frac` is chosen to give exactly the stated
count (R01 0.0008 × 1,200 = 0.96 → 1; R04 0.0041 × 480 = 1.97 → 2; R06 0.0222 × 90 = 1.998 → 2; R07 0.0022 × 890 =
1.958 → 2). `verify.yml` passes `--salt "$GITHUB_RUN_ID"`;
the request cannot fix the salt, so record the run id of each dispatch and reproduce a sample with
`uv run python -m experiments.verify <spec> results/<spec>-<id>/hashes.csv --frac <frac> --salt <id>`. The
`hashes.csv` is the merged file committed by the results PR (§5 step 6), not a per-shard partial. The 18 reruns may
repeat a shared central cell across specs (at most 10 such repeats), so they cover 12-18 distinct configs. They are
reproduction checks of already-reported cells, not new data, so they do not violate the run-once rule (plan V12.3).

## 5. Order of operations

1. Done: cleanup PRs **A-F** (`docs/FREEZE_CHECKLIST.md` §2) and the D-135 pipeline are merged.
2. **D01a cleanup.** The request landed in PR #138 and run 45138203406 started by `workflow_dispatch`, but it failed
   in 17 s before any simulation: `scenario.machines: reference bundle i7_12700_64g_full-b4f89a4def (calibration) is
   not among ('node02-i7-12700-64g-nvme_nvme', 'node02-i7-12700-64g-nvme_hdd', 'node04-i7-4790s-8g-hdd_hdd')`. Fix
   the **D01a spec** (not the request): set its `calibration` to the fleet reference (or add the i7 bundle to
   `scenario.machines.bundles`), then re-dispatch the same 2-shard request. The fleet is the right choice for the
   memory gate because the held-out runs use it; the development comparison to the earlier D01a runs is then not
   like-for-like, which the development log states. Once it runs: 9 runs in 2 shards of 5 and 4, up to 4 processes
   on the 16 GB runner; log the peak RSS, the D-113 gate and the wall time (~2 waves, ~3 h). If the memory gate
   fails, take the split fallback: R02/R04-R09 at `--jobs 3`, R01 and R03 on the 32 GB runner.
3. If the D-113 gate fails, take D-113 option B (caps return as swept constants) and add the R06/R07 variants before
   the tag; re-check the shard counts against the measured wall time.
4. Tag `v2-freeze`; confirm checklist 5.4 (`ls runs/requests/experiment/ | grep -i '^r0'` is empty).
5. After the tag, merge the R01-R09 request files (draft PR #136) and launch all nine in one batch with
   `gh workflow run experiment.yml --ref revision-v2 -f request=runs/requests/experiment/rXX.yaml` (§2.5). If the
   merge push started `r01` via the fallback trigger, cancel it first. The R08 decision-timing bench
   (`runs/requests/bench/r08-decision.yaml`) has no `workflow_dispatch`: land it as one push after the freeze (the
   #136 merge can be that push) and let `bench-decision.yml` run; merge the `bench/run-<id>` branch it produces. R01
   and R03 need the 32 GB runner with `--jobs 6`; the rate-21 specs run at `--jobs 3` or 6.
6. Merge each spec's results PR (the merged `summary.parquet` and `hashes.csv` of every run, from
   `experiments.merge_results`), then dispatch its verify request from `runs/requests/verify/` (created then,
   because `hashes:` must point at the committed `results/<spec>-<id>/hashes.csv`).
7. After all nine specs are verified: scorecard and the V12.4 claim choice.

## 6. R specs after the cleanup PRs

Cleanup PRs A-F are merged and closed the gaps this runbook listed at `b7b5921`: `exact_program` is out of
`configs/baselines.yaml` and the R01-R03 `left_out` lists; R06 has synchronous-first-off, backup-off and
drop-estimate-off; R07 has the D-111/D-119/D-120/D-122 variants and one `m_base` key; R09's trusted hosts run on the
node02 bundle; the D-113 caps and the D-134 start-up prices are deleted. What remains:

1. **Shared-run claim.** R02/R06/R07/R08/R09 say "shared run" / "nothing runs twice", which is true of the config
   hashes but not of the pipeline: `sweep` writes under `runs/<spec>/` and does not read another spec's directory.
   D-135 publishes only a raw sample, so the shared cells cannot be seeded from the release either; the sweep
   executes 4,510 runs (4,390 distinct). Change the headers to say the cells are re-run, or add a seeding step
   outside the release (a local copy before dispatch).
