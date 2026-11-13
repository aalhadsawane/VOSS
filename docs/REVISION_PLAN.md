# VOSS v2: build plan (architecture, code, experiments, paper)

**Audience:** the agent that builds v2 (assume a smaller model than the one that wrote this; follow steps literally).
**Status:** plan. Nothing here is implemented.
**Stance:** clean slate. v1 results, parameters, experiment specs and prose are not reused. A v1 artefact survives only if this
plan names it and says why. "It already exists" is never a reason.

Companion documents (all binding):
| File | What it is |
|---|---|
| `manuscript/reviews/FABLE_PAPER_REVIEW_1..7*.md` | The 110 defects of v1 (IDs A, B, C, E, S, W, D, X) and the reasoning behind this plan |
| `manuscript/HUMAN_FEEDBACK.md` | The author's feedback on abstract, introduction and background; style profile and heuristics 1-30 |
| `manuscript/WRITING_SPEC.md` | How the v2 paper must be written so that feedback and review issues do not recur |
| `docs/handoff/CALIBRATION_HANDOFF.md` | Runbook for the separate bare-metal session |
| `docs/handoff/CALIBRATION_DATA_CONTRACT.md` | Exactly what the bare-metal session must deliver, with acceptance checks |
| `AGENTS.md` | Repository rules 1-14 (unchanged) plus guardrails G1-G18 of §4 once V0 adds them |

Issue IDs in square brackets (e.g. [D3]) refer to the review files. F-numbers refer to §1.

---

## 0. Operating rules for the builder

1. **Branch.** All v2 work lands on the long-lived branch `revision-v2`. It is merged into `main` once, at the end (V15).
   Each phase is a short branch `v2/V<n>-<slug>` cut from `revision-v2`, with a PR **into `revision-v2`**; merge it yourself
   when `make check` and the phase's exit criteria pass (AGENTS.md rule 1). Never push to `main`. Never force-push.
2. **Order.** Phases run in the order of §5's dependency graph. Do not start a phase before its predecessors meet their exit
   criteria.
3. **No inherited numbers.** Every constant a reported system uses must be in `docs/PARAMETERS.md` (V0.6) with one of the
   classes in §3. If you meet a constant in the code that is not in the ledger, add it and classify it before using it.
4. **Experiments run on GitHub Actions** (§6), never on the development container, except smoke tests under two minutes.
   The repository is public; minutes are not a constraint. Calibration and emulation run on bare metal in a separate session
   (`docs/handoff/`).
5. **Decide from results by the written rules** (§V11, §V12.4). Do not ask the author which story to tell. Ask only at the points
   marked **[ASK]** (there are three: bare-metal access, the held-out result if every claim fails, and the author's read of
   abstract/introduction/background).
6. **Design versus held-out data.** Design and tuning use the *development split*; reported results come from the *held-out
   split*, run once after the scheduler is frozen (V11, V12). This is what makes result-driven design honest [E4].
7. **Record decisions** in `docs/DECISIONS.md` in a separate commit (AGENTS.md rule 12). IDs continue from D-81 (D-81 to D-93 were written in V0).
8. **Log raw** through `metrics.Recorder`; analysis reads logs only (AGENTS.md rule 10).
9. **Modules < 400 lines, functions < 50 lines** (rule 11). Three modules are already at the limit [F6]; split before adding.
10. **When unsure, prefer deleting to keeping.** Unused code paths are how v1's confounds stayed hidden [D1, D5].

---

## 1. Facts about v1 found in the code (why a clean slate is needed)

| ID | Fact | Evidence |
|---|---|---|
| F1 | All v1 experiments except E24/E24b ran on the placeholder calibration. | `configs/base.yaml`: `calibration: configs/calibration/placeholder/c0`; no spec overrides it |
| F2 | Placeholder function run times are 5-18,000x **longer** than the measured ones. Measured handler times at the catalogue's reference inputs are microseconds to milliseconds (dynamic-html 25-79 µs, uploader 11-63 µs, graph-bfs 0.9 ms, video-processing 0.18-0.54 s). | `configs/functions.yaml` vs `configs/calibration/measured/*/functions.yaml`; raw samples in `calibration/raw/*/sebs/` agree with the bundles. (An earlier version of this table called two measured values implausible; that was a formatting error in the comparison script, `2.5e-05` printed as `2.500000`. Corrected.) |
| F2a | The measured profiles are faithful to the guest functions, but at one input size each they span only microseconds to 0.5 s, while trace durations span milliseconds to seconds. Mapping trace functions to profiles by duration would put most of them on two or three functions. | V9.1 mapping; `tools/calibrate/suites/sebs.py` `SIZES` |
| F3 | Measured co-run slowdown is 1.6-3.5x at 20 concurrent guests; v1 assumed at most 1.1x. | `interference` in the i7 bundle |
| F4 | No provider-hosted scheduler exists; every scheduler is appointed from workers. | `voss/runtime/orchlib/appoint.py` |
| F5 | A lost invocation is retried no sooner than 3 s + 2 s after dispatch. | `DetectionConfig.watchdog_min_s`, `probe_timeout_s` |
| F6 | `voss/core/config.py` (391 lines), `voss/runtime/scheduler_role.py` (399), `voss/runtime/worker_agent.py` (396) are at the size limit. | `wc -l` |
| F7 | Keys are per tenant everywhere (`y[T, J]`, `Key`, `KeyRequest`, trust sets). | `voss/policy/plan/types.py`, `tenant_kbs.py` |
| F8 | The headline experiment ran in clustered mode at 0.05 invocations/s per worker with an undisclosed exposure weight of up to 3.0. | review 5 D1-D3 |
| F9 | The heartbeat baseline had every request timeout disabled; the histogram baseline had a 30-minute range. | review 5 D4, D5 |
| F10 | "Success" ignored deadlines; latency excluded lost invocations. | `experiments/analysis/common.py` |

Conclusion: no v1 number, default or baseline configuration can be trusted as a starting point.

---

## 2. What v2 is

**Contribution (fixed by the author):** an architecture and a scheduler that let serverless functions with deadlines of seconds
run on volunteer machines that the provider neither owns nor trusts. The evaluation shows that it works, where it stops working,
and what each part contributes.

**Architecture.**
- *Volunteer sessions.* An owner lends a whole machine for a session by booting the VOSS image (no co-use while lent).
  Capacity is the machine's physical cores and its memory minus what the image uses [A3, C13].
- *Provider services* (trusted for availability and correct records, never given keys): front-end routers, one scheduler,
  verifier (also the certificate authority), registry of ciphertext. No broker, no clusters, no scheduler on a volunteer
  machine, no succession protocol [B1-B5, F4].
- *Data path.* A client's TLS connection terminates inside the attested worker. The router forwards bytes by function name and
  cannot read them [C3]. Requests pass through provider front ends; the paper does not claim proximity [A1, D12].
- *Trust.* Three owner classes [C1, D8]:
  - S, software-only: can boot other software, drop or delay messages, power off. Attestation holds. Omission and timing faults only.
  - P, physical access without memory encryption: can read memory, so keys and the signing key can leak. No confidentiality
    guarantee. Integrity is bounded by sampled audit.
  - M, memory-encrypted hardware: as S, up to side channels.
  A tenant states per function which classes may hold its key.
- *Keys.* The tenant's root key stays in the tenant's key service. Each function has a data key, rotated every `R`. A worker
  receives a function's data key only after attestation and keeps it until its session ends or the key rotates. Bundles and
  snapshots are encrypted under the function's data key. Nothing is copied between workers [C4, D9-D11].
- *Holder budget.* A tenant sets `K`, the largest number of workers that may hold a function's key at one time. Every policy
  obeys it. This replaces v1's exposure score, trust scores and weights [D3, B7, C5].

**Scheduler.**
- *Provisioning* (periodic): for each function choose which workers hold its key, how many sandboxes each keeps warm and how much
  concurrency each reserves, so that the 95th-percentile concurrent demand is still covered after losing any `f` holders, within
  `K` and memory. `f` is derived from the measured rate at which workers leave during the time it takes to prepare a
  replacement (not a tenth of a cluster).
- *Request placement* (per invocation): among holders, choose the worker with the lowest probability of missing the deadline;
  ties go to the lowest predicted completion time. No weights.
- *Failure handling:* per-attempt timeout at the predicted 95th-percentile completion time; on timeout an idempotent invocation
  immediately gets a backup attempt on a holder with a different owner, city and ISP; a per-worker drop estimate ejects workers
  that keep failing; a sampled audit re-executes a fraction of idempotent invocations and bans a worker whose result differs.

**Evaluation.** Simulator driven by public traces, calibrated on at least three real machines with the real image, validated
against a multi-worker emulation on real hardware. Primary metric: share of synchronous invocations that return a correct result
within their deadline.

**What v2 does not contain:** clustered or volunteer-hosted schedulers, publish/subscribe, succession, exposure scores,
miss-probability hedging, reputation, credits and payment, peer-to-peer transfers, confidential-VM substrates, "filler"
invocations, loss-model planners, cost analysis, the exact integer program as a system (kept only as an offline optimality
check).

