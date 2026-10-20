# Roadmap

Build **one phase at a time**. Each phase ends with a demo command and **exit criteria**; do not start phase *n+1*
until *n* passes. Open a PR per phase and merge it yourself when the exit criteria pass. Sizes are relative (S/M/L).

```
P0 ─ P1 ─ P2 ─ P3 ─ P4 ─ P5 ─ P6 ─ P7 ─ P8 ─ P10 ─ P11
      └──── P9 calibration (parallel from P1; needs the real node) ────┘
```

Critical path for the paper's headline (C2 two-timescale scheduler, C4 cold-start characterization, C5 viability
map): P0 → P4, then P6 and P10, with P9 in parallel.

## P0 · Scaffold (S)
- `pyproject.toml` + `uv.lock`, `Dockerfile`, `Makefile` (`check test run repro-smoke sweep figs paper`), ruff, mypy,
  pytest, `.importlinter` (layer rules + actor isolation), CI.
- `core/`: kernel, rng streams, `types.py`, `messages.py` (empty skeletons), pydantic config, registry, decision clock
  (three modes stubbed), recorder, run manifest; `voss run` and `voss repro` CLIs.
- **Exit:**
  - `make check` green;
  - kernel determinism test;
  - RNG independence test;
  - import-linter fails on `policy → world`;
  - `voss repro` reproduces a toy run's hash.

## P1 · World and scenarios (M)
- `geo`, `hardware` (classes; C0 placeholder until P9), `workers`, `sessions` (donation sessions per tier, diurnal,
  heavy-tailed, regional shocks, fake drains), `adversary` traces, `network` with `net.send`, `resources` (Cpu, Disk
  tiers, Link, Tpm, Psp), `workload` (functions, tenants, arrivals, SLO classes), `substrate` YAML loader (schema +
  validation), `scenario` (generate, hash, store).
- **Exit:**
  - `voss gen-scenario` produces a hashed scenario;
  - tests: delay grows with distance, messages to down hosts are lost, session tails are heavy, timezone waves exist,
    adversary schedules match their spec;
  - all five substrate YAMLs validate.
- **Start P9 now** (suites `caps`, `disk`, `fc_boot`, `fc_snapshot`, `sebs`, `tpm` on the real node).

## P2 · Vertical slice: attested execution end to end (L)
- `world/lifecycle.py` (generic ladder engine) + `world/cache.py` (three tiers, content addressing, LRU only for now)
  + `execution`.
- `observe` (heartbeats → views).
- Actors:
  - `worker_agent` (session establishment, attestation, key requests, ladder, results with receipts);
  - `verifier` (session certs, re-quotes, revocation);
  - `tenant_kbs`;
  - `orchestrator` + `opdb` (one cluster, appointment by epoch CAS);
  - `router` (pending table, `ASSIGNED`/`INPUT`/`ACCEPTED`/`RESULT`, receipts to DB);
  - `scheduler_role` with `random` and `least_loaded` placement and basic retry.
- Substrates: `none`, `appliance_tpm`.
- **Exit:**
  - `voss run configs/smoke.yaml` (1k workers, 1 h) in < 5 min;
  - all invariants of doc 05 §7 pass;
  - latency components sum to end-to-end;
  - trust-cold vs trust-warm visible in logs;
  - deterministic rerun.

## P3 · Prediction and fast loop (L)
- `policy/predict` (means, ewma, blr + conformal, arrival forecaster), `survival`, `omission` (Beta + CUSUM), `cost`
  (components incl. readiness/trust/startup/exposure, completion distribution, scalarizers), placers (`greedy`,
  `flow`, `ilp_window` baseline, first baselines), `hedge`, `retry`, `admission`, decision clock (all modes).
- **Exit:**
  - `flow == ilp_window` on uncoupled instances (property test);
  - online predictor evaluation report;
  - pilots of E03 and the simulated side of E-CS1.

## P4 · Slow loop: trust and warm-state planner + cache policy (L) ★ core novelty
- `policy/plan` (types, `greedy`, `milp` with robust top-f coverage, domain caps, exposure, switching cost, memory/SSD
  knapsack; `diff` → actions), plan actions in `worker_agent` (`PREPARE`, `PIN_SNAPSHOT`, `WARM`, `RELEASE`),
  `cache_value` (GDSF value density, pins, P2P source scoring, SSD↔HDD promotion), planner timers in
  `scheduler_role`, `plans.parquet` logging.
