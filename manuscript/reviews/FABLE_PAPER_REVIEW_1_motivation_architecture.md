# Fable Paper Review 1: motivation and architecture

Target: ACM TOIT. Verdict on the current draft: **reject**. Format per item: quote, problem, fix.
Severity: **F** fatal (rejection on its own), **M** major, **m** minor. Files: `sections/*.tex`.

Other files: [2 security](FABLE_PAPER_REVIEW_2_security_trust.md), [3 evaluation](FABLE_PAPER_REVIEW_3_evaluation.md), [4 writing](FABLE_PAPER_REVIEW_4_writing_structure.md), [5 deeper technical, code-checked](FABLE_PAPER_REVIEW_5_deeper_technical.md), [6 deeper writing](FABLE_PAPER_REVIEW_6_deeper_writing.md), [7 coherent revision plan](FABLE_PAPER_REVIEW_7_coherent_revision_plan.md). Read 7 before fixing anything.

## A. Motivation

### A1 (F) The stated benefit, proximity, is never delivered and the paper's own numbers refute it
> "A request must still travel to the datacenter and back, and keeping environments alive does not shorten that trip. Meanwhile, millions of home and office computers sit close to users" (`intro.tex`)

> "Median latency is about 0.13\,s higher at every load." (`results.tex`)

> "The \emph{router} is the public entry point: it ... streams the input to the chosen worker, returns the result" (`design.tex`)

- The data path is client → provider router → worker → provider router → client. Every request still makes the datacenter trip, plus a second leg to a home link.
- Result: slower than the datacenter at the median and at P99. The only motivation in the introduction is contradicted by Section 9.
- No experiment places clients geographically or reports latency by client-to-worker distance.
- Fix: either (a) add a direct client-to-worker data path and show a latency win for nearby clients, or (b) drop proximity and motivate by something the results support (capacity without datacenters, cost, data locality). Do not keep a motivation the evaluation falsifies.

### A2 (F) No remaining reason to use the system
> "\potrem{cost analysis; removed from the abstract}" (`results.tex`)

> "Against datacenter references ... its P99 is ... higher" (abstract)

- Latency is worse, cost is being deleted, security is weaker than a datacenter (C-series in file 2). The paper never states what a tenant gains.
- Fix: state one concrete advantage in the introduction and evaluate it. If it is cost, do the cost model properly (donor payment, electricity, provider control plane, tenant key service) instead of removing it.

### A3 (F) "Idle computers" versus "reboot into our image"
> "idle home and office computers that their owners donate" (abstract)

> "A session starts when the owner reboots into the image" (`trust.tex`)

> "CPU threads & 0.75 & assumed ... Memory & 0.6" (`method.tex`, Table)

- A machine booted into a locked image with no login is not idle capacity; it is a machine the owner cannot use. BOINC-style harvesting (work while the owner uses the PC) is impossible in this design.
- If the owner cannot log in, what consumes the other 25% of CPU and 40% of memory? The donated-share model belongs to a co-located design the paper does not build.
- "Nightly" and "idle-hours" worker classes imply the owner manually reboots twice a day. No adoption argument is given.
- The one technology that fits the motivation, "a measured hypervisor started under the owner's operating system", is listed and never evaluated.
- Fix: pick one deployment model. Either dedicated dual-boot machines (then say so, drop "idle", set shares to ~1) or late-launch/DRTM under the owner's OS (then evaluate that, with its attestation cost and weaker isolation).

### A4 (M) Scale of the problem does not need the system
> "200 workers for 30 minutes" ... "at 20 invocations per second" (`results.tex`, abstract)

- 20 requests/s of sub-second functions fits on one server. 200 volunteer machines serve what one rented VM serves.
- Fix: report load per worker and utilisation; evaluate at a load where pooled volunteer capacity is actually needed.

### A5 (M) Volunteers, donors, or paid providers?
> "which is all that paying donors requires" (`faulttol.tex`)

> "counting the control plane and not volunteer credits" (`results.tex`)

- Payment appears twice in passing. Paid owners are rational adversaries (credit farming, self-invocation), not volunteers. The threat model ignores this.
- Fix: decide. If unpaid, delete receipts-for-payment. If paid, add the incentive attacks to the threat model.

## B. Architecture

### B1 (F) The clustered, volunteer-hosted scheduler is refuted by the paper and still occupies a contribution, a section and the abstract
> "Geographic clustering is the only component whose removal improves P99" ... "It holds \GeoExpRatio{} times the key exposure of a global scheduler" (`results.tex`)

> "Compute is not why the scheduler runs on a volunteer machine ... we keep the clustered one because it needs no per-cluster provider server and because it is the harder case for fault tolerance." (`network.tex`)

- "Harder case" is not a design reason. The provider already runs router, broker, orchestrator, verifier and registry; saving one scheduler process (stated cost: one core per 10^5 workers) saves nothing.
- Contribution (4), Section 6, half of Section 7, the scheduler-fault results and one abstract clause all describe a design the authors show is slower, more exposed and unnecessary.
- Fix: make the global scheduler the system. Move the clustered design to a short "design we rejected, and why" subsection, or remove it.

