# 01 · Simulation Core

## 1. Engine choice (see ADR-001)

A **custom Python discrete-event kernel** (`heapq` of timestamped callbacks), not SimGrid. Reasons: (a) the
spec's key physics for FaaS is network transfer, disk read, CPU slots and fixed delays, which are small to model
directly; (b) real solver wall-time must be injected into simulated time, which is trivial in-process; (c) 10⁴–10⁵
peers need cheap per-peer state; (d) the team ships faster. The resource models sit behind narrow interfaces
(`Network.transfer`, `Disk.read`, `Cpu.run`) so a SimGrid backend can be validated against them on micro-scenarios
(Roadmap P9, optional). The paper reports this as a stated threat to validity plus that validation.

## 2. Kernel API (`core/kernel.py`)

```python
class Kernel:
    now: float                                   # seconds, float64
    def at(self, t: float, fn, *args) -> Handle  # schedule absolute
    def after(self, dt: float, fn, *args) -> Handle
    def cancel(self, h: Handle) -> None
    def run(self, until: float) -> None
```

- Callback style (no coroutines): easy to profile and to keep deterministic. Ties broken by insertion sequence.
- No component sleeps; components schedule continuations. Long activities are chains: `transfer → disk → cpu → done`.
- Units: seconds in sim time, bytes, MB for memory, ms only in reported metrics.

## 3. Determinism and RNG

- `core.rng.stream(name, *keys)` returns a `numpy.random.Generator` seeded by `hash(master_seed, name, keys)`.
  Example: `stream("avail", peer_id)`, `stream("exec", inv_id)`. Adding a component never perturbs another's stream.
- **True runtime of an invocation is drawn from its own stream at dispatch**, independent of the scheduling
  decision, so every compared system sees the same underlying randomness (common random numbers).

## 4. Scenario = precomputed exogenous traces

A `Scenario` is generated once from `(config, seed)` and hashed; all systems in a comparison replay it.

| Trace | Content | Generator (see 02) |
|---|---|---|
| `PeerTable` | Peers with static attributes, location, tier, hardware class, behavior (honest/lazy) | `world.peer` |
| `AvailabilityTrace` | Per-peer events: `JOIN, OWNER_BUSY(grace), OWNER_IDLE, DRAIN_NOTICE(deadline), LEAVE, CRASH, RECOVER` | `world.availability` |
| `ArrivalTrace` | `(t, fn, origin_city, payload_in, slo_class)` | `world.workload` |
| `LinkTable` | Per-peer access bandwidth up/down, last-mile RTT; city-pair base RTT | `world.network` |
| `ControlFaultTrace` | Control-plane component failures (separate so it can be swept independently) | `runtime.faults` |

Storage: Parquet/npz under `runs/scenarios/<hash>/`. Real traces (Azure arrivals, Failure Trace Archive) enter by
providing a loader that outputs the same trace schema.

## 5. Ground truth vs. observed state

```
world.*  (true state)  ──heartbeat events──▶  observe.StateStore  ──▶  ClusterView (immutable, timestamped)
                                                                   └─▶  ClusterSummary (router/orchestrator)
```

- Peers emit heartbeats every `heartbeat_s` (config) carrying: free cores, free memory, per-function lifecycle
  states, queue length, load. Network delay and loss apply. The `StateStore` holds the last report per peer.
- **Push events** reach the store with network delay: drain notices, owner-busy-with-grace, completions.
  Abrupt crashes are only observed via missed heartbeats (timeout `3×heartbeat_s`).
- A `ClusterView` is a frozen dataclass of numpy arrays plus `as_of` time and per-peer age. Policies receive views
  only; they have no reference to `world`. This is the enforcement point for spec §8 "information boundary".
- The scheduler's own dispatch decisions update its **local optimistic bookkeeping** (e.g., slots it has
  committed) so it does not double-assign between heartbeats. This is explicit state in `ClusterScheduler`, not in
  the world.
- Heartbeat/monitoring traffic is counted (messages, bytes) as scheduling overhead.

## 6. Decision latency (spec §8, §14: "never hide overhead")

`DecisionClock.charge(kind, work_units) → seconds` is called by every runtime agent *before* it applies a
decision; the decision takes effect at `now + charge`.

| Kind | Mode `measured` | Mode `modeled` (default for sweeps) |
|---|---|---|
| `solve` (ILP/MCF/greedy) | wall-clock of the solver call × `cpu_scale` | fitted `a + b·W·K` per placer from pilot runs |
| `cost_matrix` | wall-clock of the build | fitted `a + b·W·N` |
| `router` | constant + per-cluster term | same |
| `orchestrator` | wall-clock of the step | same |
| `coordination` | n/a | quorum RTT from control-plane model (04) |

`measured` is used for the §8.6 experiment and logged per call (`solve_wall_s`, status, gap); `modeled` keeps
large sweeps fast and reproducible. Both modes are recorded in the run manifest. `cpu_scale` maps the
simulation host to a reference scheduler-host speed (it is a simulated machine, since schedulers run on
volunteer or Tier 2 peers).

## 7. Run manifest

Every run writes `manifest.json`: git SHA, full resolved config, scenario hash, seeds, library versions,
decision-clock mode, host info, wall time, event counts. Re-running from the manifest must reproduce the
invocation log byte-for-byte in `modeled` mode.

## 8. Performance budget

Target: 1k peers × 1 simulated hour × ~100 invocations/s in < 5 wall-minutes on a laptop; 10⁵ peers for the
scalability experiment using fast-path placement, coarser heartbeats and a shorter horizon. Rules: vectorize cost
matrices in numpy; keep per-peer state in struct-of-arrays inside `PeerPool`; avoid per-event object churn
in hot paths. No premature optimization beyond that; profile first.
