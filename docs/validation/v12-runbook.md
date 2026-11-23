# V12 held-out runbook (prepared; nothing here has run)

Prepared on branch `v2/V12-requests` from `revision-v2` at `b7b5921`; the held-out request files stay in draft PR
#136 and this branch carries only the `d01a-cleanup` request and this runbook. **No `r0*` request file may land on
`revision-v2` before the `v2-freeze` tag** (`docs/FREEZE_CHECKLIST.md` 5.4). `d01a-cleanup.yaml` is the one request
that lands before the tag (checklist 4.4), and it lands without the held-out files (see §5). Nothing here has run.

This version assumes the pipeline of PR #137 (D-135): each shard collects its own `summary.parquet` and `hashes.csv`,
the publish job merges them with `experiments.merge_results`, and the release carries the merged summaries/hashes plus
one raw-log run from every 100th shard. If #137 is not merged before dispatch, the release-asset limit of the old
pipeline returns and the shard counts need the split/asset check again.

## 1. Runs

| Spec | Systems | Grid cells | Seeds | Runs | Shared with R01 | Distinct new |
|---|---|---|---|---|---|---|
| R01 | 8 | 15 (`K` 5 × load 3) | 10 | 1,200 | — | 1,200 |
| R02 | 8 | 1 (central cell) | 10 | 80 | 80 | 0 |
| R03 | 9 | 18 (pool 3 × load 3 × notice 2) | 10 | 1,620 | 0 | 1,620 |
| R04 | 4 | 12 (alpha 3 × strategy 4) | 10 | 480 | 0 | 480 |
| R05 | 1 | 12 (class-P 2 × forge_p 2 × p 3) | 10 | 120 | 0 | 120 |
| R06 | 6 | 1 | 10 | 60 | 10 | 50 |
| R07 | 71 | 1 | 10 | 710 | 10 | 700 |
| R08 | 1 | 1 | 10 | 10 | 10 | 0 |
| R09 | 2 | 1 | 10 | 20 | 10 | 10 |
| **Total** | | | | **4,300** | **120** | **4,180** |

Counted from the specs with `experiments.sweep.plan()` and compared by config hash: the 120 shared points are R02's
80 central-cell runs plus 40 repeats of the same 10 `voss` central-cell runs in R06-R09 (so the 120 duplicates cover
80 distinct R01 configs).

**Distinct held-out runs: 4,180. Total including verification repeats: 4,198** (4,180 + 18 reruns, §4). The sweep as
written executes **4,300** points: `experiments/sweep._one` caches only under `runs/<spec>/<hash>`, and each job
starts from a fresh checkout, so the shared cells run again under R02/R06/R07/R08/R09. D-135 publishes only a raw
sample, not every run's raw directory, so the shared cells can no longer be seeded from the release: **4,300
executions is the operational count** (4,318 with verification). The 4,180 distinct configs remain the reporting
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
| R06 | 60 | 20 | 3 |
| R07 | 710 | 237 | 2-3 |
| R08 | 10 | 5 | 2 |
| R09 | 20 | 7 | 2-3 |
| **Total** | **4,300** | **968** | |

The counts are the `--jobs 3` layout: 3 runs per shard on the rate-21 specs (one round on 3 workers), 5 on R01 and
7 on R03. The **256-job matrix limit** sets the minimum runs per shard for the two large specs: R01 cannot have more
than 256 shards, so it needs 5 runs per shard; R03 needs 7. The other specs are free to use 3, which is the best size
for a 3-worker shard and also works on 4 and 6 workers. With D-135 the release-asset limit no longer constrains the
shard size.

### 2.3 Runner memory, `--jobs` and the timeout

Measured peak RSS is **4.5-4.8 GB per 28 h run** (`resource.getrusage` in the manifest), and the standard
GitHub-hosted runner has **16 GB**:

- **`--jobs 4` is not safe on 16 GB**: 4 × 4.8 = 19.2 GB, over the runner. `nproc` on the 4-vCPU runner is 4, so
  the workflow's `--jobs "$(nproc)"` as written would run 4 processes and can be OOM-killed.
- **`--jobs 3` fits memory** (3 × 4.8 = 14.4 GB, 90% of 16 GB) but not the timeout for R01 and R03:

| Spec | Shards | Runs/shard | `--jobs 3` mean | `--jobs 3` p99 | `--jobs 6` mean | `--jobs 6` p99 |
|---|---|---|---|---|---|---|
| R01 | 240 | 5 | 232 min | **367 min** | 172 min | 246 min |
| R02 | 27 | 2-3 | 131 min | 173 min | 131 min | 173 min |
| R03 | 232 | 6-7 | 284 min | **430 min** | 195 min | 299 min |
| R04 | 160 | 3 | 140 min | 173 min | 140 min | 173 min |
| R05 | 40 | 3 | 152 min | 173 min | 152 min | 173 min |
| R06 | 20 | 3 | 144 min | 173 min | 144 min | 173 min |
| R07 | 237 | 3 | 142 min | 173 min | 142 min | 173 min |
| R08 | 5 | 2 | 132 min | 171 min | 132 min | 171 min |
| R09 | 7 | 2-3 | 138 min | 173 min | 138 min | 173 min |

