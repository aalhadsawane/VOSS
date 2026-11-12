# Fable Paper Review 5: deeper technical issues (second pass, checked against code and configs)

Second pass. Items marked **[code]** were verified in the repository, not inferred from the text.
Format: quote or evidence, problem, fix. Severity: **F** fatal, **M** major, **m** minor.
The fixes here are written to fit together; the combined plan is in
[file 7](FABLE_PAPER_REVIEW_7_coherent_revision_plan.md).

---

## D1 (F) [code] The headline experiment ran on the architecture the paper rejects
Evidence:
- `configs/experiments/E04b.yaml` sets no `voss.clusters.mode`.
- `voss/core/config.py`: `ClustersConfig.mode = "dynamic"`, `target_size = 30`, `PlannerConfig.max_plan_workers = 40`.
- Only E05 and the `no_geo` ablation use `none_global`.

> "A single global scheduler was faster than geographic clusters and held less key exposure." (`intro.tex`)

> "We compare provisioning with the strongest keep-alive baselines on 200 workers for 30 minutes" (`results.tex`)

Problem:
- The 21% result was measured with about seven dynamic clusters of 30, each scheduled from a volunteer machine. The paper never says so, and recommends the other architecture.
- Each cluster needs its own key holders (the paper's own explanation for 5x exposure). So "provisioning holds 2.5x the key holders" and "baselines have two to six holders" are both properties of clustering. A baseline's 2-6 holders are spread over ~7 clusters, so some clusters have zero or one. That is where the 10 s queue comes from.
- This also explains B12: the cap of 40 is harmless only because clusters are 30.

Fix:
- Make the single provider-hosted scheduler the system under test everywhere. Rerun the main comparison with `none_global`, and raise or remove `max_plan_workers` (greedy at 8 ms for 40 workers; measure it at 200 and 1,000).
- State the architecture, worker count, load and duration in the first sentence of every experiment paragraph.
- Expect the gap to shrink. If provisioning no longer beats keep-alive under one scheduler, that is the finding, and the paper becomes the trade-off study in file 7.

## D2 (F) [code] The load of the main experiment is unstated, and it is 0.05 invocations per second per worker
Evidence: `E04b.yaml`: `scenario.load.rate=10`, `scenario.workers=200`, `horizon_s=1800`, warm-up 300 s (`round4.py`).

> "at 20 invocations per second" (abstract; this is a different experiment: 600 workers, 900 s, warm-up 60 s)

Problem:
- 10 requests/s x 1,500 s is about 15,000 invocations per run, of which roughly half are synchronous. P99 of ~8,000 samples is the 80th-worst invocation. The text confirms it: "a baseline's tail is one episode of 40--120\,s".
- The result is the frequency of one kind of rare episode in a nearly idle system (200 machines, 10 requests/s), not steady-state tail latency.
- The abstract mixes three experiments with different sizes, durations and warm-ups in one paragraph without saying so.

Fix:
- Report utilisation (busy concurrency / offered concurrency) for every experiment. Choose loads that give 30%, 60% and 85% utilisation.
- Run long enough that the tail has thousands of samples per function class (file 7: 24 simulated hours).
- Report episode statistics directly (count and length of intervals where a tenant's synchronous queue exceeds its deadline); that is the phenomenon being measured.
- One table at the start of Results listing every experiment: workers, load, duration, warm-up, architecture, seeds.

## D3 (F) [code] The exposure penalty that throttles the baselines is not disclosed
Evidence: `CostConfig.sigma = {"low": 0.1, "medium": 1.0, "high": 3.0}`; `components.py`: `exposure = sigma * (1 - assurance)` for non-holders; `tenants.yaml`: two of six tenants are `high` with `assurance_floor: 0.7`.

> "handing a medium-sensitivity tenant's key to a new worker with trust score 0.8 counts as much as a 20\% chance of a miss" (`scheduling.tex`)

Problem:
- For a high-sensitivity tenant the same step costs 3.0 x 0.2 = 0.6. Placement prefers a key holder with a 59% chance of missing the deadline over a free worker without the key. The paper reports only the medium case.
- $P^{\text{miss}}$ is at most 1, so for high tenants the penalty is most of the scale. Request placement is, in effect, forbidden from adding holders. Only provisioning may add them. The comparison "provisioning vs per-request" is decided by this constant.
- The paper never says which tenant suffers the tail episodes. If it is the two high-sensitivity tenants, the result is entirely the penalty.

Fix (fundamental):
- Remove exposure from the per-request cost. Replace it with a hard, tenant-chosen budget: at most $K_t$ key holders (per function, see D10), and a minimum protection class. Every policy, baselines included, works under the same $K_t$.
- The main figure becomes deadline-met rate against $K$ for every policy. Equal-exposure comparison is then true by construction and no weight needs defending.
- Report results per sensitivity class until then (`pareto.py` already computes `p99_sync_high`).

## D4 (F) [code] The "Azure Functions histogram policy" is a reduced version, and the three keep-alive baselines are nearly the same policy
Evidence: `KeepaliveHistConfig`: `bin_s = 1.0`, `range_s = 1800.0` ("paper 4 h; scaled to E04 v2 runs of 1800 s"), "paper: ARIMA, omitted", `min_samples = 10`, `fallback_ttl_s = 600`. Run length 1,800 s, warm-up 300 s.

> "the hybrid histogram policy of Azure Functions~\cite{shahrad2020wild}, which learns each sandbox's idle times and pre-warms and keeps alive accordingly" (`method.tex`)

Problem:
- The histogram range equals the run length. A function invoked less often than every few minutes never gathers a representative histogram and uses the 600 s fallback, i.e. it is the fixed timer. The time-series component is omitted. The paper states none of this.
- Shahrad et al. keep the histogram per application; the text says per sandbox.
- With a 1,500 s measured window, "10-minute keep-alive" and "unbounded keep-alive" differ only for idle gaps between 600 and 1,500 s. The table shows it: 1.534 vs 1.542 s. "The strongest keep-alive policies" are one policy three times.

Fix:
- Implement the policy as published (4 h range, 1 min bins, per application, the out-of-bounds path), give it at least 4 h of simulated history before measuring, and say in the text exactly what differs from the original.
- Add baselines that differ in kind: a target-concurrency autoscaler (Knative-style, with its 60 s stable and 6 s panic windows), FaaSCache greedy-dual (already cited), and "keep-alive with $K$ pre-released key holders".
- Never write "the Azure Functions policy" for a modified reimplementation; write "our implementation of the hybrid histogram policy [cite], with these differences".

## D5 (F) [code] The heartbeat baseline has every timeout switched off, and its "60 s" is the length of the injected fault
Evidence:
- `watchdog.py:54`: `if dc.mode != "progress": return` (no result timeout is armed);
- `watchdog.py:61`, `router.py:178`, `appoint.py:73,78`: dispatch timeout, router stall detection and slow-scheduler replacement are all conditioned on `mode == "progress"`;
- `E15.yaml`: every fault has `duration_s: 60`.

> "detection by heartbeats with otherwise identical machinery falls to \HbSuccAlpha\%" (`results.tex`)

> "heartbeats alone need the 60\,s timeout (\BhDetectHb\,s, \BhTimeoutsHb{} timeouts)" (`results.tex`)

Problem:
- "Otherwise identical machinery" is false. The baseline has no request timeout, no dispatch timeout and no retry trigger. It is a system that waits forever for lost results.
- There is no 60 s heartbeat timeout in the configuration. The heartbeat baseline never detected the fault; the fault was removed after 60 s. The reported detection time is a censored value.
- So the result is "request timeouts versus none", which nobody disputes.

Fix:
- Baseline A: heartbeats + a fixed per-request timeout (e.g. the tenant deadline) + retry on another worker. This is what any RPC framework or load balancer does.
- Baseline B: A plus consecutive-failure outlier ejection (Envoy-style: eject after 5 consecutive failures for 30 s).
- VOSS's detector must be compared with B. Its distinct parts are the predicted-completion timeout and the per-worker Beta/CUSUM estimate; claim what those add over B, in deadline-met rate and in time-to-eject.
- Report detection time with faults that last longer than any detector needs (e.g. 600 s), and report "not detected" as such.

## D6 (F) [code] "Success" ignores deadlines, and latency is computed over successes only
Evidence: `experiments/analysis/common.py`: `success = (outcome == "ok").mean()`, `met` is a separate column; `round4.py:93`: P99 over `outcome == "ok"` only. `tab_simple`: VOSS `Met` = 0.978 and 0.989. `paper/negative-results.md`: VOSS `met` 0.877-0.959 in several cells.

> "A failure matters through the deadline of the invocation it hits. ... a crash, a dropped result and a late result all miss it." (`background.tex`)

> "keeps \VossSuccAlpha\% of requests successful" (abstract)

Problem:
- The background defines failure by deadline. The headline metric counts a result that arrives after its deadline as a success. 99.95% "successful" coexists with 1-6% (up to 12%) of deadlines missed.
- P99 over completed invocations is survivorship: an invocation lost after three attempts does not appear in the latency distribution at all.
- The paper has the right metric (`met`) and reports it only inside one feasibility criterion.

Fix:
- Primary metric everywhere: share of synchronous invocations that return a correct result within their deadline. Lost and late both count as misses.
- Secondary: slowdown (response time divided by warm run time) at P50/P99, computed with lost invocations entered at their deadline or as censored.
- Drop "success" or define it in the abstract.

## D7 (F) [code] Results where the system fails are in the repository and not in the paper
Evidence: `paper/negative-results.md` "cells where VOSS is not the winner": 100 workers at 5-40 requests/s, VOSS deadlines met 0.877-0.939; confidential-VM pools at 20-40 requests/s, "baseline_better". `generated/macros.tex` holds three feasibility maps (`ViabA`: 9 cells, `ViabB`: 16, `ViabC`: 12); the manuscript reports one.

> "\voss{} is feasible in \RerunViabPTwoVoss{} of \RerunViabCells{} cells" (`results.tex`)

Problem:
- The reported grid is the one where the result is 9 of 9. The grids over scale, load and trust technology, where VOSS fails or loses, are omitted. A reviewer who opens the artifact will find this in minutes, and it reads as selective reporting.
- The omitted cells are the most informative data in the project: they show where the approach stops working (small pools, slow trust technology).

Fix:
- Report all three grids as one "operating region" figure: axes pool size and load, colour = deadline-met rate, one panel per policy. State the boundary in words ("below about N workers per M requests/s no policy meets 95%").
- This turns the weakest part of the evaluation into its most useful result and removes the suspicion.

## D8 (F) The integrity claim falls with the confidentiality claim
> "cannot forge results, which are signed with a key that never leaves the image" (`design.tex`)

> "against reading the memory of a running machine that does not encrypt memory" [not defended] (`design.tex`)

> "running every task several times to check results is unnecessary" (`design.tex`)

Problem:
- The session signing key and the TLS private key sit in the same unencrypted RAM as the tenant key. An owner who can read memory (which the paper calls realistic) extracts the signing key and can then sign arbitrary results and receipts outside the image. C1 said Property 1 should become integrity-only; that is not enough. Both halves depend on memory secrecy.
- So Property 1 holds only against an owner who never touches the hardware. For that adversary, full-disk encryption plus a locked image already suffice.

Fix (fundamental): define the adversary by capability, and give each class its own guarantee and its own mechanism.

| Owner class | Can do | Guarantee | Mechanism |
|---|---|---|---|
| Software-only | boot other software, drop, delay, power off | integrity and confidentiality | measured boot, attestation, sealed keys |
| Physical, no memory encryption | read RAM, sniff TPM bus | none by attestation alone | (a) sampled re-execution for integrity; (b) tenant excludes this class for sensitive functions |
| Physical, memory-encrypted hardware | as above | integrity and confidentiality up to side channels | attestation of the memory-encryption feature |

- Add sampled audit: re-run a small random fraction (e.g. 1%) of idempotent invocations on a worker of a different owner and compare. Detection probability after $n$ forged results is $1-(1-p)^n$; a caught worker is banned by its TPM identity, which costs the owner a machine. This restores a quantitative integrity argument and gives the receipts a purpose.
- Replace "replication is unnecessary" with "replication of every task is unnecessary; a sampled audit bounds forging".
- The cost of the audit (1% extra executions) goes into the evaluation.

## D9 (M) Key exposure counts current holders; a leak is cumulative
> "$E_t=\sum_{j}(1-a_j)$ over the workers $j$ holding its key" (`design.tex`)

> "A leaked key is silent and permanent" (`trust.tex`)

> "it releases a key \RfourRelPlanGreedyMed{} times after warm-up ... against \RfourRelKeepaliveTtlMed{}" (`results.tex`)

Problem:
- The metric is an instantaneous count. The paper's own argument says a key that was ever on a machine may have leaked for good. The right quantity is the number of distinct machines that ever received the key during its lifetime.
- By that measure provisioning is far worse than "2.5x": 270 releases against 6 in 25 minutes. The headline understates the cost by an order of magnitude.
- A session "ends" when the worker leaves the network; the owner can keep the machine powered and the key in RAM.

Fix:
- Report three numbers: concurrent holders (capacity view), distinct holders per key lifetime (leak view), and releases per hour (load on the tenant's key service).
- Bound the leak view by design: short-lived per-function data keys with rotation (D10), and hysteresis so that a holder keeps its key until its session ends rather than being released and re-added.

## D10 (M) Key hierarchy: one tenant key for code and snapshots is the wrong granularity
(Extends C4 with a concrete design.)

Problem:
- One key per tenant means every function of the tenant is exposed on every holder, and it cannot be rotated without re-encrypting everything.
- Snapshots are encrypted with the tenant key although they are bound to one CPU model and stay on one disk.

Fix:
- Tenant root key: never leaves the tenant's key service (in practice a cloud KMS; say so).
- Per-function, per-version data key, wrapped by the root key; rotated every $R$ hours. A worker receives only the data keys of the functions it is provisioned for. Exposure is then per function and bounded by $R$.
- Snapshots: encrypted under a key generated inside the image and sealed to the TPM measurement. No tenant key involved; a snapshot is useless on any other machine and after any image change. Drop peer copying of snapshots (D11).
- Simulator change: key scope becomes the function; add a rotation period. One sensitivity run (per-tenant vs per-function keys) shows the cost of the finer granularity in key releases.

## D11 (M) Peer-to-peer fetching contradicts the NAT argument and the ablation
> "workers fetch from nearby workers before the provider's registry" (`background.tex`)

> "hole punching works only for some pairs of home routers" (`network.tex`)

Evidence: `tab_ablation`: removing peer fetching changes P99 by -0.036 s (slightly better); removing the hard-disk tier changes nothing (+0 [+0, +0]).

Problem:
- Two home machines behind NAT cannot open a connection to each other without the hole punching the paper dismisses one section later. If transfers are relayed, they cost provider bandwidth and both uplinks.
- The paper's own ablation shows no benefit. Text that describes a mechanism with zero measured effect, and that conflicts with another section, should not be in the design.

Fix: remove peer fetching and the disk-tier distinction from the design text. Workers fetch ciphertext from the provider's registry (a CDN in practice). Mention the two null results in one line of the negative-results table.

## D12 (M) Edge serverless already provides proximity
> "A request must still travel to the datacenter and back" (`intro.tex`)

Problem:
- Commercial edge platforms run functions in hundreds of cities (Cloudflare Workers, Lambda@Edge, Fastly Compute). "The datacenter is far away" has not described serverless for years. The introduction and related work do not mention them.
- Combined with A1 (the request path goes through the provider's router anyway), the proximity argument has no ground.

Fix:
- Cite edge serverless and state the actual difference: those are provider-owned points of presence; this work asks whether machines the provider does not own or trust can serve the same class of requests, and what it costs.
- Motivation that survives: (i) capacity without capital expenditure, (ii) coverage where no point of presence exists, (iii) the research question itself (how far attestation plus scheduling closes the gap to trusted, always-on hosts). Pick (iii) as the frame and (i) as the practical reason.

## D13 (M) [code] Decision latency is a formula, although the policies are real code
Evidence: `base.yaml`: `decision_clock: {mode: modeled}`; `config.py`: modes `measured`, `modeled`, `replay`.

> "decision time is a placeholder formula" (`discussion.tex`)

> "decision latency has grown from about 0.1\,s to tens of seconds" (`results.tex`, scale)

Problem: the scale result and the "one core for $10^5$ workers" claim both rest on an invented cost for code that exists and can be timed.

Fix: time the real provisioning and placement code offline across view sizes (40 to 10,000 workers, 6 to 500 functions), fit a table, and feed it to the simulator through the existing `replay` mode (keeps determinism). Then state one measured scale limit for a single scheduler and stop there. If it is around 10^4 workers, say that larger pools need regional shards on provider hardware, and do not evaluate them.

## D14 (M) Synchronous duplication is justified by asynchronous at-least-once delivery
> "Developers already follow this contract: AWS Lambda retries failed asynchronous invocations and warns of duplicate events ..., Google's event-driven functions run at least once" (`background.tex`)

Problem:
- All four citations are about asynchronous, event-driven invocation. The system duplicates and retries synchronous request-response calls. Synchronous Lambda invocations are not retried by the platform. The evidence does not support the claim it is attached to.
- "11 functions are idempotent by our assumption" then carries the fault-tolerance result.

Fix:
- State it as a requirement the tenant declares per function, not as existing practice.
- Evaluate with idempotent fraction 0, 0.5 and 1. For non-idempotent synchronous functions the only tools are choosing reliable workers and failing fast; show how much of the benefit remains.

## D15 (M) Runtime integrity after boot is not covered
> "Periodic re-quotes keep it valid during the session." (`trust.tex`)

> "tenants may run malicious code, which microVMs isolate" (`design.tex`)

Problem:
- A TPM quote reports boot-time measurements. A re-quote an hour later returns the same PCR values even if the host kernel was compromised in between, for example by a tenant escaping the microVM, or by the owner through a device interface (malicious USB or Thunderbolt peripheral). Re-quoting proves the TPM is still there, nothing more.
- A malicious tenant who escapes on a volunteer machine reaches every other tenant's keys held there. That is a multi-tenant risk the datacenter has too, but there the host is patched by the provider; here the image update path is not described.

Fix: say what re-quotes prove (liveness of the TPM-bound identity). Add one paragraph on image updates (how a new measurement is rolled out, how old ones are retired) and on co-tenancy policy (a tenant may request single-tenant workers; this multiplies holders, which the $K$ budget then prices).

## D16 (m) The datacenter reference's own P99 is above one second
Evidence: `ref_lambda_like.yaml`: `hosts_per_region: 40` "sized to never saturate", 600 s keep-alive; VOSS P99 at 20 requests/s is 1.28 s and the reference is 0.11-0.17 s lower.

Problem: an unsaturated, always-on datacenter with P99 around 1.1 s for functions whose longest synchronous run is about 0.5 s is paying cold starts in the tail. In a 900 s run with a 60 s warm-up, those are start-of-run cold starts of rare functions. The reference's tail is a warm-up artifact, and VOSS "comes within 0.1 s" of an artifact.

Fix: long warm-up for all systems; report the reference's cold-start share. Use the reference as an upper bound on what any policy can reach, described as "always-on trusted hosts, same workload", with no vendor names.

## D17 (m) A worker's speed is "declared"
> "The scheduler knows such a machine only by its declared speed" (`background.tex`)

Problem: who declares it? If the owner, it is adversarial input. If the image benchmarks at boot, say so. Speed also varies with thermal state and power source on laptops.

Fix: the image measures a short benchmark at session start and reports it under the session key; the run-time estimator's per-worker correction (already in the design) tracks drift. One sentence.

---

## Summary of what the code check changes
- The 21% headline is confounded three ways: clustered architecture (D1), near-idle load with episode-driven tails (D2), an undisclosed exposure weight (D3).
- Both baselines the abstract names are weakened: the histogram policy (D4) and heartbeat detection (D5).
- The abstract's success figure uses a definition the background section rejects (D6).
- Unfavourable grids exist and are unreported (D7).
- None of this is fixed by wording. It needs the reruns in file 7.
