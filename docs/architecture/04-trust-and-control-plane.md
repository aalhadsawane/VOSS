# 04 · Trust, Incentives and Control Plane (C5, §4.4–4.6, §5.5)

These are **models inside the simulator**, deliberately thin, with calibrated delays and capacities. They are
evaluated as separate axes from scheduling quality (spec §9).

## 1. Reputation (`policy/reputation.py`, pure)

State per peer: `(alpha, beta, last_update, probation_left, tier)`.

**Default rule: Beta-Bernoulli with time decay.** Events (all from *verified* outcomes):

| Event | Effect | Notes |
|---|---|---|
| Verified-correct completion | `alpha += w_ok` (+ timeliness bonus) | Weighted by invocation cost class to resist farming only trivially short, safe work |
| Verification mismatch | `beta += w_bad` (large) | Dominant penalty |
| Broken commitment (Tier 1/2 leaves inside declared window, abrupt) | `beta += w_commit` | |
| Clean graceful drain | no penalty; small `alpha` bonus | |
| Tier 0 owner preemption, crash | **no effect** | Behaving as declared; failure is the survival model's job (03 §6) |

- `score = lower credible bound (e.g. 20th pct) of Beta(alpha, beta)`; decay: `alpha, beta` shrink toward the prior
  with half-life `H` (recovery path, avoids permanent starvation).
- **Newcomer / whitewashing:** prior `Beta(a0, b0)` is pessimistic; punished score is **floored at the
  newcomer score**, so rejoining never beats staying punished. New identities start in **probation** (replicated or
  low-stakes work; also forces exploration for predictors). Sybil cost is modeled as identity-creation rate limit.
- **Starvation/concentration guards:** exploration quota `ε` routes a small share of low-stakes work to
  low-score peers; per-peer load cap (share of cluster work) in the placer limits rich-get-richer.
- Registered variants: `beta_decay` (default), `success_rate`, `ewma`, `survival_informed`,
  `eigentrust_lite`, `static`, `none`, `no_decay`, `no_fair_punishment`.

Metrics: score distribution, recovery time, starvation incidents, Lorenz/Jain of work and rewards.

## 2. Verification (`policy/verify.py` decision, `runtime/verifier.py` execution)

Immutability is not correctness, so records are verified **before** anchoring:

- Policy `verify(inv, peer_rep, cluster) → {none | spot_check(p) | replicate(r)}`. Default is BOINC-like adaptive:
  probation peers → replicate (r=2, quorum compare); trusted peers → spot-check with probability
  `p = clip(p0·(1−score))`; critical invocations → replicate regardless.
- Simulated correctness is a bit: honest peers always correct; `lazy(q)` / `malicious` wrong w.p. `q`. A replicated
  mismatch (or failed spot check) flags the peer; the **extra work consumes real capacity** (replica placed through
  the normal placer on a different domain), so verification cost shows up in latency and utilization metrics.
- Outputs: verified receipts to the ledger; mismatches to reputation; detected-cheating and missed-cheating counts.

## 3. Verifiable work ledger (`runtime/ledger.py`)

A **service model**, not a chain implementation. Receipts flow off the critical path:

```
verified receipt → per-cluster epoch buffer → close epoch (interval Δ_a) → Merkle root + batch submit
   → validator/consensus delay → finality → settlement (reward credit applied)
```

| Mode (`ledger.mode`) | Model |
|---|---|
| `none` | No recording (reference) |
| `signed_log` | Centralized operator appends and signs: ~0 consensus delay, trust-the-operator (the honest baseline) |
| `per_invocation_chain` | One tx per receipt: throughput cap, finality delay, tx cost |
| `batched_merkle` (**default**) | One tx per cluster-epoch; params: `epoch_s`, `submit_delay`, `finality_s`, `tx_cost`, `max_tps` |

