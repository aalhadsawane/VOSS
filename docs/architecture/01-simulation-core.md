# 01 · Simulation Core

## 1. Engine choice (see ADR-001)

A **custom Python discrete-event kernel** (`heapq` of timestamped callbacks), not SimGrid. Reasons: (a) the
spec's key physics for FaaS is network transfer, disk read, CPU slots and fixed delays, which are small to model
directly; (b) real solver wall-time must be injected into simulated time, which is trivial in-process; (c) 10⁴–10⁵
workers need cheap per-worker state; (d) the team ships faster. The resource models sit behind narrow interfaces
(`Network.send`, `Disk.read`, `Cpu.run`) so a SimGrid backend can be validated against them on micro-scenarios
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
  Example: `stream("avail", worker_id)`, `stream("exec", inv_id)`. Adding a component never perturbs another's stream.
- **True runtime of an invocation is drawn from its own stream at dispatch**, independent of the scheduling
  decision, so every compared system sees the same underlying randomness (common random numbers).
- Iterate dicts/sets only in sorted order wherever the order affects behavior.

## 4. Scenario = precomputed exogenous traces

A `Scenario` is generated once from `(config, seed)` and hashed; all systems in a comparison replay it.

| Trace | Content | Generator (see 02) |
|---|---|---|
| `WorkerTable` | Workers with static attributes, location, tier, hardware class, failure domain | `world.worker` |
| `AvailabilityTrace` | Per-worker events: `JOIN, OWNER_BUSY(grace), OWNER_IDLE, DRAIN_NOTICE(deadline), LEAVE, CRASH, RECOVER` | `world.availability` |
| `ArrivalTrace` | `(t, fn, origin_city, payload_in, slo_class)` | `world.workload` |
| `LinkTable` | Per-worker access bandwidth up/down, last-mile RTT; city-pair base RTT | `world.network` |
| `ControlFaultTrace` | Extra control-plane faults and partitions, separate so it can be swept independently | `runtime.faults` |

Storage: Parquet/npz under `runs/scenarios/<hash>/`. Real traces (Azure arrivals, Failure Trace Archive) enter by
providing a loader that outputs the same trace schema.

## 5. Ground truth vs. observed state

```
world.*  (true state)  ──heartbeat messages──▶  observe.StateStore  ──▶  ClusterView (immutable, timestamped)
                                                                    └─▶  ClusterSummary (router/orchestrator)
```

- Workers emit heartbeats every `heartbeat_s` (config) to **the active scheduler of their cluster (and its warm standbys, 07 §4.2)**, carrying: free
  cores, free memory, per-function lifecycle states, queue length, load. Heartbeats are `net.send` messages, so
  network delay (and optional loss) applies. Each recipient keeps its own `StateStore`.
- **Push events** also use `net.send`: drain notices, owner-busy-with-grace, outcomes. Abrupt crashes are only
  observed via missed heartbeats (timeout `3×heartbeat_s`).
- A `ClusterView` is a frozen dataclass of numpy arrays plus `as_of` time and per-worker age. Policies receive views
  only; they have no reference to `world`. This is the enforcement point for the information boundary.
- A scheduler's own dispatch decisions update its **local optimistic bookkeeping** (slots it has committed) so it
  does not double-assign between heartbeats; this is soft scheduler state, rebuilt by roll call after a failover (07 §4.3), not the world.
- Heartbeat/monitoring traffic is counted (messages, bytes) as scheduling overhead.

## 6. Network lag and the actor model

**All cross-node interaction is a message with geo-derived delay.** This is both the realism requirement
(geo-distribution drives latency) and the anti-spaghetti rule.

```python
class Network:                       # world/network.py
    def send(self, src: NodeId, dst: NodeId, msg, size_bytes: int, kind: str) -> None
    # delivers msg to dst.on_message(msg) at now + delay, unless src/dst is down, dropped, or partitioned
    def rtt(self, a: NodeId, b: NodeId) -> float
```

- **Delay** = `RTT/2 + size / effective_rate` for bulk data (with access-link sharing, 02 §3) or `RTT/2 + jitter` for
  small control messages. RTT comes from the geographic model:
  `last_mile_a + last_mile_b + great_circle_km / c_eff × route_factor`, plus jitter. Registry, storage and
  the orchestrator tier and cloud DB are nodes with cloud-region locations; workers are nodes with their own locations.