### B2 (F) The comparison of global and clustered confounds two variables, and the obvious third design is missing
> "We did not run a provider-hosted variant" (`discussion.tex`)

> "in that experiment the global scheduler also ran on a volunteer machine, which favours clusters" (`results.tex`)

- Variables: (i) one scheduler vs many, (ii) provider host vs volunteer host. Only two of four combinations exist, and one of them was run in a configuration the paper calls wrong.
- The standard answer to a central scheduler bottleneck is sharded provider-hosted schedulers. It is not considered.
- Fix: run the 2x2, or delete the comparison.

### B3 (M) Scaling claim contradicts the scale result
> "on provider hardware, greedy planning for $10^5$ workers in clusters of 30 needs about one processor core" (`network.tex`)

> "falls to \ScaleMidSucc\% at $3\times10^4$ and \ScaleBigSucc\% at $10^5$, where decision latency has grown from about 0.1\,s to tens of seconds" (`results.tex`)

> "decision time is a placeholder formula" (`discussion.tex`)

- The global design the paper recommends collapses at 3x10^4 workers, and the collapse is produced by a placeholder formula. Neither claim is usable.
- Fix: measure decision time of the real policy code against view size and use that; then state the scale limit once.

### B4 (M) Publish/subscribe is presented as a design contribution; it is a relay
> "HTTP and gRPC assume a server at an address its clients know" (`network.tex`)

- False dichotomy. NATed agents holding one outbound long-lived connection (HTTP/2 or gRPC bidirectional stream, WebSocket, QUIC) to a provider front end is the standard pattern (CI runners, tunnels, kubelet-style agents). Topic-based addressing adds a name indirection that a routing table in the router also gives.
- MQTT at-least-once is then patched with epochs, sequence numbers and signatures, i.e. the properties are rebuilt above it.
- Unspecified: how the router "streams the input" to a NATed worker. Through the broker (payloads of megabytes over MQTT)? Through a second connection? The data plane is missing from the design.
- "The simulator models only the delay of messages ..., not broker capacity, reconnection or the cost of signatures": the mechanism is not evaluated.
- Fix: describe the data path. Justify MQTT against outbound streaming RPC, or reduce this to one paragraph. Drop "publish/subscribe" from the abstract and keywords.

### B5 (M) "Replacing schedulers without agreement among volunteers" sells a lease as a result
> "replacing failed ones without agreement among volunteers" (abstract)

> "an atomic compare-and-swap that increments it ... much like a lease" (`faulttol.tex`)

- This is epoch fencing by a central configuration master (Chubby, ZooKeeper, GFS master, Vertical Paxos). Consensus is not avoided; it is delegated to the orchestrator's replicated database.
- "a scheduler that cannot reach the orchestrator for 5\,s stops on its own": the timer runs on a machine whose owner controls the hardware clock. State that safety rests on the worker-side epoch check only, not on this timer.
- Fix: describe it in two sentences as standard fencing, cite, and remove it from the contributions.

### B6 (F) "Separating provisioning from request placement" is existing practice
> "(1)~a scheduler ... that separates provisioning ... from request placement" (`intro.tex`)

> "Edge computing often places services on a slow timescale and routes requests on a fast one. \voss{} shares this structure" (`related.tex`)

> "Keep-alive baselines, none of which provisions" (`method.tex`)

- The related-work section concedes the structure is known. Serverless platforms also have it: Knative autoscaler plus activator, Lambda provisioned concurrency, Azure pre-warming, Kubernetes HPA plus load balancer.
- The histogram policy pre-warms, so "none of which provisions" is wrong by the paper's own definition.
- Missing baseline: a target-concurrency autoscaler (Knative-style) that keeps N warm instances on N workers per function. That is the datacenter equivalent of "provisioning" and the baseline a serverless reviewer will ask for first.
- Fix: contribution (1) must be what is new: provisioning *keys* under churn with a loss-tolerant cover. Add the autoscaler baseline.

### B7 (F) The measured gain comes from relaxing the exposure penalty, not from the provisioning algorithm
> "a baseline's tail is one episode of 40--120\,s in which synchronous invocations of one tenant queue for about 10\,s behind long asynchronous jobs on the two to six workers that hold its key, while greedy has 11--20 holders" (`results.tex`)

> "Key-release delay accounts for 0.1--0.4\% of synchronous invocations in every system." (`results.tex`)

> "about \RfourDecompShareMed\% of greedy's gain" [early keys] ... "(H15, weak)" (`results.tex`)

