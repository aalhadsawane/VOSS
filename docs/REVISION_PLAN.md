# Revision plan: architecture, code, experiments, paper

**Audience:** a coding agent (or the author) executing the revision of VOSS for ACM TOIT.
**Status:** plan only; nothing here is implemented.
**Authority:** where this plan and older docs disagree, this plan wins once its decision records (D-81 to D-95, §3) are
committed to `docs/DECISIONS.md`. Until then, ask the author.

**Inputs this plan is built on (read in this order before starting any phase):**
1. `AGENTS.md` (rules 1-14 still apply unchanged).
2. `manuscript/reviews/FABLE_PAPER_REVIEW_7_coherent_revision_plan.md` (the target paper and the eight design decisions R1-R8).
3. `manuscript/reviews/FABLE_PAPER_REVIEW_5_deeper_technical.md` (code-checked defects D1-D17).
4. `manuscript/reviews/FABLE_PAPER_REVIEW_1..4, 6` (issue IDs A, B, C, E, S, W, X).
5. `manuscript/HUMAN_FEEDBACK.md` (author's style profile and heuristics 1-30; binding for every sentence of the paper).
6. `docs/DECISIONS.md` D-77 to D-80, `docs/EXPERIMENT_TODO.md` X-1 to X-4, `docs/architecture/02, 03, 04, 06, 07, 10`.

Issue IDs in brackets, e.g. [D3], refer to the review files. Every step in this plan names the issues it closes; the
traceability table in §9 lists every review issue and the step that closes it.

---

## 0. How to use this plan

- Execute phases **in order**. Each phase has: goal, issues closed, decisions, file-level changes, tests, exit criteria, and
  stop conditions. Do not start a phase until the previous one meets its exit criteria (AGENTS.md rule 1).
- One branch and one PR per phase (`rev/V<n>-<slug>`). Merge yourself when `make check` and the phase's exit criteria
  pass (AGENTS.md rule 1). Never force-push; never push to `main`.
- **Stop and ask the author** at every point marked **[ASK]**. Do not guess past these.
- **Do not change any default in `voss/core/config.py` that alters the result hash of a committed v1 run** (repository
  practice, D-79). All new behaviour is behind config keys whose defaults reproduce v1, and the revision's settings live in
  `configs/revision.yaml` (§V0.4). The v1 paper stays reproducible (`make paper-verify` must stay green).
- When a step says "log", it means through `metrics.Recorder` (AGENTS.md rule 10); analysis reads logs only.
- When a step introduces a number from literature, tag it `literature` in YAML and `# TODO verify` in code (rule 13).
- When a design flaw blocks you, make the smallest sensible choice and add a decision in a separate commit (rule 12).

---

## 1. New findings from the code audit for this plan

These were found while preparing this plan, are not in review files 1-7, and change the plan. Verify each before acting.

| ID | Finding | Evidence | Consequence |
|---|---|---|---|
| F1 | Every reported experiment except E24/E24b runs on the **placeholder** calibration, not the measured laptop bundle. | `configs/base.yaml`: `calibration: configs/calibration/placeholder/c0`; no other spec overrides it (`grep calibration configs/experiments/*.yaml`). | `method.tex` "Start-up, snapshot, quote and boot costs come from one consumer laptop" is false for the headline. Every v1 number except the calibration-sensitivity row is literature-seeded. |
| F2 | Placeholder function profiles differ from measured ones by 10-400x, and several measured values look wrong. | `configs/functions.yaml` vs `configs/calibration/measured/*/functions.yaml`: compression 1.5 s → 0.0056-0.0197 s; graph-bfs 0.4 s → 0.0009 s; dynamic-html 0.005 s → 2.5-7.9 s; uploader 0.2 s → 1.1-6.3 s. Laptop bundle covers 6 of 12 functions. | Deadlines (`k × (w + 0.05)`) and therefore every deadline-met and P99 number depend on these. dynamic-html and uploader measured times are implausible for those benchmarks (likely network or harness time inside the measurement) and must be audited before use. |
| F3 | Measured co-run interference is far above the assumed cap of 1.1. | i7 bundle `interference`: 1.16-1.65x at 8 concurrent, 1.6-3.5x at 20; laptop: up to 1.55x at 2. | Background "slow one another by a factor of at most 1.1 (assumed)" is contradicted by the project's own data [C13]. |
| F4 | No provider-hosted scheduler exists. Every scheduler, including `clusters.mode = none_global`, is appointed from workers. | `voss/runtime/orchlib/appoint.py` `_rank`/`_appoint` rank `WorkerId`s; `orchestrator.py:149,164`. | The paper's "single global scheduler on provider hardware" was never simulated [B2, D1]. Must be built (§V2.2). |
| F5 | The result watchdog is followed by a probe with its own 2 s timeout before a retry. | `DetectionConfig.probe_timeout_s = 2.0`, `watchdog.py:_watch_fire` → `_probe_timeout`. | Minimum time to retry a lost synchronous invocation is ≥ 3 s + 2 s, above every synchronous deadline [C9]. |
| F6 | Three modules are at the 400-line limit. | `voss/core/config.py` 391, `voss/runtime/scheduler_role.py` 399, `voss/runtime/worker_agent.py` 396. | Any addition must first move code out (AGENTS.md rule 11). Done in §V0.3. |
| F7 | Keys are scoped per tenant throughout: plan arrays `y[T, J]`, `Key`/`KeyRequest` carry `TenantId`, worker trust sets hold tenant ids. | `voss/policy/plan/types.py`, `diff.py`, `tenant_kbs.py`, `watchdog.py:_suspect`. | Per-function keys [C4, D10] are implemented by remapping key domains, not by rewriting the plan's dimensions (§V4.1). |
| F8 | Exposure can already be switched off by config. | `CostConfig.lambda_exposure`, `PlanParams.use_exposure`. | The gate experiment G0 (§V1) needs no code. |

---

## 2. Target state (one paragraph per layer)

**Research question.** Can machines a provider neither owns nor trusts serve function invocations with deadlines of seconds,
and what determines how well? Expected answer: the number of prepared key holders per function, traded against the number of
machines that could leak the key (review 7 §1). The paper is a design-and-simulation study, says so, and claims nothing it
does not measure [X1, A1, A2].

**Deployment.** Owners lend whole machines for sessions (dedicated, no co-use; e.g. office or lab fleets outside working hours,
booted into the image) [A3]. One scheduler on provider hardware; workers and clients connect outward to provider front ends;
no broker, no clusters, no succession protocol in the paper [B1-B5]. Client TLS terminates inside the worker; the router
forwards bytes it cannot read [C3].

**Trust.** Three owner classes: software-only (Property 1 holds), physical without memory encryption (no confidentiality; integrity
bounded by sampled audit), memory-encrypted (Property 1 up to side channels) [C1, D8]. Tenant root key in the tenant's key
service; per-function data keys, rotated; a worker holds a key until its session ends; snapshots encrypted under the function
data key and never copied between workers [C4, D9-D11].

**Scheduling.** Each function has a key-holder budget `K` set by its tenant; every policy, baselines included, obeys it.
Placement minimises predicted miss of the deadline; there is no exposure weight [D3, B7]. Provisioning keeps enough holders to
cover the 95th-percentile concurrent demand after losing any `f` holders, within `K` [R8].

**Failure handling.** Per-attempt timeout = predicted 95th-percentile completion (no floor); on timeout an idempotent invocation
gets a backup attempt on another holder in a different owner/city/ISP immediately, and the probe runs in parallel for evidence;
per-worker drop estimate with ejection. Compared with heartbeat + fixed timeout + retry, and with consecutive-failure ejection
[C8, C9, D5, F5].

**Evaluation.** Primary metric: share of synchronous invocations that return within their deadline (lost or late = miss).
Trace-driven sessions and arrivals; 24 h measured after warm-up; measured calibration on ≥3 machines; measured decision timing;
all grids reported [D2, D6, D7, E5, E6, F1, F2].

---

## 3. Decision records to add to `docs/DECISIONS.md` (commit first, in its own commit, in V0)

Write each in the file's format (**Decision**, why, rejected alternatives), citing review IDs.

| ID | Decision (one line) | Supersedes / touches |
|---|---|---|
| D-81 | The paper is a design-and-simulation study of the latency/key-holder trade-off; contributions per review 7 §4. | P11 scope; `docs/ROADMAP.md` |
| D-82 | Deployment model: dedicated sessions, no owner co-use; capacity = physical cores; memory = machine memory minus image use. | D-80 (`cpu_frac`), D-02 `drtm_hv` becomes future work |
| D-83 | The paper's system is one scheduler on provider hardware; clustered volunteer-hosted scheduling is reported as a negative result only. | D-12-era geo design, P5 |
| D-84 | Data path: client TLS terminates in the worker; the router forwards without reading. | doc 08 |
| D-85 | Adversary classes S, P, M (software-only, physical, memory-encrypted); Property 1 only for S and M. | D-03 |
| D-86 | Sampled audit: re-execute a fraction `p` of idempotent invocations on a worker of a different owner; ban the TPM identity on mismatch. Receipts feed the audit; no payment claim. | D-04 (blockchain decision stays), doc 09 |
| D-87 | Keys: per-function data keys wrapped by a tenant root key, rotated every `R` hours; hold until session end; snapshots encrypted under the function key; no snapshot or bundle copies between workers. | doc 04 §6, cache P2P |
| D-88 | Exposure is a hard per-function holder budget `K`, enforced for every policy; the exposure term leaves placement and provisioning costs; trust scores leave the paper. | D-12 `sigma`, doc 04 §8 |
| D-89 | Failure handling: timeout at predicted q95 without floor, immediate backup attempt for idempotent functions, probe in parallel; miss-probability hedging removed from the evaluated system. | doc 07 §4-6 |
| D-90 | Detector baselines `timeout_fixed` and `timeout_eject` replace `heartbeat_only` as the comparison. | E08/E15 design |
| D-91 | Metrics: deadline-met as primary; P99 and slowdown include lost invocations at their deadline (censored); holders reported as concurrent, distinct per key version, releases per hour. | doc 06 §2 |
| D-92 | Workload and churn are trace-driven (Azure Functions 2019, Failure Trace Archive SETI@home); parametric regimes become sensitivity sweeps. | doc 02 §2, §8 |
| D-93 | Decision latency: `modeled` mode with coefficients fitted from timing the real policy code on a stated provider CPU. | doc 01 §7 |
| D-94 | Only measured calibration bundles are used for reported results; the placeholder bundle is for tests only. Function profiles must be audited (F2) before use. | doc 10 |
| D-95 | Revision experiments live in a new family (`R*` specs, `paper-v2/`); v1 specs and hashes stay frozen and reproducible. | D-63, D-79 |

---

## 4. Guardrails: rules that prevent the same mistakes (add to `AGENTS.md` as rules 15-32 in V0)

Each guardrail names the review issues it comes from. A PR that violates one is not mergeable.

- **G1 Claims need measurements.** No benefit in the abstract or introduction unless a figure or table in Results measures it
  (proximity [A1], cost [A2], decentralisation [B1]).
- **G2 Equal budgets.** Every compared policy runs under the same key-holder budget `K` and the same detector timeouts; no weight
  converts exposure into latency [B7, D3].
- **G3 Baselines as published.** A baseline named after a paper or product implements that paper's algorithm and parameters; every
  deviation is listed in the methodology section; vendor names are never used for in-house models [D4, E8].
- **G4 Baselines get their class's standard mechanisms.** Any failure-detection baseline has per-request timeouts and retry
  [D5, C8].
- **G5 Deadline-met is the primary metric.** Lost and late both count as misses; latency percentiles include lost invocations as
  censored at their deadline [D6, E9].
- **G6 Report every grid.** Every experiment run for the paper appears in it (main text or appendix); no subset selection [D7].
- **G7 Experiment header.** Every experiment paragraph and caption states: workers, load, utilisation, duration, warm-up,
  architecture, calibration bundle, seeds [D1, D2, F1].
- **G8 One implementation.** All reported results come from one code revision and one configuration family [E3].
- **G9 Warm-up ≥ learning window.** Any learning policy (histogram, survival, rate forecast) gets warm-up at least as long as its
  window before measurement starts [E5, D4].
- **G10 Security claims by class.** A security claim states which owner class (S, P, M) it holds for; no claim relies on memory
  secrecy for class P [C1, D8].
- **G11 Every mechanism has a result or is removed** from the paper [X22, B13].
- **G12 Vocabulary.** Terms from the glossary only (§V12.2); `HUMAN_FEEDBACK.md` style profile and heuristics apply [W, X].
- **G13 Constants table.** Every tunable constant used by a reported system appears once in a table with value, source and whether
  swept [B10].
- **G14 Measured calibration only** for reported results; the bundle name appears in the experiment header [F1, F2].
- **G15 No invented costs.** Decision time, co-run slowdown, start-up and attestation costs are measured or the result that
  depends on them is labelled as model-dependent [D13, F3].
- **G16 Design and simulator are separate.** Design sections never mention the simulator; the methodology section lists what is
  modelled [X1].
- **G17 v1 stays frozen.** No default change that alters v1 hashes; new settings live in `configs/revision.yaml` [D-79].
- **G18 Honest hypothesis timing.** Hypotheses written after a gate run say so; no "pre-registered" for them [E4].

---

## V0. Preparation (docs, structure, no behaviour change)

**Goal:** record decisions, make room in over-full modules, create the revision configuration family. No result hash changes.
**Closes:** prerequisites for all; F6; part of E4, G17.

### V0.1 Decision records and guardrails
- Add D-81 to D-95 (§3) to `docs/DECISIONS.md` under "Current decisions", each marking what it supersedes.
- Add G1-G18 to `AGENTS.md` as rules 15-32 (keep them short; link to this file).
- Add a "Revision (V0-V13)" section to `docs/ROADMAP.md` pointing to this file; move P5 (geo hierarchy) items the paper drops to
  "Parked: kept in code, not evaluated".

### V0.2 Freeze v1
- Copy `paper/` to `paper-v1/` is **not** needed; instead add `paper/README.md` text: "v1 results, frozen; see paper-v2 for the
  revision". Keep `paper/` untouched so `make paper-verify` keeps working.
- In `experiments/paper.py`, rename `ORDER` to `ORDER_V1`, keep an alias `ORDER = ORDER_V1`; add an empty `ORDER_V2 = ()`.
- `tests/unit/test_paper_frozen.py`: keep all v1 checks; add a parallel test for `ORDER_V2` specs (≥ 10 seeds, spec hashes in
  `paper-v2/manifest.json`) that passes vacuously while `ORDER_V2` is empty.

### V0.3 Split over-full modules (pure moves, no logic change)
- `voss/core/config.py` (391 lines): move `CostConfig`, `HedgeConfig`, `AdmissionConfig`, `PlannerConfig`, `ModelsConfig`,
  `DetectionConfig`, `SuccessionConfig` into `voss/core/config_policy.py`; re-export from `config.py` so imports do not change.
- `voss/runtime/scheduler_role.py` (399): move dispatch and outcome handling into `voss/runtime/schedlib/dispatch.py`
  (keep the actor class thin: decode → policy → send, AGENTS.md rule 3).
- `voss/runtime/worker_agent.py` (396): move key handling (`KeyRequest` send, `Key` receive, trust set updates) into
  `voss/runtime/workerlib/keys.py`. V4 extends this module.
- **Test:** `make check` green; `make repro-smoke` and one `voss repro` of a v1 run give identical hashes.

### V0.4 Revision configuration family
- Create `configs/revision.yaml` (`extends: base.yaml`). It starts with only what V1 needs and grows phase by phase; each key has a
  comment naming its decision ID. Initial content:
  - `calibration: configs/calibration/measured/<bundle chosen in V1.1>`
  - `voss.clusters.mode: none_global`
  - `voss.planner.max_plan_workers: 100000`
  - `voss.cost.wait_model: per_worker`, `voss.worker.sync_priority: true` (D-78; on for all revision runs)
- Create `configs/experiments/revision/` for `R*` specs; teach `experiments/sweep.py` and `experiments/runner.py` to accept that
  folder (small change: glob both folders, keep names unique).

**Exit criteria V0:** decisions and guardrails committed; module splits merged with unchanged hashes; `configs/revision.yaml` loads
(`voss run` on a 5-minute toy spec with it succeeds).

---

## V1. Metrics, calibration audit, and the gate run (G0)

**Goal:** before any large investment, find out whether the headline survives the three confounds that need no new mechanism:
global scheduling [D1], no exposure weight [D3], measured calibration [F1], with the right metric [D6].
**Closes:** D6, F1, F2 (audit), part of D1, D2, D3, D9.

### V1.1 Audit measured function profiles [F2] **[ASK before running any harness suite]**
- For each function in each measured bundle, compare `work_ref_s` and `init_s` with SeBS's published ranges and with the
  placeholder. Flag any value more than 10x off either.
- For dynamic-html (2.5-7.9 s) and uploader (1.1-6.3 s): read `tools/calibrate/suites/sebs.py` and the raw logs under
  `calibration/raw/<bundle>/sebs/`; determine whether network fetches, first-run compilation or a harness timeout are inside the
  timing. Fix the harness so `work_ref_s` measures only the handler's execution with inputs local, and `init_s` only
  initialisation. Re-ingest from existing raw logs if possible; rerunning `sebs` (no reboot) needs the author's go-ahead.
- Missing functions in the laptop bundle (6 of 12): either measure them or restrict the workload to functions measured on every
  calibrated machine. **[ASK]** which.
- Write `docs/validation/function-profiles.md` with the table (placeholder, laptop, i7, verdict).
- Choose the bundle for `configs/revision.yaml` (recommend: the i7 NVMe bundle as default, laptop as sensitivity) and record it in
  D-94.

### V1.2 New logged fields (behaviour unchanged)
In the worker and KBS actors, log through the recorder (all go to `Table.EVENTS`, existing schema):
- `key_drop` when a worker discards a key (release, suspicion revocation, session end), with `worker`, `tenant` (key domain),
  `reason`. Today only `key_release` is logged (`tenant_kbs.py`), so holder intervals cannot be reconstructed for sessions that
  end without a release.
- In `Table.INVOCATIONS`, make sure every invocation has a terminal row, including invocations lost after the last attempt
  (`outcome = "lost"`, `t_done = NaN`). Check `experiments/analysis/common.py` to confirm which outcomes exist today.

### V1.3 Analysis library (`experiments/analysis/v2/`)
New package; do not modify v1 analysis modules.
- `metrics.py`:
  - `deadline_met(inv)`: synchronous invocations after warm-up; met = outcome ok and `t_done - t_arrive <= deadline_s`.
  - `latency_censored(inv, q)`: percentile over all synchronous invocations after warm-up, lost ones entered at `deadline_s`
    (and flagged); return value plus the share censored.
  - `slowdown(inv, q)`: response time / warm run time at the invocation's input size (`warm_estimate_s`).
  - `holders(events)`: per key domain, time series of concurrent holders (from `key_release`/`key_drop`), its time average and
    maximum; distinct holders per key version; releases per hour.
  - `utilisation(samples)`: busy concurrency / offered concurrency, time-averaged.
  - `episodes(inv, events)`: intervals where a key domain's synchronous deadline-miss rate over a 10 s window exceeds 50%; count and
    total length per run.
- `paired.py`: paired per-seed differences and ratios with bootstrap intervals (reuse `experiments/analysis/lib.py` functions;
  define the estimator explicitly: ratio of per-seed means, bounded at -100% for reductions) [E13].
- Unit tests in `tests/unit/test_analysis_v2.py` with hand-built frames for each function.

### V1.4 Gate run G0 (configuration only)
- Spec `configs/experiments/revision/R00.yaml` extending `configs/revision.yaml`:
  - 200 workers, `scenario.load.rate` chosen to give 40-60% utilisation (find with a 3-seed pilot, record the value), horizon 3600 s,
    warm-up 900 s, regimes `churn_med`, `churn_high`, seeds 1-20.
  - systems: `keepalive_ttl`, `keepalive_inf`, `hist_prewarm`, `provisioned_keys`, `greedy`.
  - all systems: `voss.cost.lambda_exposure=0`, `voss.planner.params={use_exposure: false}`.
- Analyse with V1.3: deadline-met, censored P99, concurrent and distinct holders, utilisation, episodes.
- Write `docs/validation/R00-gate.md`: table per system; the gap greedy vs best keep-alive in deadline-met with interval; holders.

**Stop condition V1 [ASK]:** report R00 to the author with one recommendation:
- If greedy's advantage over the best keep-alive policy in deadline-miss rate shrinks below 10% relative or its interval
  includes 0, the paper takes story branch C or B (review 7 §7); continue with V2-V8 anyway (they are needed for any branch), but
  the hypotheses in V10 change.
- Otherwise continue unchanged.

**Exit criteria V1:** analysis v2 tested; R00 report written and acknowledged by the author.

---

## V2. Architecture: provider-hosted scheduler and holder budget

**Goal:** make the system the paper describes exist in the simulator, and make exposure comparable by construction.
**Closes:** F4, D1, B2, B12, D3, B7, C5, C6, B10 (partly), X15.

### V2.1 Holder budget `K` (D-88)
- Data: add `max_holders: int | null` per tenant in `configs/tenants.yaml` (null = unlimited) and an experiment-level override
  `voss.keys.max_holders` (int or null) in a new `KeysConfig` in `voss/core/config_policy.py` (default null → v1 behaviour).
- Single choke point: new module `voss/policy/keys/budget.py`:
  - `allowed_new_holders(key_domain, current_holders, K) -> int`.
  - `truncate_plan(plan, K_by_domain, priority)`: keep at most `K` holders per key domain in `plan.y`, preferring existing holders,
    then highest `plan.c`; zero out `c`, `w`, `s` of dropped pairs.
- Call sites:
  - `voss/policy/plan/objective.py:finish()` calls `truncate_plan` for every planner (greedy, milp, erlang*, provisioned_keys,
    histogram, keepalive). This makes the budget policy-independent.
  - `voss/policy/place/candidates.py`: when a key domain is at `K`, exclude non-holders from candidates. If no holder can accept the
    invocation, it queues on holders (it is never sent to a non-holder).
  - `voss/runtime/schedlib/planning.py`: pass current holder counts from the view (confirmed keys) into both.
- Invariant: `voss/runtime/invariants.py` gets `holders_within_budget` checked at each logged `key_release`.
- Tests: property test (`tests/property/test_holder_budget.py`) that random plans and placement sequences never exceed `K`;
  integration test that a keep-alive run with `K=2` shows at most 2 concurrent holders per key domain.

### V2.2 Provider-hosted scheduler [F4] (D-83)
- Config: `voss.scheduler.host: volunteer | provider` (default `volunteer` = v1). With `provider`, also `voss.scheduler.provider_metro`
  (default: the orchestrator's metro) and `voss.scheduler.provider_hw: DC`.
- Read first: `voss/runtime/voss_system.py` (how actors are created and placed on hosts), `orchlib/appoint.py` (appointment),
  `schedlib/succession.py`, `runtime/router.py` (how routers find schedulers).
- Implement: with `provider`, `voss_system.py` creates one scheduler actor on a provider node at system start, registers it with the
  orchestrator as the holder of cluster 0 at epoch 1, and the orchestrator skips worker-based appointment and succession for
  that cluster (guard in `appoint.py`: `if cfg.scheduler.host == "provider": return`). Requires `clusters.mode = none_global`;
  fail config validation otherwise.
- Provider scheduler failures are out of scope for the paper (provider services trusted for availability, D-03); do not inject
  scheduler faults in revision experiments.
- Decision time: charged at DC host speed (until V8 replaces the coefficients).
- Network: scheduler-to-worker messages use the provider node's location; routers reach it directly (no broker hop). Check
  `voss/world/network.py` for how provider nodes are modelled (router metros) and reuse that.
- Tests: integration test that with `provider` no `worker_appointed` (or equivalent) events occur and no worker hosts a scheduler;
  determinism test (two runs, same hash).
- Add to `configs/revision.yaml`: `voss.scheduler.host: provider`.

### V2.3 Remove exposure from costs in revision runs
- `configs/revision.yaml`: `voss.cost.lambda_exposure: 0`, `voss.planner.params: {use_exposure: false, exposure_weight: 0}`.
- Greedy's worker score `S_j(1−p_j)·a_j / (mem + σ(1−a_j))` still multiplies by `a_j`. With one trust technology `a_j` is constant,
  so this is harmless; state it in the constants table. Do not delete code.

### V2.4 Rerun the gate with `K` (G1)
- `R01.yaml` = R00 with `voss.scheduler.host=provider` and a grid `voss.keys.max_holders: [2, 4, 8, 16, null]`.
- Report as in V1.4 plus the curve deadline-met vs `K` per policy. Append to `docs/validation/R00-gate.md`.
- **[ASK]** with the result: choose story branch A, B or C (review 7 §7). Record the choice as D-96.

**Exit criteria V2:** budget enforced for every policy (invariant passes in all R01 runs); provider scheduler runs; G1 reported;
branch chosen.

---

## V3. Baselines that a reviewer will accept

**Goal:** baselines that are published algorithms with published parameters, under the same budget and timeouts.
**Closes:** D4, B6, E7, B14 (autoscaling, harvest-VM parts), G3.

### V3.1 Hybrid histogram policy as published (Shahrad et al., ATC 2020)
- `voss/policy/keepalive_hist.py`, `KeepaliveHistConfig`: add a `profile: v1 | published` switch (default `v1`).
  `published` sets: bin 60 s, range 4 h, per application (here: per function, because each application in the workload is one
  function; say so), head/tail percentiles 5/99, margin 10%, CV threshold 2, out-of-bounds → fixed keep-alive of 4 h range
  (the paper uses ARIMA for that case; we use the fixed fallback and state the deviation).
- Warm-up for every run that includes it: ≥ 4 h of simulated history before measurement (G9). With trace-driven arrivals (V7), the
  history comes from the trace's preceding hours.
- Test: unit test reproducing the paper's example windows for a synthetic idle-time distribution.

### V3.2 Target-concurrency autoscaler (Knative-style)
- New planner `autoscale_kpa` in `voss/policy/plan/autoscale.py`: per function, desired warm instances
  `ceil(observed_concurrency / target)` with target 1 (one invocation per sandbox, as our serial execution), stable window 60 s,
  panic window 6 s, panic threshold 200%, scale-to-zero grace 30 s (Knative defaults; tag `literature`, `# TODO verify` against
  the Knative docs). Places desired instances on the least-loaded holders; keys follow sandboxes; obeys `K` via `finish()`.
- Test: step-load unit test that desired instances follow the published formula.

### V3.3 Greedy-dual keep-alive (FaaSCache, ASPLOS 2021)
- New worker-side keep-alive policy option `voss.worker.keepalive: ttl | greedy_dual` (default `ttl`). Priority = clock +
  frequency × cold-start cost / memory; evict lowest when memory is needed. Implement in `voss/policy/cache_value.py` (it already
  has GDSF; reuse it if it matches the published formula, and say which).

### V3.4 Keep-alive with `K` pre-released holders
- This is `provisioned_keys` without borrowing the count from greedy: new planner option `provisioned_keys` with
  `params.holders = "budget"` → hold the key on `K` most reliable workers. This is the baseline that separates "how many holders"
  from "which and how" [B7].

### V3.5 Synchronous isolation baseline
- Already exists as `voss.worker.sync_priority=true` (D-78) and is on for all revision runs (V0.4), so head-of-line blocking is
  removed for every policy. State in the paper that every system has it [B7 second cause].

### V3.6 Remove from revision experiments
- `on demand` stays (it is the lower bound). `keepalive_inf` stays only as a sensitivity row; the main figure uses the 10-minute
  timer, histogram (published), autoscaler, greedy-dual, keep-alive+K, greedy provisioning.
- Exact program and loss-model variants run only in the alternatives experiment (R06).

**Exit criteria V3:** each baseline has a unit test against its published behaviour; `docs/architecture/06-experiments.md` §4 lists
each baseline with its source and deviations.

---

## V4. Key model

**Goal:** per-function keys with rotation, holders keep keys for the session, no peer copies.
**Closes:** C4, C11, D9, D10, D11, B9.

### V4.1 Key domains [F7]
- Config `voss.keys.scope: tenant | function` (default `tenant`).
- With `function`, the catalog loader (`voss/world/workload.py:load_catalog`) creates one *key domain* per function, id
  `"<tenant>/<function>"`, inheriting the tenant's attributes (`sensitivity`, `kbs_city`, `assurance_floor`, `max_holders`).
  Every place that keys on `TenantId` for keys (plan `y[T,J]`, `KeyRequest`, `Key`, worker trust set, `Release`, KBS) receives the
  key-domain id instead. Invocations keep the real tenant in a separate column for reporting.
- One KBS actor per real tenant serves all its key domains (`tenant_kbs.py`: accept `msg.tenant` in its domain set).
- This is a remapping, not a new dimension; the planner code is unchanged.
- Tests: with `function` scope, a worker running two functions of one tenant issues two key requests; holder counts are per function.

### V4.2 Rotation
- `voss.keys.rotate_s` (default null = never). The KBS increments a version per key domain every `rotate_s`; it logs
  `key_rotate`. Holders receive a `KeyRotate` notice (new message in `voss/core/messages.py`, via `net.send`) and must re-fetch the
  new version before the next invocation start; until then the worker counts as a non-holder for placement.
- Snapshots record the key version they were written under; a restore with an old version is not allowed (it falls back to boot).
  This is the freshness check that closes [C11].
- Cost: one key-release round trip per holder per rotation (logged as `key_release` with `reason=rotate`).

### V4.3 Hold until session end (hysteresis)
- `voss.planner.release: immediate | session` (default `immediate` = v1). With `session`, `diff.py` emits `RELEASE` only when
  (a) the worker is suspected or leaving, or (b) the key domain is at `K` and the plan needs the slot for another worker.
- Test: plan sequence where a holder drops out of the plan for one round and returns: no release/readd with `session`.

### V4.4 Snapshot and bundle copies
- Revision runs set `voss.cache.p2p: false` (exists). Snapshot copies from peers are thereby off; bundles come from the registry.
- The hard-disk tier: keep the model (it is a disk on the worker), but drop it from the paper's design text; its ablation was null.

### V4.5 Snapshot encryption (correction to review 5 D10)
- Review 5 D10 proposed sealing snapshots under a worker-local TPM key. **Do not do this.** A worker that can restore a snapshot
  without the function key can run the function after the tenant revoked it, and the restored memory exposes the code anyway, so
  a snapshot holder is a key holder. Snapshots are encrypted under the function data key and its version (V4.2). Record this in
  D-87.

**Exit criteria V4:** with `scope=function, rotate_s=3600, release=session` a 2-hour run shows: holders per function ≤ K, distinct
holders per version reported, releases per hour reported, no snapshot restore across versions.

---

## V5. Failure handling, detector baselines, audit

**Goal:** failures recovered inside deadlines; fair detector baselines; integrity bounded for class P.
**Closes:** C8, C9, D5, F5, B13, D8, C10, D14, E12 (idempotent fraction).

### V5.1 Timeout and backup attempt (D-89)
- `DetectionConfig` additions (defaults reproduce v1): `timeout_quantile: 0.90`, `watchdog_min_s: 3.0` (exists),
  `on_timeout: probe_then_retry | backup_now`.
- Revision values: `timeout_quantile: 0.95`, `watchdog_slack: 1.0`, `watchdog_min_s: 0.0`, `on_timeout: backup_now`.
- `backup_now` (in `voss/runtime/schedlib/watchdog.py:_watch_fire`): if the function is idempotent, immediately place a backup
  attempt on the best holder in a different failure domain (reuse `hedge._other_domain` logic, moved to
  `voss/policy/backup.py`), then send the probe; the probe's outcome only updates the omission estimate and suspicion. If the
  function is not idempotent, only the probe runs.
- First result wins; the other attempt is cancelled (existing cancel path).
- Revision runs set `voss.hedge.name: off`; miss-probability hedging is not part of the evaluated system.
- Predicted completion quantile comes from the run-time estimator (`policy/predict/blr.py` + conformal); check the q95 is
  available and calibrated (the conformal layer exists).

### V5.2 Detector baselines (D-90)
- `DetectionConfig.mode` gets two values; both arm a result timer (today only `progress` does, `watchdog.py:54`):
  - `timeout_fixed`: timer = the invocation's deadline; on expiry retry once on another worker (idempotent only); no omission
    estimate, no suspicion; heartbeats (2 s, 7 s stale) declare crashes.
  - `timeout_eject`: as `timeout_fixed`, plus eject a worker for 30 s after 5 consecutive timeouts (Envoy outlier-detection
    defaults; tag `literature`, `# TODO verify`).
- Keep `heartbeat_only` for v1 reproducibility, unused in revision experiments.
- Every revision detector experiment runs faults longer than any detector needs (worker dropping starts at a random time and
  lasts for the rest of its session); report "not detected" explicitly (censored detection times).

### V5.3 Forging adversary and sampled audit (D-85, D-86)
- World: `voss/world/adversary.py` gets a strategy `forge` (class P only): with probability `forge_p` a completed invocation's
  result digest is wrong. Results carry `digest` (add field to the result message; the true digest is
  `hash(inv_id)` from `core.hashing`).
- Policy: `voss/policy/audit.py`: pure function `select_for_audit(inv, rng_stream, p) -> bool` (idempotent only) and
  `audit_target(view, worker)` (a holder of a different owner and failure domain).
- Runtime: the router (provider, trusted) requests audit re-execution through the scheduler; on mismatch it reports to the
  orchestrator, which bans the worker's TPM identity (worker id) for the rest of the run: the verifier refuses its sessions.
- Metrics: forged results accepted, time to ban, audit overhead (extra executions / all executions).
- Note in the paper: audit catches forging of idempotent functions only; non-idempotent functions of class-P workers have no
  integrity guarantee (G10).

### V5.4 Idempotent fraction
- Scenario key `scenario.idempotent_frac` (default null = catalog values). With a value, the catalog loader marks that fraction of
  functions idempotent by a seeded draw (stream `workload.idempotent`), stratified so the synchronous/asynchronous split is kept.

**Exit criteria V5:** unit tests for each detector mode's timers; integration test where a dropping worker under `backup_now`
yields a met deadline for an idempotent invocation whose first attempt was dropped; audit test where a forging worker is banned.

---

## V6. Capacity model

**Goal:** capacity and contention from measurement, consistent with dedicated sessions.
**Closes:** C13, F3, A3 (capacity part), S10.

- `configs/hardware/*.yaml`: add `physical_cores` (keep `cores` = hardware threads for v1). Fill from the calibration specs
  (`calibration/specs/`) where measured; else from the CPU model (tag `literature`).
- `EnvelopeParams` (`voss/world/workers.py:_envelope`): add `capacity_basis: threads | physical` (default `threads`), and
  `mem_reserved_mb` (image's own memory; default 0). Revision: `physical`, `cpu_frac: 1.0`, `mem_frac: 1.0`,
  `mem_reserved_mb` measured from the image (V11.1; until then 1024 tagged `assumed`), disk fractions 1.0 of the image's
  cache partition size (assumed until V11).
- Interference: `voss/world/execution.py` uses the bundle's measured `interference` table (n concurrent → factor) per function and
  machine, interpolated; the static `1 + 0.1(busy−1)/limit` stays the v1 default. Revision: `execution.interference: measured`.
- Re-check D-80's memory invariant (`world.scenario.check_memory_invariant`) with the new envelope; if it fails for a class,
  that class's concurrency limit is reduced to fit, and the reduction is logged in the scenario summary.
- Tests: envelope unit test for both bases; execution test that measured interference is applied.

**Exit criteria V6:** revision scenario passes the memory invariant for every hardware class; capacity table generated for the paper.

---

## V7. Trace-driven workload and churn; long horizons

**Goal:** realistic arrivals, function mix, tenant structure and host availability; enough duration for learning policies.
**Closes:** E5, E6, D2, A4, X4 (partly).

### V7.0 Throughput check (do first)
- Time a 1-hour simulated run at 1,000 workers and the target load with `configs/revision.yaml`. Record events/s and memory.
- Choose the largest of {24 h at 1,000 workers, 12 h at 500, 6 h at 300} that keeps one run under 2 wall hours and 8 GB.
  **[ASK]** if none fits. Record the choice in D-92.

### V7.1 Azure Functions 2019 trace (arrivals)
- Tool: `tools/traces/azure_functions.py` downloads the public dataset (invocations per function per minute, duration and memory
  percentiles, trigger type, owner and app hashes). Network access may be blocked: check with
  `curl -sS "$HTTPS_PROXY/__agentproxy/status"`; if blocked, **[ASK]** the author to provide the files or allow the host.
- Derivation (committed output `configs/traces/azure2019/<sample>.parquet` plus `provenance.yaml` with source URL, licence, sample
  seed and SHA-256 of inputs; raw files are not committed):
  - Sample 200-500 functions (stratified by invocation-rate decile) from day 1-2.
  - Tenant = owner hash; trigger `http` → synchronous, all others → asynchronous; timer-triggered functions → asynchronous.
  - Each sampled function is mapped to one of the measured profiles (V1.1) by nearest duration percentile (log scale); record the
    mapping. Run time = measured profile scaled to the trace's median duration? **No**: use the measured profile unchanged, so
    run times stay measured; the trace supplies only arrival times, tenant structure and trigger type. State this.
  - Within a minute, arrivals are Poisson with the minute's count (the trace has per-minute counts only; state the assumption).
  - Scale total rate to the utilisation targets by a single multiplier per experiment (record it).
- World: `voss/world/workload.py` gets `load.regime: trace` that reads the derived file; the parametric MMPP stays for sensitivity.

### V7.2 Host availability (sessions)
- Tool: `tools/traces/fta_seti.py` for the Failure Trace Archive SETI@home host availability trace (same network caveat).
- Derivation (`configs/traces/fta_seti/<sample>.parquet` + provenance): sample N hosts with at least 7 days of data; per host,
  availability intervals → sessions; take a 2-day window aligned to a common start; if the trace lacks location, assign cities by
  population weight with stream `world.trace_city` and state it.
- World: `voss/world/sessions.py` gets `kind: trace`. Graceful versus abrupt ends: the trace does not say; keep `graceful_frac` as a
  swept parameter (0, 0.5) and state it.
- The parametric regimes (`churn_med`, `churn_high`) stay as a sensitivity axis.

### V7.3 Horizons and warm-up
- Revision runs: warm-up ≥ 4 h (G9: histogram range) plus the chosen measurement window (V7.0). Analysis drops arrivals in
  warm-up via a per-spec `analysis.warmup_s` field (do not reuse the global constants in `round4.py`/`rerun.py`).

**Exit criteria V7:** trace files committed with provenance; a revision run on traces completes within budget; utilisation targets
hit within ±5 points.

---

## V8. Decision latency and scale

**Goal:** a measured scale limit for one provider-hosted scheduler.
**Closes:** D13, B3, (B1 scale argument).

- Tool: `tools/bench/decision_timing.py` builds synthetic views of 50 to 10,000 workers and 10 to 500 key domains, times the real
  `greedy` planner and the placer (`policy/place/greedy.py`) with `time.perf_counter` (median of 20), on a stated provider-class
  CPU (record `lscpu`). Output `configs/calibration/measured/<host>/decision.yaml` with fitted `a + b·work` per decision kind,
  using the same `work` units `decision_clock` already receives (read the call sites of `DecisionClock.charge` first).
- `configs/revision.yaml`: `decision_clock.coeffs` from that file (keep `mode: modeled`; this preserves determinism; this
  refines review 5 D13, which suggested `replay`).
- Scale experiment R05 (V10) uses the coefficients; report the pool size at which placement latency exceeds 10% of the median
  synchronous deadline.
- Paper: one sentence on regional sharding on provider hardware beyond that size; not evaluated.

**Exit criteria V8:** coefficients committed with host spec; scale runs use them.

---

## V9. What stays in code but leaves the paper

Do not delete working, tested code (other experiments and v1 depend on it). Instead:
- Keep: clusters (`dynamic`, `static_*`), broker modelling, succession, heartbeat-only mode, hedging, MILP, Erlang planners,
  reputation, credits/accounting, five substrates.
- Mark each in `docs/architecture/*.md` with "Not evaluated in the revision (D-83/…)".
- Revision experiments may use them only in R06 (alternatives) or not at all.
- Remove from the paper (V12): everything in this list except the R06 alternatives table.

---

## V10. Revision experiments

**Goal:** the runs behind every figure and table of the revised paper.
**Closes:** D7, E1 (with V11), E3, E9, E10, E11, E12, E14, E16, G6-G8.

### V10.1 Hypotheses (write before running R02-R07; add as doc 06 §9)
State them after G1 and say so (G18). Draft for branch A (adjust for B or C after D-96):
- H19: at equal `K`, greedy provisioning meets more synchronous deadlines than every baseline, at `K` ∈ {4, 8}.
- H20: at equal deadline-met target (95%), provisioning needs fewer holders than the best baseline.
- H21: misses under keep-alive concentrate in episodes where a key domain has fewer free holders than concurrent demand.
- H22: deadline-derived timeouts with backup attempts meet more deadlines than `timeout_eject` when 10-20% of owners drop work.
- H23: sampled audit at p = 1% bans every forging worker within N completed invocations (N computed from `1-(1-p)^n`).
- H24: below a pool size and above a load stated after R03, no policy meets 95% of deadlines.
Decision rules: effect size and 95% paired interval; "supported" if the interval excludes 0 in the stated direction. Holm
correction across H19-H22.

### V10.2 Specs (`configs/experiments/revision/`, all extend `configs/revision.yaml`; ≥ 10 seeds)
| Spec | Purpose | Grid | Systems | Output |
|---|---|---|---|---|
| R02 main | trade-off curve | `K` ∈ {2,4,8,16,∞} × utilisation {30,60,85%} × calibration {i7, laptop} | on demand, ttl-10min, histogram (published), autoscaler, greedy-dual, keep-alive+K, greedy | Fig. deadline-met vs `K`; latency CDF; table |
| R03 mechanism | episodes | subset of R02 (`K`=4, 60%) with full time series logging | ttl-10min, keep-alive+K, greedy | Fig. one episode; episode stats |
| R04 operating region | where anything works | pool {100,300,1000} × utilisation {30,60,85%} × churn {trace, med, high} | best baseline from R02, greedy | Fig. region map |
| R05 droppers and forgers | failure handling | drop α {0,10,20%} × forge {0,5%} × audit {off, 1%} | detectors `timeout_fixed`, `timeout_eject`, ours | Fig. deadline-met; time to eject/ban; false ejections; audit overhead |
| R06 alternatives | negative results | one cell of R02 | exact, loss-model, loss-model budget, survival-blind greedy, clustered volunteer-hosted, hedging on, P2P on, reputation on | Table: effect and interval |
| R07 sensitivity | assumptions | idempotent frac {0,0.5,1}; deadline multiple {2,5,10}; `f` {0,1,2,10%}; rotation {none,1h,24h}; cost-prediction error ±50%; scope {tenant, function}; scale (V8) | greedy, best baseline | Table |
| R08 reference | upper bound | R02 central cell | always-on trusted hosts (`ref_lambda_like` substrate renamed `ref_trusted`) | Line in R02 figure |

- Each spec has an `analysis:` block (warm-up, metrics) read by `experiments/analysis/v2/`.
- Add the specs to `ORDER_V2`; generate `paper-v2/manifest.json` and `paper-v2/run-hashes.csv` with the existing tooling
  (parametrise the output folder).
- Report every cell (G6): main text for R02-R05, appendix tables for the rest.

**Exit criteria V10:** all specs run; `make paper-verify` for v2 matches hashes on a second runner; hypotheses' verdicts in
`paper-v2/scorecard.csv`.

---

## V11. Real measurements **[ASK before each; reboots need explicit approval, AGENTS.md rule 14]**

**Closes:** E1, E2, X11, X17, F2 (if re-measurement chosen), the author's CRITICAL items X-1, X-2, X-3.

### V11.1 Build and boot the image (= EXPERIMENT_TODO X-2 completion)
- Build the locked image (signed kernel, dm-verity root, encrypted cache partition sealed to PCRs, agent). Boot it end to end
  on each calibration machine, ≥ 10 boots, per-step timestamps: firmware, loader, kernel, initrd, dm-verity setup, unseal,
  services, agent start, quote, verifier round trip, certificate, first mutual-TLS connection.
- Fix the `systemd-analyze` race on the i7 (noted in X-2) by reading firmware/loader times from `efivar` LoaderTime variables or
  the TPM event log timestamps.
- Measure the image's resident memory (feeds `mem_reserved_mb`, V6).

### V11.2 Machines (= X-1)
- At least three machines: the HDD laptop, the i7 NVMe desktop, one mid-range SATA-SSD laptop with a **discrete** TPM. Same
  suites, one bundle each, spec files via `tools/calibrate/spec.sh`.

### V11.3 Co-run slowdown per machine
- Already in the bundles (`interference`) for the i7; extend to every machine and to every function used (V1.1).

### V11.4 Multi-worker emulation (the single most valuable validation for acceptance) [E1]
- Extend `tools/emu/` from one host to 5-10 workers (physical machines or VMs with swtpm), real Firecracker, injected WAN delay
  (`tc netem`) matching the simulator's model, sessions killed from the trace, provider-hosted scheduler.
- Run the R02 central cell for ttl-10min and greedy at `K`=4 for 2 h each, 3 repetitions.
- Compare with the simulator on the same scenario: deadline-met, holders, episode count. Report agreement with intervals in the
  paper's methodology section.

**Exit criteria V11:** bundles and spec tables for ≥3 machines; per-step boot table; emulation comparison table.

---

## V12. Paper rewrite

**Goal:** a manuscript that follows review 7 §4, the guardrails, and `HUMAN_FEEDBACK.md`. Wording-only items may start in parallel
with V2 (review 7 §6 Phase 0); results text waits for V10.
**Closes:** all S, W, X items; A, B, C, E items in their writing parts.

### V12.1 Files
- New generator module `experiments/paper_tex/v2.py` emitting `generated/v2/macros.tex` (prefix `V2`) and `generated/v2/tab_*.tex`;
  figures via `experiments/paper_figs.py` new functions writing `figures/v2/`. Never type a result number into a `.tex` file.
- `main.tex`: inputs in this order: `intro`, `background`, `trust` (merged design+trust), `design` (new content), `method`, `results`,
  `discussion`, `related`, `conclusion`, `appendix`. Delete `network.tex` and `faulttol.tex` from the inputs (content moves into
  `design.tex` as listed below). Use `acmsmall,screen,review` options. Fix stacked labels: one `\label` per heading [X12].
- `refs.bib`: verify all 36 `TODO verify` entries against publisher pages or DBLP; move the marker out of `note` (ACM prints it)
  into a BibTeX comment; delete entries that cannot be verified together with the claims citing them [X10].

### V12.2 Glossary (enforce with `tests/unit/test_manuscript.py`: a forbidden-terms check over `sections/*.tex`)
| Use | Never use in prose |
|---|---|
| owner | donor, volunteer (as the person), host (for the owner) |
| worker | node, PC (except "consumer PC" for hardware) |
| invocation | request (except "request rate"), task, job, work |
| sandbox | environment, started environment |
| key holder; holder budget `K` | key exposure, trust score, exposure units |
| provisioning; request placement | plan/planner/planning, slow/fast loop |
| ISP | provider (for the network operator) |
| deadline met | success, successful |
| outcome-based failure detection | judging workers by returned work |
| backup attempt | second copy, hedge, duplicate |
Also forbidden: `E\d\d`, `H\d\d`, "round", "rerun", "placeholder", "shipped", "corrected placement", "original placement",
"blockchain", "\\critical", "\\potrem", "\\todo" [W1, W7, S2].

### V12.3 Section-by-section content (each closes the listed issues)
1. **Abstract** (≤ 170 words; skeleton in review 7 §4; numbers from `V2` macros only): question; dedicated attested machines;
   holder count governs deadlines and leak surface; provisioning result at equal `K`; failure handling result; "simulator calibrated
   on N machines, validated against an N-worker emulation; the worker image is built and measured" (only if V11 done; else say what
   is not built) [S4, X15, E8, A1].
2. **Introduction** (≤ 1.5 pages): serverless and cold start in plain terms (keep the author-approved opening, HUMAN_FEEDBACK round
   8/10); edge serverless exists and is provider-owned [D12]; the question; dedicated sessions [A3]; what attestation gives per
   owner class [C1]; the three costs before a worker can run (measured on N machines); the holder trade-off; what is built vs designed
   [X1]; three contributions (review 7 §4); findings with numbers; roadmap sentence [S9].
3. **Background and problem**: Terms table [X3]; start-up cost breakdown figure (stacked per-step bars per machine) [X17, X-3]; how
   sessions end; deadlines: where they come from (one sentence on Lambda's default, not three) [S7]; the problem statement as an
   optimisation (variables: holders `y`, warm sandboxes `w`, reserved concurrency `c`; objective; constraints: `K`, memory, cover
   after `f` losses) [S6, B11].
4. **Trust model**: owner classes table (class, capabilities, guarantee, mechanism) [C1, D8, R4]; attestation flow figure (keep
   `diagrams/attest.tex`); key hierarchy and rotation [C4, D10]; what the tenant must trust (provider image, verifier; tenant key
   service availability) [C7]; runtime limits (re-quote proves only the TPM-bound identity; image updates; single-tenant workers
   option) [D15]; firmware reference values as an open problem [C2]; forging and sampled audit [D8, C10].
5. **Design**: request path, numbered to the redrawn architecture figure (router, scheduler, verifier, registry, KBS; no broker)
   [X16, B4]; provisioning (Algorithm 1, greedy cover within `K`) [S6]; request placement (Algorithm 2, cost = predicted miss)
   [D3]; failure handling (timeouts, backup attempts, ejection) [C9]; constants table (every constant, source, swept?) [B10, G13].
   No simulator sentences [G16].
6. **Methodology**: subsections and tables per review 6 X4 (simulated system; workers and traces; workload and traces; network;
   calibration per machine with spec table; decision timing; systems compared with sources and deviations [G3]; experiments table
   with the G7 header fields; metrics and statistics with the estimator defined [E13, E14]); validation against emulation [E1];
   reproducibility in two sentences plus artifact link [E16].
7. **Results**: one subsection per question (review 7 §4), each opening with its finding [X7]: R02 trade-off; R03 mechanism; R04
   operating region (includes the cells where nothing works) [D7]; R05 failure handling and audit; R07 sensitivity; R06 negative
   results table (including clustered volunteer-hosted scheduling: give its v1 numbers only if rerun under revision settings, else
   omit) [B1, B8].
8. **Discussion and limitations**: when the result holds (conditions from R04/R07), why (R03), what would change it; limitations
   list (simulation scope, traces' limits, idempotence, single provider scheduler, class P) [X8].
9. **Related work** (1.5-2 pages + comparison table): serverless keep-alive and autoscaling; edge serverless; harvest/spot capacity
   for FaaS; volunteer and desktop-grid computing; decentralised compute markets with TEEs; confidential FaaS; attestation on consumer
   machines and its attacks; observation-based failure detection (Panorama and successors); fencing and leases (only if needed)
   [S5, B14, C8, D12].
10. **Conclusion**: the trade-off and its conditions; no "strongest we could build" [X9].
11. **Appendix**: all remaining grid tables (G6); reproduction table; hypothesis scorecard with plain-language rows [E13].

### V12.4 Writing pass (after the content is in)
- Apply review 4 W1-W12 and review 6 X6-X23 as a checklist; for each, grep the pattern listed and fix every instance.
- Apply `HUMAN_FEEDBACK.md` heuristics 1-30; after each section, reread it as the cold systems reader described there.
- Run the forbidden-terms test; rebuild `manuscript/main.pdf` in place (HUMAN_FEEDBACK round 13).
- Update `HUMAN_FEEDBACK.md` with a "Revision" entry that summarises the changes and new lessons.

### V12.5 Companion docs
- `docs/explainer/voss-explained.md`, diagrams `arch`, `sim`, `loops`: same vocabulary and the new architecture (remove broker and
  clusters from `arch`; `loops` shows provisioning and placement only).
- `docs/architecture/00, 02, 03, 04, 06, 07, 08, 10`: update to D-81..D-96; mark unevaluated parts (V9).

**Exit criteria V12:** forbidden-terms test green; no red markers in the PDF; every abstract number is a `V2` macro; every figure and
table referenced; page count within TOIT norms (aim 25-30 pages in `acmsmall` including references).

---

## V13. Final review loop

- Re-run the review: for each issue in `manuscript/reviews/FABLE_PAPER_REVIEW_1..6`, write its status (fixed / not applicable after
  revision / open with reason) in `manuscript/reviews/STATUS.md`, citing the commit or section.
- Ask for a fresh review of the new PDF (new reviewer instance or the author) before submission; append findings as review 8.

---

## 9. Traceability: every review issue and where it is closed

| Issues | Closed in |
|---|---|
| A1, D12 | V12.3 (1, 2), D-84, G1 |
| A2, E15 | D-81; cost removed in V12; G1 |
| A3, S10, C13, F3 | D-82, V6 |
| A4, D2 | V7.0, V10 R02 utilisation axis, G7 |
| A5, C10 | D-86, V5.3 |
| B1, B2, B4, B5, S8 | D-83, V2.2, V9, V12.3 (7: R06) |
| B3, D13 | V8 |
| B6, E7, D4 | V3 |
| B7, D3, C5, C6, X15 | D-88, V2.1, V2.3, V3.4 |
| B8 | V10 R06, V12.3 (7) |
| B9, D9, D10, D11, C4, C11 | D-87, V4 |
| B10, G13 | V12.3 (5) constants table, V10 R07 |
| B11, S6 | V12.3 (3, 5) |
| B12, D1, F4 | V2.2, `max_plan_workers` in V0.4 |
| B13 | D-89, V5.1 |
| B14 | V3, V12.3 (9) |
| C1, C2, C7, D8, D15, C12 | D-85, V5.3, V12.3 (4) |
| C3 | D-84, V12.3 (5) |
| C8, C9, D5, F5 | D-89, D-90, V5.1, V5.2 |
| D6, E9 | D-91, V1.3 |
| D7, E10, E11 | V10 R04, G6 |
| D14, E12 | V5.4, V10 R07 |
| D16, E8 | V10 R08 (renamed reference) |
| D17 | V12.3 (5): one sentence; worker benchmarks itself at session start (already modelled by per-worker run-time correction) |
| E1 | V11.4 |
| E2, X11, X17, F1, F2 | D-94, V1.1, V11 |
| E3 | G8, V10 (all on revision family) |
| E4 | G18, V10.1 |
| E5, E6 | D-92, V7 |
| E13, E14 | V1.3, V12.3 (6, 11) |
| E16 | V12.3 (6) |
| S1, S2, S3, S4, S5, S7, S9 | V12.1, V12.3 |
| W1-W12 | V12.2, V12.4 |
| X1-X23 | V12 (X1: G16; X4: V12.3 (6); X5: figures per V10 outputs; X10: V12.1; X12: V12.1; X21: V12.1) |
| HUMAN_FEEDBACK open items (multi-machine, Figure 1, cost, "stop or delay", "What remains", cores, 30 s period, two deployments) | V11.2, V11.1 + V12.3 (3), D-81, V12.4, V12.4, V6, V12.3 (5) constants table, D-83 |

---

## 10. Risks and what to do

| Risk | Sign | Action |
|---|---|---|
| Headline disappears at G0/G1 | gap interval includes 0 | Branch B or C (review 7 §7); keep V2-V11; rewrite hypotheses; do not tune parameters to recover the gap (that would violate G18). |
| Traces cannot be downloaded | proxy refuses host | **[ASK]**; fallback: parametric regimes as primary, labelled assumed, and state it in the abstract. |
| Long runs too slow | V7.0 over budget | Reduce workers before duration; profile the kernel; never shorten warm-up below G9. |
| Function profiles unusable (F2) | harness cannot isolate handler time | Use SeBS published execution times as `literature` seeds for those functions, labelled; keep measured where valid. |
| Image build blocked | no machine or no approval | Keep the paper honest per X1 ("designed, not built"); V11.1 becomes future work; the per-step table uses the stock-system steps with that caveat. |
| Module size limit | > 400 lines | Split before adding (V0.3 pattern). |
| v1 hash drift | `make paper-verify` fails | A default changed; move the change to `configs/revision.yaml`. |
