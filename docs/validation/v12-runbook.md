# V12 held-out runbook (prepared; nothing here has run)

Prepared on branch `v2/V12-requests` from `revision-v2` at `b7b5921`, as a DRAFT pull request. **No file in
`runs/requests/experiment/` may land on `revision-v2` before the `v2-freeze` tag** (`docs/FREEZE_CHECKLIST.md` 5.4).
The one exception is `d01a-cleanup.yaml`: it is a development rerun (checklist 4.4), it lands **before** the tag, and
it must land alone (see §5).

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

**Distinct held-out runs: 4,180. Total including verification repeats: 4,198** (4,180 + 18 reruns, §5). The sweep as
written executes **4,300** points: `experiments/sweep._one` caches only under `runs/<spec>/<hash>`, and each job
starts from a fresh checkout, so the shared cells run again under R02/R06/R07/R08/R09. Seeding `runs/<spec>` with
R01's run directories before those five dispatches would save 120 executions (80 distinct configs); the plan counts
4,300 executions and 4,318 with verification.

## 2. Shard plan

### 2.1 Assumptions

- One shard = one `sweep` job of `experiment.yml`, `--jobs "$(nproc)"` = **4** on the 4-vCPU runner, timeout **340
  min** (20,400 s).
- Measured per-run wall time: the 66 runs of `results/*/summary.parquet` (D01a and D02, 500 workers, `K` = 8,
  `rate_mult` 21, 28 h): mean **5,152 s (86 min)**, p50 5,250 s, p90 7,149 s, max 7,899 s (132 min).
- Wall time scales with arrivals (D-97: 130 M events at `rate_mult` 30 in 114 min), so rate-30 cells are assumed
  1.43× the rate-21 wall.
- 10% for the post-freeze code (D-113 plans without the caps; the D01a cleanup measures it) and 10% for four
  processes on one 4-vCPU runner.
- 8 min per job for checkout, `uv sync` and the trace fetch.

A shard is a round-robin sample of the spec's stable point order, so each shard mixes systems and load cells; the
table below is a bootstrap over the measured per-run distribution (within system, scaled by `rate_mult`, with the two
10% margins and the 8-min setup), not a worst-cell bound.

### 2.2 Shard counts

| Spec | Runs | Shards | Runs per shard | Shard mean | Worst shard, p99 |
|---|---|---|---|---|---|
| R01 | 1,200 | 240 | 5 | 124 min | 178 min |
| R02 | 80 | 27 | 2-3 | 78 min | 104 min |
| R03 | 1,620 | 232 | 6-7 | 169 min | 225 min |
| R04 | 480 | 160 | 3 | 84 min | 111 min |
| R05 | 120 | 40 | 3 | 93 min | 125 min |
| R06 | 60 | 20 | 3 | 87 min | 121 min |
| R07 | 710 | 237 | 2-3 | 86 min | 124 min |
| R08 | 10 | 5 | 2 | 60 min | 84 min |
| R09 | 20 | 7 | 2-3 | 81 min | 109 min |
| **Total** | **4,300** | **968** | | | |

Every shard is under 340 min with at least 115 min of headroom at p99. The shard counts are **not** free:

- **Matrix limit.** GitHub Actions generates at most **256 jobs from one matrix**, so a spec cannot have more than
  256 shards in one dispatch. That sets the minimum runs per shard: R01 5, R03 7, R07 3. R01's 240 shards are
  exactly 5 runs each; the round-robin stride still mixes the load axis across a shard.
- **Release-asset limit.** A release takes at most **1,000 assets, each under 2 GiB**. One 28 h run at rate 21 is
  643-657 MB as `tar.zst` (measured on the `runs-D01a-44056745829` release), so a 5-run shard is ~3.2 GB and a 7-run
  shard ~4.5 GB (rate 30: ~4.7 and ~6.5 GB). **The publish step fails as written.** Before dispatch, split each
  shard's tarball into <2 GiB parts, e.g.
  `tar --zstd -cf - -C runs $SPEC | split -b 1900M - shard-$i.tar.zst.part-`, upload `shard-$i.tar.zst.part-*`,
  `gh release create "$TAG" shards/*.part-*`, and extract with
  `cat shards/shard-$i.tar.zst.part-* | tar --zstd -xf - -C runs`. With 4 parts per R03 shard the release has 928
  assets, under 1,000; more parts per shard would exceed it. The 3-run shards are ~1.95 GB, 91% of the 2 GiB limit,
  so check the first published asset and split those too if it is over 2 GiB.
