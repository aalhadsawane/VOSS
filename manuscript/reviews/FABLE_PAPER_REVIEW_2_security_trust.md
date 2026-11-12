# Fable Paper Review 2: trust model, security, failure detection

Format per item: quote, problem, fix. Severity: **F** fatal, **M** major, **m** minor.

### C1 (F) The central security claim excludes the attack the paper calls realistic
> "reduces a hostile owner to an unreliable one who can crash a machine or withhold its results but not read or forge anything" (abstract)

> "consumer firmware ships with it disabled or absent --- both machines we calibrated report TME off ... so a volunteer pool cannot be expected to provide it" (`trust.tex`)

> "on consumer hardware the assumptions we exclude are the realistic ones" (`trust.tex`)

- The abstract says the owner cannot read. The body says the owner can read memory on essentially every machine in the pool, and that this is the realistic attack. Property 1 therefore does not hold for the system the paper evaluates.
- "laboratory-grade physical attacks" understates it. Not laboratory-grade, and unaddressed:
  - DMA over Thunderbolt/PCIe/M.2 (no mention of IOMMU policy in the image);
  - cold boot on socketed DDR4;
  - sniffing a discrete TPM's LPC/SPI bus to capture the sealed disk key (no mention of TPM parameter encryption);
  - TPM reset and measurement replay on boards exposing the reset line;
  - malicious or downgraded UEFI/SMM below the measured chain.
- Fix: state Property 1 as integrity only ("cannot forge"), with confidentiality conditional on memory encryption and IOMMU. Change the abstract. Add a table: attack, cost to owner, whether excluded, what is lost.

### C2 (M) Firmware allow-listing across consumer PCs is assumed away
> "reduced if its firmware is not on a known-good list" (`trust.tex`)

- SRTM measurements (PCR 0-7) differ per vendor, model, BIOS version and setting. A known-good list over an open pool of consumer PCs is the hard operational problem of TPM attestation, and it gets one clause.
- Fix: say which PCRs the policy binds, how reference values are obtained per model, and what fraction of real machines would pass. If unknown, list it as an open problem.

### C3 (F) Plaintext inputs and results pass through the provider's router
> "sends the invocation's metadata (never its input) to that cluster's scheduler ... streams the input to the chosen worker, returns the result" (`design.tex`)

> "An attacker who takes over the provider's registry, database, routers or broker obtains ciphertext and metadata, but no tenant code or data." (`design.tex`)

- Code is encrypted at rest, but nothing says requests are encrypted end to end from client to worker. If the router terminates TLS (it "streams the input", "returns the result", "checks" receipts), a compromised router reads every input and output.
- Fix: specify client-to-worker encryption (how does a client obtain and verify a worker session certificate?) or remove "routers" and "data" from the claim.

### C4 (M) One long-lived tenant key for everything is a design flaw that the exposure metric then tries to manage
> "A leaked key is silent and permanent: it decrypts every bundle and snapshot of that tenant, past and future, wherever the ciphertext is stored" (`trust.tex`)

- This is a consequence of the key design, not of the setting. Standard alternatives, none discussed:
  - envelope encryption: per-function or per-bundle data keys, wrapped by the tenant key that never leaves the key service;
  - key rotation per epoch, so a leak is bounded in time;
  - snapshots encrypted under a worker-local TPM-sealed key. The paper says a snapshot "can be restored only on a machine with the same CPU model, kernel and virtual machine monitor" and "stays on that worker's disk", so the tenant key is not needed for it.