---

## 3. Parameter policy (no sunk-cost constants)

Every constant used by a reported system has exactly one class. `docs/PARAMETERS.md` (created in V0.6) is the single list; the
paper's constants table is generated from it.

| Class | Meaning | Requirement |
|---|---|---|
| **M** measured | from a calibration bundle or a timing run | bundle or file path; machine named |
| **T** trace | from a public dataset | dataset, version, derivation script |
| **L** literature | from a paper or official documentation | citation checked against the source; page or section |
| **D** derived | computed from M/T/L values | formula in the ledger |
| **A** axis | a choice of the tenant or operator shown as an axis of the results | values listed; appears in a figure |
| **S** swept | a design constant with no better basis | default chosen on the development split; sensitivity reported |

There is no "assumed" class. v1 constants and their fate:

| v1 constant | v1 value | v2 |
|---|---|---|
| donated CPU share | 0.75 of threads | removed; capacity = physical cores (M, from machine spec) |
| donated memory share | 0.6 | removed; memory = total − image resident memory (M) |
| donated disk shares | 0.2 | removed; cache partition size of the image (M, a build parameter stated in the paper) |
| co-run slowdown | ≤ 1.1 | M: per function and concurrency level from the bundle |
| trust scores, sensitivity weights σ | 0.8/0.95; 0.1/1/3 | removed |
| cost weight on expected latency | 0.05 | removed; lexicographic tie-break |
| `f` | a tenth of the cluster | D: from measured departure rate × preparation time (V5.3) |
| demand quantile for reserved concurrency | 0.95 | S |
| provisioning period | 30 s | D lower bound (longest preparation action) and S above it |
| deadline multiple | 5 | A: {2, 5, 10} |
| idempotent functions | 11 of 12 | A: fraction {0, 0.5, 1} |
| timeout floor, slack | 3 s, 1.2 | removed; timeout = predicted q95 (D) |
| probe timeout | 2 s | probe no longer gates the retry; S for evidence only |
| hedge threshold and budget | 0.2, 10% | removed |
| suspicion streak and duration | 2, 600 s | S |
| candidates per placement, workers per plan | 12, 40 | removed (all holders are candidates; all live workers are planned) |
| keep-alive timer (baseline) | 600 s | L (cite the measurement study used) and A: {600 s, 4 h} |
| heartbeat period and staleness | 2 s, 7 s | S |
| link speeds, last-mile delay | log-normal 100/30 Mbit/s | T: public broadband measurement dataset (V9.3) |
| worker classes and mix | 4 assumed classes | M classes = the calibrated machines; mix from T (V9.4) |
| session lengths, churn regimes | assumed Weibull/log-normal | T (V9.2) |
| arrivals, popularity, burstiness | assumed MMPP/Zipf | T (V9.1) |
| function run times and sizes | literature placeholders | M (all workload functions, every calibrated machine) |
| decision latency | invented formula | M: timed policy code (V10) |
| key rotation period `R` | none | A: {none, 1 h, 24 h} |
| holder budget `K` | none | A: {2, 4, 8, 16, unlimited} |
| audit rate `p` | none | A: {0, 1%, 5%} |

---

## 4. Guardrails (become AGENTS.md rules 15-32 in V0.5)

A PR that violates one is not mergeable. Each names the defects it prevents.

- **G1 Claims need measurements.** Nothing in the abstract or introduction unless a figure or table measures it [A1, A2, B1].
- **G2 Equal budgets.** Every compared policy runs under the same holder budget `K`, the same timeouts and the same capacity [B7, D3].
- **G3 Baselines as published.** A baseline named after a paper implements that paper's algorithm and parameters; deviations are
  listed in the paper; no vendor names for in-house models [D4, E8].
- **G4 Baselines get their class's standard mechanisms** (request timeouts, retry) [D5, C8].
- **G5 Deadline-met is primary.** Lost and late are both misses; latency percentiles include lost invocations as censored [D6, E9].
- **G6 Report every grid cell** that was run for the paper [D7].
- **G7 Experiment header.** Every experiment states workers, load, utilisation, duration, warm-up, calibration bundles, trace split, seeds [D1, D2, F1].
- **G8 One code revision** for all reported results: the commit tagged `v2-freeze` [E3].
- **G9 Warm-up ≥ the longest learning window** of any compared policy [E5, D4].
- **G10 Security claims name the owner class** they hold for [C1, D8].
- **G11 Every mechanism described in the paper has a result**, or it is not described [X22, B13].
- **G12 Vocabulary and style** per `manuscript/WRITING_SPEC.md` [W, X, HUMAN_FEEDBACK].
- **G13 Every constant is in `docs/PARAMETERS.md`** with a class from §3 [B10].
- **G14 Reported results use measured bundles only**; development may use a provisional bundle, labelled as such [F1].
- **G15 No invented costs** [D13, F3].
- **G16 Design sections never mention the simulator**; the methodology section says what is modelled [X1].
- **G17 Development split for design, held-out split for results**; the held-out sweep runs once [E4].
- **G18 Delete what is not evaluated.** No dormant options, no dead baselines [D1, D5].

---

## 5. Phases and dependencies

```
V0 clean slate ──► V1 calibration harness ──► (bare-metal session: bundles) ─────────────┐
      │                                                                                  │
      ├──► V2 metrics + analysis ──► V6 Actions pipeline ─┐                              │
      │                                                   │                              ▼
      └──► V3 architecture ──► V4 keys ──► V5 scheduler ──┼─► V7 failure handling ─► V8 baselines
                                                          │                              │
                              V9 traces + world data ─────┤                              │
                              V10 decision timing ────────┘                              ▼
                                                              V11 development experiments + freeze
                                                                                         │
                                         (bare-metal session: emulation) ─► V13 ◄────────┤
                                                                                         ▼
                                                              V12 held-out experiments ─► V14 paper ─► V15 merge
```

V1 comes early because the bare-metal session takes calendar time. V2-V10 proceed in parallel with it, using a **provisional
bundle** (the existing `i7_12700_64g_nvme` bundle with dynamic-html and uploader excluded) for development only (G14).

---

## V0. Clean slate

**Goal:** a repository that contains only what v2 uses.
**Closes:** F6; enables G18; removes every v1 confound by construction.

### V0.1 Branch and archive
- `git tag v1-archive origin/main` and push the tag. If tag push is refused, record the `main` commit SHA in
  `docs/DECISIONS.md` D-81 instead.
- Work continues on `revision-v2` (already created from the planning branch).

### V0.2 Delete v1 results, specs and prose (one PR)
Delete:
- `paper/`, `runs-e01/`, `runs-e01-i7-12700-64g/`, `VOSS_research_spec.md`
- `configs/experiments/E*.yaml`, `configs/pilot.yaml`, `configs/ablations.yaml`, `configs/scalability.yaml`, `configs/regimes/`,
  `configs/references/`, `configs/geo/` (rebuilt in V9), `configs/calibration/placeholder/` (keep one tiny fixture under
  `tests/fixtures/calibration/` for unit tests), `configs/functions.yaml` and `tenants.yaml` (rebuilt in V9)
- `experiments/analysis/*` (all v1 modules), `experiments/paper_tex/*`, `experiments/figures/*`, `experiments/paper.py`,
  `experiments/paper_figs.py`, `experiments/paper_verify.py`, `experiments/ecs1*.py`
- `manuscript/ieee-draft9/`, `manuscript/draft/`, `manuscript/generated/*`, `manuscript/figures/*`, and the text of
  `manuscript/sections/*.tex` (replace each with a one-line stub; they are rewritten in V14). Keep `main.tex`,
  `diagram-styles.tex`, `refs.bib`, `HUMAN_FEEDBACK.md`, `reviews/`, `WRITING_SPEC.md`.
- `docs/validation/*` except `i7-12700-64g.md` and `README.md` (calibration worked example); `docs/PLAN-ROUND4.md`,
  `docs/pilots/`, `docs/critique/`, `docs/TRACEABILITY.md`, `docs/proposals/`, `docs/EXPERIMENT_TODO.md` (its open items are
  absorbed by `docs/handoff/`), `docs/AGENT_PROMPT.md`, `docs/research/` (check first; keep only literature notes that V14 cites)
- `.github/workflows/paper-rerun.yml`, `numeric-diagnostic.yml` (replaced in V6; reuse their structure)
- tests that test deleted things: `test_paper_frozen`, `test_paper_verify`, `test_scorecard`, `test_viability`,
  `test_manuscript` (rewritten in V14), `test_breadth`, `test_accounting` and any other that imports a deleted module.