At `--jobs 3`, R02 and R04-R09 are safe (p99 171-173 min), but **R01 has a 59% chance that one of its 240 shards
exceeds 340 min** (p99 367) and **R03 is certain to** (p99 430, three rounds of 3+3+1 runs at the rate-30 wall).
R03 against the 256-job cap: 232 shards of 7 fit the cap, but 6 runs per shard would need 270 shards, over it. So
**R03 cannot run at `--jobs 3` on 16 GB within the 340-min timeout and the matrix limit**.

- `--jobs 4` on a ~20 GB runner removes R01's risk (p99 308) but not R03's: p99 380, a 92% chance of one timeout.
- **`--jobs 6` on a 32 GB runner is the required configuration** (6 × 4.8 = 28.8 GB, under 32): every spec's p99 is
  at most 299 min, with at least 41 min of headroom. `nproc` on an 8-core runner is 8 (38.4 GB), so the sweep step
  must pass **`--jobs 6` explicitly**; this is a one-line workflow change, not something a request file can set.
  If only a 16 GB runner is available, run R02 and R04-R09 at `--jobs 3` and defer R01 and R03 to the 32 GB runner
  (or split them across dispatches, which needs another workflow change).

### 2.4 Release contents (D-135)

Each shard runs `experiments.collect` on its own runs and uploads only `results/partial-<i>` (a summary and a hash
row per run, a few MB); the publish job merges the parts with `experiments.merge_results` and commits one
`summary.parquet` and `hashes.csv` for every run. The release carries those two files plus one raw-log run from
every 100th shard: shards 0, 100 and 200, so at most 3 raw runs per spec and 16 in all (~11 GB), each under 2 GiB.
The old 2 GiB/1,000-asset limit and the ~3 TB full-log download are gone; the publish job moves a few MB of
summaries and ~11 GB of raw samples, not terabytes. The raw sample is a reproduction exhibit, not the archive: every
run is reproducible from its committed config hash, scenario hash and seed (D-135).

### 2.5 Trigger

The plan job takes only the **first** changed request file of a push
(`git diff --name-only ... | sort | head -1`). The held-out request files stay on draft PR #136; `d01a-cleanup`
lands in this PR. After the tag the held-out files must be landed **one commit and one push at a time** (or
dispatched with `workflow_dispatch`); a single push of several would start only the first file and silently skip the
rest.

## 3. Wall clock

| Configuration | Total job-hours | At 20 concurrent jobs | Timeout verdict |
|---|---|---|---|
| `--jobs 3`, 16 GB | 3,199 | 160 h = 6.7 days | R01 and R03 fail |
| `--jobs 4`, ~20 GB | 2,897 | 145 h = 6.0 days | R03 fails (92%) |
| **`--jobs 6`, 32 GB** | **2,613** | **131 h = 5.4 days** | all pass |