- **Runner memory.** Measured peak RSS is 4.5-4.8 GB per 28 h run. Four co-running processes need 18.4-19.2 GB and
  the standard runner has 16 GB: `--jobs nproc` (4) can be OOM-killed. Use a runner with at least 20 GB (then pass
  `--jobs 4` explicitly, because `nproc` on an 8-core/32 GB runner would start 8 processes and need 36.8 GB).
  `--jobs 3` on the 16 GB runner does not fit R03: 7 runs in 3 rounds at the rate-30 wall is over 340 min, and the
  256-shard cap forbids 6-run shards (270 shards).
- **Publish capacity.** 4,300 runs at 0.65-0.93 GB is **~3 TB** of raw logs. The publish job downloads every shard,
  runs `collect` and re-uploads the same bytes to a release; R03 alone is ~1.5 TB and is likely to exceed the default
  6 h job timeout. Decide before dispatch: object storage for the raw logs, or a larger publish timeout plus the transfer
  time, or per-shard collection with selective archiving.
- **Trigger.** The plan job takes only the **first** changed request file of a push
  (`git diff --name-only ... | sort | head -1`). Land the request files one commit at a time (or dispatch with
  `workflow_dispatch`). Merging this whole draft PR after the tag would start only `d01a-cleanup.yaml` and silently
  skip R01-R09.

## 3. Wall clock

| Case | Job-hours | At 20 concurrent jobs |
|---|---|---|
| Measured mean, no margins | 1,552 | 78 h = 3.2 days |
| With the two 10% margins and setup | 1,851 | 93 h = 3.9 days |
| Plus a 10% tail for the last wave | 1,851 | 102 h = 4.3 days |
| Conservative: every run at its system's p90 | 2,206 | 110 h = 4.6 days |

20 concurrent jobs is the Free-plan limit (40 on Pro, 60 on Team), shared with every other workflow in the account.
If the D01a cleanup shows the frozen code 20% slower than the measured mean, add 20% (4.6-5.5 days); the worst shard
rises to ~270 min, still under 340. A 32 GB runner is needed for memory, not for speed: the wall clock stays ~3.9
days unless the account's concurrency is raised.

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
`uv run python -m experiments.verify <spec> results/<spec>-<id>/hashes.csv --frac <frac> --salt <id>`.
The 18 reruns may repeat a shared central cell across specs (at most 10 such repeats), so they cover 12-18 distinct
configs. They are reproduction checks of already-reported cells, not new data, so they do not violate the run-once
rule (plan V12.3).

## 5. Order of operations

1. Merge cleanup PRs **A-F** (`docs/FREEZE_CHECKLIST.md` §2).
2. Land `runs/requests/experiment/d01a-cleanup.yaml` **alone** on `revision-v2` (one commit, one push): 9 shards,
   1 run each, development split. Check that D01a's `calibration=configs/calibration/measured/
   i7_12700_64g_full-b4f89a4def` override still resolves after PRs A-F; if that bundle is deleted, the D01a spec
   changes, not this request. Log the result and the D-113 gate (wall time of the 500-worker 28 h run with the
   planning caps removed) in `docs/validation/development-log.md` (checklist 4.4).
3. If the gate fails, take D-113 option B (caps return as swept constants) and add the R06/R07 variants before the
   tag; re-check the shard counts against the measured wall time.
4. Tag `v2-freeze`; confirm checklist 5.4 (`ls runs/requests/experiment/ | grep -i '^r0'` is empty).
5. Land `r01.yaml` ... `r09.yaml` one at a time, largest first (R01, R03, R04, R07, R02, R05, R06, R08, R09), so the
   20 slots stay full and each push triggers exactly one spec. Dispatch the R08 decision-timing bench
   (`bench-decision.yml`) in the same window (D-127).
6. Merge each spec's results PR, then dispatch its verify request from `runs/requests/verify/` (created then, because
   `hashes:` must point at the published `results/<spec>-<id>/hashes.csv`).
7. After all nine specs are verified: scorecard and the V12.4 claim choice.

## 6. What in the R specs is still inconsistent with D-110..D-133

The cleanup PRs have not landed at `b7b5921` (v1 symbols are still in `voss/`, `sync_priority` is not in
`configs/base.yaml`, `exact_program` is still in `configs/baselines.yaml`). These are the edits the specs still need:

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
7. **D-134 does not exist.** The brief cites D-110..D-134; `docs/DECISIONS.md` ends at D-133. Nothing in R01-R09
   refers to a D-134, but the freeze checklist's "D-110 to D-131" line is also stale relative to D-132/D-133.
8. **Shared-run claim.** R02/R06/R07/R08/R09 say "shared run" / "nothing runs twice", which is true of the config
   hashes but not of the pipeline: `sweep` writes under `runs/<spec>/` and does not read another spec's directory.
   Either seed the shared run directories from R01's release before those dispatches, or change the headers to say
   the cells are re-run (4,300 executions, §1).
