# 01 · Simulation Core

## 1. Method: measure locally, simulate globally (D-11)

- **Engine:** a custom Python discrete-event kernel. No simulator models TEEs or attestation, and FaaS physics
  (transfer, disk, CPU slots, fixed delays) is small to model directly. Solver wall time must enter simulated time.
- **Everything distributed is simulated:** geography, churn, adversaries, clusters, 10³–10⁵ workers, scheduling. It is
  bit-reproducible.
- **Everything node-local that we can run is measured** on the real calibration node (Intel i7 12th gen, 128 GB, NVMe
  SSD + HDD, Intel PTT) by the harness in doc 10, and ingested as distributions.
- **Everything we cannot run** (server CVMs) comes from literature as **ranges**, and conclusions are checked across
  the range.
- **Validation:** a single-box emulation testbed (doc 10 §4) runs small scenarios for real and is compared with the
  simulator.

## 2. Kernel API (`core/kernel.py`)

```python
class Kernel:
    now: float                                   # seconds
    def at(self, t: float, fn, *args) -> Handle
    def after(self, dt: float, fn, *args) -> Handle
    def cancel(self, h: Handle) -> None
    def run(self, until: float) -> None
```

- Callbacks, not coroutines. Ties broken by insertion sequence. Long activities are chains of continuations.
- Units: seconds, bytes, MB for memory; ms only in reports.

## 3. Determinism and RNG

- `core.rng.stream(name, *keys)` → `numpy.random.Generator` seeded by `hash(master_seed, name, keys)`. Streams are
  independent, so adding a component never perturbs another.
- **Common random numbers:** an invocation's true runtime, noise and failure draws come from its own stream, so every
  compared system sees the same underlying randomness.
- Iterate sets and dicts in sorted order wherever order affects behavior.

## 4. Scenario = precomputed exogenous traces

Generated once from `(config, seed)`, hashed, and replayed by every compared system.

| Trace | Content |
|---|---|
| `WorkerTable` | Workers: hw class, substrate, tier, location, failure domain, link, identity, firmware policy |
| `SessionTrace` | Per worker: `BOOT_START, ATTESTED, DRAIN_NOTICE(deadline, is_fake), SESSION_END(abrupt/graceful), JOIN/LEAVE platform` |
| `AdversaryTrace` | Per worker: behavior and its schedule (on/off windows, collusion events) |
| `ArrivalTrace` | `(t, fn, tenant, origin_city, in_bytes, slo_class)` |
| `LinkTable` | Access bandwidth, last-mile RTT, city-pair base RTT |
| `ControlFaultTrace` | Extra partitions/crashes for control-plane experiments |

Stored under `runs/scenarios/<hash>/` (Parquet/npz). Real traces (Azure arrivals, availability datasets) enter
through loaders that emit the same schema.

## 5. Ground truth vs. observed state

```
world.* (truth) ──HEARTBEAT messages──▶ observe.StateStore ──▶ ClusterView (immutable, as_of)
                                                         └──▶ ClusterSummary (router/orchestrator)
```

- Heartbeats (`WorkerState`, doc 08 §5) go to the active scheduler and warm standbys every `heartbeat_s`.
- Push events (outcomes, accepted, drain hints) use `net.send` too.
- Views are frozen dataclasses of numpy arrays with `as_of` and per-worker age. Policies get views only, never the
  world. The scheduler's own dispatches since `as_of` live in its soft bookkeeping (`inflight`).

## 6. Actors, messages and the network

```python
class Actor:                       # runtime/actor.py
    host: WorkerId | InfraNodeId   # dies with its host (memory lost)
    def on_message(self, msg: Message) -> None: ...

class Network:                     # world/network.py
    def send(self, src, dst, msg: Message, size_bytes: int) -> None
    # delivers dst.on_message(msg) at now + geo delay, unless src/dst is down, partitioned or dropped
```

- **All cross-node interaction is a `net.send`.** Actors set timers with `kernel.after` and never call or import each
  other. Message types are frozen dataclasses in `core/messages.py`.
- **Simulated node resources** (`world/resources.py`), all FIFO or processor-sharing servers with calibrated rates:
  - `Cpu(slots)`;
  - `Disk(tier ∈ {ssd, hdd}, read_MBps, write_MBps)`;
  - `Link(up, down)`;
  - `Tpm` (one quote at a time, quote-latency distribution);
  - `Psp` (for `cvm_snp`: CVM launches serialize).
- TLS channels: a handshake cost on first use per peer pair per session, then per-message CPU overhead.

## 7. Decision latency (never free)

`DecisionClock.charge(kind, work, host) → seconds`, applied before a decision takes effect.

| Kind | `measured` | `modeled` (default for sweeps) | `replay` |
|---|---|---|---|
| `plan` (MILP / greedy) | Wall clock × `cpu_scale` / host speed | Fitted `a + b·vars` | From the logged `solver.parquet` |
| `place` (cost matrix + placer) | Same | Fitted `a + b·K` | Logged |
| `route`, `orchestrate` | Constant + per-cluster term | Same | Same |
| Coordination | Emerges from `net.send` | — | — |

- `measured` drives E02/E04 solver studies. `replay` reproduces those runs bit-for-bit.
- Solvers run single-threaded with fixed seeds and deterministic limits in `modeled`/`replay` modes.

## 8. Reproducibility contract

1. **Pinned environment:** `uv.lock`, `Dockerfile`, `OMP/MKL/OPENBLAS_NUM_THREADS=1`.
2. **Run manifest:** git SHA (dirty refused for paper runs), resolved config, scenario hash, **calibration bundle
   hash**, seeds, versions, clock mode, result hash.
3. **Entrypoints:**
   - `voss run <config>`;
   - `voss repro <manifest>` (asserts the result hash);
   - `make repro-smoke` (CI);
   - `make paper` (all experiments → tables and figures).
4. **Calibration bundles** (`configs/calibration/measured/<host_fingerprint>/`) are versioned data with the
   harness version and raw logs; `voss calibrate ingest` turns raw logs into fitted distributions deterministically.
5. Figures are registered functions of run directories and embed the manifest hashes they used.
6. No unseeded randomness (lint bans global `random` and `np.random.*`).

## 9. Performance budget

- 1k workers × 1 simulated hour × ~100 inv/s in < 5 wall-minutes on a laptop.
- 10⁵ workers with greedy placement, coarse heartbeats and a short horizon.
- Vectorize cost matrices; keep per-worker state in struct-of-arrays; profile before optimizing.
- The planner MILP runs per cluster every `T_plan`, so its cost is amortized.