- **Exit:**
  - brute-force test: on tiny instances, plans keep coverage after removing any *f* workers;
  - MILP is never worse than greedy on the objective;
  - pilots of E02, E04, E09, E23.

## P5 · Geo hierarchy (M)
- Clustering (k-medoids + diversity), router scoring with trust-cold penalty, orchestrator triggers, static/global
  baselines, cluster summaries.
- **Exit:**
  - pilots of E05, E06, E07, E10;
  - bounded migrations per worker per hour.

## P6 · Fault tolerance and adversaries (L)
- Progress-based detection (router dispatch watchdog, scheduler result watchdog, stall reports, decision-latency SLO),
  suspicion, succession (instance-bound appointment, fencing, roll call, checkpoint incl. plan, warm standbys, planned
  handover, self-fence), `fault_driver` (adversary effects, partitions).
- **Exit:**
  - property tests under random fault schedules: no stale-epoch execution, no lost invocations;
  - pilots of E08, E14, E15, E16.

## P7 · Accounting and reputation (S)
- Receipt verification and logging, credits (reference work units, cache-donation credit, scheduler credit),
  reputation (`beta_decay` + variants).
- **Exit:**
  - receipts complete vs ground truth under faults;
  - pilots of E12 and E13.

## P8 · Breadth: substrates, references, runner, analysis (L)
- Substrate YAMLs for `cvm_snp`, `coco_pool`, `drtm_hv` (literature ranges; `Psp` resource used), reference clouds,
  remaining baselines, sweep runner, analysis library, figure registry, scalability mode, ablation switches.
- **Exit:**
  - `make sweep EXP=E19` and `make figs` reproduce figures from a clean checkout;
  - E17 and E18 pilots.

## P9 · Calibration and validation (M, parallel)
- **Access (2026-10-08):** the calibration node C0 is not available yet. When it is, the user will share **SSH
  details**; it is *not* the machine the coding agent runs on. The harness must therefore run remotely over SSH
  (copy `tools/calibrate/` to the node, run suites there, copy raw logs back, ingest locally). Reboot/BIOS suites
  still need explicit user approval (AGENTS.md rule 14). Until then, simulator phases use `literature`/`assumed`
  placeholder values for C0.
- **Stand-in laptop (2026-10-14):** a spare Linux laptop, run locally without SSH via `tools/calibrate/laptop/`
  (`appliance run` reboots it ~10 times via a bounded, abortable systemd loop, D-60; `tme` is skipped when the CPU
  lacks memory encryption). The owner approved reboots and data loss for this machine only (rule 14). Its bundle
  describes that laptop, not the i7 node; the C0 label is decided at ingest.
- **Status (2026-10-15):** the stand-in laptop was calibrated in three rounds (D-60, D-61). Committed:
  `calibration/raw/laptop-b9212a4528/`, the measured bundle `configs/calibration/measured/laptop-b9212a4528/` and
  `docs/pilots/ECS1-measured.md`; validation notes in `docs/validation/`. Not measured: four SeBS functions, QEMU q35,
  TME, SSD tier, CVM paths (see the notes). Still open: the i7 node C0 (re-ingest replaces the bundle), E01 (needs P9b).
- `tools/calibrate/` suites (doc 10 §3), `ingest.py`, the measured calibration bundle for C0; manual suites `tme` and
  `appliance` (with user approval).
- P9b: single-box emulation testbed (doc 10 §4), unparked for E01 (D-72); code in `tools/emu/`, scenarios in
  `configs/e01/`, bundle `configs/calibration/measured/c0-9132c8a291` (node C0, non-reboot suites).
- **Exit:**
  - calibration bundle committed and hashed (done for the stand-in laptop);
  - E-CS1 measured table (done, `docs/pilots/ECS1-measured.md`);
  - E01 validation errors reported in `docs/validation/` (blocked on P9b; the notes say so).

