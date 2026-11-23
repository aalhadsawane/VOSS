# V12 held-out runbook (prepared; no held-out run has started)

Prepared on branch `v2/V12-requests` from `revision-v2` at `b7b5921`. The `d01a-cleanup` request and the first
version of this runbook landed in PR #138; this update travels with draft PR #136, which holds the held-out R01-R09
request files and the R08 bench request. **No `r0*` request file may land on `revision-v2` before the `v2-freeze` tag**
(`docs/FREEZE_CHECKLIST.md` 5.4). The D01a cleanup run 45138203406 started by `workflow_dispatch` and failed before
any simulation because the D01a spec's calibration override no longer resolves against the fleet (§5 step 2); no
held-out run has started.

The D-135 pipeline is in `revision-v2` (`experiments/merge_results.py`): each shard collects its own summary and
hashes, the publish job merges them, and the release carries the merged files plus one raw-log run from every 100th
shard (shards 0, 100, 200). The launch is on the **D-137 fallback code**: `voss.planner.max_plan_workers` (40),
`hot_top_k` (20) and `hot_fn_k` (50) return as class-S pre-filters (the D-113 fallback), and R07 varies each.
The R specs carry **D-138** (PR #154): `scenario.load.rate_mult` is **{2.2, 4.4, 6.3}**, central 4.4; the request
files are unchanged. The held-out projection is **1.2-1.7 h (70-102 min)** for one 28 h run: the held-out trace has
4.8× the development counts, and the normalised rate restores the development event budget. D-137 and D-138 must be
merged before dispatch.

## 1. Runs

| Spec | Systems | Grid cells | Seeds | Runs | Shared with R01 | Distinct new |
|---|---|---|---|---|---|---|
| R01 | 8 | 15 (`K` 5 × load 3) | 10 | 1,200 | — | 1,200 |
| R02 | 8 | 1 (central cell) | 10 | 80 | 80 | 0 |
| R03 | 9 | 18 (pool 3 × load 3 × notice 2) | 10 | 1,620 | 0 | 1,620 |
| R04 | 4 | 12 (alpha 3 × strategy 4) | 10 | 480 | 0 | 480 |
| R05 | 1 | 12 (class-P 2 × forge_p 2 × p 3) | 10 | 120 | 0 | 120 |
| R06 | 9 | 1 | 10 | 90 | 10 | 80 |
| R07 | 95 | 1 | 10 | 950 | 10 | 940 |
| R08 | 1 | 1 | 10 | 10 | 10 | 0 |
| R09 | 2 | 1 | 10 | 20 | 10 | 10 |
| **Total** | | | | **4,570** | **120** | **4,450** |

Counted from the post-D-137 specs with `experiments.sweep.plan()` and compared by config hash: the 120 shared points
are R02's 80 central-cell runs plus 40 repeats of the same 10 `voss` central-cell runs in R06-R09 (so the 120
duplicates cover 80 distinct R01 configs).

**Distinct held-out runs: 4,450; 4,468 including verification repeats** (4,450 + 18 reruns, §4). The sweep as written
executes **4,570** points: `experiments/sweep._one` caches only under `runs/<spec>/<hash>`, and each job starts from
a fresh checkout, so the shared cells run again under R02/R06/R07/R08/R09. D-135 publishes only a raw sample, not
every run's raw directory, so the shared cells can no longer be seeded from the release: **4,570 executions is the
operational count** (4,588 with verification). The 4,450 distinct configs remain the reporting count.

## 2. Shard plan

### 2.1 Assumptions

- One shard = one `sweep` job of `experiment.yml`, timeout **340 min** (20,400 s).
- Held-out per-run wall: **1.2-1.7 h (70-102 min)** for one 28 h run across the normalised load axis (D-138:
  `scenario.load.rate_mult` {2.2, 4.4, 6.3}, central 4.4; the held-out trace has 4.8× the development counts and
  the normalised rate restores the development event budget). The old development measurement and the old rate-30
  factor are superseded and not used.
- 10% for co-running processes on one runner; 8 min per job for checkout, `uv sync` and the trace fetch; **2 min per
  run** for the per-shard `experiments.collect` step.
- A shard's wall is the pool's list schedule, not `sum(runs)/jobs`: 5 runs on 4 workers is two waves, 7 runs on 4
  workers is two waves (4+3). The table below uses the wave count × the 1.2-1.7 h range plus the collect/setup; the
  job-hour totals use the mid-point **1.45 h** per run.

