# 05 · Code Structure

**Stack:** Python ≥ 3.11 with `uv`.

| Need | Library |
|---|---|
| Numerics | `numpy` |
| MILP, assignment | `scipy` (HiGHS `milp`, `linear_sum_assignment`) |
| Data and logs | `pandas`, `pyarrow` |
| Config | `pydantic` |
| Plots | `matplotlib` |
| Quality | `pytest`, `hypothesis`, `ruff`, `mypy`, `import-linter` |

No other frameworks. The calibration harness (`tools/calibrate/`) may use shell tools on the real node, never in the
simulator.

## 1. Repository layout

```
VOSS/
├─ pyproject.toml  uv.lock  Dockerfile  Makefile  .importlinter  AGENTS.md  README.md
├─ configs/
│  ├─ base.yaml                       # full default config
│  ├─ substrates/                     # appliance_tpm.yaml, cvm_snp.yaml, coco_pool.yaml, drtm_hv.yaml, none.yaml
│  ├─ hardware/                       # hw classes (C0 = calibration node, others scaled)
│  ├─ functions.yaml  tenants.yaml
│  ├─ regimes/                        # churn_*.yaml, adversary_*.yaml, load_*.yaml
│  ├─ calibration/measured/<host>/    # ingested distributions + raw logs (doc 10)
│  └─ experiments/                    # E*.yaml
├─ voss/
│  ├─ core/       kernel.py rng.py types.py messages.py config.py registry.py decision_clock.py ids.py
│  ├─ world/      geo.py hardware.py workers.py sessions.py adversary.py network.py resources.py
│  │              substrate.py lifecycle.py cache.py execution.py workload.py scenario.py reference_cloud.py
│  ├─ observe/    statestore.py views.py summaries.py
│  ├─ policy/
│  │   predict/   base.py blr.py ewma.py means.py conformal.py arrivals.py
│  │   survival.py omission.py reputation.py
│  │   cost/      components.py completion.py scalarize.py
│  │   plan/      types.py milp.py greedy.py baselines.py diff.py        # slow loop
│  │   place/     greedy.py flow.py ilp_window.py baselines/*.py          # fast loop
│  │   hedge.py retry.py admission.py cache_value.py route.py orchestrate.py succession_rank.py exposure.py
│  ├─ runtime/    actor.py system.py
│  │              worker_agent.py scheduler_role.py router.py orchestrator.py verifier.py tenant_kbs.py
│  │              opdb.py accounting.py fault_driver.py succession.py
│  └─ metrics/    schema.py recorder.py
├─ experiments/   runner.py sweep.py analysis/*.py figures/*.py
├─ tools/calibrate/  harness (doc 10): probes/*.sh, run.py, ingest.py, emulate/ (single-box testbed)
└─ tests/         unit/ property/ integration/ regression/
```

## 2. Dependency rules (enforced by `import-linter`)

| Layer | May import |
|---|---|
| `core` | stdlib, numpy, pydantic |
| `world` | `core` |
| `observe` | `core`, `world` |
| `policy` | **`core` only** (never `world`, `observe`, `runtime`) |
| `runtime` | `core`, `world`, `observe`, `policy`, `metrics`. **No runtime actor module imports another actor module**; they talk via `core/messages.py` |
| `metrics` | `core` |
| `experiments`, `tools` | Anything; nothing imports them |

View dataclasses (`ClusterView`, `WorkerState`, …) are defined in `core/types.py`, so `policy` stays free of `observe`.

## 3. Core types (frozen dataclasses / struct-of-arrays)