## P10 · Paper experiments (M)
- Freeze configs; run everything with ≥ 10 seeds; E20 viability map; Pareto fronts (E23); negative results.
- **Done (2026-10-16):** `make paper` runs the 21 frozen specs in `configs/experiments/` (10 seeds; deviations in D-63:
  E18's 30k/100k points; E02 stays a pilot) and writes every table, figure and the hypothesis scorecard under
  `paper/` from the run logs (`paper/README.md` indexes them; `paper/manifest.json` holds spec hashes and run counts).
  E20 is three viability panels (churn × α, substrate × load, N × load) with VOSS against the best simple baseline and
  an unattested one; E23 is a three-way Pareto with per-class latency; E24 repeats the key comparison under the
  laptop-measured bundle. `make paper-analyze` redraws everything from `runs/` without simulating.
- **Exit:** every paper figure regenerates via `make paper`. ✔
- Results worth knowing (details in `paper/`): H1, H3, H4, H-FT1 and H10 supported; H7 (geo vs global), H11 (simple
  matches VOSS) and the E-CS1 "CVM 10-100× slower" claim refuted at these sizes; H2, H6, H8, H-FT3 inconclusive at 10
  seeds; E20 verdicts depend on the SLO (absolute P99 targets and the deadline-met target are both reported).

## P11 · Manuscript (S)
- First draft of the paper (IEEE Transactions, `IEEEtran` journal mode) under `manuscript/`; numbers and tables are
  generated from `paper/` and the measured bundle (D-65).
- **Done (2026-10-16, draft 1):** `make manuscript` regenerates `manuscript/generated/` and `manuscript/figures/` and
  builds `main.pdf` (11 pages). `tests/unit/test_manuscript.py` fails when the committed generated files are stale;
  the generator fails when a result stops supporting a sentence of the draft.
- **Open before submission:** verify every bibliography entry (written from memory, several marked TODO verify); fill
  author, affiliation and funding; choose the target journal and adapt the class options and length; add related work
  found by a proper literature search; real multi-machine validation (E01) so the simulator claims can be strengthened.

## Parked
Workflows (SeBS-Flow), GPU functions (the node has 2 × RTX 4060 Ti; no confidential GPU path on consumer hardware),
provider-signed transparency log, padding against traffic analysis, DRTM real implementation, real multi-machine
deployment.

From the P5 pilots (to revisit in P8):
- Geo vs global at larger N and load (E05 × E18): at 600 workers a global scheduler still wins; find the crossover.
- Per-cluster robust trust sets multiply key exposure by the number of clusters a tenant is hot in: consider
  cross-cluster robustness (borrowing covered capacity from a neighbor) instead of independent f-robust sets.
- Routing price calibration: amortize the trust-cold price over the expected follow-up demand, and damp herding on
  stale cards (`po2_nearby`/`warm_aware` handled the flash crowd better than `score`).

From P7 (accounting and reputation):
- `reputation_in_cost` ablation (doc 09 §1 double counting) with the P8 ablation switches.
- Probation as low-stakes work (keep newcomers off high-σ tenants' trust sets); P7 implements only the exploration
  floor on tie-break scores.
- Delivered-vs-declared envelope beyond lateness (slots and storage actually offered vs declared at join).
- Work concentration (E12): trust-warm planning gives ~94% of work credit to the top 10% of identities and none to
  ~60% of benign ones, with or without reputation. A tie-break cannot fix that; consider rotating trust-warm sets or an
  exploration quota inside the planner, and measure the latency and exposure cost.

From P8:
- Reject at admission (or at the router) when no reachable host can meet a tenant's assurance floor, instead of
  waiting for give-up (substrate `none`).
- E11 (prediction-error injection × heartbeat period) was not piloted in P6; the `instant` predictor and the
  heartbeat knob exist, noise injection does not yet.
- HDD tier and P2P effects need SSD pressure and longer horizons (E09, E19 show none at 15 min).
- Routing herding at scale (E18): with ~1,000 inv/s, `score` routes each metro's demand to its trust-warm home
  cluster on 1 s-stale cards; those clusters' queues explode (decide P99 12-27 s at 30k-100k workers). Candidate
  fixes: router-side accounting of its own sends since the last card, power-of-d among near-equal clusters, or
  spreading hot tenants' trust over several clusters per metro.