### 2.2 Shard counts

| Spec | Runs | Shards | Runs per shard |
|---|---|---|---|
| R01 | 1,200 | 240 | 5 |
| R02 | 80 | 27 | 2-3 |
| R03 | 1,620 | 232 | 6-7 |
| R04 | 480 | 160 | 3 |
| R05 | 120 | 40 | 3 |
| R06 | 90 | 20 | 4-5 |
| R07 | 950 | 237 | 4-5 |
| R08 | 10 | 5 | 2 |
| R09 | 20 | 7 | 2-3 |
| **Total** | **4,570** | **968** | |

The counts are unchanged by D-138. The **256-job matrix limit** sets the minimum runs per shard for the two large
specs: R01 cannot have more than 256 shards, so it needs 5 runs per shard; R03 needs 7. R06 (20 shards) and R07
(237) are under the cap. At `--jobs 4`, R01's 5-run and R03's 7-run shards are two waves; every shard is at most 3.8 h
(228 min), so the counts fit the 340-min job. The request files keep these shard counts. With D-135 the release-asset
limit no longer constrains the shard size.

### 2.3 Runner memory, `--jobs` and the timeout

Measured peak RSS is **4.5-4.8 GB per 28 h run** (`resource.getrusage` in the manifest), and the standard
GitHub-hosted runner has **16 GB**:

- **`--jobs 4` is not assumed safe on 16 GB**: 4 × 4.8 = 19.2 GB, over the runner. `nproc` on the 4-vCPU runner is 4,
  so the workflow's `--jobs "$(nproc)"` as written would run 4 processes and can be OOM-killed. The D01a cleanup is
  the empirical gate (last bullet).
- **`--jobs 3` fits memory** (3 × 4.8 = 14.4 GB, 90% of 16 GB); the timeout now fits too, with R03 tight.

| Spec | Shards | Runs/shard | Waves at 4 jobs | Wall at 4 jobs | Waves at 6 jobs | Wall at 6 jobs |
|---|---|---|---|---|---|---|
| R01 | 240 | 5 | 2 | 2.7-3.8 h | 1 | 1.5-2.0 h |
| R02 | 27 | 2-3 | 1 | 1.4-1.9 h | 1 | 1.4-1.9 h |
| R03 | 232 | 6-7 | 2 | 2.7-3.8 h | 2 | 2.7-3.8 h |
| R04 | 160 | 3 | 1 | 1.4-1.9 h | 1 | 1.4-1.9 h |
| R05 | 40 | 3 | 1 | 1.4-1.9 h | 1 | 1.4-1.9 h |
| R06 | 20 | 4-5 | 1-2 | 1.5-3.8 h | 1 | 1.5-2.0 h |
| R07 | 237 | 4-5 | 1-2 | 1.5-3.8 h | 1 | 1.5-2.0 h |
| R08 | 5 | 2 | 1 | 1.4-1.8 h | 1 | 1.4-1.8 h |
| R09 | 7 | 2-3 | 1 | 1.4-1.9 h | 1 | 1.4-1.9 h |

Every shard is under 3.8 h (228 min) at `--jobs 4`, so the shard counts stay. At `--jobs 3`, the 5-run shards are two
waves (2.7-3.8 h) and the 7-run shards three waves (4.0-5.5 h = 240-330 min); R03 is the only tight case, with about
10 min to spare at the 1.7 h high end. At `--jobs 6` on 32 GB, the 5-run shards are one wave and the 7-run shards two
(2.7-3.8 h).

- **`--jobs 6` on a 32 GB runner is the comfortable configuration** (6 × 4.8 = 28.8 GB, under 32): every shard is at
  most 3.8 h. `nproc` on an 8-core runner is 8 (38.4 GB), so the sweep step must pass **`--jobs 6` explicitly**; this
  is a one-line workflow change, not something a request file can set.
