# 04 · Reputation, Ledger, Rewards, Drain (C5, §4.4–4.6)

Control-plane fault tolerance (scheduler replication, failover) is in **07**. These are **models inside the
simulator**, deliberately thin, with calibrated delays and capacities, evaluated as separate axes from scheduling
quality (spec §9).

**Threat model (ADR-016):** crash-fault only. Workers and schedulers crash, get preempted or drain; none lies.
Result verification for lazy/cheating workers is an **optional extension** (§2), off by default
(`threat_model: crash_only`; the extension is `crash_plus_lazy`).

## 1. Reputation (`policy/reputation.py`, pure)

State per peer: `(alpha, beta, last_update, probation_left, tier)`. Under the crash-only model reputation measures
**commitment-keeping and timeliness**, not honesty.

**Default rule: Beta-Bernoulli with time decay.**

| Event | Effect | Notes |
|---|---|---|
| On-time completion | `alpha += w_ok` (+ timeliness bonus) | Weighted by invocation cost class to resist farming trivially short work |
| Broken commitment (Tier 1/2 leaves or goes dark inside declared window, abrupt) | `beta += w_commit` | The case reputation exists to catch |
| Delivered envelope far below declared (sustained) | `beta += w_env` | Declared cores/bandwidth vs. measured |
| Clean graceful drain | no penalty; small `alpha` bonus | |
| Tier 0 owner preemption, crash | **no effect** | Behaving as declared; the survival model handles it (03 §6) |
| *(extension)* verification mismatch | `beta += w_bad` (large) | Only with `crash_plus_lazy` |

- `score = lower credible bound (e.g. 20th pct) of Beta(alpha, beta)`; decay: `alpha, beta` shrink toward the prior
  with half-life `H` (recovery path, avoids permanent starvation).
- **Newcomer / whitewashing:** prior `Beta(a0, b0)` is pessimistic; punished score is **floored at the newcomer
  score**, so rejoining never beats staying punished. New identities start in **probation** (low-stakes work;
  also forces exploration for predictors). Sybil cost is modeled as an identity-creation rate limit.
- **Starvation/concentration guards:** exploration quota `ε` routes a small share of low-stakes work to low-score
  peers; per-peer load cap (share of cluster work) limits rich-get-richer.
- Registered variants: `beta_decay` (default), `success_rate`, `ewma`, `survival_informed`, `eigentrust_lite`,
  `static`, `none`, `no_decay`, `no_fair_punishment`.

Metrics: score distribution, recovery time, starvation incidents, Lorenz/Jain of work and rewards.

## 2. Optional extension: lazy-worker verification (`crash_plus_lazy`)

Off by default. Kept because spec §4.5 notes immutability is not correctness, and so the paper can report what
verification costs *if* rational/lazy workers exist. It is a separate axis, never mixed into main results.

- `VerifyPolicy.decide(inv, peer_score) → none | spot_check(p) | replicate(r)` (BOINC-like adaptive: probation →
  replicate, trusted → spot-check with probability `p = clip(p0·(1−score))`).
- `lazy(q)` workers return a wrong result with probability `q`. Replicas go through the normal placer on a different
  failure domain, so the extra work consumes real capacity and shows up in latency and utilization.
- Outputs: verified receipts, mismatches to reputation, detected/missed cheating counts.

## 3. Verifiable work ledger (`runtime/ledger.py`)

A **service model**, not a chain implementation. Everything is off the critical path:

```
worker receipt ─┐
                ├─▶ per-cluster epoch buffer ─▶ EPOCH_CLOSE (interval Δ_a) ─▶ Merkle roots + batch submit
scheduler epoch ┘                                  ─▶ validator quorum commit ─▶ finality ─▶ settlement
record (07 §6)
```

| Mode (`ledger.mode`) | Model |
|---|---|
| `none` | No recording (reference) |
| `signed_log` | Centralized operator appends and signs; no consensus delay; trust-the-operator (the honest baseline) |
| `per_invocation_chain` | One tx per receipt: throughput cap, finality delay, tx cost |
| `batched_merkle` (**default**) | One tx per cluster-epoch; `epoch_s`, `tx_cost`, `max_tps` |

- **Records:** worker execution receipts (peer, fn, outcome, duration, resources, term/assignment id) **and
  scheduler epoch records** (assignments, leader terms, counts; 07 §6). Because nodes are not Byzantine, nothing
  needs to be re-verified before anchoring; the ledger is an audit and reward substrate.
- **Validators** are a small federation (cluster orchestrators / Tier 2 hosts) running a **CFT** consensus group using
  the same `ReplicationGroup` component as schedulers (07 §3.2). **Finality = batching delay + quorum RTT among
  validators**, derived from geography rather than a fixed constant. A public chain or rollup is a different
  parameter set (longer finality, tx fee), not different code.
- **Audit joins** (done in analysis from the recorded tables): every executed invocation has an assignment under a
  valid term; every assignment has an outcome or is flagged lost; fencing violations must be zero.
- **Outputs:** settlement latency CDF, receipts/s, backlog, bytes stored, tx count/cost, unanchored work lost
  when a whole scheduler group dies (≤ one epoch), and audit completeness. **Invocation latency is never gated by
  the ledger** (test: invocation records are identical across ledger modes).
- **The honest question** the paper answers: what does decentralized immutability buy over a trusted operator's
  signed log, given CFT-only participants? Compare `signed_log` vs. `batched_merkle` on cost and on what the audit can
  and cannot detect.
- Dispute window: configurable delay before rewards finalize; reputation applies on event (fast), rewards at
  settlement (slow).

## 4. Rewards (accounting only)

`reward = base_credit(cpu_s, mem, bytes) × timeliness multiplier` for **workers**; **schedulers** earn credit
for committed assignments (leader) and replica-uptime (followers) (07 §6). Credits are accounted per node and never
converted to money. Give-to-get/free-rider rules, tier rates and the scheduler/worker credit ratio are config.
Output is for fairness metrics (Lorenz/Jain) and for checking that scheduler duty is not a net loss to hosts.

## 5. Departure handling and graceful drain

- World emits `DRAIN_NOTICE(t_notice, deadline)`; delivered as a message (`net.send` delay).
- **Worker drain:** scheduler adds `deadline` as a hard constraint (only invocations predicted to finish before
  `deadline − margin`), stops new work after notice if configured, triggers an orchestrator rebalance, optionally
  hands over state (`handover=seed_images|none`: seed images to a cluster peer using the draining peer's uplink).
- **Scheduler/orchestrator drain:** planned leadership transfer before leaving, then replica replacement (07 §3.5, §4).
- Reputation: clean drain unpenalized; drain beyond `D_max` is capped and counted (abuse bounded by `D_max` and a
  per-day quota).
- Sweeps: `graceful_frac`, notice lead time, deadline distribution (spec §4.6).