```python
# core/types.py
Invocation     id, fn, tenant, origin, t_arrive, in_bytes, slo_class, deadline, attempt, idempotent, excluded
WorkerState    (doc 08 §5) slots, running, queued, mem/ssd/hdd free, cache: dict[FnVer, CacheEntry], trust: frozenset[TenantId],
               session_expiry, drain_hint, as_of
ClusterView    as_of, workers: tuple[WorkerId], states: WorkerStateArrays, assurance, domains, survival_inputs, ...
ClusterSummary cluster, as_of, load, slo_health, trust_warm_capacity: dict[TenantId, float], robust_slack, diversity
Plan           y: dict[(TenantId, WorkerId), bool], s/w/c: ..., valid_until, cost_terms: dict[str, float]
PlanAction     kind ∈ {PREPARE, PIN_SNAPSHOT, WARM, RELEASE}, worker, tenant/fn, n
CostMatrix     components: dict[str, ndarray[W,K]], candidates: ndarray[W,K], feasible
Placement      assign: dict[InvId, WorkerId], hedges: dict[InvId, WorkerId], status, solve_s
Outcome        inv, attempt, worker, status, timings{route,wait,trust,startup,net,exec}, start_level, trust_cold

# core/messages.py — one frozen dataclass per message in doc 08 §4
```

## 4. Interfaces (each is a `Protocol`, registered by name, chosen in config)

```python
# slow loop
class Planner(Protocol):         def plan(self, view: ClusterView, demand: Demand, prev: Plan, cfg) -> Plan
class Forecaster(Protocol):      def forecast(self, history: ArrivalHistory, now: float) -> Demand
# fast loop
class CostModel(Protocol):       def build(self, invs, view, plan, preds) -> CostMatrix
class Scalarizer(Protocol):      def __call__(self, cm: CostMatrix, invs) -> ndarray
class Placer(Protocol):          def place(self, req: PlaceRequest) -> Placement
class HedgePolicy(Protocol):     def decide(self, inv, cm_row, budget) -> WorkerId | None
class RetryPolicy(Protocol):     def on_failure(self, inv, outcome, view, plan) -> RetryDecision
# predictions
class Predictor(Protocol):       def predict(self, fn, in_bytes, workers, load) -> LogDist; def update(self, obs) -> None
class Survival(Protocol):        def p_alive(self, workers, horizon_s, now) -> ndarray
class OmissionModel(Protocol):   def p_omit(self, workers) -> ndarray; def update(self, outcome) -> ChangePoint | None
class Reputation(Protocol):      def update(self, state, event) -> state; def score(self, state, now) -> float
# other
class CacheValue(Protocol):      def value(self, entry, forecast) -> float; def source_score(self, src, dst, digest) -> float
class Router(Protocol):          def route(self, inv, summaries) -> ClusterId
class OrchestratorPolicy(Protocol): def step(self, summaries, membership, events) -> list[MoveOp]
class SuccessionRank(Protocol):  def rank(self, view, cluster) -> list[WorkerId]
```

**Registry:** `@register("planner", "milp")`, and the config says `planner: {name: milp, T_plan: 30, T_solve: 2}`.

## 5. Substrate profiles are data (one engine, no per-substrate code)

`world/substrate.py` loads a profile and `world/lifecycle.py` interprets it. Example (abridged):

```yaml
# configs/substrates/appliance_tpm.yaml
name: appliance_tpm
assurance_base: 0.80
concurrent_owner_use: false
session:
  establish:                          # BOOTING → ATTESTED
    - {op: delay,  dist: measured/reboot_to_kernel}        # firmware + bootloader + UKI
    - {op: delay,  dist: measured/appliance_userspace}
    - {op: tpm_quote}                                      # Tpm resource, measured/tpm2_quote
    - {op: rpc,    to: verifier, size: 6KB}                # geo RTT
    - {op: cpu,    work: measured/verify_ms}
  reattest_every_s: 600
trust:                                 # tenant key release
  - {op: rpc, to: tenant_kbs, size: 2KB}
  - {op: cpu, work: 0.002}
ladder:                                # levels and transitions (doc 02 §5)
  levels: [L0, L1, L2, L3, L4]
  transitions:
    L0->L1: [{op: fetch, artifacts: [bundle, rootfs]}, {op: cpu, work: verify_per_MB}]
    L1->L3: [{op: disk_read, what: rootfs}, {op: delay, dist: measured/fc_boot}, {op: cpu, work: fn.init_s}]
    L2->L3: [{op: disk_read, what: snapshot_touched}, {op: delay, dist: measured/fc_restore}]
    L3->L4: [{op: delay, dist: measured/dispatch}]
slowdown: {cpu: measured/tme_cpu_factor, mem: measured/tme_mem_factor, io: 1.0}
```