- With these, "key exposure" shrinks to a per-function, time-bounded quantity and the latency-exposure trade-off (the paper's main result) changes.
- Fix: adopt envelope encryption and rotation, or argue why not. Rotation is not mentioned anywhere.

### C5 (M) "Key exposure" is an invented metric with arbitrary constants
> "$E_t=\sum_{j}(1-a_j)$ ... (0.8 for the TPM image on a consumer PC, 0.95 for a confidential virtual machine)" ... "it is not a probability of compromise" (`design.tex`)

- 0.8 and 0.95 have no source. The evaluation pool is homogeneous TPM machines, so $E_t$ = 0.2 x number of key holders. The headline "2.5 times their key exposure" means "2.5 times as many key holders".
- A linear sum that is "not a probability" has no interpretation a tenant can act on.
- Fix: report the number of key holders (and holder-seconds). Introduce weights only in an experiment with mixed trust technologies, and justify them.

### C6 (M) Direct contradiction on whether exposure costs latency
> "Limiting exposure costs no measurable latency" (`design.tex`, `results.tex`)

> "\textbf{Exposure is the price of latency.} Every system on the front ... trades the two." (`discussion.tex`)

- Both cannot stand. The first refers to removing a small penalty term from an already high-exposure system; the second to the main result.
- Fix: delete the first claim or scope it precisely ("the per-placement exposure term has no measurable effect once provisioning has chosen the holders").

### C7 (M) The tenant must trust the provider anyway
> "our measured image" ... "If the key service accepts any certificate the verifier issued for an approved image, the tenant trusts the verifier as well." (`design.tex`, `trust.tex`)

- The provider builds the image, runs the verifier/CA and the router. A tenant who trusts the provider's image trusts the provider. "The provider ... never receive[s] tenant keys" is true only while the provider's image is honest, which is the same trust.
- The tenant must also run an always-online, low-latency key service. In serverless the tenant runs no infrastructure; an outage of the tenant's service stops provisioning. Not modelled.
- No reproducible-build or image-audit story lets a tenant check the measurement it is asked to approve.
- Fix: say plainly that the provider is trusted for integrity of the image; state who runs the key service in practice (a cloud KMS?) and its availability assumption.

### C8 (F) "Judging workers by returned work" is a request timeout, and the heartbeat baseline is a strawman
> "(3)~failure detection that judges workers by returned work rather than by heartbeats" (`intro.tex`)

> "heartbeats alone need the 60\,s timeout" (`results.tex`)

- Per-request deadlines, passive health checks and outlier ejection are standard in every RPC stack and load balancer. Gray-failure detection from request outcomes observed by callers is published (e.g. Panorama, OSDI 2018). The paper cites only the gray-failure position paper.
- No production system detects failures with a 60 s heartbeat and no request timeout. 99.95% vs 96.8% measures "timeouts versus no timeouts".
- "returned work" is a coined phrase for "request outcomes".
- Fix: baseline = heartbeat + fixed per-request timeout + retry (what gRPC or Envoy give by default). Claim only the delta: deadline-derived timeouts plus a per-worker Beta/CUSUM drop estimator. Cite the observability-based detection literature.

### C9 (F) The detection timeout is longer than every deadline it is meant to protect
> "The scheduler expects each result by its predicted 90th-percentile completion time times 1.2, at least 3\,s" (`faulttol.tex`)

> "the seven synchronous ones have deadlines of 0.27 to 2.75\,s" ... "At these deadlines a failure must be found and worked around within seconds." (`background.tex`)

- The floor of 3 s exceeds all seven synchronous deadlines. Detection cannot rescue any synchronous invocation; by the time a worker is suspected the deadline has passed. Only pre-emptive duplication can, and the paper says duplication was not shown necessary (B13).
- Then what does "success" mean in "\VossSuccAlpha\% of requests successful"? If success ignores the deadline, the metric does not match the problem statement ("a crash, a dropped result and a late result all miss it").
- Fix: define success; report deadline-met rate under 20% droppers; explain how a dropped synchronous invocation is recovered inside its deadline.

### C10 (M) Receipts solve the wrong fraud
> "A worker cannot claim work it did not do, which is all that paying donors requires" (`faulttol.tex`)

- If donors are paid, the fraud is an owner invoking cheap functions on their own worker (as or with a tenant) to farm credits. Signed receipts certify that work happened, not that it was wanted.
- Fix: remove the payment claim or add the collusion case.

### C11 (m) Snapshot rollback and replay are not addressed
> "the disk partition that holds the cache is encrypted with a key that the TPM releases only if the machine booted the expected image" (`trust.tex`)

- The owner can restore an old disk image between sessions. Stale bundles or snapshots (e.g. with a revoked function version) would be accepted unless versions are checked against the registry. Not stated.
- Fix: one sentence on freshness (version or hash check against the registry at load).

### C12 (m) "stop or delay" survives in the threat table
> "& stop or delay \\" (`trust.tex`, Table)

- The author's own feedback (round 6) asked how an owner delays. Text elsewhere says "drop or delay messages". Make the table match Property 1 wording.

### C13 (m) The no-overcommit security argument conflicts with the capacity model
> "Time-sharing would stretch it by an amount the scheduler cannot observe ... an owner who delays work on purpose could hide the delay in it." (`background.tex`)

> "those running together slow one another by a factor of at most 1.1 (assumed)" ... "CPU threads (hyperthreads counted)" (`background.tex`, `discussion.tex`)

- Counting hyperthreads at 0.75 gives 3 concurrent single-vCPU microVMs on the 2-core/4-thread calibration CPU. SMT siblings do not give 1.1x slowdown; 1.5-2x is typical. Thermal throttling and battery mode on laptops add more. The "tight predicted time" the detector depends on is not tight.
- Fix: count physical cores, or measure the co-run slowdown on the calibration machines and use it.