- **Memory gate.** `d01a-cleanup.yaml` runs the 9 D01a points in **2 shards of 5 and 4**, so each shard starts up to 4
  processes on the 16 GB runner; its peak RSS and completion decide `--jobs 4` versus `--jobs 3`. If it passes with
  headroom, use `--jobs 4` on 16 GB (time-safe: every shard ≤3.8 h). If it fails, use `--jobs 3` on 16 GB for all
  nine specs (memory 14.4 GB; R03's 7-run shards are 3 waves, ≤330 min), so the old split-R01/R03 fallback is no
  longer needed. The 32 GB/`--jobs 6` configuration remains the comfortable option.

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
| `--jobs 3`, 16 GB | 3,308 | 83 h = 3.4 days | 165 h = 6.9 days | R03 tight (330 min) |
| `--jobs 4`, ~20 GB | 2,562 | 64 h = 2.7 days | 128 h = 5.3 days | all pass |
| **`--jobs 6`, 32 GB** | **2,163** | **54 h = 2.3 days** | **108 h = 4.5 days** | all pass |

The owner's GitHub plan is **Pro** and the repository is public: **40 concurrent jobs** (20 on Free, 60 on Team),
shared with every other workflow in the account. **40 is the planning assumption**; the 20-job column is the
conservative fallback. 40 concurrent jobs × 4 runs/shard = up to 160 runs in flight (the exact peak is 40 × 3 = 120
with `--jobs 3`, and 40 × 6 = 240 on the 5- and 7-run shards with `--jobs 6`).

The recommended 6-job configuration at 40 jobs: **2.3 days expected**, 63 h = 2.6 days conservative (every run at the
1.7 h high end), 2.5-2.9 days with a 10% tail for the last wave. If the frozen code is 20% slower: 2.7 days expected
and 3.2 days conservative; R03's worst shard rises to ~274 min, still under 340. The 3-job configuration is now a full
time fallback (R03's 7-run shards are 3 waves, ≤330 min); memory alone decides between 3 and 4 jobs on 16 GB.

The per-spec waves in §2.3 are shard (job) times, not makespans, and do not change with concurrency. If a spec runs
alone, its makespan is `ceil(shards/40) × its mean shard`: R01 11.1 h, R03 20.7 h, R04 7.3 h, R07 11.2 h; R02, R05,
R06, R08 and R09 are one wave (1.8-1.9 h). Run one at a time, largest first, the sum is ~59 h; interleaving all specs
in one 40-slot queue gives the 54 h figure.

## 4. Verification plan

`verify.yml` is one job, no matrix, 340 min, and `experiments/verify.py` reruns the sample **sequentially** in that
job. At the held-out projection, 2 runs = 2.4-3.4 h (144-204 min) and 3 runs = 3.6-5.1 h (216-306 min); 3 fits at the
1.7 h high end (316 min with setup) but leaves under 25 min, so the plan keeps 2. R01 and R03 keep 1 run per job,
dispatched twice: their 6.3 cells sit at the high end, and one run per job leaves the most margin.

| Spec | Runs | `frac` | Runs per job | Jobs | Reruns | Salt |
|---|---|---|---|---|---|---|
| R01 | 1,200 | 0.0008 | 1 | 2 | 2 | run id |
| R02 | 80 | 0.025 | 2 | 1 | 2 | run id |
| R03 | 1,620 | 0.0006 | 1 | 2 | 2 | run id |
| R04 | 480 | 0.0041 | 2 | 1 | 2 | run id |
| R05 | 120 | 0.0166 | 2 | 1 | 2 | run id |
| R06 | 90 | 0.0222 | 2 | 1 | 2 | run id |
| R07 | 950 | 0.0021 | 2 | 1 | 2 | run id |
| R08 | 10 | 0.2 | 2 | 1 | 2 | run id |
| R09 | 20 | 0.1 | 2 | 1 | 2 | run id |
| **Total** | | | | **11** | **18** | |

`experiments/verify.sample` picks `max(1, ceil(frac × n))` runs, so each `frac` is chosen to give exactly the stated
count (R01 0.0008 × 1,200 = 0.96 → 1; R04 0.0041 × 480 = 1.97 → 2; R06 0.0222 × 90 = 1.998 → 2; R07 0.0021 × 950 =
1.995 → 2). `verify.yml` passes `--salt "$GITHUB_RUN_ID"`;
the request cannot fix the salt, so record the run id of each dispatch and reproduce a sample with
`uv run python -m experiments.verify <spec> results/<spec>-<id>/hashes.csv --frac <frac> --salt <id>`. The
`hashes.csv` is the merged file committed by the results PR (§5 step 6), not a per-shard partial. The 18 reruns may
repeat a shared central cell across specs (at most 10 such repeats), so they cover 12-18 distinct configs. They are
reproduction checks of already-reported cells, not new data, so they do not violate the run-once rule (plan V12.3).

## 5. Order of operations

1. Done: cleanup PRs **A-F** (`docs/FREEZE_CHECKLIST.md` §2), the D-135 pipeline and D-137 (the caps fallback) are
   merged; **D-138 (PR #154)** must be merged before dispatch (the R specs carry the normalised load axis; the
   request files are unchanged).
2. **D01a cleanup.** The request landed in PR #138 and run 45138203406 started by `workflow_dispatch`, but it failed
   in 17 s before any simulation: `scenario.machines: reference bundle i7_12700_64g_full-b4f89a4def (calibration) is
   not among ('node02-i7-12700-64g-nvme_nvme', 'node02-i7-12700-64g-nvme_hdd', 'node04-i7-4790s-8g-hdd_hdd')`. Fix
   the **D01a spec** (not the request): set its `calibration` to the fleet reference (or add the i7 bundle to
   `scenario.machines.bundles`), then re-dispatch the same 2-shard request. The fleet is the right choice for the
   memory gate because the held-out runs use it; the development comparison to the earlier D01a runs is then not
   like-for-like, which the development log states. Once it runs: 9 runs in 2 shards of 5 and 4, up to 4 processes
   on the 16 GB runner; log the peak RSS, the capped wall time (D-137) and the collect time (~2 waves, ~3 h). If the
   memory gate fails, take the split fallback: R02/R04-R09 at `--jobs 3`, R01 and R03 on the 32 GB runner.
3. D-137 is the outcome of the D-113 gate: the caps return as class-S pre-filters and R07 varies them, so no further
   R06/R07 variant edits are needed. The D01a cleanup measures the capped wall time; if it does not fit 340 min, the
   held-out cells need a shorter measured window or a different shard shape.
4. Tag `v2-freeze`; confirm checklist 5.4 (`ls runs/requests/experiment/ | grep -i '^r0'` is empty).
5. After the tag, merge the R01-R09 request files (draft PR #136) and launch all nine in one batch with
   `gh workflow run experiment.yml --ref revision-v2 -f request=runs/requests/experiment/rXX.yaml` (§2.5). If the
   merge push started `r01` via the fallback trigger, cancel it first. The R08 decision-timing bench
   (`runs/requests/bench/r08-decision.yaml`) has no `workflow_dispatch`: land it as one push after the freeze (the
   #136 merge can be that push) and let `bench-decision.yml` run; merge the `bench/run-<id>` branch it produces. Every
   spec fits the timeout at `--jobs 4` (≤3.8 h per shard); the 32 GB/`--jobs 6` runner is the comfortable choice, and
   `--jobs 3` on 16 GB fits the time as in §2.3. R01 and R03 no longer need a separate runner.
6. Merge each spec's results PR (the merged `summary.parquet` and `hashes.csv` of every run, from
   `experiments.merge_results`), then dispatch its verify request from `runs/requests/verify/` (created then,
   because `hashes:` must point at the committed `results/<spec>-<id>/hashes.csv`).
7. After all nine specs are verified: scorecard and the V12.4 claim choice.

## 6. R specs after the cleanup PRs

Cleanup PRs A-F are merged and closed the gaps this runbook listed at `b7b5921`: `exact_program` is out of
`configs/baselines.yaml` and the R01-R03 `left_out` lists; R06 has synchronous-first-off, backup-off and
drop-estimate-off; R07 has the D-111/D-119/D-120/D-122 variants and one `m_base` key; R09's trusted hosts run on the
node02 bundle; the D-134 start-up prices are deleted; D-137 returns the D-113 caps as class-S pre-filters and R07
varies them; D-138 normalises the load axis (`rate_mult` {2.2, 4.4, 6.3}) and leaves the run counts unchanged. What
remains:

1. **Shared-run claim.** R02/R06/R07/R08/R09 say "shared run" / "nothing runs twice", which is true of the config
   hashes but not of the pipeline: `sweep` writes under `runs/<spec>/` and does not read another spec's directory.
   D-135 publishes only a raw sample, so the shared cells cannot be seeded from the release either; the sweep
   executes 4,570 runs (4,450 distinct). Change the headers to say the cells are re-run, or add a seeding step
   outside the release (a local copy before dispatch).
