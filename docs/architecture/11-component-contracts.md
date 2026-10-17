# 11 · Component Contracts: inputs, outputs, decisions, constraints

For every mechanism: what goes in, what it decides, what it is constrained by, what comes out, and how often. "O/H/F/C/P"
denote the kinds of input defined in doc 03 §9 (observed, learned from history, forecast, calibrated, policy). Defaults
are those of `core/config.py`.

## 1. Router (`policy/route.py`, `runtime/router.py`)

| | |
|---|---|
| **Input** | Invocation (tenant, function, origin, class, deadline) from the client; one `ClusterCard` per cluster (O: load, free slots, observed SLO-miss rate, measured in-cluster overhead, provisioned capacity per tenant, warm functions, measured cold prices; refreshed from scheduler summaries every 1 s); origin location (O) |
| **Decision** | One cluster per invocation (and a re-route on a stall) |
| **Objective** | `min_c  rtt(origin,c) + overhead_c + backlog_c + health_s·max(0, miss_c − θ) + [0 if tenant provisioned in c else cold_trust_c + exposure_s] + [0 if f warm in c else cold_fn_c]` (seconds) |
| **Constraints** | cluster not excluded by an earlier stall; prefers clusters with a free slot |
| **Output** | `ENQUEUE` (metadata only) to that cluster's scheduler; a pending copy kept until `ACCEPTED` |
| **Cadence / timers** | per request; dispatch watchdog `T_dispatch = 1 s`, spill after `T_spill = 1.5 s`, at most 3 resends |

## 2. Orchestrator: clustering and appointment (`policy/orchestrate*.py`, `runtime/orchestrator.py`)

| | |
|---|---|
| **Input** | Worker table and session events (O); scheduler summaries and keepalives (O); router stall reports (O); RTT embedding (C) |
| **Decisions** | Cluster membership (split, merge, move), scheduler appointment and succession list |
| **Objective** | Keep every cluster within `[min_size 10, max_size 60]` around `target_size 30`, with at least `d_min = 3` failure domains, and low RTT inside clusters; migrate only when a trigger fires (size, SLO health θ = 0.2 for 3 periods, demand imbalance δ = 0.4, forecast, diversity, scheduler loss) |
| **Constraints** | dwell time 600 s per worker, at most 3 moves per worker per hour, at most 10 moves per period |
| **Output** | `MEMBERSHIP`, `APPOINT(epoch, token, checkpoint)`, `REVOKE` |
| **Cadence** | every 30 s and on events; appointment by atomic compare-and-swap on the epoch |

## 3. Slow loop: planner (`policy/plan/*`, `runtime/schedlib/planning.py`)

| | |
|---|---|
| **Input** | Per-host: slots, memory/SSD budgets (O static); survival over the horizon `S_j(H)` (H → F); omission `p_j` (H); assurance `a_j` (O); failure domain (O); attestation validity (O). Per hot tenant: demand quantile `q_t` (F from H), sensitivity σ_t, assurance floor, robustness `f_t` (P). Per hot function: memory and snapshot size (C), warm benefit `b_f` (F + C). Previous plan and what workers confirmed (O) |
| **Decision variables** | `y_tj` (provisioned), `s_fj` (snapshot pinned), `w_fj` (warm VMs), `c_tj` (earmarked slots), `u_t` (uncovered demand) |
| **Objective** | minimise `Σ Λ_t u_t + ρ_mem Σ m_f w_fj + ρ_ssd Σ z_f s_fj + λ Σ σ_t(1−a_j) y_tj + κ_switch Σ(y−y_prev)⁺ − β Σ b_f (w_fj + γ s_fj)` |
| **Constraints** | robust coverage `Σ_j S_j(1−p_j) c_tj − (f_t largest c_tj) + u_t ≥ q_t`; `c ≤ cap·y`, `w ≤ W_max·y`, `s ≤ y`; `Σ_t c_tj ≤ cap_j`; memory and SSD budgets; failure-domain share ≤ κ_dom = 0.5; `y = 0` below the assurance floor or without a valid attestation through the horizon |
| **Output** | A plan `{y, s, w, c, valid_until}`, diffed against the *confirmed* state into idempotent actions `PREPARE`, `PIN_SNAPSHOT`, `WARM`, `RELEASE`, rate-limited to 2 parallel prepares per worker; a `PLAN_INFEASIBLE` report if shortfall remains |
| **Cadence** | `T_plan = 30 s` and on events; horizon `H = 60 s`; re-solved only if the log-quantised forecast changed by more than 20% (otherwise the previous plan is reused); up to 40 hosts per solve, top 20 tenants and 50 functions |
| **Solvers** | greedy heuristic (default, ~10 ms) or HiGHS MILP (reference, 2 s limit, ~5 s wall) |

