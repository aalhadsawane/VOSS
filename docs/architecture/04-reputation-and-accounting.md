# 04 · Reputation, Work Log, Credits and Drain (C5, §4.4, §4.6)

Fault tolerance is in **07**; state and DB in **08**; threat model in **09**. These are **models inside the
simulator**, deliberately thin, evaluated as separate axes from scheduling quality (spec §9).

**Threat model (ADR-016, ADR-026):** vetted, honest, crash-prone volunteers; the orchestrator tier is trusted. There
is **no blockchain** (ADR-027): work is recorded in the orchestrator's operational DB.

## 1. Reputation (`policy/reputation.py`, pure)

State per worker identity (stored in `workers.reputation`, global across clusters): `(alpha, beta, last_update,
probation_left, tier)`. Because identities are vetted, reputation measures **commitment-keeping and timeliness**,
not honesty.

**Default rule: Beta-Bernoulli with time decay.**

| Event (from `worker_events` / `invocation_log`) | Effect | Notes |
|---|---|---|
| On-time completion | `alpha += w_ok` (+ timeliness bonus) | Weighted by invocation cost class to resist farming trivially short work |
| Broken commitment (Tier 1/2 leaves or goes dark inside declared window) | `beta += w_commit` | The case reputation exists to catch |
| Delivered envelope far below declared (sustained) | `beta += w_env` | Declared cores/bandwidth vs. measured |
| Clean graceful drain | no penalty; small `alpha` bonus | |
| Tier 0 owner preemption, crash | **no effect** | Behaving as declared; the survival model handles it (03 §6) |

- `score = lower credible bound (e.g. 20th pct) of Beta(alpha, beta)`; decay: `alpha, beta` shrink toward the prior
  with half-life `H` (recovery path, avoids permanent starvation).
- **Newcomers and whitewashing:** identity is vetted (09), so a new account cannot be freely created; a returning
  worker keeps its record. New workers start with a pessimistic prior and a **probation** period (low-stakes work),
  which also forces exploration for the predictor.
- **Starvation/concentration guards:** exploration quota `ε` routes a small share of low-stakes work to low-score
  workers; per-worker load cap (share of cluster work) limits rich-get-richer.
- Registered variants: `beta_decay` (default), `success_rate`, `ewma`, `survival_informed`, `eigentrust_lite`,
  `static`, `none`, `no_decay`.

Where it lives: updated by the orchestrator from `worker_events` and `invocation_log`; the scheduler receives a
snapshot at appointment and periodic deltas (08 §3). Metrics: score distribution, recovery time, starvation
incidents, Lorenz/Jain of work and credits.

## 2. Work log (replaces the ledger)

The authoritative record of work done is the `invocation_log` table in the operational DB, **written by the routers**
(08 §3), which are trusted and observe `ASSIGNED`, `ACCEPTED` and `RESULT` for every attempt, independent of whether
the scheduler survives. Rows are batched and appended asynchronously (≤ 1 s), **never on the invocation critical
path**. Each row carries `cluster, epoch, scheduler_id, worker_id, status, exec_s, cpu_s, bytes, start_state`.

- **Completeness:** a router row exists for every attempt the router saw; attempts that failed silently appear as
  `no_result` after the router timeout. The simulator asserts log completeness against its own ground truth.
- **Modes (`accounting.mode`):** `none` (reference) and `db_log` (default). A provider-signed Merkle transparency log
  for volunteer-facing auditability is parked (09 §4).
- **Optional extension `canary_audit`** (off by default, 09 §5): the orchestrator injects known-answer canary
  invocations; their cost is measured.

## 3. Credits (accounting only)

A periodic orchestrator batch job derives the `credits` table:

- **Workers:** `credit = base(cpu_s, mem, bytes) × timeliness multiplier`, only for rows with a successful result.
- **Schedulers:** credit for assignments made (`ASSIGNED`/`ACCEPTED` rows carrying their `epoch`/`scheduler_id`)
  and for time held as active or warm-standby scheduler (from `scheduler_roles`); this compensates the reserved
  `sched_cores` and uplink.

Credits are non-monetary, never converted to money. Give-to-get/free-rider rules, tier rates and the
scheduler/worker credit ratio are config. Outputs feed fairness metrics and check that scheduler duty is not a net
loss to hosts. Settlement latency is the batch period (reported, off the critical path).

## 4. Departure handling and graceful drain

- World emits `DRAIN_NOTICE(t_notice, deadline)`; delivered as messages to the orchestrator and scheduler.
- **Worker drain:** scheduler adds `deadline` as a hard constraint (only invocations predicted to finish before
  `deadline − margin`), stops new work after notice if configured, the orchestrator rebalances, optionally hands over
  state (`handover=seed_images|none`: seed images to a cluster worker using the draining worker's uplink).
- **Scheduler drain / owner-preempt grace:** planned handover to the next successor (07 §4.5).
- Reputation: clean drain unpenalized; drain beyond `D_max` is capped and counted (abuse bounded by `D_max` and a
  per-day quota).
- Sweeps: `graceful_frac`, notice lead time, deadline distribution (spec §4.6).
