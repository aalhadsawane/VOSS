# 05 · Code Structure

Python ≥ 3.11, `uv` for env, `numpy`, `scipy` (HiGHS MILP, assignment), `ortools` (CP-SAT/min-cost-flow
comparison), `pandas`+`pyarrow`, `pydantic` (config), `matplotlib`, `pytest`, `ruff`, `mypy`, `import-linter`.
No other frameworks.

## 1. Repository layout

```
VOSS/
├─ pyproject.toml  Makefile  AGENTS.md  README.md  .importlinter
├─ docs/                         # these documents
├─ configs/
│  ├─ base.yaml                  # full default config
│  ├─ functions.yaml             # SeBS-derived function profiles
│  ├─ calibration/               # hw classes, lifecycle dists, reference-cloud params
│  ├─ regimes/                   # churn_{none,low,med,high,burst,correlated}.yaml, load_*.yaml
│  └─ experiments/               # E01_*.yaml ... (see 06)
├─ voss/
│  ├─ core/        kernel.py rng.py types.py config.py registry.py decision_clock.py
│  ├─ world/       geo.py peer.py availability.py network.py lifecycle.py execution.py
│  │               workload.py scenario.py reference_cloud.py
│  ├─ observe/     statestore.py views.py            # only layer allowed to read world
│  ├─ policy/
│  │   predict/    base.py blr.py ewma.py means.py gbq.py knn.py conformal.py
│  │   survival.py reputation.py verify.py keepalive.py retry.py route.py orchestrate.py
│  │   cost.py scalarize.py
│  │   place/      base.py greedy.py matching.py lp_round.py ilp.py baselines/*.py
│  ├─ runtime/     system.py router.py cluster.py orchestrator.py dataplane.py
│  │               controlplane.py faults.py verifier.py ledger.py
│  └─ metrics/     schema.py recorder.py
├─ experiments/    runner.py sweep.py analysis/*.py figures/*.py
├─ tools/          calibrate/ (firecracker, sebs profiling), fit/ (trace fitting)
└─ tests/          unit/ property/ integration/ regression/
```

## 2. Dependency rules (enforced by `import-linter`, run in `make check`)

| Layer | May import |
|---|---|
| `core` | stdlib, numpy |
| `world` | `core` |
| `observe` | `core`, `world` |
| `policy` | `core` **only** (never `world`, `observe`, `runtime`) |
| `runtime` | `core`, `world`, `observe`, `policy`, `metrics` |
| `metrics` | `core` |
| `experiments`, `tools` | everything; nothing imports them |

Policies receive data only via the typed structures in `core/types.py` and `observe/views.py`'s *dataclasses*.
To keep `policy` free of `observe`, the view dataclasses are defined in `core/types.py` and merely *constructed* by
`observe`. This is the single most important rule against spaghetti.

## 3. Core types (`core/types.py`, frozen dataclasses / numpy struct-of-arrays)

```python
Invocation      id, fn, origin, t_arrive, in_bytes, slo_class, deadline, attempt, excluded: frozenset[PeerId]
PeerFeatures    arrays: speed_est, cores, mem_free, disk_free, bw_est, rtt_to(origin), tier, domain, age, rep ...
ClusterView     as_of, peer_ids, PeerFeatures, queue_len, running_residual, lifecycle[fn]→state array, drain_deadline
ClusterSummary  cluster_id, as_of, utilization, headroom, warm_fns, slo_health, pred_completion[fn], n_live
CostMatrix      components: dict[str, ndarray[W,N]], feasible: ndarray[W,N]
Placement       assign: dict[inv_id → list[PeerId]], prewarm: list[...], status, gap, solve_wall_s
MoveOp          kind: move|split|merge, peers, src, dst
Outcome         inv_id, peer, status, timings{wait,startup,net_in,exec,net_out}, wasted_s
```

## 4. Interfaces (`Protocol`s; one line each; all registered by name)

```python
Predictor:   predict(fn, in_bytes, peers, load) -> LogDist ;  update(obs)
Survival:    p_available(peers, horizon_s, now) -> ndarray[N]
Reputation:  update(state, event) -> state ;  score(state, now) -> float
CostModel:   build(invs, view, predictors, survival, rep) -> CostMatrix
Scalarizer:  __call__(cm: CostMatrix, invs) -> ndarray[W,N]
Placer:      place(req: PlaceRequest) -> Placement
Router:      route(inv, summaries) -> ClusterId
OrchestratorPolicy: step(summaries, membership, events) -> list[MoveOp]
KeepAlive:   ttl(peer, fn, view) -> float ;  Prewarm: plan(forecast, view) -> list[PrewarmOp]
RetryPolicy: on_failure(inv, outcome, view) -> RetryDecision
VerifyPolicy: decide(inv, peer_score) -> VerifyDecision
```

Registry: `@register("placer", "ilp")`; config `placer: {name: ilp, time_limit: 0.5, K: 20}`;
`registry.make("placer", cfg)`.

## 5. Config (single pydantic tree, YAML)

```yaml
seed: 1
horizon_s: 3600
scenario:  {peers: 1000, tier_mix: [0.7,0.25,0.05], regime: churn_med, load: {rate: 100, flash: null}, cities: world100}
world:     {heartbeat_s: 5, snapshots: true, p2p_images: true, hw_classes: calibration/hw.yaml}
voss:     # (the VOSS system under test)
  clusters:    {init: kmedoids, target_size: 60, orchestrator: {enabled: true, triggers: [size, slo, demand, drain]}}
  router:      {name: score}
  scheduler:   {mode: hybrid, window_s: 0.2, placer: {name: ilp, time_limit: 0.5, K: 20}, fast_placer: greedy}
  predictor:   {name: blr, forgetting: 0.995, conformal: true}
  cost:        {scalarizer: slo_miss, eps: 0.05, lam: 1.0}
  reputation:  {name: beta_decay}
  lifecycle:   {keepalive: churn_aware, prewarm: ewma_hour}
  retry:       {name: other_lowest_cost, max_attempts: 3, hedge: null}
  verify:      {name: adaptive}
  ledger:      {mode: batched_merkle, epoch_s: 30}
  control:     {mode: replicated, r: 3, hosts: reliability_ranked}
decision_clock: {mode: modeled}
```

A baseline is just another config: same `scenario`, different `voss`-section values (e.g.,
`placer: random`, `clusters: none`). A `system:` key selects `voss` or `reference_cloud`.

## 6. Testing strategy

- **Unit:** every policy on hand-built views (no simulator). Property tests (hypothesis): cost matrix monotonicity,
  `mcf == ilp` on uncoupled instances, placements respect constraints.
- **Invariants (integration, run in every sim test):** no invocation executes on an offline peer; memory/disk
  accounting never exceeds envelope; latency components sum to end-to-end; each invocation has exactly one terminal
  outcome; policies never receive a view with `as_of > now`.
- **Information-boundary test:** a "spy" scenario where world state changes between heartbeats; assert policies saw
  stale data.
- **Determinism:** same manifest ⇒ identical invocation log (`modeled` mode).
- **Regression:** small golden scenario with stored summary metrics (tolerance bands).

## 7. Conventions

Typed everywhere, no module > ~400 lines, no policy state hidden in globals (state objects are passed in/returned),
`Recorder.log(event_type, **fields)` for all observability, one `Makefile` with `check`, `test`, `run`, `sweep`,
`figs`. Docstrings cite the spec section a model implements.