- Key release is cheap (one round trip, 0.1-0.4% of invocations). So why do baselines queue 10 s on 2-6 holders instead of fetching a key on a free worker? Because the shared placement cost charges $x_{ij}=\sigma_t(1-a_j)$ for a new holder. The baselines are throttled by a penalty the proposed system is allowed to pay in bulk.
- What the experiment shows: more key holders → more usable capacity → shorter tail. That is a capacity statement, reachable by a keep-alive baseline with a "minimum k key holders" knob or a smaller $\sigma_t$.
- At equal exposure (early keys), the full machinery adds about 5% with a CI that touches the threshold. The robust constraint, survival estimator, exact program and loss model contribute nothing measurable.
- Second cause is head-of-line blocking of synchronous work behind asynchronous work. Separate queues or reserved synchronous concurrency per worker fix that without key provisioning.
- Fix: (i) sweep $\sigma_t$ for every baseline and compare at equal exposure, as a curve; (ii) add "keep-alive + k key holders" and "keep-alive + sync/async isolation" baselines; (iii) reframe the finding as "latency versus number of key holders" if (i) and (ii) close the gap.

### B8 (M) Two pages of algorithms with null results
> "the exact program was not measurably better" ... "it trades latency for exposure rather than replacing greedy" ... "The variant that enforces an exposure budget ... did not meet its budget" ... "Hiding survival estimates from provisioning changes P99 by less than 3\%" (`scheduling.tex`, `results.tex`)

- Exact integer program, Erlang-loss submodular provisioning with a $(1-1/e)$ guarantee that "holds per tenant only", exposure-budget variant, Weibull survival: all null. The guarantee is stated and then withdrawn in the next sentence.
- A variant that fails its own constraint is a bug report, not a result.
- Fix: keep greedy. Move the rest to one paragraph of negative results or an appendix. Cut the submodularity argument unless a guarantee holds for the problem actually solved.

### B9 (M) Provisioning contradicts its own premise about key lifetime
> "giving a worker a tenant's key lasts the rest of its session" (`scheduling.tex`)

> "it releases a key \RfourRelPlanGreedyMed{} times ... against \RfourRelKeepaliveTtlMed{} for a keep-alive timer, so one release serves about \RfourAmortPlanGreedyMed{} synchronous invocations" (`results.tex`)

- The separation is justified by key decisions being long-lived. The implementation re-releases keys 45 times more often than the baseline. Every release is a call to the tenant's key service, a cost never charged to the tenant.
- Fix: add hysteresis (do not revoke a key while the session lives) and rerun, or remove the lifetime argument.

### B10 (M) The cost function adds a probability, seconds and an invented unit with unswept weights
> "$J_{ij}=P^{\text{miss}}_{ij}+0.05\,\mathbb{E}[T_{ij}]+x_{ij}$" (`scheduling.tex`)

- 0.05, $\sigma_t$, miss threshold 0.2, duplicate budget 10%, 12 candidates, 40 workers, $f$ = a tenth, 95th percentile, 60 s look-ahead, 30 s period, 1.2x timeout, 3 s floor, 200 ms, 5 s, 1 s: fifteen constants, none swept. B7 shows the result is sensitive to at least $\sigma_t$.
- Fix: one table of all constants with source; sensitivity runs for the three that drive the headline ($\sigma_t$, $f$, period).

### B11 (M) The robust constraint mixes an expectation with a worst case
> "$\sum_j e_j\,c_{tj} - (\text{sum of the } f \text{ largest } c_{tj}) \ge q_t$" (`scheduling.tex`)

- Capacity is discounted by survival probability $e_j$ and then the $f$ largest are removed again at full weight. Departures are counted twice; no stated failure model yields this inequality.
- $q_t$ is a Poisson percentile while the text admits "Real arrivals are burstier than Poisson".
- The provisioning objective is given only in words ("minimises the memory and disk the plan uses, key exposure, and the number of new key releases, minus the start-up time"), with no weights.
- Fix: write the full optimisation problem once (variables, objective with weights, constraints). Derive the constraint from one model: either chance-constrained or $f$-worst-case, not both.

### B12 (M) View cap contradicts the experiment size
> "Provisioning considers the live, non-leaving workers in its view (at most 40) ... so these limits never apply" (`scheduling.tex`)

- The main experiment has 200 workers under a global scheduler. Either the cap of 40 applies (then how are 40 chosen, and is $f$ a tenth of 40 or of 200?) or the sentence is wrong.
- Fix: state what the global scheduler does with 200 workers.

### B13 (m) Hedging is advertised and then found unnecessary
> "the invocation also runs on a second worker ... and the first result to arrive is used" (`intro.tex`)

> "duplicating only at-risk invocations is cheap insurance that we could not show to be necessary" (`results.tex`)

- Fix: remove it from the introduction's system description or show a setting where it matters.

### B14 (M) Design alternatives from existing work that are not used or discussed
- **Harvest VMs for serverless** (cited as `zhang2021harvest`, dismissed in one clause): closest prior system for serverless on evictable capacity. Its eviction-aware placement is a required baseline.
- **Trace-driven availability**: the cited Failure Trace Archive contains SETI@home host availability. See file 3, E6.
- **Checkpoint and migrate** (HTCondor-style): snapshots exist in the design but are never used to move in-flight work on an owner's leave notice.
- **Envelope encryption with short-lived data keys**: see file 2, C4.
- **Passive health checking and outlier ejection** (load balancers): see file 2, C8.
