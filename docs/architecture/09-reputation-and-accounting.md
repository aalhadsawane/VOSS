# 09 · Reliability, Reputation, Receipts and Credits (C5, supporting)

## 1. Three signals, disjoint inputs (no double counting)

| Signal | Question | Inputs | Used by | Lives in |
|---|---|---|---|---|
| **Survival** `S_j(τ)` | Will this session last long enough? | Session start/end events, tier, local hour, session age; drain notices only shorten it | Planner, placement (`pFail`) | Scheduler (checkpointed) |
| **Omission** `p_j` + change point | Does this host return results it accepted? | Accepted vs result-returned outcomes **during live sessions** (excludes session ends) | Planner, placement, suspicion | Scheduler (checkpointed) |
| **Reputation** `R_id` | Does this identity keep its declared commitments over the long run? | Declared-tier commitments (e.g., `dedicated` sessions ended early), delivered vs declared envelope, long-run omission summary | **Rewards** and planner tie-breaks only (never `pFail`) | Orchestrator DB (per EK identity) |

**Why disjoint:**
- Session ends feed only survival.
- Mid-session omissions feed only the omission model.
- Reputation aggregates long-horizon *behavior vs. declarations* for incentives.

The ablation `reputation_in_cost` shows the double-counting effect.

**Fake signals:** drain or preemption notices come from the owner side. They are hints that shorten predicted survival
and never excuse an omission or a commitment breach.

## 2. Reputation rule (default `beta_decay`)

- Per identity: Beta(α, β) with decay to a pessimistic prior (half-life `H`).
- `+α`: sessions that honored the declared tier; on-time results (weighted by reference work).
- `+β`: commitment breaches; sustained envelope shortfall; omission bursts (change points).
- **Score** = lower credible bound.
- **Newcomers:** prior + probation (low-stakes work, also exploration). Identities cost a TPM (Sybil-bounded).
- **Guards:** exploration quota `ε`; per-identity share cap (concentration).
- **Variants:** `success_rate`, `ewma`, `survival_informed`, `eigentrust_lite`, `none`, `no_decay`.

## 3. Attested receipts (work log)

- Each `RESULT` carries a receipt signed by the worker's session key (doc 04 §9). The router verifies it against the
  session certificate (revocation list from the verifier) and appends a row to `receipts` (doc 08 §3).
- Attempts with no result appear as `no_result` after the router timeout.
- **Completeness and correctness:** a receipt exists iff an attested appliance produced the result, so hosts cannot
  claim work they did not do. The simulator asserts log completeness against ground truth.
- **No blockchain:** receipts are already third-party verifiable (attested signatures). The trusted orchestrator
  could only *withhold or delete* records. A provider-signed transparency log is parked for volunteer-facing audits.

## 4. Credits

- **Workers:** `credit = ref_work_units(fn, input) × timeliness multiplier`, only for verified successful results.
  Reference units (not elapsed time) make throttling unprofitable.
- **Donor caching:** a small credit for planner-pinned warm state (pinned GB·s, **only while** the worker answered
  probes), so donating cache and memory is rewarded without paying for idle omission.
- **Schedulers:** credit for assignments (receipts carry the epoch and scheduler) and for time as active/standby
  (`scheduler_roles`).
- A batch job over `receipts` + `scheduler_roles` writes `credits`. Non-monetary.
- Fairness metrics: Lorenz curve, Jain index.

## 5. Experiments touching this doc

- **E12:** reputation dynamics (starvation, concentration, on-off identities).
- **E13:** accounting cost and completeness (receipt volume, verification CPU, credit settlement latency).
