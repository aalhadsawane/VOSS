# Fable Paper Review 3: evaluation and methodology

Format per item: quote, problem, fix. Severity: **F** fatal, **M** major, **m** minor.

### E1 (F) Simulation only, and the validation error is as large as the headline effect
> "agrees with the simulator ... on median latency (within 6--23\%), but only partly on the shape of the latency distribution" (`method.tex`)

> "lowers 99th-percentile (P99) latency by about \RfourDecompGreedyMed\%" (abstract)

- The headline is a 21% difference in the tail. The simulator is validated to 23% at the median, on one box, and not validated in the tail, the network, attestation or failover. The claimed effect is inside the model error.
- "we compare designs rather than absolute latencies" is then broken by the absolute comparison to AWS/Azure-like references in the abstract.
- Fix: a small real testbed (5-10 machines, real churn injected) reproducing the provisioning-versus-keep-alive comparison is the minimum for a journal systems paper. The author already lists it as future work; it is present work.

### E2 (F) The first number in the paper was not measured
> "On our calibration laptop ... this takes \CalAttested\,s from power-on" (`intro.tex`)

> "The time to an attested worker (\CalAttested\,s) is a sum of measured steps run on the laptop's installed system rather than one boot of the final locked image." (`method.tex`)

- The locked image does not exist. 65 s is an estimate assembled from a stock Linux install; the introduction presents it as a measurement.
- Calibration came from one i3 laptop with 3.7 GiB memory and a hard disk. With a 0.6 memory share that worker offers 2.2 GiB, while "snapshots of up to 600\,MB" and "file systems of 90--450\,MB" are in the workload. The reference machine can barely host the workload.
- Literature placeholders were off by up to 33x when measured (snapshot create 0.2 s vs 6.68 s, `tab_calibration`). The confidential-VM numbers are still placeholders of the same kind.
- Fix: build the image, boot it, measure end to end on at least three machine types (already the author's own CRITICAL item). Until then, call 65 s "estimated".

### E3 (F) Half of the experiments ran with a placement the paper calls defective, including the ablation
> "the experiments about VOSS alone (ablation, failure detection, geographic clusters, scale) ran with the original placement, which changes VOSS's own P99 by about 2\%" (`discussion.tex`)

> "Our first request placement ... handicapped baselines and made provisioning's lead look larger." (`discussion.tex`)

> "removing provisioning \AblPlanningP\,s" (`results.tex`)

- An ablated VOSS *is* a baseline. The defect handicapped baselines. So "2% for VOSS's own P99" does not bound the error on ablation deltas.
- Evidence: the ablation says removing provisioning costs 1.1 s; the corrected main experiment says provisioning gains 0.3-0.4 s. The ablation overstates by 3x.
- Fix: rerun every experiment with the corrected placement. Delete "original placement" and "corrected placement" from the paper; a submitted paper has one implementation.

### E4 (M) "Hypotheses fixed before the runs" is not credible as written
> "Hypotheses and their verdict rules ... were written down before the runs" (`method.tex`)

- H12-H16 were added in a later round, after the defect was found and the first results were seen. The 0.95 threshold, the choice of "best baseline per setting on the test seeds", and reruns labelled `b` are post hoc.
- Fix: say which hypotheses predate which data. Drop the pre-registration language for the rest; report effect sizes and intervals.

### E5 (F) Thirty-minute runs cannot exercise what the system models
> "200 workers for 30 minutes" (`results.tex`)

> "bursty, day-and-night arrivals" ... "sessions last minutes to hours" ... "the larger of two moving averages (1 and 15 minutes)" ... "learned from many sessions, over hours" (`method.tex`, `scheduling.tex`)

- No day-night cycle fits in 30 minutes. Few sessions end. The Weibull estimator has little data; the 15-minute average covers half the run.
- The histogram policy of Shahrad et al. learns idle-time histograms over hours to days per application. Run for 30 minutes from a cold start, it is the fixed fallback with noise. Its poor result is an artifact.
- This also explains the null result on survival estimates (H16), which the paper attributes to nothing ("Plausibly ... but we did not test this").
- Fix: runs of at least 24 simulated hours, with a warm-up period for every learning policy; report after warm-up.

### E6 (M) "No public trace exists" while citing the archive that has them
> "no public trace of donation sessions exists, so these parameters follow availability studies~\cite{javadi2013fta}, are marked \emph{assumed}" (`method.tex`)

- The Failure Trace Archive contains SETI@home host availability traces (about 230k hosts). They are not "donation sessions under a locked image", but they are measured volunteer availability, and better than assumed Weibulls.
- The Azure Functions 2019 trace is cited for the workload shape but not replayed. 6 tenants and 12 functions is not a serverless workload; the long tail of rarely invoked functions is exactly where keep-alive and provisioning differ.
- Fix: drive sessions from FTA traces and arrivals from the Azure trace (sampled to a few hundred functions).

### E7 (M) The "strongest" baseline is neither the strongest nor run fairly
> "against the strongest keep-alive policies, including the Azure Functions histogram policy" (abstract)

> "We use the Azure histogram policy as our strongest keep-alive baseline." (`related.tex`)

> "The hybrid histogram policy ... is no faster." ... "the best keep-alive baseline, which is a fixed or unbounded keep-alive timer" (`results.tex`)

- Results say the histogram policy is the weakest of the three keep-alive policies at high churn (1.669 vs 1.520). Related work says it is the strongest. The abstract name-drops it.
- Missing baselines (see B6, B7, B14): target-concurrency autoscaler; keep-alive with a minimum number of key holders; harvest-VM eviction-aware placement; FaaSCache greedy-dual keep-alive (cited, not run).
- Fix: correct the wording; add the baselines.

### E8 (F) "Modelled on AWS Lambda and Azure Functions" is the authors' own simulator with always-on hosts
> "Against datacenter references modelled on AWS Lambda and Azure Functions, its P99 is ...\,s higher" (abstract)

> "at 10 per second the gap to the Azure-like reference is not distinguishable from zero" (`results.tex`)

- A volunteer pool on home links matching a datacenter at P99 signals a weak reference, not a strong system. The references share the unvalidated network model and an assumed keep-alive.
- Using two vendors' names for unvalidated models in an abstract invites a desk rejection.
- Fix: call it "a simulated always-on datacenter baseline", keep it out of the abstract, or measure real Lambda/Azure latency for the SeBS functions and calibrate to it.

### E9 (M) P99 pooled over functions of 4 ms to 6 s is not a meaningful metric
> "The 12 functions run for 4\,ms to 6\,s" ... "We report the 99th percentile of the latency of synchronous invocations" (`background.tex`)

> "every system meets a 3\,s P99 target, so the differences are in the tail between 1.2 and 1.8\,s" (`results.tex`)

- A pooled P99 of 1.2-1.8 s is set by the slowest functions and their share of traffic. It says nothing about the 4 ms function with a 0.27 s deadline.
- The paper defines per-invocation deadlines and then does not use them as the main metric. `tab_simple` shows "Met" 0.978-0.989, i.e. 1-2% of deadlines missed, next to "success above 99.9%".
- Fix: primary metric = share of deadlines met (overall and per function), plus slowdown (latency / warm run time) percentiles.

### E10 (M) Every system already meets the target
> "Success is above 99.9\% for every system and every system meets a 3\,s P99 target" (`results.tex`)

- Under the paper's own feasibility definition, keep-alive is feasible everywhere in the main experiment. The contribution is 0.3-0.5 s inside an already-met target, bought with 2.5x exposure and 1.5x warm memory (86.7 vs 56.6 GB).
- Warm memory is in the table and never discussed as a cost. Donor memory is the scarce resource in the capacity model.
- Fix: find and show the regime where keep-alive fails the target and provisioning meets it (higher load, more tenants, longer-tail functions). If none exists, say so.

### E11 (M) The feasibility experiment compares against a broken baseline, and the paper says so
> "The simple baseline is feasible in \RerunViabPFiveSimple{} cells under every criterion, with P99 between \RerunViabPNinetynineLoSimple{} and \RerunViabPNinetynineHiSimple\,s even in the cells without adversaries" ... "This gap does not show that provisioning matters" (`results.tex`)

- A baseline with P99 of 6-8 s on a benign pool, when plain keep-alive reaches 1.5 s, is misconfigured. 9 of 9 against 0 of 9 is not evidence, and the text concedes it.
- Fix: remove the simple baseline, or replace the feasibility grid's comparator with the best keep-alive policy.

### E12 (M) Assumptions that carry the result and are not varied
> "11 functions are idempotent by our assumption" ... "a multiple we did not vary" ... "we have not swept them" ... "we did not sweep prediction error" ... "We did not sweep the 30\,s period" (`discussion.tex`, `scheduling.tex`)

- Idempotence of 11/12 functions enables retry and duplication; real synchronous functions with side effects are not idempotent. Deadline multiple 5 fixes how much slack exists. Declared worker speeds and start-up costs are "taken as exact" on consumer hardware.
- Fix: sweep idempotent fraction (0, 0.5, 1), deadline multiple (2, 5, 10) and cost-prediction error (±20%, ±50%).

### E13 (M) Scorecard intervals are not well-formed
> "-54.5\% {\scriptsize[-105.8, -12.6]}" (`generated/tab_scorecard.tex`)

- A relative reduction cannot be below -100%. The statistic is undefined in the text. The table also carries stale pre-fix numbers (H1: -54% to -62%) and internal labels ("MILP planner", "appliance", "GDSF", "black-holed", "blr", "RQ15").
- `sections/appendix.tex` is not `\input` in `main.tex`, so this table and the reproduction appendix are currently orphaned.
- Fix: define the estimator (ratio of means? mean of ratios?), bound it, regenerate from corrected runs, rename labels, and include or delete the appendix.

### E14 (m) Statistics details
> "percentiles are computed per run and then averaged" (`method.tex`)

- Averaging per-run P99 over 30-minute runs weights rare episodes oddly ("one episode of 40--120\,s" decides a seed). Report the distribution over seeds (box plot) and pooled percentiles as a check.
- "$\pm$0.192" in the front table: say whether this is SD, SE or CI half-width.

### E15 (m) Cost analysis
> "counting the control plane and not volunteer credits" (`results.tex`)

- Compute priced at zero makes the comparison meaningless. Already marked for removal; remove it, or do it properly (A2).

### E16 (m) Bit-reproducibility is hygiene, not a contribution
> "(5)~a deterministic simulator in which every compared system faces the same machine departures and request arrivals" (`intro.tex`)

> "matched 2{,}366 of 2{,}366 runs" (`method.tex`)

- Common random numbers and seeded runs are standard simulation practice. Hash-matching shows the code is deterministic, not that the model is right (E1). The SSE4/AVX-512 paragraph is an artifact-evaluation note.
- Fix: one sentence plus an artifact link. Remove contribution (5).
