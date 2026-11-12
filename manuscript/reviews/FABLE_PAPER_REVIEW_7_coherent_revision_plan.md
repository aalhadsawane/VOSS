# Fable Paper Review 7: one coherent revision that answers every issue

Files 1-6 list 110 separate problems. Fixing them one by one would produce contradictions (examples in section 3).
This file gives one design, one methodology and one paper structure under which all of them are resolved together.
Issue IDs (A, B, C, E, S, W from files 1-4; D, X from files 5-6) are cited throughout.

---

## 1. What the paper should be

**Current paper:** "We present a system with a new scheduler, a new detector and a new decentralised deployment, and it is
21% faster." Each of the three is either existing practice (B5, B6, C8) or refuted by the paper (B1), and the 21% is
confounded (D1-D5).

**Revised paper:** a design and evaluation study with one question.

> Can machines that a provider neither owns nor trusts serve function invocations with deadlines of seconds, and what
> determines how well?

**The answer the data already points to (to be confirmed by the reruns):**
- The controlling variable is the number of prepared key holders per function: workers that are attested, hold the
  function's key and have a warm sandbox.
- More holders means more deadlines met and more places the key can leak from. This trade-off is the result.
- A simple rule that sizes the holder set to survive the loss of $f$ workers reaches a target deadline-met rate with
  fewer holders than keep-alive or autoscaling policies. (If the reruns do not show this, see section 7.)
- Omission by owners is handled by deadline-derived timeouts with per-worker outlier ejection, and forging by sampled audit.
- A single scheduler on provider hardware is sufficient up to a measured pool size; volunteer-hosted schedulers are worse.

Why this framing is coherent: it claims only what the evidence can carry, it converts the null results (B8) and the
rejected deployment (B1) from embarrassments into findings, and it needs no claim of beating a datacenter (A1, A2, D12).

---

## 2. Design decisions (eight, each with what it resolves)

### R1. Deployment model: dedicated sessions
- An owner lends the whole machine for a session by booting the image (overnight, outside office hours). No co-use.
- Drop "idle" and the donated shares. A worker offers its physical cores and its memory minus the image's own use.
- Realistic source of such machines to name in the introduction: office and lab fleets outside working hours, where
  an administrator can schedule network boot. This is a more credible pool than individual volunteers.
- The late-launch hypervisor option moves to future work in one sentence.
- Resolves: A3, C13, S10, round-15/17 feedback on 0.75. Changes simulator: capacity = physical cores; co-run slowdown measured, not assumed.

### R2. One scheduler on provider hardware
- Workers and clients connect outwards to provider front ends (router). No broker, no clusters, no succession protocol.
- Scale statement comes from timing the real policy code (D13). Beyond that size: regional shards on provider hardware, stated, not evaluated.
- The volunteer-hosted clustered design becomes one paragraph plus one row in the negative-results table
  ("17% slower in Europe, 5x the key holders").
- Resolves: B1, B2, B3, B4, B5, D1, S8, B12. Removes Section 6, two thirds of Section 7, contribution (4), `broker`/`failover`/`seq` diagrams.

### R3. Data path: the router forwards, it does not read
- Client TLS terminates in the worker, with the session certificate issued by the verifier. The router forwards the
  connection by function name and sees sizes and timing only.
- Proximity is no longer claimed. The introduction states that requests pass through provider front ends.
- Simulator: add one TLS handshake round trip to a worker for a new client connection (or state resumption).
- Resolves: A1, C3, D12.