### V0.3 Delete v1 mechanisms from the code (one PR per row; `make check` green after each)
| Remove | Files (starting points; follow imports) | Replace with |
|---|---|---|
| Clusters, cluster routing, dynamic orchestration | `policy/orchestrate*.py`, `policy/route.py`, `runtime/orchlib/standing.py`, `ClustersConfig`, cluster scoring in `runtime/router.py` | one scheduler; router forwards to it |
| Volunteer-hosted scheduler, appointment, succession, epochs for scheduler fencing, scheduler fault injection | `runtime/orchlib/appoint.py`, `runtime/schedlib/succession.py`, `standing.py`, `policy/succession_rank.py`, `SuccessionConfig`, `core/messages_ft.py` (scheduler parts), `runtime/faultdriver.py` (scheduler faults) | scheduler actor on a provider node (V3.1) |
| Broker relay delay | `world/network.py` (relayed-end delay) | direct provider links |
| Hedging by miss probability | `policy/hedge.py`, `HedgeConfig` | backup attempts (V7.1) |
| `heartbeat_only` detection mode | `DetectionConfig.mode`, guards in `watchdog.py`, `router.py` | detector baselines (V7.2) |
| Reputation, credits, accounting, receipts for payment | `policy/reputation.py`, `policy/credits.py`, `runtime/accounting.py`, `core/messages_acct.py`, tables `RECEIPTS`, `CREDITS`, `REPUTATION` | result digest only (V7.3) |
| Loss-model planners | `policy/plan/erlang*.py` | none |
| Exposure terms and trust scores | `CostConfig.sigma`, `lambda_exposure`, `PlanParams.use_exposure/exposure_weight/e_budget`, `assurance` in cost and plan, `assurance_floor` | holder budget and allowed owner classes (V4) |
| Peer-to-peer fetch | `CacheConfig.p2p`, `runtime/workerlib/fetching.py` peer path | registry only |
| Substrates other than the TPM image and the trusted reference | `configs/substrates/{cvm_snp,coco_pool,drtm_hv}.yaml` | keep `appliance_tpm`, `none` (renamed `trusted_host`) |
| "Filler" invocation class | `world/workload.py`, admission filler headroom, preemption of filler | two classes: synchronous, asynchronous |
| Placement baselines not used | `policy/place/baselines/{k8s,aware,random}.py`, `policy/place/flow.py` (batch matching) | `least_loaded` stays as the simple baseline |
| Planner caps | `max_plan_workers`, `hot_top_k`, `hot_fn_k` | none (measure decision time instead, V10) |
| Envelope shares | `EnvelopeParams.cpu_frac/mem_frac/ssd_frac/hdd_frac` | capacity model of V5.5 |
| Decision clock modes `measured`, `replay` | `core/decision_clock.py` | `modeled` with measured coefficients (V10) |
| Parametric session and load regimes | `world/sessions.py` tier models, `world/workload.py` MMPP/Zipf | trace readers (V9); keep one tiny synthetic generator for unit tests under `tests/` |

Keep: kernel, RNG streams, hashing, recorder, manifests, `voss repro`, actor model, `net.send`, lifecycle engine, cache (disk
tiers of one worker), verifier, tenant key service, worker agent, router, scheduler role, predictors (`blr`, conformal, arrivals),
`survival.py`, `omission.py`, greedy planner (rewritten in V5), greedy placer, `milp.py` (offline optimality check only),
calibration harness, emulation tools, import-linter contracts.

After each removal: delete its tests, update `docs/architecture/*.md` (V0.4), run `make check` and a 2-minute smoke run twice
and compare hashes (determinism).

### V0.3 outcome (done on `v2/V0-clean-slate`)
Removed: loss-model planners; batch, random, k8s and warm-aware placers; miss-probability hedging; heartbeat-only
detection; credits, settlement, reputation and the accounting actor; clusters, cluster routing, spillover, scheduler
appointment from workers, leases, checkpoints, standbys, roll calls and scheduler fault injection (replaced by the
provider-hosted scheduler, V3.1 done early); peer-to-peer fetching; relayed workers; substrates other than the TPM image
and the trusted reference; decision-clock replay; the filler class; unused detection settings. Signed receipts stay (the
audit trail for V7.3). The three over-long modules are now under 400 lines, so V0.6's split is no longer needed.
Moved to their phases (they need the replacement first): exposure and trust scores (V4), donated-share envelope and
planner caps (V5), parametric sessions and workload (V9). `system: reference_cloud` has no profiles until V8 rebuilds the
trusted-host baseline. Observed: under one scheduler only about 20 of 74 attested workers received work in a smoke run;
V5 must check how provisioning spreads holders.

### V0.4 Rewrite the architecture docs to the v2 design
Rewrite `docs/architecture/00-overview.md` to §2 of this plan. For `01` (keep), `02` (capacity, lifecycle), `03` (scheduling),
`04` (trust), `06` (experiments), `07` (failure handling), `08` (protocols), `10` (calibration): delete sections about removed
mechanisms; write the v2 text as each phase lands. Delete `09` (reputation and accounting) and `11` if it only lists removed
contracts.

### V0.5 Decisions and guardrails
- `docs/DECISIONS.md`: move D-01..D-80 under a heading "v1 history (not authoritative)". Start "v2 decisions" with:
  D-81 clean slate and archive tag; D-82 contribution and scope (§2); D-83 architecture (§2 Architecture); D-84 owner classes
  and audit; D-85 key hierarchy, rotation, holder budget; D-86 scheduler (§2 Scheduler); D-87 parameter policy (§3);
  D-88 metrics (V2); D-89 traces and splits (V9, V11); D-90 experiments on GitHub Actions (V6); D-91 calibration scope
  (`docs/handoff/`). Re-affirm in one line each the v1 decisions that still hold: custom deterministic simulator, information
  boundary (`policy` never imports `world`), actor model with typed messages, reproducibility rules, no blockchain.
- `AGENTS.md`: add G1-G18 as rules 15-32; replace the workflow line "Read ... `docs/ROADMAP.md`" with "Read
  `docs/REVISION_PLAN.md`"; state the branch rule of §0.1.
- `docs/ROADMAP.md`: replace content with a pointer to this plan and a short "Parked" list (late-launch hypervisor, regional
  scheduler shards, confidential VMs, payment).

### V0.6 Module splits and the parameter ledger
- Split [F6]: `core/config.py` → `config.py` (world, scenario) + `config_policy.py` (scheduler-side); `scheduler_role.py` →
  move dispatch/outcome handling to `schedlib/dispatch.py`; `worker_agent.py` → move key handling to `workerlib/keys.py`.