- **Failure behavior:** a message to a down host is silently lost (senders detect via timeout); optional per-link
  loss probability and **partitions** (from `ControlFaultTrace`) drop messages in a window.
- **Actors:** every runtime entity (`WorkerAgent`, `SchedulerRole`, `Router`, `Orchestrator`,
  `LedgerGateway`) is an `Actor` with a `host: WorkerId` and `on_message(msg)`. When the host crashes, leaves or is
  preempted the actor dies (memory lost; disk state survives a crash-recover). The orchestrator tier (orchestrator, routers, operational DB, ledger gateway) runs on provider-hosted nodes that never crash (07 §1). Actors may call
  `kernel.after` for timers and `net.send` for communication, **never another actor's methods**.
- Message counts and bytes per `kind` are logged for overhead metrics.

## 7. Decision latency (spec §8, §14: "never hide overhead")

`DecisionClock.charge(kind, work_units, host) → seconds` is called before a runtime actor applies a decision;
the decision takes effect at `now + charge`.

| Kind | `measured` | `modeled` (default for sweeps) | `replay` |
|---|---|---|---|
| `solve` (ILP/MCF/greedy) | wall-clock of the solver call × `cpu_scale` ÷ `host.speed` | fitted `a + b·W·K` per placer ÷ `host.speed` | read logged solve times from a previous run's `solver.parquet` |
| `cost_matrix` | wall-clock of the build, same scaling | fitted `a + b·W·N` | logged |
| `router`, `orchestrator` | constant + per-cluster term | same | same |
| `coordination` | emerges from `net.send` (appointment, roll call, checkpoint RTTs to the orchestrator/cloud DB, 07) | same | same |

- The **scheduler host's speed** scales solver time (a slow volunteer schedules slowly), tying scheduler placement
  (07 §4) to decision latency.
- `measured` is used for E02 (solver tail behavior) and logs every call (`solve_wall_s`, status, gap). Because wall
  time is not reproducible, `replay` mode re-runs the same experiment deterministically from those logs. A paper result
  from a `measured` run is reproduced via `replay`.
- In `modeled`/`replay` modes, solvers use **deterministic limits** (single thread, fixed seed, node/iteration
  limit); the wall-clock `time_limit` applies only in `measured` mode.

## 8. Performance budget

Target: 1k workers × 1 simulated hour × ~100 invocations/s in < 5 wall-minutes on a laptop; 10⁵ workers for the
scalability experiment using fast-path placement, coarser heartbeats and a shorter horizon. Rules: vectorize cost
matrices in numpy; keep per-worker state in struct-of-arrays inside `WorkerPool`; avoid per-event object churn in hot
paths. Profile before optimizing.

## 9. Reproducibility contract (ADR-019)

Everything in the paper must be reproducible by someone else with one command.

1. **Pinned environment:** `uv.lock` committed; `Dockerfile` pins OS, Python and solver wheels; CI builds it.
   `OMP/MKL/OPENBLAS_NUM_THREADS=1`, solvers single-threaded with fixed seeds, to avoid nondeterministic float
   reduction order.
2. **Run manifest** (`manifest.json` per run): git SHA (+ dirty flag, refused for paper runs), full resolved config,
   scenario hash, seeds, library versions, decision-clock mode, host info, wall time, event counts, result hash.
3. **One-command entrypoints:** `voss run <config>`, `voss repro <manifest.json>` (re-executes and **asserts the
   result hash matches**), `make repro-smoke` (small golden scenario, runs in CI), `make paper` (all experiments
   → tables and figures).
4. **Determinism levels:** `modeled` and `replay` modes are bit-identical across reruns on the same lockfile;
   `measured` mode is reproduced only via `replay`.
5. **Results are derived, not hand-edited:** every figure/table is a registered function of run directories,
   named by experiment id; figure files embed the manifest hashes they were built from.
6. **Seeds:** experiment configs list seeds explicitly; no unseeded randomness (lint: ban global `random` and
   `np.random.*`).
7. **Provenance of inputs:** traces and calibration data are versioned files with source, date and checksum in
   `configs/calibration/SOURCES.md`.