### R4. Adversary classes instead of one Property
- Software-only owner: Property 1 holds (omission and timing faults only).
- Owner with physical access, no memory encryption: Property 1 does not hold. Integrity is bounded by sampled audit
  (re-run 1% of idempotent invocations on a different owner's worker; ban by TPM identity on mismatch).
  Confidentiality is not provided; tenants exclude this class for functions they consider sensitive.
- Memory-encrypted hardware: Property 1 holds up to side channels.
- The abstract says "against owners who do not physically attack their own machine".
- Resolves: C1, C2 (scope), C7 (honest statement of provider trust), D8, D15, C10 (receipts now feed the audit), W8 (Property wording).

### R5. Keys: per-function data keys, rotation, local snapshot keys
- Tenant root key stays in the tenant's key service (a cloud KMS in practice).
- Per-function data key, rotated every $R$ hours, released to attested workers.
- Snapshots sealed under a key generated in the image and bound to the TPM; never copied between workers.
- A holder keeps its key until its session ends (no release-and-readd).
- Resolves: C4, D9, D10, D11, B9, C11.

### R6. Exposure is a budget, not a weight
- Metric: number of key holders per function, reported three ways (concurrent, distinct per key lifetime, releases per hour). No trust scores, no $\sigma$.
- Each tenant sets $K$ (maximum holders) and a minimum machine class. Every policy, baselines included, obeys the same $K$.
- Placement cost becomes predicted completion time against the deadline; the exposure term is deleted.
- Resolves: B7, B10 (three constants gone), C5, C6, D3, E7 (fair baselines), X15.

### R7. Failure handling tied to the deadline
- Timeout per attempt = predicted 95th-percentile completion, no 3 s floor. With deadline = 5x run time there is room
  for one retry inside the deadline.
- One mechanism instead of two: a backup attempt on a worker of a different owner, city and ISP when the first attempt
  passes its timeout (idempotent functions only). The miss-probability hedging rule is removed.
- Per-worker drop estimate and ejection stay. Compared against heartbeat + fixed timeout + consecutive-failure ejection (D5).
- Resolves: C8, C9, B13, D5, D14 (with the idempotent-fraction sweep), E12.

### R8. Keep one provisioning rule
- Provisioning = choose the holder set per function so that reserved concurrency covers the 95th-percentile demand after
  losing any $f$ holders, within $K$. Written once as an optimisation problem, solved greedily, given as Algorithm 1.
- Derive the constraint from one model: $f$-worst-case over holders, with $f$ set from the measured departure rate over
  the provisioning period. Drop the survival-weighted sum (B11).
- Exact program, loss-model variants, exposure-budget variant, survival-aware choice, cost-aware caching, reputation,
  peer fetching: one table "Alternatives that did not help", with effect and interval. No prose derivations.
- Resolves: B6 (the novelty is the loss-tolerant key-holder set, not "two timescales"), B8, B11, S6, D11.

---

## 3. Tensions between individual fixes, and how the plan resolves them

| Tension | Resolution |
|---|---|
| A1 asks for proximity evidence; B1 and C3 push all traffic through provider front ends. | Drop the proximity claim (R3). Do not add a direct client-to-worker path; it would reopen NAT traversal (B4). |
| C1 says make Property 1 integrity-only; D8 shows integrity also depends on memory secrecy. | Classes by adversary capability (R4) and a sampled audit. Property 1 is stated for the software-only class. |
| B7 asks for equal-exposure comparison; C5 says the exposure scale is arbitrary. | A hard budget $K$ in holders (R6) gives equal exposure with no scale. |
| C4 (finer keys) increases key releases; B9 and D9 say releases are already too many. | Hysteresis (hold until session end) plus per-function keys (R5). Report releases per hour so the net effect is visible. |
| E6 asks for SETI@home availability traces; R1 says machines are dedicated, which those traces do not describe. | Use the traces as the primary session source and say what they measure (intervals when a volunteered host was on and available). Keep the parametric classes as a sensitivity sweep. This is the honest best available; say so. |
| B3 (global scheduler collapses at 3x10^4) vs B1 (drop clusters). | Measure real decision time (D13). Claim the measured limit. Name provider-hosted shards as the path beyond it. |
| C9 removes the timeout floor; short timeouts raise false suspicion on slow machines. | Suspicion needs consecutive misses (already `suspect_streak = 2`); report false-positive ejections as a metric. |
| R7 makes backups common; D9 says each extra holder is exposure. | Backups go only to existing holders. If no second holder exists, the invocation is not backed up; this is the latency-exposure trade-off acting on fault tolerance, and should be shown as such. |
| D7 (report failing cells) vs wanting a positive result. | The operating-region map is the positive result: it tells a deployer the pool size and load at which the approach works. |
| X1 (admit nothing is built) vs TOIT expecting a system. | TOIT publishes modelling and simulation studies. A calibrated simulator, a small real validation (section 5, V1-V3) and an explicit "designed, not built" statement are acceptable; an implied prototype that does not exist is not. |

---

## 4. Paper structure after revision

Title (from the paper's own vocabulary; S3):
**"Serverless Functions on Attested Volunteer Machines: Provisioning Key Holders under Churn"**

| # | Section | Content | Replaces |
|---|---|---|---|
| 1 | Introduction | Question, setting (dedicated sessions), what is built vs designed (X1), findings with numbers, contributions | intro |
| 2 | Background and problem | Terms table (X3), start-up cost breakdown (measured), failure model, formal problem statement | background (cut by half; S7) |
| 3 | Trust model | Adversary classes (R4), attestation flow, key hierarchy (R5), what a tenant must trust | design + trust (merged; S1) |
| 4 | Design | Request path (R3), provisioning (R8, Algorithm 1), placement (Algorithm 2), failure handling (R7), audit | scheduling + faulttol + network |
| 5 | Methodology | Subsections and tables per X4; metrics per D6; one table of all assumed constants (B10) | method |
| 6 | Results | Five questions below | results |
| 7 | Discussion and limitations | Conditions, mechanism, threats to validity | discussion |
| 8 | Related work | 1.5-2 pages with a comparison table (S5), including edge serverless and harvest VMs | related |
| 9 | Conclusion | The trade-off and where it holds | conclusion |

Results, one subsection per question, each opening with its finding (X7):
1. How do deadline-met rate and key holders trade off, per policy? (main figure; R6)
2. What causes misses under keep-alive, and does provisioning remove the cause? (episode time series)
3. Where does any policy work? (operating region over pool size, load, churn; D7)
4. How much do dropping owners cost, and what does each detector component add? (R7)
5. Which assumptions matter? (sweeps: idempotent fraction, deadline multiple, $K$, $f$, cost error, key rotation period; plus the alternatives table)

Contributions (three):
1. A characterisation of the trade-off between deadlines met and key holders for serverless functions on attested, churning machines, over traces of real host availability and function arrivals.
2. A provisioning rule for key holders that tolerates the loss of $f$ workers, and a deadline-derived failure detector with sampled audit; both evaluated against keep-alive, autoscaling and timeout-based baselines under equal key-holder budgets.
3. Negative results: volunteer-hosted schedulers, exact optimisation and survival-aware selection did not help; and the pool sizes and loads at which no policy meets the target.

Abstract skeleton (fill numbers after reruns; about 150 words):
> Function-as-a-service platforms run on machines their provider owns. We study whether machines lent by untrusted
> owners for sessions of minutes to hours can serve function invocations with deadlines of seconds. Each worker boots a
> measured image and is attested before it receives a function's decryption key; attestation and key release take up to
> N s and are lost when the session ends. We show that the number of workers holding a function's key governs both the
> share of deadlines met and the number of machines from which the key could leak. A provisioning rule that keeps enough
> key holders to survive the loss of f workers meets N% of deadlines with N key holders, where keep-alive and
> autoscaling policies need N. With N% of owners discarding work, deadline-derived timeouts keep N% of deadlines met
> against N% for fixed timeouts. Results come from a simulator calibrated on N machines and driven by host-availability
> and function-arrival traces; the worker image is designed but not built.

---

## 5. Experiment and measurement plan

### 5.1 Simulator changes (small, in dependency order)
| # | Change | For |
|---|---|---|
| S-1 | `clusters.mode = none_global` as default for all paper experiments; lift `max_plan_workers` | R2, D1 |
| S-2 | Remove exposure from placement cost; add per-function holder budget $K$ honoured by every policy | R6 |
| S-3 | Key scope = function; rotation period; hold key until session end | R5 |
| S-4 | Timeout = predicted q95 without floor; backup attempt replaces miss-probability hedging; baseline detectors A and B | R7, D5 |
| S-5 | Capacity = physical cores; measured co-run slowdown | R1 |
| S-6 | Histogram policy as published; target-concurrency autoscaler; greedy-dual keep-alive; keep-alive with $K$ pre-released holders | D4, E7 |
| S-7 | Trace-driven sessions (Failure Trace Archive, SETI@home hosts) and arrivals (Azure Functions trace sample of 200-500 functions mapped to the 12 measured profiles) | E5, E6 |
| S-8 | Decision clock from measured timings (`replay` mode) | D13 |
| S-9 | Sampled audit at rate $p$ with an adversary that forges | R4, D8 |
| S-10 | Metrics: deadline-met (lost and late both miss), slowdown with censoring, concurrent and distinct holders, releases per hour, utilisation, false ejections | D6, D9 |

Each needs a decision record (AGENTS.md rule 12) and the affected hypotheses restated; do not call the new set pre-registered (E4).

### 5.2 Runs (all on one implementation; E3)
| Run | Design | Output |
|---|---|---|
| M1 main | 1,000 workers, trace-driven, 26 h (2 h warm-up), 3 utilisation levels, $K \in \{2,4,8,16,\infty\}$, 8 policies, 10 seeds | Figure: deadline-met vs holders; latency CDF |
| M2 mechanism | subset of M1 with full queue and holder time series | Figure: one episode |
| M3 operating region | pool size {100, 300, 1,000, 3,000} x load x 3 churn settings, best baseline vs provisioning | Figure: region map (D7) |
| M4 droppers | owners dropping 0/10/20%, forging 0/5%; detectors A, B, ours; audit on/off | Figure: deadline-met; time to eject; false ejections |
| M5 sensitivity | idempotent fraction, deadline multiple, $f$, rotation period, ±50% cost error, calibration machine | Table |
| M6 alternatives | exact, loss-model, survival-aware, clustered volunteer-hosted | Table of negative results |
| M7 reference | always-on trusted hosts, same workload | Upper-bound line in M1 figure |

Cost is modest: the current sweep of 2,366 runs takes about four hours on hosted runners; 26 h horizons at 1,000 workers
are heavier per run, so check event throughput first and reduce seeds before reducing duration.

### 5.3 Real measurements (the minimum that makes the simulator credible)
| # | What | Why |
|---|---|---|
| V1 | Build the image. Boot it end to end on three machines (the HDD laptop, the NVMe desktop, one mid-range SSD laptop). Per-step times, 10 boots each. | E2, X11, X17; the author's CRITICAL items |
| V2 | Measure co-run slowdown with 1..n single-vCPU microVMs on each machine. | C13, R1 |
| V3 | Multi-worker emulation on real hardware: 5-10 workers (physical or VMs with software TPMs), real Firecracker, WAN delay injected, sessions killed from a trace; run keep-alive vs provisioning at one load. Compare deadline-met and holder counts with the simulator on the same scenario. | E1 |

V1 needs reboots, so it needs the author's explicit approval (AGENTS.md rule 14). V3 is the single most valuable item
for acceptance; even a 5-worker result that agrees in direction changes the paper's standing.

---

## 6. Order of work

**Phase 0, wording only (days). Do first; none of it depends on reruns.**
- Merge `design.tex` and `trust.tex`; fix labels (S1, X12).
- State what is built (X1). Adversary classes and honest abstract (R4).
- Remove: broker section, succession detail, blockchain sentences, receipts-for-payment, cost analysis, trust technologies beyond the one evaluated, peer fetching, filler (B1, W2, C10, E15, X22, D11).
- Terminology table and grep pass (X2, X3, W6, W7). Headings (W3). Remove E/H identifiers and process narrative (W1, W4).
- Verify or remove the 36 flagged references (X10). Expand related work (S5, D12).
- Remove red markers by resolving or deleting what they mark (S2).

**Phase 1, simulator and reruns (S-1 to S-10, M1 to M7).**
- S-1, S-2, S-10 first, then rerun the existing 30-minute comparison once. This alone tells whether the headline survives D1 and D3, before any further investment.

**Phase 2, measurements (V1 to V3), in parallel with Phase 1.**

**Phase 3, rewrite Results, Discussion, abstract and introduction from the new numbers.**

---

## 7. If the reruns change the answer

Decide the story from the first Phase 1 rerun.

| Outcome under one scheduler, equal $K$ | Paper |
|---|---|
| Provisioning meets the target with clearly fewer holders than every baseline | Story as in section 1. Strongest version. |
| Provisioning equals "keep-alive with $K$ pre-released holders" | The finding is the trade-off itself: holder count decides, the selection rule does not. Contribution 2 shrinks to the sizing rule for $K$ and the detector. Still a paper; say it plainly. |
| No policy differs once exposure is budgeted | The paper is a characterisation study: operating region, cost of attestation and churn, cost of droppers. Title and contributions change accordingly; do not present a system. |

All three are publishable in TOIT if written honestly. The current draft is none of them.

---

## 8. Coverage: which decision resolves which issue

| Decision | Issues resolved |
|---|---|
| Reframe as a study (section 1) | A2, A4, B6, B8, E10, W12, X8, X9 |
| R1 dedicated sessions | A3, A5 (unpaid, stated), C13, S10 |
| R2 one scheduler | B1, B2, B3, B4, B5, B12, D1, D13, S4, S8 |
| R3 data path | A1, C3, D12 |
| R4 adversary classes + audit | C1, C2, C7, C10, C12, D8, D15, D17, W8 |
| R5 key hierarchy | B9, C4, C11, D9, D10, D11 |
| R6 holder budget | B7, B10, C5, C6, D3, X15 |
| R7 deadline-derived failure handling | B13, C8, C9, D5, D14, E12 |
| R8 one provisioning rule | B8, B11, S6 |
| Methodology (5.1, 5.2) | D2, D4, D6, D7, D16, E3, E4, E5, E6, E7, E8, E9, E11, E13, E14, E16 |
| Measurements (5.3) | E1, E2, X11, X17 |
| Phase 0 wording | S1-S3, S5, S7, S9, W1-W11, X1-X7, X10, X12-X14, X16, X18-X23, E15, B14 (related work part) |