- Create `docs/PARAMETERS.md` with the table of §3 expanded to one row per config key that survives V0.3: key, value (or
  "pending V<n>"), class, source. Add `tests/unit/test_parameters.py`: every numeric default in `config*.py` and every numeric
  field in `configs/*.yaml` must have a row (parse the ledger's first column).

**Exit criteria V0:** `make check` green; smoke run deterministic; `grep -ri "cluster\|succession\|hedge\|reputation\|credit\|erlang\|sigma\|assurance\|cpu_frac\|filler" voss/` returns nothing (or only words in unrelated senses, each justified in the PR);
decisions and guardrails committed; ledger test green.

---

## V1. Calibration harness changes (so the bare-metal session only runs things)

**Goal:** the harness measures everything the data contract asks for, testable in CI with `--dry-run` and fixtures.
**Closes:** F2a, F3; prepares E1, E2, X11, X17.
Read `docs/handoff/CALIBRATION_DATA_CONTRACT.md` first; it defines the outputs. Implement:

1. **Input sizes that span the trace [F2a].** For every function, measure at SeBS's `test`, `small` and `large` input
   classes (from `benchmarks/*/input.py` in spcl/serverless-benchmarks; e.g. dynamic-html 10/1,000/100,000 random
   numbers, graph benchmarks 10/10,000/100,000 nodes) and at two larger sizes, so that the measured (function, input
   size) profiles together cover handler times from under 1 ms to over 10 s. Record the SeBS class of each size. The
   catalogue's `in_kb` mapping to each function's own size parameter must be stated in the guest function's docstring.
2. **Handler-only timing.** In `guest/fnrunner.py` make sure `make_input` runs before the timer starts and only `handler` is
   timed; log input generation time separately. Add unit tests with a fake clock.
3. **All workload functions.** The workload uses the functions that have a guest implementation in
   `tools/calibrate/guest/functions/` (ten today). Remove the two JavaScript variants from the catalogue unless a Node guest is
   added. Every function is measured on every machine.
4. **Co-run levels.** `sebs` suite: concurrency levels 1, 2, …, physical cores, and threads (not 4x threads); one vCPU per guest;
   record per-guest times so the slowdown distribution is available.
5. **Memory.** New probes: resident memory of the idle image (`image_mem`), resident memory of a running sandbox per function
   (`fn_rss`), snapshot file size per function (`snap_size`).
6. **Image boot per step** (`appliance` suite): per-step timestamps listed in the data contract; read firmware and loader times
   from the EFI `LoaderTimeInitUSec`/`LoaderTimeExecUSec` variables instead of racing `systemd-analyze`.
7. **Key and bundle crypto.** Time bundle decryption per MB (AES-GCM) and the key-release exchange on the machine (`tls` suite
   already exists; confirm it covers both).
8. **Bundle check.** `tools/calibrate/check_bundle.py <bundle>`: verifies every field the contract lists is present, tagged
   `measured`, with `n` ≥ the contract's minimum, and flags any function whose run time is more than 10x away from SeBS's
   published value (as a warning the session must explain). Unit-test it with a good and a bad fixture.
9. **Ingest.** `tools/calibrate/ingest.py` writes the fields of the contract (per-step distributions, not only totals).

**V1 outcome (branch `v2/V1-calibration-harness`).**
- Step 1: `sebs.SIZES` lists every function's input sizes with the SeBS class each matches; co-run levels 1, 2, 4, …,
  physical cores and threads; `fn_rss` and `snap_size` per function.
- Step 2: already true in v1 (`fnrunner` times only `handler`; `make_input` runs before the timer). No change.
- Step 3: the JavaScript variants stay in `configs/functions.yaml` until the catalogue is rebuilt in V9; the harness
  measures only functions with a guest implementation.
- Steps 5-7: `appliance` probe stamps every boot step and idle memory; image gains a TPM-sealed cache partition (not yet
  built or booted); new `keys` suite (key request, unwrap, AES-GCM decryption); `qemu_vm` suite deleted.
- Steps 8-9: `tools/calibrate/check_bundle.py` (tests in `tests/unit/test_check_bundle.py`); ingest writes
  `exec_by_size`, `rss_mb`, `snapshot_mb` per function and `key_release`, `decrypt_per_MB`, `boot_*`, `image_mem_mb`.
- `check_bundle.PUBLISHED` (SeBS reference times) is empty: fill it only from a checked source (class L).

**Exit criteria V1:** `python -m tools.calibrate.run --dry-run --suite all` lists every probe; fixtures pass
`check_bundle.py`; handoff documents reviewed against the final probe names; **[ASK]** the author to start the bare-metal
session(s) with `docs/handoff/CALIBRATION_HANDOFF.md`.

---

## V2. Metrics and analysis

**Goal:** the metric definitions of G5, implemented once, tested, used everywhere.
**Closes:** D6, E9, E13, E14, D9 (metric part), F10.

- Logging (worker, key service, scheduler; all through the recorder):
  - `key_release` (exists) and new `key_drop` with `worker`, `key` (function key id), `version`, `reason`
    (`session_end`, `rotate`, `budget`, `suspect`, `banned`).
  - every invocation gets exactly one terminal row: `outcome ∈ {ok, late, lost, rejected}`, with all attempt timestamps.
  - `attempt` rows: start, end, worker, kind (`first`, `retry`, `backup`, `audit`), result (`ok`, `timeout`, `dropped`, `mismatch`).
  - `eject`, `ban` events with reason.
- `experiments/analysis/` (new package, v2 only):
  - `metrics.py`: `deadline_met` (synchronous, after warm-up; met = ok and on time), `latency_censored(q)` (lost entered at
    deadline, share censored returned), `slowdown(q)` (response time / measured warm run time at that input size),
    `holders` (concurrent time average and maximum per function; distinct holders per key version; releases per hour),
    `utilisation`, `warm_memory`, `episodes` (intervals where a function's deadline-miss rate over 10 s exceeds 50%),
    `detector` (time from first dropped invocation to ejection; false ejections), `audit` (forged results accepted, time to ban,
    extra executions).
  - `paired.py`: per-seed paired differences and ratios with 95% bootstrap intervals; the estimator is written in the
    docstring and in the paper (ratio of per-seed means).
  - `tables.py`, `figures.py`, `macros.py`: emit `manuscript/generated/*.tex`, `manuscript/figures/*.pdf`, and
    `manuscript/generated/macros.tex` (prefix `V`). No number is ever typed into a `.tex` file.
- Tests: `tests/unit/test_metrics.py` with hand-built frames for every function, including a lost invocation and a late one.

**V2 outcome (branch `v2/V2-metrics-analysis`).** Logged: `attempts` table (one row per attempt: first, retry or backup;
ok, cancelled or failure status), `key_dropped` with `reason` (`release`, `session_end`), `busy` and `capacity` in
`samples`. Analysis: `experiments/analysis/metrics.py` (classes met/late/lost/rejected, deadline-met, censored
percentiles with a lower-bound flag, slowdown, holders, utilisation, warm memory, episodes, detection),
`paired.py` (paired difference and ratio of means with seeded bootstrap, Holm), `summary.py` (one row per run),
`macros.py` (prefix `V`, two significant digits). Table and figure emitters are written in V12, when the result
shapes exist. Audit metrics come with V7.3.

**Exit criteria V2:** tests green; a smoke run produces every metric.

---

## V3. Architecture in the simulator

**Goal:** the simulator models the architecture of §2 and nothing else.
**Closes:** F4, B1-B5, C3, D1, B12.

### V3.1 Provider-hosted scheduler
- One scheduler actor created at system start on a provider node (read `runtime/voss_system.py` for actor creation and
  `world/network.py` for provider nodes). Its location is a config key (`provider.scheduler_metro`); its CPU is the provider
  class used in V10.
- The scheduler does not fail in v2 experiments (provider services are trusted for availability; the paper says so).
- Routers send each invocation's metadata to the scheduler and receive an assignment; workers hold one outbound connection to the
  provider (model: provider↔worker messages use the geographic delay to the nearest router metro plus last-mile delay).
- Membership: the verifier tells the scheduler when a session certificate is issued or revoked; workers report state every
  heartbeat period.

### V3.2 Data path
- Message flow per invocation: client → router (nearest metro) → scheduler (metadata) → router → worker (input bytes over the
  worker's downlink) → router (result over its uplink) → client. Add one TLS handshake round trip client↔worker for the first
  invocation of a client connection; model connection reuse with a per-function keep-alive pool at the router (S: pool idle time).
- The router never holds plaintext in the model; this is a design statement, not a simulated property.

### V3.3 Owner classes
- Each worker has `owner_class ∈ {S, P, M}` (from the hardware mix: M only for machines whose spec reports active memory
  encryption; P and S split is an axis A: fraction of owners willing to attack physically, default 0 for performance experiments
  and >0 in the security experiment). Each function has `allowed_classes` (tenant choice; default {S, P, M} for performance
  experiments; the security experiment restricts it).

**Exit criteria V3:** integration test: no scheduler runs on a worker; an invocation's logged path matches V3.2; determinism holds.

---

## V4. Keys

**Goal:** per-function keys, budget, rotation, hold-until-session-end.
**Closes:** C4, C5, C6, C11, D3, D9, D10, D11, B7, B9, F7.

1. **Key identity.** Replace tenant-scoped keys by function-scoped keys everywhere [F7]: plan arrays indexed by function
   (`y[F, J]`), `KeyRequest`/`Key`/`Release` carry `FnId` and `version`, worker trust set holds `(fn, version)`. One key service
   actor per tenant serves its functions' keys.
2. **Budget `K`.** `functions` entries carry `max_holders` (int or null). One enforcement module `voss/policy/keys/budget.py`:
   `may_add_holder(fn, holders_now) -> bool` and `truncate(y, K)`. Called from (a) the end of every provisioning policy and
   baseline, (b) candidate selection in placement (a non-holder is a candidate only if the budget allows a new holder),
   (c) the key service itself, which refuses a release beyond `K` (the tenant enforces its own budget; this is the real
   mechanism and belongs in the design). Runtime invariant `holders_within_budget`.
3. **Rotation.** `key.rotate_s` per function (null = never). At rotation the key service increments the version; holders must
   fetch the new version (one round trip each) before starting another invocation; snapshots written under an old version cannot
   be restored and are deleted.
4. **Hold until session end.** A holder keeps a key until its session ends, the key rotates, it is ejected or banned, or the
   budget requires the place for another worker. Provisioning never releases a key merely because a plan changed.
5. **Snapshots** are encrypted under the function key and version. (Review 5 D10's idea of a worker-local sealed key is
   rejected: a worker that can restore without the key can run the function after revocation.)

**V4 outcome (branch `v2/V4-keys`).** V4.1: the catalogue makes every function its own key domain
`<tenant>/<function>` (`workload.key_domains`), so the planner, placement, trust sets and key messages are per function
unchanged. V4.2: key rotation every `voss.keys.rotate_s`; holders keep their place, drop the old version, delete
snapshots written under it, and fetch the new version on next use (`key_rotate`, `key_dropped reason=rotate`,
`key_release value=version`). V4.3: `hold_until_needed` keeps keys unless the budget needs the place. Budget:
`voss/policy/keys/budget.py`, applied in plan `finish()`, in placement candidates and in the tenant key service; invariant
`holders_within_budget`. Not done here: peer copies were already removed in V0 (V4.4); snapshots are encrypted under the
key version by construction of the rotation rule (V4.5). Test suite runtime grew from about 3.5 to 9 minutes (twice the
keys); revisit with V10's decision timing.

**Exit criteria V4:** property test: random policies never exceed `K`; integration: rotation forces re-fetch; metrics show
distinct holders per version.

---

## V5. Scheduler

**Goal:** the v2 scheduler of §2, written as an optimisation problem and two algorithms, with every constant classified.
**Closes:** B6, B8, B10, B11, S6, D2 (utilisation awareness), C13 (capacity), F3.

### V5.1 Problem statement (write in `docs/architecture/03-scheduling.md` first, then code)
- Sets: functions `F`, live attested workers `J`.
- Per worker (from reports and bundles): physical cores `c_j`, free memory `m_j`, machine class, link speeds, owner class,
  failure domain (owner, city, ISP), drop estimate `p_j`, current keys, warm sandboxes, snapshots, bundles on disk.
- Per function (estimated): arrival rate `λ_f`, mean run time `s_f` on each machine class, memory `mem_f`, `K_f`,
  `allowed_classes`.
- Decisions per period: `y_fj ∈ {0,1}` (j holds f's key), `w_fj ∈ ℕ` (warm sandboxes), `r_fj ∈ ℕ` (reserved concurrency).
- Constraints: `Σ_j y_fj ≤ K_f`; `Σ_f r_fj ≤ c_j`; `Σ_f w_fj·mem_f ≤ m_j`; `r_fj, w_fj ≤ c_j·y_fj`; cover:
  `Σ_j r_fj − (sum of the f_f largest r_fj) ≥ q_f`, where `q_f` is the demand quantile of concurrent invocations and `f_f` is from V5.3.
- Objective: minimise warm memory `Σ w_fj·mem_f` plus the number of new key releases, subject to the constraints; if the cover
  cannot be met within `K_f`, maximise covered demand (lexicographic).
- No survival weighting inside the cover constraint (v1 mixed an expectation with a worst case [B11]).

### V5.2 Algorithms
- **Algorithm 1, provisioning (greedy cover).** For functions in order of uncovered demand: keep existing holders (V4.4); add
  holders in different failure domains, lowest drop estimate first, until the cover holds or `K_f` is reached; spread `r_fj`
  evenly so that no single loss removes more than `q_f/(n−f_f)`; then place warm sandboxes by start-up time saved per MB until
  memory runs out. Rewrite `policy/plan/greedy.py` to this; target < 120 lines.
- **Algorithm 2, placement.** Candidates: holders of `f` with a free concurrency unit or the shortest predicted queue; a
  non-holder is a candidate only if `may_add_holder`. For each candidate predict the completion-time distribution (queue wait
  from replaying that worker's queue, key fetch if needed, start-up at its current level, transfer over its link, run time with
  the measured co-run slowdown at its current concurrency). Choose the lowest probability of exceeding the remaining deadline;
  ties → lowest expected completion. Synchronous invocations are served before queued asynchronous ones on every worker and in
  every compared system.
- **Offline optimality check.** `policy/plan/milp.py` solves V5.1 exactly on small instances (≤ 30 workers, ≤ 10 functions) in a
  test and in one appendix table (gap of greedy to optimum in warm memory and holders). It is never a simulated system.

### V5.3 Derived constants
- `f_f`: the 99th percentile of the number of a function's holders that leave within one preparation time `T_prep` (time to
  attest-if-needed + key release + bundle fetch + sandbox start on the slowest allowed class), from the binomial with the
  per-worker departure probability over `T_prep` estimated online by `survival.py`. Minimum 1.
- Provisioning period: at least the longest preparation action; default chosen on the development split (S).
- Demand quantile `q_f`: quantile (S, default 0.95) of the observed concurrent invocations of `f` over the last window, not a
  Poisson formula (arrivals are bursty).

### V5.4 Estimators (keep, re-check each against the ledger)
- Run time: Bayesian log-linear regression per function and machine class with conformal quantiles (exists).
- Session survival: Weibull per machine class with censoring (exists); used only for `f_f` and for preferring workers less
  likely to leave soon when adding holders.
- Drop estimate: Beta with change detection (exists).
- Arrival rate: maximum of short and long moving averages (exists); window lengths are S.

### V5.5 Capacity model
- A worker's concurrency limit = its physical cores (M, from the machine spec). One vCPU per sandbox.
- Run time of an invocation = measured single-run time × measured co-run slowdown for that function at the worker's current
  concurrency (bundle `interference`, interpolated) [F3].
- Memory available to sandboxes = machine memory − measured idle image memory. Running invocations are admitted against memory
  as well as concurrency (v1's memory-blind admission is removed).
- Cache space = the image's cache partition size (build parameter; in the ledger).

**Exit criteria V5:** unit tests for Algorithm 1 (cover holds after removing any `f_f` holders; never exceeds `K`) and Algorithm 2
(prefers a warm holder; respects deadline); optimality test passes with the gap recorded.

---

## V6. GitHub Actions pipeline

**Goal:** every experiment is a workflow run whose inputs and outputs are recorded.
**Closes:** E3, E16, G8; D-90.

Workflows (adapt the structure of the deleted `paper-rerun.yml`: plan → sweep matrix → publish → analyse):

| Workflow | Trigger | Does |
|---|---|---|
| `ci.yml` | push to `revision-v2`, `v2/**`; PRs | `make check`, 2-minute determinism smoke |
| `traces.yml` | dispatch; push of `runs/requests/traces-*.yaml` | downloads public datasets, runs `tools/traces/*`, uploads derived files to a release `data-<name>-<sha>`, opens a PR with `provenance.yaml` |
| `bench-decision.yml` | dispatch; push of `runs/requests/bench-*.yaml` | times policy code (V10), records `lscpu`, opens a PR with `decision.yaml` |
| `experiment.yml` | dispatch (`spec`, `shards`); push of `runs/requests/<spec>-*.yaml` | plan job builds a shard matrix; each shard runs `python -m experiments.sweep --spec <spec> --shard i/n`; packs raw logs as `tar.zst` release assets under tag `runs-<spec>-<run id>`; analyse job runs `experiments.analysis`, pushes `results/<spec>-<run id>` and opens a PR into `revision-v2` |
| `verify.yml` | dispatch | re-runs a random 10% of a finished experiment on fresh runners and compares result hashes |
| `manuscript.yml` | push touching `manuscript/**` | builds the PDF, runs the forbidden-terms and feedback-regression tests (V14), uploads the PDF |

Rules:
- **Trigger from a non-default branch:** `workflow_dispatch` may not be offered for workflows that exist only on `revision-v2`.
  Every workflow therefore also triggers on a push of a small request file under `runs/requests/` on `revision-v2`
  (`{spec: R02, shards: 40, note: "..."}`). Committing the request file is the way to start a run; it also records who asked
  for what.
- Use the GitHub MCP tools to watch runs and read logs. Do not poll in a loop; check when the next step needs the result.
- Each shard job: `timeout-minutes: 340`. A single simulation run must finish within one job; size runs accordingly (V9.5).
- Keep the numeric pin (`NPY_DISABLE_CPU_FEATURES`, single-threaded BLAS) from v1's workflows; it is what makes hashes equal across runner CPUs.
- Every job prints `nproc`, memory and `lscpu` at start. Do not assume a runner size.
- Raw logs live in releases (assets < 2 GiB each); the repository stores manifests, hashes, per-run metric summaries
  (`results/<spec>/summary.parquet`) and generated tables and figures.
- `experiments/sweep.py` gains `--shard i/n` (deterministic partition of the run list) and writes one manifest per run with
  scenario hash, bundle hashes, trace hashes, config hash, code commit.

**Exit criteria V6:** a 3-seed toy spec goes request file → sweep → release → analysis PR without manual steps; `verify.yml` matches hashes.

---

## V7. Failure handling, detector baselines, audit

**Closes:** C8, C9, C10, D5, D8, D14, B13, F5, F9.

### V7.1 Timeouts and backup attempts
- Per-attempt timer = predicted q95 completion time of that attempt (from Algorithm 2's distribution). No floor.
- On expiry: if the function is idempotent and another holder exists in a different failure domain, start a backup attempt
  there at once; first result wins, the other is cancelled. A probe to the first worker runs in parallel and only feeds the
  drop estimate. Non-idempotent functions: no backup; the invocation fails at its deadline (reported separately).
- If no second holder exists, there is no backup. The budget `K` therefore limits fault tolerance; show this in the results.
- Retries follow the same rule. Observed in V0 (`tests/integration/test_faults.py`): a v1 retry of a 0.97 s-deadline invocation
  was placed on a worker with no key and no code and started 30 s later. A retry or backup attempt goes only to a worker whose
  predicted completion fits the remaining deadline; if none exists, the invocation is reported as missed at once rather than
  started cold. Restore the assertion "every omitted idempotent invocation meets its deadline when a second holder exists".

### V7.2 Detectors compared (same timers available to all; G4)
| Name | Timer | On expiry | Ejection |
|---|---|---|---|
| `fixed` | the invocation's deadline | retry once elsewhere (idempotent) | never; heartbeat loss removes crashed workers |
| `consecutive` | deadline | retry once | eject after 5 consecutive failures for 30 s (L: Envoy outlier-detection defaults; verify) |
| `voss` | predicted q95 | backup attempt | per-worker drop estimate with change detection; suspicion duration S |

### V7.3 Audit and forging
- Results carry a digest. Adversary strategy `forge` (class P owners only): wrong digest with probability `forge_p`.
- `voss/policy/audit.py`: `select(inv, stream, p)` (idempotent only), `target(view, first_worker)` (holder with different owner
  and domain). The router compares digests; on mismatch both workers are re-audited against a third; the minority worker's TPM
  identity is banned (the verifier refuses its sessions).
- Dropping adversary (classes S and P): strategies drop-all, drop-fraction, drop-after-delay, delay. Faults last until the
  session ends; detection times are reported with "not detected" as a value.

**Exit criteria V7:** integration tests: a dropped idempotent invocation meets its deadline through a backup; each detector's
timers; a forging worker is banned; non-idempotent invocations are never duplicated (invariant).

---

## V8. Baselines

**Closes:** D4, B6, E7, B14, F9; G2-G4.

All baselines run on the v2 architecture, under the same `K`, the same placement (Algorithm 2), the same synchronous-first
queueing and the same failure handling. They differ only in **when keys are released and sandboxes kept warm**.

| Baseline | Source | Implementation notes |
|---|---|---|
| On demand | lower bound | key and sandbox only when an invocation needs them; nothing kept |
| Fixed keep-alive | common practice (L: cite the measurement study the value comes from) | sandbox kept for the timer after each invocation; keys follow first use |
| Hybrid histogram | Shahrad et al., ATC 2020 | as published: per application (one function each here; say so), 1-minute bins, 4-hour range, 5th/99th percentiles, 10% margin, CV rule; out-of-range case uses the fixed timer instead of ARIMA (stated deviation) |
| Target-concurrency autoscaler | Knative pod autoscaler | desired warm sandboxes = ceil(observed concurrency / 1) over a 60 s stable window, 6 s panic window, 200% panic threshold, 30 s scale-to-zero grace (L: verify in Knative docs) |
| Greedy-dual keep-alive | Fuerst and Sharma, ASPLOS 2021 | worker-side eviction by frequency × cold-start cost / size (check `policy/cache_value.py` against the paper's formula) |
| Pre-released keys | isolates "how many holders" | key on the `K_f` workers with the lowest drop estimate; sandboxes by fixed keep-alive |
| Eviction-aware placement | Zhang et al., SOSP 2021 (harvested resources) | prefer workers with the longest predicted remaining session; fixed keep-alive |
| Trusted always-on hosts | upper bound | same workload on hosts that never leave and need no attestation; never called by a vendor's name |

Each has a unit test against its published rule and a row in the paper's "systems compared" table with source and deviations.

**Exit criteria V8:** tests green; all baselines pass the holder-budget invariant.

---

## V9. Traces and world data

**Closes:** E5, E6, D2, A4; classes T in §3.

Every dataset: a tool under `tools/traces/`, run in `traces.yml`, derived file published as a release asset and referenced by
hash in manifests, `configs/traces/<name>/provenance.yaml` (source URL, licence, download date, SHA-256 of inputs, derivation
parameters). Raw downloads are not committed.

### V9.1 Function arrivals: Azure Functions 2019
- Source (verified reachable): `https://github.com/Azure/AzurePublicDataset/releases/download/dataset-functions-2019/azurefunctions_dataset2019_azurefunctions-dataset2019.tar.xz`
  (description: `AzureFunctionsDataset2019.md` in the same repository; licence in `LICENSE`).
- Content: invocations per function per minute for 14 days, trigger type, owner and application hashes, duration and memory percentiles.
- Derivation: tenant = owner hash; a function is synchronous if its trigger is `http`, else asynchronous. Sample functions
  stratified by invocation-rate decile (count is set in V9.5). Map each sampled function to one measured workload function by
  nearest median duration on a log scale among all measured (function, input size) profiles (V1 step 1), and invocations
  of that trace function use that input size (record the mapping and the share of trace functions whose duration is
  outside the measured range). Run times come from the bundles, never from the trace. Within a
  minute, arrivals are a Poisson process with that minute's count (the trace has only per-minute counts; stated in the paper).
  One global rate multiplier per experiment sets utilisation.
- Splits (G17): **development** = days 1-4; **held-out** = days 8-11. Different functions may appear in each; sample separately.

### V9.2 Host availability
Try sources in this order; use the first that works and record which:
1. Failure Trace Archive, SETI@home host availability (`fta.scem.westernsydney.edu.au`; the site refused this planning
   sandbox with 403, so try from an Actions runner and through `web.archive.org`).
2. Any public BOINC project host-availability dataset with per-host on/off intervals (search Zenodo and the project sites).
3. Fallback: draw availability and unavailability intervals from the distributions that Javadi et al. fitted to that trace
   (their per-cluster distribution families and parameters; class L). State in the paper that fitted distributions, not the
   raw trace, were used.
- Derivation: host intervals → sessions; a machine is available to VOSS during an availability interval (state the mapping's
  limit: the trace records when a volunteered host was on and idle, not when an owner would boot a dedicated image).
  Whether a session ends with notice is not in the data: axis A, notice fraction {0, 0.5}.
- Splits: development = hosts with even id, first week; held-out = odd ids, a later week.

### V9.3 Home network
- Use a public broadband measurement dataset with download, upload and latency per connection or small area (candidates: Ookla
  Open Data fixed-broadband tiles; M-Lab NDT; FCC Measuring Broadband America). Choose one whose licence allows research use;
  derive per-region distributions of downlink, uplink and last-mile latency; workers draw from their region's distribution.
- Wide-area delay between cities: great-circle distance with a documented factor (L: cite a measurement study) — keep
  `world/geo.py`'s approach only if its factor has a source; otherwise replace it with a public inter-city latency dataset.

### V9.4 Machines and their mix
- Machine classes are exactly the calibrated machines (one class per bundle).
- Mix: weights from a public hardware survey (e.g. the Steam Hardware Survey's core-count, memory and disk-type shares; or host
  specs in the BOINC data if obtained in V9.2), each survey bucket assigned to the nearest calibrated machine by cores and
  memory. Record the mapping and the share of the survey no calibrated machine represents well.
- Cities: population-weighted (GeoNames), restricted to the regions covered by V9.3.

### V9.5 Sizing (do this before defining experiments)
- On an Actions runner, time simulated runs of 1 h at 300, 1,000 and 3,000 workers at 60% utilisation. Record events per second
  and peak memory.
- Choose the largest pool and duration such that one run (warm-up 4 h + measured window) finishes in under 4 wall hours and
  under 10 GB. Target: 1,000 workers, 24 h measured. If that does not fit, reduce workers before duration; never shorten warm-up
  below 4 h (G9). Record in D-89.

**Exit criteria V9:** derived files published with provenance; `docs/PARAMETERS.md` rows for every T value; a traced smoke run completes.

---

## V10. Decision timing

**Closes:** D13, B3, G15.

- `tools/bench/decision_timing.py`: synthetic views of 50-10,000 workers and 10-500 functions; time Algorithm 1 and Algorithm 2
  (median of 20, `time.perf_counter`), single thread. Run in `bench-decision.yml`; record the runner's `lscpu`.
- Fit `a + b·work` per decision kind with the `work` units the decision clock already receives; write
  `configs/calibration/provider/<cpu-label>/decision.yaml`; the decision clock reads coefficients from it.
- The result also gives the pool size at which placement latency exceeds 10% of the median synchronous deadline; that is the
  stated limit of one scheduler. Beyond it the paper says "regional scheduler shards on provider hardware", in one sentence,
  not evaluated.

**Exit criteria V10:** coefficients committed with CPU label; a test checks the clock uses them.

---

## V11. Development experiments and scheduler freeze

**Goal:** make the scheduler as good as honest iteration allows, on the development split only, then freeze it.
**Closes:** E4 (by construction), part of B7.

1. Run `D01` (development main): development split, calibration = provisional or final bundles (final as soon as they exist),
   `K` ∈ {2, 4, 8, 16, ∞}, utilisation ∈ {30, 60, 85%}, all baselines and VOSS, 5 seeds.
2. Run `D02` (dropping and forging owners), `D03` (pool size × load).
3. Iterate on Algorithm 1, Algorithm 2 and the S-class constants **at most five rounds**. Each round: one written hypothesis
   about a cause of misses (from the `episodes` metric and logs), one change, rerun `D01`. Keep a log in
   `docs/validation/development-log.md` (round, hypothesis, change, result). Do not change baselines' published parameters. Give
   baselines the benefit of every general improvement (placement, queueing, timeouts are shared code).
4. Freeze: tag `v2-freeze`. After the tag, no change to `voss/` or `configs/` except bug fixes that are listed in the paper's
   methodology section with their effect.
5. Final bundles are required before the freeze. If the bare-metal session has not delivered, wait (work on V14's wording-only
   parts meanwhile).

**Exit criteria V11:** `v2-freeze` tagged; development log complete; `docs/PARAMETERS.md` has no "pending" rows.

---

## V12. Held-out experiments (run once)

**Closes:** D2, D7, E1 (with V13), E3, E10, E11, E12, G6-G8.

### V12.1 Hypotheses (commit to `docs/architecture/06-experiments.md` before starting the sweep; G17)
- H1 At equal `K`, VOSS meets more synchronous deadlines than every baseline.
- H2 VOSS reaches 95% deadlines met with fewer key holders than every baseline.
- H3 Under 10% and 20% dropping owners, the `voss` detector meets more deadlines than `consecutive`.
- H4 With audit rate `p`, a forging worker is banned after the number of forged results predicted by `1 − (1 − p)^n`.
- H5 There is a pool size and load below which no policy meets 95%; report it.
Verdict rule: paired difference per seed, 95% bootstrap interval, Holm correction over H1-H3; "supported" if the interval
excludes zero in the stated direction.

### V12.2 Specs (held-out split, final bundles, `v2-freeze` code, ≥ 10 seeds)
| Spec | Question | Grid | Output |
|---|---|---|---|
| R01 main | deadlines met against key holders | `K` {2,4,8,16,∞} × utilisation {30,60,85%} × all systems | Fig. 1: deadlines met vs `K`; Fig. 2: latency and slowdown CDFs; Table: holders, releases/h, warm memory |
| R02 mechanism | why baselines miss | R01 central cell, full time series | Fig. 3: one episode (queue, holders, misses over time); episode statistics |
| R03 operating region | where it works | pool {100, 300, 1,000, 3,000 if V9.5 allows} × utilisation × notice fraction | Fig. 4: region map per system |
| R04 owners who drop work | failure handling | dropping owners {0,10,20%} × strategy × detector | Fig. 5: deadlines met; time to eject; false ejections |
| R05 owners who forge | audit | class-P share {5,20%} × `forge_p` × `p` {0,1,5%} | Table: forged results accepted, results to ban, overhead |
| R06 ablation | what each part adds | VOSS minus: cover (`f`=0), warm sandboxes, backup attempts, drop estimate, synchronous-first | Fig. 6 |
| R07 sensitivity | assumptions | deadline multiple, idempotent fraction, rotation `R`, each S constant ±, calibration machine mix, trace source fallback | Table |
| R08 scale | one scheduler's limit | pool sizes up to the V10 limit | Table |
| R09 upper bound | trusted always-on hosts | R01 central cell | line in Fig. 1 |

### V12.3 Run
- One request file per spec; `verify.yml` afterwards on each.
- Every cell appears in the paper or its appendix (G6).

### V12.4 What the paper claims (decided by rule, not by asking)
| Result | Claim in abstract and contributions |
|---|---|
| H1 and H2 supported | "VOSS meets X% of deadlines with N holders; the best existing policy needs M" (primary claim) |
| H2 supported, H1 not at every `K` | state the range of `K` where it holds, in the same sentence |
| Neither, but VOSS meets the 95% target wherever any system does | claim the architecture and scheduler make volunteer serverless work, state the measured operating region, and report that pre-released keys match provisioning at equal `K` (the finding is then that the holder count is what matters) |
| VOSS misses the 95% target everywhere on the held-out split | **[ASK]** the author; do not tune on held-out data |
| H3 supported | include the detector claim with numbers; otherwise describe failure handling as design and report the comparison neutrally |
| H5 | always reported |

**Exit criteria V12:** all specs verified; scorecard generated; claims chosen by the table and recorded as the next free decision ID.

---

## V13. Validation on real hardware (bare-metal session, second visit)

**Closes:** E1.
- Defined in `docs/handoff/CALIBRATION_HANDOFF.md` Part E: 6-10 emulated workers on one bare-metal host (each a process tree
  with pinned cores, a memory limit, its own network namespace with injected delay), real Firecracker sandboxes, real TPM quotes
  at session start, the frozen scheduler, sessions killed from the trace. Runs the R01 central cell at small scale for VOSS and
  fixed keep-alive.
- The builder prepares `tools/emu/` for this before `v2-freeze` (multi-worker support, same policies, same recorder schema) and a
  matching simulator scenario, so the two can be compared run for run.
- Report: deadlines met, holders, start-up level mix, latency CDF, simulator vs emulation, with intervals over repetitions.
  The paper states the agreement and the disagreements.

---

## V14. Paper

**Closes:** all S, W, X items; the writing parts of A, B, C, D, E; HUMAN_FEEDBACK open items.
Follow `manuscript/WRITING_SPEC.md` exactly. Summary of what it fixes:
- structure and content of every section, with paragraph-level outlines for the abstract, introduction and background (the
  sections the author reviewed);
- vocabulary (glossary and forbidden terms, enforced by a test);
- a regression checklist with one check per feedback round 1-20 and per review item W1-W12, X1-X23;
- the process: outline → draft → fact-check against macros and code → cold-reader pass → tests → author's read.
- **[ASK]** the author to read the abstract, introduction and background before the rest is polished; log the result as a new
  round in `HUMAN_FEEDBACK.md`.

Build the checks before writing prose: `make manuscript-check` runs `tests/unit/test_manuscript.py`, which (a) fails on any
forbidden term of `WRITING_SPEC.md` §4.2, (b) fails on the patterns of §5 that can be matched mechanically (rhetorical
questions, sentences opening with "And"/"So", "about" before a macro, draft markers), (c) fails if a number in the abstract
is not a macro, (d) fails if a figure or table is never referenced. The checklist of §6 is applied by hand and its result is
committed as `manuscript/FEEDBACK_REGRESSION.md` (one line per round: pass, with the sentence that satisfies it).

Also in V14: verify every entry of `refs.bib` against the publisher or DBLP and remove printed "TODO verify" notes [X10];
redraw diagrams (`arch` without broker and clusters; `attest`; one for provisioning and placement); update
`docs/explainer/voss-explained.md` to the same vocabulary.

---

## V15. Final review and merge

1. `manuscript/reviews/STATUS.md`: one line per review issue (A1…X23, F1…F10): fixed (where), not applicable in v2 (why), or open.
   No issue may be "open" without the author's acknowledgement.
2. Fresh review of the PDF by a new reviewer session using the same brief as reviews 1-6; fix what it finds.
3. PR `revision-v2` → `main`. Merge only when: all V12 experiments verified, V13 report in, STATUS complete, `make check`
   green, PDF builds without red markers.

---

## 7. Traceability: review issue → phase

| Issues | Where closed |
|---|---|
| A1, D12 | §2 data path; V14 (introduction states provider front ends; edge serverless cited) |
| A2, E15 | §2 scope (no cost analysis); V14 motivation |
| A3, C13, S10, F3 | V5.5; §3 |
| A4, D2 | V9.5 sizing; utilisation axis in R01 |
| A5, C10 | V0.3 (payment removed); V7.3 |
| B1-B5, S8, F4, D1, F8 | V0.3, V3 |
| B6, E7, D4, B14, F9 | V8 |
| B7, D3, C5, C6, X15 | V4 (budget), V8 (pre-released keys), G2 |
| B8 | V0.3 (removed); V5.2 optimality check |
| B9, D9, D10, D11, C4, C11, F7 | V4 |
| B10 | §3, V0.6 |
| B11, S6 | V5.1, V5.2 |
| B12 | V0.3 (caps removed), V10 |
| B13 | V0.3, V7.1 |
| C1, C2, C7, C12, D8, D15 | §2 trust; V3.3; V7.3; V14 trust section |
| C3 | V3.2 |
| C8, C9, D5, F5 | V7.1, V7.2 |
| D6, E9, E13, E14, F10 | V2 |
| D7, E10, E11 | R03, G6 |
| D13, B3 | V10 |
| D14, E12 | §3 axes; R07 |
| D16, E8 | V8 trusted always-on hosts; R09 |
| D17 | V5.1 (machine class from attested spec; run-time estimator per worker) |
| E1 | V13 |
| E2, X11, X17, F1, F2 | V1, bare-metal session, G14 |
| E3 | G8, `v2-freeze` |
| E4 | G17, V11, V12.1 |
| E5, E6 | V9 |
| E16 | V6; one sentence in the paper |
| S1-S9, W1-W12, X1-X23 | V14 and `manuscript/WRITING_SPEC.md` |

---

## 8. Risks

| Risk | Action |
|---|---|
| Bare-metal session delayed | V2-V10 continue on the provisional bundle; `v2-freeze` waits for final bundles |
| Host-availability trace unobtainable | V9.2 fallback (fitted distributions, class L), stated in the paper |
| Runs too slow for one Actions job | reduce pool before duration; profile the kernel; split the measured window into independent days with separate seeds |
| Over-deletion in V0.3 breaks something needed | restore the specific file from `v1-archive`, and record why in a decision |
| VOSS does not beat pre-released keys | V12.4 row 3: the claim changes, the paper does not stall |
| Held-out result fails the target | **[ASK]**; never tune on held-out data |
| A constant has no source | it is class S: sweep it on the development split and report sensitivity |

---

## 9. Every v1 experiment and what replaces it

No v1 experiment is kept or rerun. Each is either replaced by a v2 experiment with a new design, or dropped because the
mechanism it studied is not in v2. "Calibration" (v1's E01 emulation and the calibration suites) becomes the bare-metal work in
`docs/handoff/`.

| v1 | Studied | v2 | Why |
|---|---|---|---|
| E01 | single-box emulation vs simulator | V13 Part E (multi-worker emulation) | one worker could not validate placement, churn or holders |
| calibration suites, E-CS1 | start-up and attestation costs; substrate comparison | bare-metal sessions (handoff Parts A-D); substrate comparison dropped | v1 used the placeholder bundle (F1); other substrates are out of scope |
| E02 | solver time vs planning-pool size | V10 decision timing (bench on Actions) + R08 scale | v1 charged an invented formula |
| E03 | predictors × cost scalarisations | dropped; estimator choice is a development-split decision (V11) | scalarisation weights no longer exist |
| E04, E04b | provisioning vs keep-alive | D01 (development) → R01 main, R02 mechanism | clustered mode, exposure weight, placeholder costs, 30-min runs (D1-D4) |
| E05, E06, E07 | geographic clusters, cluster arrangement, cluster routing | dropped | one provider-hosted scheduler (D-83) |
| E08 | robustness to owners who drop work | D02 → R04 | heartbeat baseline had no timeouts (D5) |
| E09 | cache value policy, P2P, disk tier | dropped; greedy-dual keep-alive becomes a baseline (V8) | P2P removed; v1 result null |
| E10, E10b | simple baseline | dropped; replaced by published baselines (V8) | v1 baseline was misconfigured (E11) |
| E12, E13 | reputation, accounting | dropped | mechanisms removed |
| E14, E25 | churn regimes, session length | traced sessions (V9.2) + R03 operating region + R07 (notice fraction) | parametric churn was assumed |
| E15 | scheduler faults and failover | dropped | provider scheduler trusted for availability |
| E16 | miss-probability hedging | R06 ablation (backup attempts) | hedging removed; backup attempts replace it |
| E17, E17b | Lambda-like and Azure-like references | R09 trusted always-on hosts | vendor names on in-house models (E8) |
| E18 | scale to 10^5 workers | R08 (up to the measured single-scheduler limit) | decision time was invented (D13) |
| E19 | ablation | R06 | ran on the defective placement (E3) |
| E20a/ab/b/c | viability maps | R03 operating region (all cells reported) | grids were selectively reported (D7) |
| E23 | latency vs exposure Pareto | R01 (deadlines met vs holder budget `K`) | exposure score removed |
| E24, E24b | calibration sensitivity | R07 (machine-mix sensitivity over measured bundles) | placeholder bundle no longer exists |
| — | new | R05 forging owners and audit | owner class P (D8) |
| — | new | D03 → R03 pool size × load | operating region |
| — | new | V5.2 optimality check of greedy vs exact (test + appendix table) | replaces E04's MILP-as-system |

Total v2 experiments: 3 development (D01-D03), 9 held-out (R01-R09), 1 emulation (V13), plus the calibration runs per machine.

---

## 10. Breadth, baselines and novelty (amendment after the author's review of V0)

The author asked whether removing clusters, loss-model planners and the rest narrows the paper. Each removed mechanism
was re-examined. A mechanism comes back if v2 can evaluate it fairly and it either adds a claim or answers a question a
reviewer will ask; otherwise the paper states the argument in one paragraph and does not simulate it.

### 10.1 Decisions per removed mechanism

| v1 mechanism | v2 | Reason |
|---|---|---|
| Loss-model (Erlang) provisioning | **Restored as Algorithm 1b, a candidate provisioning rule (V5.2b)** | Its only provable part, the (1 − 1/e) bound for choosing holders under a cardinality limit, applies exactly in v2: the per-function holder budget `K` is a cardinality limit and keys are per function. v1 lost the bound through exposure weights and per-tenant keys. Development (V11) picks Algorithm 1 or 1b as VOSS by deadline-met at equal `K`; the other is reported in R06. |
| Exact program | kept as offline optimality check (V5.2) | answers "how far from optimal is the chosen rule" directly |
| Geographic clusters with volunteer-hosted schedulers | **not restored; replaced by an experiment on partitioning (R10) and a stated argument** | (a) The provider must run routers, verifier and registry with high availability anyway, so a volunteer-hosted scheduler saves no infrastructure. (b) It puts an untrusted owner on the control path of every invocation of a cluster, which needs succession and fencing to tolerate. (c) Under a per-function holder budget, partitioning workers into `C` groups gives each group at most `K/C` holders of a function (or `C·K` holders in total), so partitioning trades holders against latency structurally. R10 measures (c) with provider-hosted regional schedulers, which isolates partitioning from hosting; (a) and (b) are design arguments that need no simulation. v1's numbers are not cited (confounded, D1). |
| Miss-probability hedging | replaced by backup attempts, **and the published hedged-request policy becomes a baseline** | Backup attempts are hedged requests (Dean and Barroso, CACM 2013) restricted to key holders in another failure domain and triggered by the attempt's predicted q95. The baseline sends the second request after the observed 95th-percentile latency to any eligible worker (as published). R04 compares both. |
| Reputation, credits | dropped | the paper does not study incentives (Parked) |
| Peer-to-peer fetching | dropped | null in v1's ablation; contradicts the NAT argument |
| Relayed workers | dropped | only existed for the broker |
| Confidential-VM substrates | dropped | no measurement possible here (Parked) |
| Filler invocations | dropped | never evaluated |

### 10.2 Baselines (all under the same `K`, timeouts, placement and capacity; G2-G4)

Provisioning: on demand; fixed keep-alive; hybrid histogram (Shahrad et al., ATC 2020); target-concurrency autoscaler
(Knative KPA); greedy-dual keep-alive (FaaSCache, ASPLOS 2021); pre-released keys on `K` workers; eviction-aware
placement (harvested resources, SOSP 2021); exact program (optimality bound); trusted always-on hosts (upper bound).
Failure handling: fixed timeout and retry; consecutive-failure ejection (Envoy); hedged requests (Dean and Barroso).
Scheduling structure: one scheduler vs regional provider shards (R10).

### 10.3 What is new (the paper's novelty claims, each tied to a result)

1. **Problem.** Serving deadline-bound functions on machines that leave and whose owners are untrusted, where every
   machine that can run a function must hold its key. The resource scheduled is the set of attested key holders,
   bounded per function by the tenant (`K`). Serverless schedulers assume trusted, durable machines; confidential FaaS
   assumes provider servers that do not leave; volunteer computing replicates every task. (Related work, §8 of the paper.)
2. **Provisioning under a holder budget that survives departures.** A cover rule that keeps demand served after losing
   `f` holders, with `f` derived from measured departure rates over the preparation time, and (Algorithm 1b) a
   loss-model rule with a (1 − 1/e) guarantee per function under the budget; an optimality check against the exact
   program. Result: R01, R06 and the appendix gap table.
3. **Failure handling for owners who drop or forge work.** Timeouts from each attempt's predicted completion, backup
   attempts only on holders in another failure domain, a per-worker drop estimate, and a sampled audit whose detection
   bound is stated per owner class (S, P, M). Result: R04, R05.
4. **Key lifecycle measured as a cost.** Per-function keys, rotation and hold-until-session-end, with key holders
   reported as concurrent, distinct per version and releases per hour; the trade-off between deadlines met and holders
   is the main figure. Result: R01, R07.
5. **An evaluation that a reader can trust.** Real attested image booted on several machines, public traces, a
   development/held-out split, equal budgets for every baseline, every grid cell reported, and a multi-worker emulation.
   Result: methodology and V13.
6. **Partitioning under a holder budget.** Why one scheduler beats regional partitions when holders are budgeted, with
   the measured single-scheduler limit (V10, R08, R10).

### 10.4 Plan changes

- **V5.2b** Restore `erlang_keys.py`, `erlang_math.py` and `erlang_warm.py` from `main` b0f2fb24 as Algorithm 1b. Adapt to
  per-function keys (V4), the budget `K` as the cardinality limit, no exposure prices and no virtual queue (the budget is
  hard). Keep the property tests (Erlang-B closed form, convexity, monotone submodular gain, cardinality respected).
  State the guarantee exactly: per function, for the holder choice with fixed per-holder concurrency; none for the joint
  plan across functions sharing workers.
- **V8** Add the hedged-request baseline (Dean and Barroso): after the observed 95th-percentile latency of the function,
  send a second request to the best other eligible worker; cancel the slower one.
- **V12** Add **R10 partitioning**: `C` ∈ {1, 2, 4, 8} regional provider-hosted schedulers, each with its own holder sets
  (budget `K` per region, and `K/C` per region), on the R01 central cell. Implementation: workers assigned to the
  nearest region; routers send to the region's scheduler; no failover between regions.
- **V11** Development chooses between Algorithm 1 and 1b by deadline-met at equal `K` (D01), recorded as a decision.