- **Permissioned**: validators are cluster orchestrators / a small federation (ADR-007). Public chain/rollup is
  represented by a different parameter set, not different code. Optional: measure a local dev chain once to
  calibrate `finality_s`, `tx_cost`.
- Outputs: settlement latency CDF, receipts/s, queue backlog, bytes stored (growth), tx count/cost, and verification
  overhead. **Invocation latency is never gated by the ledger** (asserted by a test: invocation records are
  identical across ledger modes when verification is held constant).
- Dispute window: configurable delay before rewards finalize; reputation updates apply at verification time (fast),
  rewards at settlement (slow).

## 4. Rewards (accounting only)

`reward = base_credit(cpu_s, mem, bytes) × reliability/timeliness multiplier × verified`; credits accounted per peer,
never converted to money. Give-to-get/free-rider rules and tier-0 vs tier-1 rates are config. Output for fairness
metrics only.

## 5. Departure handling and graceful drain (`world.availability` events + policy reactions)

- World emits `DRAIN_NOTICE(t_notice, deadline)`; the observe layer delivers it as a push event (delay = network).
- Cluster scheduler reaction: add `deadline` as a hard constraint (only invocations with predicted completion
  `< deadline − margin`), stop new work after notice if configured, trigger orchestrator rebalance, optionally
  hand over state (`handover=seed_images|none`: seed images to a cluster peer using the peer's uplink during drain).
- Reputation: clean drain unpenalized, drain beyond `D_max` is capped and counted (abuse model: a peer declaring
  drain to dodge work or draining indefinitely is bounded by `D_max` and a per-day drain quota).
- Sweeps: `graceful_frac`, notice lead time, deadline distribution (spec §4.6).

## 6. Control-plane fault tolerance (`runtime/controlplane.py`, `runtime/faults.py`)

**Components modeled:** per cluster a `ClusterControl` group (scheduler + state store), the global `Router`, the
`Orchestrator`, `Ledger submitters`, `Image seeds`. Each is a **replica group** hosted on peers.

**Model (kept simple, no Raft implementation):**

```python
class ReplicaGroup:
    mode: "none" | "active_passive" | "replicated"; r: int     # replication factor
    hosts: list[PeerId]                                         # chosen across failure domains, high tier/reputation
    leader: PeerId | None
    def available(t) -> bool                                    # leader up, or failover completed
    def decision_overhead() -> float                            # quorum RTT among replicas (replicated mode)
```

- A host failing (from the peer availability trace, or a `ControlFaultTrace` injection) triggers:
  `none` → component down until a new host is provisioned and state rebuilt from heartbeats (long);
  `active_passive` → failover after `detect + takeover` with state age = replication lag;
  `replicated` → leader election `detect + election` (fast; loses a quorum if `> r/2` hosts die).
- Host selection: reliability-ranked (tier, reputation, uptime), at most one replica per `failure_domain`/timezone
  where possible; `dedicated_tier2` option places control planes only on Tier 2.
- **Data plane vs. control plane:** `DataPlane` owns in-flight invocations; they finish and report even while the
  scheduler is down; reports are buffered until a leader exists. **Lost on scheduler failover:** unflushed local
  bookkeeping (queued, not-yet-dispatched invocations unless replicated), scheduler's optimistic reservations.
  During outage new arrivals for that cluster wait at the router, then **spill over** to other clusters after
  `T_spill`. A cluster whose group is wholly lost is declared orphaned; the orchestrator reassigns its peers.
- **Bootstrap root:** a single small provider-owned root (peer discovery + ledger genesis + orchestrator seed
  list) is the one named residual SPOF; it is stateless-ish and costed (ADR-008).
- **FaultInjector** drives scenarios: random leader loss, loss during a burst, loss correlated with regional churn,
  whole-cluster control loss. Metrics: failover time, invocations delayed/lost/duplicated, P99 during failover,
  staleness after recovery, split-brain risk (modeled as concurrent leaders in `active_passive` with false
  suspicion), replication traffic and added decision latency.