20 concurrent jobs is the Free-plan limit (40 on Pro, 60 on Team), shared with every other workflow in the account.
The recommended 6-job configuration: **5.4 days expected**, 145 h = 6.0 days conservative (every run at its
system's p90), 5.9-6.6 days with a 10% tail for the last wave. If the D01a cleanup shows the frozen code 20% slower,
6.5 days expected and 7.2 days conservative; R03's worst shard rises to ~326 min, still under 340. The 3-job
configuration is not a full fallback: it is 6.7 days *and* cannot run R01/R03.

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
| R06 | 60 | 0.0333 | 2 | 1 | 2 | run id |
| R07 | 710 | 0.0028 | 2 | 1 | 2 | run id |
| R08 | 10 | 0.2 | 2 | 1 | 2 | run id |
| R09 | 20 | 0.1 | 2 | 1 | 2 | run id |
| **Total** | | | | **11** | **18** | |

`experiments/verify.sample` picks `max(1, ceil(frac × n))` runs, so each `frac` is chosen to give exactly the stated
count (R01 0.0008 × 1,200 = 0.96 → 1; R04 0.0041 × 480 = 1.97 → 2). `verify.yml` passes `--salt "$GITHUB_RUN_ID"`;
the request cannot fix the salt, so record the run id of each dispatch and reproduce a sample with
`uv run python -m experiments.verify <spec> results/<spec>-<id>/hashes.csv --frac <frac> --salt <id>`. The
`hashes.csv` is the merged file committed by the results PR (§5 step 6), not a per-shard partial. The 18 reruns may
repeat a shared central cell across specs (at most 10 such repeats), so they cover 12-18 distinct configs. They are
reproduction checks of already-reported cells, not new data, so they do not violate the run-once rule (plan V12.3).

## 5. Order of operations

1. Merge cleanup PRs **A-F** (`docs/FREEZE_CHECKLIST.md` §2) and the pipeline PR #137 (D-135).
2. Land `runs/requests/experiment/d01a-cleanup.yaml` (this PR; no `r0*` file in the same push): 9 shards,
   1 run each, development split. Check that D01a's `calibration=configs/calibration/measured/
   i7_12700_64g_full-b4f89a4def` override still resolves after PRs A-F; if that bundle is deleted, the D01a spec
   changes, not this request. Log the result and the D-113 gate (wall time of the 500-worker 28 h run with the
   planning caps removed) in `docs/validation/development-log.md` (checklist 4.4). The same run measures the new
   per-run collect time and the wall time with the frozen code.
3. If the gate fails, take D-113 option B (caps return as swept constants) and add the R06/R07 variants before the
   tag; re-check the shard counts against the measured wall time.
4. Tag `v2-freeze`; confirm checklist 5.4 (`ls runs/requests/experiment/ | grep -i '^r0'` is empty).
5. Land `r01.yaml` ... `r09.yaml` one at a time, largest first (R01, R03, R04, R07, R02, R05, R06, R08, R09), each
   as its own push so the first-changed-file trigger starts exactly that spec. Dispatch the R08 decision-timing
   bench (`bench-decision.yml`) in the same window (D-127). R01 and R03 need the 32 GB runner with `--jobs 6`; the
   rate-21 specs run on either runner at `--jobs 3` or 6.
6. Merge each spec's results PR (the merged `summary.parquet` and `hashes.csv` of every run, from
   `experiments.merge_results`), then dispatch its verify request from `runs/requests/verify/` (created then,
   because `hashes:` must point at the committed `results/<spec>-<id>/hashes.csv`).
7. After all nine specs are verified: scorecard and the V12.4 claim choice.

## 6. What in the R specs is still inconsistent with D-110..D-135

PR A (D-110) has landed at the base of this PR; the other cleanup PRs have not (`sync_priority` is not in
`configs/base.yaml`, `exact_program` is still in `configs/baselines.yaml`, and the D-113/D-114/D-117/D-124 code is
pending). These are the edits the specs still need:

1. **D-131, `exact_program`.** `R01.yaml`, `R02.yaml` and `R03.yaml` list `exact_program` in `left_out`, and their
   headers describe it. D-131 deletes it from `configs/baselines.yaml`, after which
   `test_r01_is_the_plan_grid_with_the_published_systems` fails (`set(systems) | set(left_out) != set(prov)`). Drop
   it from the three `left_out` lists and the headers in PR F.
2. **D-114/D-128, R06 variants.** R06 lacks *synchronous-first off* (D-114), *backup attempts off* and *drop estimate
   off* (D-128), and still carries the "Added when their keys land" comment that checklist 5.2 requires to be empty.
   PR C/E must add the three labels and delete that comment (and the matching R07 comment).
3. **D-111/D-119/D-120/D-122, R07 variants.** R07 lacks the prior strength and `k` (D-111), deadline multiple and
   idempotent fraction (D-119), certificate validity and re-attestation (D-120), and `0.3 tts` and `OVERDUE_FRAC`
   (D-122). Checklist 5.2 lists exactly these. If D-119's two keys become *axes*, R07 is where they go; R01's grid
   must not grow.
4. **D-117, R07 `m_base`.** The `m_base_lo`/`m_base_hi` overrides set both `voss.worker.m_base_mb` and
   `voss.planner.params.m_base_mb`; D-117 merges them into one key. After PR E the second half is a dead dict entry
   (`planner.params` is `dict[str, Any]`), so the variant silently tests only one key. Drop it.
5. **D-124, R09's upper bound.** `trusted_hosts` still runs on `configs/references/trusted_hosts.yaml` with `hw: DC`,
   which D-124 deletes. PR E must rewrite the reference to the node02 NVMe class with one third of the pool's slots
   per router metro; R09's `system=reference_cloud` override must still resolve afterwards.
6. **D-113, the gate.** If the cleanup rerun shows the uncapped planning no longer fits a job and option B returns
   the caps, they are swept constants and R07 needs variants for `max_plan_workers`, `hot_top_k` and `hot_fn_k`
   (today R07 has none, correctly, because D-113 deletes them).
7. **D-134 does not exist.** The brief cites D-110..D-134; `docs/DECISIONS.md` ends at D-133 on this branch (PR #137
   adds D-135), and D-134 is absent. Nothing in R01-R09 refers to a D-134, but the freeze checklist's "D-110 to
   D-131" line is also stale relative to D-132, D-133 and D-135.
8. **Shared-run claim.** R02/R06/R07/R08/R09 say "shared run" / "nothing runs twice", which is true of the config
   hashes but not of the pipeline: `sweep` writes under `runs/<spec>/` and does not read another spec's directory.
   D-135 publishes only a raw sample, so the shared cells cannot be seeded from the release either; the sweep
   executes 4,300 runs (4,180 distinct). Change the headers to say the cells are re-run, or add a seeding step
   outside the release (a local copy before dispatch).
