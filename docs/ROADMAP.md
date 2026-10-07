# Roadmap

Each phase ends with a demo command and **exit criteria**. Do not start phase *n+1* until *n* passes. Sizes are
relative (S/M/L). Critical path for the paper's headline (C1–C4, C6): P0 → P1 → P2 → P3 → P4 → P5 → P8 → P10.
P6 and P7 (ledger, scheduler replication) run after P5; P9 is a parallel track.

```
P0 ─ P1 ─ P2 ─ P3 ─ P4 ─ P5 ─┬─ P6 ──┐
                             ├─ P7 ──┼─ P8 ─ P10
 P9 (calibration, parallel from P1) ─┘
```

## P0 · Scaffold (S)
- `pyproject.toml` + committed `uv.lock`, `Dockerfile`, `Makefile`, ruff/mypy/pytest, `.importlinter` encoding the
  layer rules and the actor-isolation rule, CI workflow (incl. `make repro-smoke`).
- `core`: kernel, rng streams, config (pydantic), registry, `types.py`, `DecisionClock` (all three modes stubbed),
  `metrics.Recorder`, run manifest, `voss run` and `voss repro` CLIs.
- **Exit:** `make check` green; kernel determinism test; RNG stream independence test; import-linter fails if
  `policy` imports `world`; `voss repro` reproduces a toy run's result hash.

## P1 · World and scenarios (M)
- `geo` (city table), `peer`, `network` with `net.send` (geo RTT, bulk transfer, loss/partition hooks), `availability` (Weibull + diurnal + regional shocks + drain events),
  `workload` (functions yaml, Zipf/MMPP arrivals, SLO classes), `scenario` (generate, hash, store).
- **Exit:** `voss gen-scenario` produces a hashed scenario; message delay grows with great-circle distance and
  messages to down hosts are lost (tests); statistical sanity tests (session-length tail,
  timezone-shifted supply waves, regional correlation > independent baseline, arrival rate/Zipf fit); sanity plots.
- Start **P9 in parallel** now (wall-clock measurements are slow).

## P2 · Data-plane vertical slice (L)
- `lifecycle` (S0–S4, memory/disk accounting), `execution`, `observe` (heartbeats as messages, views), `Actor`
  base and `PeerAgent`, **scheduler behind the `SchedulerReplicaGroup` interface with `r=1`** (single replica, no
  consensus yet, but already an actor reached only by `net.send`, with term/token fields in dispatch), single
  global cluster with `random` and `least_loaded` placers, basic retry, recorder, invariants.
- **Exit:** `voss run configs/smoke.yaml` (1k peers, 1 h) finishes in <5 min; all invariants in 05 §6 pass;
  latency components sum to end-to-end; cold-start state shares and failure counts plausible; deterministic rerun.

## P3 · Prediction, cost and placers (L)
- `policy/predict` (means, ewma, blr+conformal), `survival`, `cost` + scalarizers, placers (`greedy`, `matching`,
  `lp_round`, `ilp` with HiGHS; CP-SAT optional), fast/window/hybrid modes, decision clock in both modes, baseline
  placers (first six in 06 §3).
- **Exit:** `mcf == ilp` on uncoupled random instances (property test); online predictor eval harness with coverage
  report; **pilot of E02/E03/E04** on a single cluster; placers respect all constraints.

## P4 · Hierarchy (L)
- Initial clustering (k-medoids), `router` (score + baselines), `orchestrator` (triggers, stability controls),
  per-cluster scheduler instances, cluster summaries, spillover; static/random/global baselines.
- **Exit:** pilots of E05, E06, E10; no thrashing (moves/peer/hour bounded in test); global-ILP gap measured at
  small scale.

## P5 · Risk, reputation, lifecycle policies, drain, tiers (L)
- Reputation rules + fair punishment + newcomer/probation; risk in cost (`pFail` from survival, drain deadlines);
  retry/hedge/replication policies; keep-alive/prewarm policies; snapshots and P2P seeding; filler class; tiers;
  graceful drain handling and handover.
- **Exit:** pilots of E08, E09, E14, E16; double-counting ablation works; no starvation in long-horizon test.

## P6 · Ledger and rewards (M)
- Ledger modes with epoch batching (worker receipts + **scheduler epoch records**), validator group on
  `ReplicationGroup` (use a fixed finality parameter until P7 lands), settlement metrics, audit-join analysis,
  rewards accounting incl. scheduler credit.
- Optional extension (`crash_plus_lazy`): lazy workers, verification policy and replicas through the placer.
- **Exit:** E13/E12 pilots; test that invocation records are invariant to ledger mode; audit join finds zero
  unassigned executions in fault-free runs.

## P7 · Scheduler replication and control-plane faults (L)
- `ReplicationGroup` (Raft-lite: terms, election, majority commit, snapshot, single-server config change) over
  `net.send`; scheduler as replicated state machine (`ENQUEUE/ASSIGN/OUTCOME/EPOCH_CLOSE/CONFIG`), fencing by term,
  token dedupe, committed vs. speculative dispatch, planned leader transfer on drain; replicated orchestrator group;
  replica host selection and replacement; orphan-group handling; `FaultInjector` (crash, preempt, partition);
  buffered outcomes and leader-hint/retry in peers and router.
- **Exit:** property tests on the replication group (07 §3.2) pass under random fault schedules; E15/E21 pilots with
  failover timeline; invariants: in-flight invocations survive scheduler failure, zero execution from stale terms,
  no lost/duplicate invocation under `dispatch: committed`.

## P8 · Baselines, reference clouds, runner, analysis (L)
- Remaining baselines; `ref_lambda_like`/`ref_azure_like`; sweep runner with multiprocessing; analysis library,
  figure registry; scalability mode (10⁵ peers); ablation switches.
- **Exit:** `make sweep EXP=E19` and `make figs` reproduce tables/figures from a clean checkout.

## P9 · Calibration and validation (M, parallel track)
- Firecracker boot/restore/init microbench; SeBS profiling on reference hardware; fit availability and arrivals to
  traces; RIPE/M-Lab-style network fit; reference-cloud calibration; optional SimGrid micro-scenario cross-check;
  solver-time model fit. Validation notes in `docs/validation/`.
- **Exit:** E01 report with errors per model; placeholders in `configs/` replaced or flagged.

## P10 · Paper experiments (M)
- Freeze configs; run E02–E20 with ≥ 10 seeds; regime maps (E20); negative results; figure polish; artifact
  README.
- **Exit:** every paper figure regenerates from `make figs`; manifests archived.

## Parked (do not build unless a result demands it)
Workflows (SeBS-Flow), real trace loaders beyond Azure/FTA, SimGrid backend, ML-heavy predictors beyond
`gbq/knn`, EigenTrust full, scenario-based stochastic program, real local chain calibration, real testbed.