Adding a substrate means adding a YAML file. Adding a new `op` means one function in `lifecycle.py`.

## 6. Config (single pydantic tree, abridged)

```yaml
seed: 1
horizon_s: 3600
scenario:
  workers: 1000
  substrate_mix: {appliance_tpm: 1.0}
  tiers: {nightly: 0.6, idle: 0.3, dedicated: 0.1}
  regime: churn_med
  adversary: {alpha: 0.1, mix: {black_hole: 0.4, on_off: 0.4, omit_random: 0.2}}
  load: {rate: 100}
voss:
  clusters:   {target_size: 30, diversity_min_domains: 3}
  router:     {name: score}
  planner:    {name: milp, T_plan: 30, T_solve: 2.0, hot_top_k: 20, f_from_alpha: 0.1}
  placer:     {sync: greedy, async: flow, K: 12}
  hedge:      {name: risk_proportional, theta: 0.2, budget: 0.1}
  predictor:  {name: blr, forgetting: 0.995, conformal: true}
  cost:       {scalarizer: slo_miss, eps: 0.05, lambda_exposure: 1.0}
  cache:      {value: gdsf, p2p: true, hdd_tier: true}
  detection:  {T_dispatch: 1.0, watchdog_q: 0.9, change_point: cusum}
  succession: {warm_standbys: 1, ckpt_s: 30, lease_s: 5}
  reputation: {name: beta_decay}
decision_clock: {mode: modeled}
calibration: configs/calibration/measured/i7-12gen-node0
```

A baseline is the same scenario with a different `voss` section, or with `system: reference_cloud`.

## 7. Testing strategy

- **Unit:** every policy on hand-built views. Planner tests on tiny instances check, by brute force, that robust
  coverage holds after removing any *f* workers.
- **Property (hypothesis):**
  - `flow == ilp_window` on uncoupled instances;
  - plans respect all constraints;
  - cache never exceeds tier budgets;
  - digest-verified loads never accept wrong bytes.
- **Invariants in every integration run:**
  - no execution on an unattested or expired worker;
  - no tenant key on a worker without a successful `KEY_REQUEST`;
  - latency components sum to end-to-end;
  - exactly one terminal outcome per invocation;
  - no dispatch from a stale epoch is executed;
  - receipts are complete vs ground truth.
- **Information boundary:** a spy scenario asserts that policies only saw stale data.
- **Determinism:** `voss repro` equals the result hash; `make repro-smoke` runs in CI.
- **Regression:** a golden scenario with metric bands.

## 8. Conventions ("clean and elegant")

- Modules < 400 lines, functions < 50 lines, typed everywhere. No globals; state objects are passed and returned.
- Pure policies are functions or small classes with explicit state in and out.
- Actors are thin: they decode a message, call a policy, encode messages. No business logic in actors.
- Data over code: substrates, hardware, regimes and experiments are YAML.
- One logging call style: `recorder.log(EventType, **fields)`. Analysis reads logs only.
- Docstrings cite the doc section they implement (e.g., `"""Doc 03 §4.2 robust coverage."""`).

## 9. Recipes for the coding agent

| Task | Steps |
|---|---|
| New placer | Add `policy/place/<name>.py` implementing `Placer` → register → add to `configs/experiments/*` → unit test on a hand-built `CostMatrix` |
| New planner | Implement `Planner` → register → brute-force robustness test on tiny instances |
| New adversary | Add the behavior to `world/adversary.py` (scenario trace generation + effect hook) → regime YAML |
| New substrate | YAML in `configs/substrates/` (+ a new `op` only if needed) |
| New message | Dataclass in `core/messages.py` → sender and receiver actors → add to the doc 08 §4 table |