## 4. Fast loop: placement, admission, hedging, retry (`policy/cost`, `policy/place`, `policy/{admission,hedge,retry}.py`)

| | |
|---|---|
| **Input** | Invocation(s) (deadline budget `b_i`, class, idempotence, tenant); cluster view: occupancy, cache tiers, provisioned tenants, expiry, assurance (O); execution-time distribution (H), survival over the run time (H → F), omission (H); start-up and trust costs, RTT, transfer times (C); the plan's provisioned sets (confirmed, O) |
| **Decision** | A host per invocation; optionally a hedge host in another failure domain; admit, defer or reject |
| **Objective** | `min_j  w_i·P_miss(i,j) + ε·E[T_ij] + λ_exp·σ_t(1−a_j)·[j not a key holder]` (doc 03 §1a) |
| **Constraints** | eligible hosts only (valid certificate beyond the expected finish plus a 5 s margin, not draining past it, assurance ≥ floor); top-K = 12 candidates after a prediction-free bound; filler only on slots idle beyond a headroom of 1; hedge only if idempotent, `P_miss > θ = 0.2` and the 10% token budget allows; retries only for idempotent functions or pre-execution failures, at most 3 attempts |
| **Output** | `DISPATCH(epoch, token)` to the host (and the hedge), `ASSIGNED` to the router; a `CANCEL` to the loser on the first result |
| **Cadence** | per sync invocation; async and filler work in 0.2 s windows with a min-cost assignment |

## 5. Failure detection (`runtime/schedlib/watchdog.py`, router, orchestrator)

| | |
|---|---|
| **Input** | Message timestamps and absence of expected messages (O), predicted completion quantile (H → F) |
| **Decision** | Suspect a worker or a scheduler |
| **Rule** | worker: `ACCEPTED` without `RESULT` by `q90 · 1.2` (at least 3 s) then a probe (2 s); two failures in a row ⇒ suspected for 600 s; CUSUM change point on omission; scheduler: dispatch watchdog fires 3 times in 5 s, or attested placement time above `T_decide_max = 0.2 s` for 3 periods |
| **Output** | Suspicion (no new work, hedge or retry in-flight work, provisioned eligibility revoked), `STALL`, failover |

## 6. Scheduler failover (`runtime/schedlib/succession.py`, `runtime/orchlib/appoint.py`)

| | |
|---|---|
| **Input** | `STALL`, keepalive timeout (5 s), drain notice, succession list (ranked by survival × speed × centrality × assurance) |
| **Decision** | Appoint a successor and bump the epoch |
| **Constraints** | atomic CAS on the epoch; token bound to the successor's session certificate; workers accept only the current (epoch, certificate); a scheduler self-fences after `lease_s = 5 s` without the orchestrator |
| **Output** | `APPOINT(epoch+1, checkpoint)`, `EPOCH_INSTALL`, roll call, re-planning from the checkpoint (taken every 30 s) |

## 7. Attestation and key provisioning (`runtime/verifier.py`, `runtime/tenant_kbs.py`, `runtime/worker_agent.py`)

| | |
|---|---|
| **Input** | Quote, event log, session public key, endorsement-key certificate (from the worker); reference values and policy (P); tenant key policy (P) |
| **Decision** | Issue or refuse a session certificate; release or refuse a tenant key |
| **Constraints** | quote signature and nonce valid, event log replays to the expected measurements, endorsement chain valid; certificate expiry = time of the last successful quote + the substrate's validity period, extended at each re-quote (every 600 s for the appliance), and never beyond the session end; assurance = substrate base × firmware-policy factor (the freshness factor of doc 04 §8 is enforced through expiry, not folded into the score); key released only to a valid certificate (and optionally a fresh quote), wrapped to the session key |
| **Output** | `SESSION_CERT(identity, key, assurance, expiry)`, `KEY(t)`; revocation on a failed re-quote |

## 8. Accounting (`runtime/accounting.py`, `policy/credits.py`, `policy/reputation.py`)

| | |
|---|---|
| **Input** | Attested receipts (invocation, attempt, worker, certificate, epoch, execution time, reference work units, output digest) |
| **Decision** | Credits per worker and scheduler; reputation score |
| **Rule** | credit = reference work units × timeliness (0.5 for late results); cache credit per pinned GB-hour while the host answered probes; reputation Beta(1,2) with 168 h half-life, score = 5% lower credible bound; never an input to `p_fail` |
| **Output** | `receipts`, `credits`, `reputation` tables; tie-break scores pushed every 30 s |
