# Fable Paper Review 6: deeper writing and presentation problems (second pass)

Format: quote, problem, fix (with a rewrite where one helps). Severity: **F** fatal, **M** major, **m** minor.
Extends [file 4](FABLE_PAPER_REVIEW_4_writing_structure.md); nothing here repeats it.

---

## X1 (F) The paper describes a system in the present tense; no system exists
> "We present \voss{}, a scheduler for this setting." (`intro.tex`)

> "Workers run each invocation in its own Firecracker microVM" ... "The image is a signed kernel with a read-only, integrity-checked root file system" ... "We take MQTT as the protocol" (`design.tex`, `trust.tex`, `network.tex`)

> "The time to an attested worker ... is a sum of measured steps run on the laptop's installed system rather than one boot of the final locked image." (`method.tex`)

- What exists: scheduling policy code, a simulator, timing measurements on one or two machines, a single-host emulation. What the text describes as existing: an image, a router, a verifier, a broker, key services, a registry.
- A reader learns that the image was never built only in Section 8. This is the kind of mismatch that turns a critical reviewer into a hostile one.
- Design and simulator are also interleaved: "The simulator charges a fixed, measured cost for the policy check" (inside the trust design), "a data file tells the simulator how long attestation takes" (inside trust technologies).

Fix:
- Say in the introduction, once and plainly: "We designed VOSS and implemented its scheduling policies. We evaluate them in a simulator whose start-up and attestation costs are measured on real hardware. The worker image, router and verifier are designed but not built."
- In design sections write the design ("a worker runs ...") and keep every sentence about the simulator out. Put all modelling in the methodology section under "What is modelled and how".
- Consider "design and simulation study" in the title or abstract. It costs prestige and buys trust.

## X2 (M) One party has six names; one word has two meanings
- The machine's owner: "owner", "volunteer", "donor", "host", "hostile owner", "malicious owner" ("volunteer owner" in the threat table, "paying donors" in receipts).
- The machine: "machine", "worker", "computer", "PC", "consumer laptop", "host", "volunteer nodes" (once, `method.tex`), "volunteer machine".
- The unit of work: "invocation", "request", "call", "work", "task", "job" ("requests successful", "accepted work", "running every task", "long asynchronous jobs").
- The environment: "environment", "sandbox", "microVM", "started environment".
- The tenant: "customer" (introduction), "tenant" (after).
- "provider" means the platform operator everywhere except here: "a second copy goes to the best worker in a different city or provider" (`scheduling.tex`), where it means internet provider.

Fix: one term per concept, fixed in a glossary table and enforced by grep.

| Concept | Use | Do not use |
|---|---|---|
| Person who lends the machine | owner | volunteer (as a noun for the person), donor, host |
| The machine while running the image | worker | node, host, PC |
| One call of a function | invocation | request (except "request rate"), task, job, work |
| Isolation unit | sandbox | environment, microVM (except when naming Firecracker) |
| Platform operator | provider | |
| Network operator | ISP | provider |

## X3 (M) The Terms paragraph is a 300-word run-in glossary, and half of it was already defined
> "\textbf{Terms.} A \emph{tenant} is a customer who deploys functions; an \emph{invocation} is one call of a function. An invocation is \emph{synchronous} when ..." (`background.tex`)

- Fourteen definitions in one paragraph. "tenant", "worker", "warm", "snapshot", "heartbeat", "idempotent" are defined in the introduction and again here; "heartbeat" a third time in Section 2.3; "epoch" twice (`network.tex`, `faulttol.tex`).
- A reader cannot find a definition later because none has a visual anchor.

Fix: a two-column table "Terms used in this paper" (term, one-line definition). Define in the introduction only what the introduction needs (worker, tenant, cold start, warm). Remove repeats.

## X4 (M) The methodology cannot be reproduced from the paper
> "Workers come in three classes (nightly, idle-hours, dedicated) with heavy-tailed session lengths and city-wide shocks" ... "The workload has six tenants and 12 functions modelled on SeBS" (`method.tex`)

- No table of the 12 functions (run time, memory, synchronous or not, idempotent or not, share of traffic). No table of worker classes (share of pool, session-length distribution and parameters, hardware). No definition of "medium" and "high" churn. No arrival-process parameters. The load of the main experiment is missing altogether (D2).
- The section is four bold-headed paragraphs of about 200 words each, with the simulator, calibration, statistics and reproducibility compressed into lists of clauses.

Fix: subsections with tables.
1. Simulated system (what is real code, what is modelled).
2. Workers: Table (class, share, session distribution, parameters, source).
3. Workload: Table (function, source benchmark, run time, memory, class, idempotent, traffic share).
4. Network model: Table (link speeds, delay model).
5. Calibration: Table (step, machine A, machine B, ...).
6. Systems compared: Table (policy, what it decides when, parameters).
7. Experiments: Table (name, purpose, workers, load, duration, warm-up, seeds).
8. Metrics and statistics.

## X5 (M) Two data figures and two result tables carry the whole evaluation
- Included: `fig_cost`, `fig_front`, `tab_round4_front`, `tab_rerun_viability`.
- Present in `figures/` and unused: `fig_ablation`, `fig_pareto`, `fig_scale`, `fig_viability`. Present in `generated/` and unused: 17 tables.
- Ablation, detection, architecture comparison, scale and session-length results are sentences with eight to twelve inline numbers each.

Fix: every claim in the abstract needs one figure or table. Minimum set: (1) deadline-met rate against number of key holders, all policies; (2) latency CDF for the main comparison; (3) time series of one tail episode (queue length and key holders over time, baseline vs provisioning), since the mechanism claim rests on it; (4) operating-region map (D7); (5) detection under droppers; (6) ablation bars; (7) calibration table across machines.

## X6 (M) Sentences that argue with an invisible reviewer (further instances)
> "Gaussian processes or regression trees would need more data and time than a millisecond decision allows." (`scheduling.tex`)

> "Removing the largest $f$ contributions is the worst case, so no model of an adversary is needed" (`scheduling.tex`)

> "Other mechanisms fall short: memory encryption alone attests nothing, voting over several copies triples the cost, and proofs that let a client verify a computation are far too slow for millisecond functions." (`trust.tex`)

> "This is a choice made for volunteer machines." (`background.tex`)

> "Each sandbox has one vCPU, as in our calibration and emulation" (`background.tex`)

- Each pre-empts an objection nobody on the page has raised. Three research areas are dismissed in one uncited sentence. "As in our calibration" justifies a model by the author's own tooling.
- These came from feedback rounds (the log shows the questions). The answer was pasted where the question was asked.

Fix: an alternative gets either a cited sentence in related work or nothing. A modelling choice gets a row in the assumptions table with its reason. Delete the rest.

## X7 (M) Results are narrated as a sequence of the authors' checks, not as findings
> "Three checks narrow the mechanism. First, in the seeds where provisioning's lead is largest, ..." (`results.tex`)

> "Plausibly provisioning's 60\,s look-ahead is short against sessions of hours, but we did not test this." (`results.tex`)

> "duplicating only at-risk invocations is cheap insurance that we could not show to be necessary" (`results.tex`)

- "First ... Second ... Third" reports what was done in order. The finding (tail episodes come from too few key holders while asynchronous work occupies them) is buried in the middle of the first.
- An untested speculation and a non-result are written as results.

Fix: one finding per paragraph, stated in its first sentence, then the evidence, then the figure reference. Example:
- "Tail latency under keep-alive comes from short episodes in which a tenant has too few key holders. [Figure: one episode.] In the 5 seeds with the largest gap, each baseline run contains one interval of 40-120 s in which ..."
Move speculation to Discussion, labelled as such, or delete.

## X8 (M) Discussion claims more than Results
> "These are statements about mechanisms, backed by paired intervals, and they hold across churn levels and adversary fractions." (`discussion.tex`)

> "Four expected benefits did not appear. ... A commercial-style datacenter reference is faster." (`discussion.tex`)

> "exposure would stop being a proxy for risk" (`discussion.tex`) vs "it is not a probability of compromise" (`design.tex`)

- "Across churn levels" is two levels. The sentence praises the paper's own evidence.
- Listing "the datacenter is faster" under expected benefits that did not appear says the authors expected to beat a datacenter.
- Exposure is called "not a probability" in Section 3 and "a proxy for risk" in Section 10.

Fix: Discussion answers three questions only: when does the result hold (conditions), why (mechanism, with the limits of the evidence), and what would change it. Remove evaluative sentences about the paper itself.

## X9 (M) The conclusion opens with a claim the results contradict
> "Serving short functions from volunteer machines needs more than keep-alive timers and repeated execution." (`conclusion.tex`)

> "every system meets a 3\,s P99 target" (`results.tex`)

- Keep-alive timers met the paper's own target in the main experiment.
- "the strongest keep-alive policies we could build" (twice: discussion, conclusion) signals doubt about the baselines in the last paragraph a reader sees.

Fix: conclude with the measured trade-off and its conditions. "we could build" goes; the baselines are either adequate (D4 fixed) or not.

## X10 (M) Thirty-six of 64 references print "TODO verify"
Evidence: `refs.bib` has 36 entries with `note = {TODO verify ...}`; ACM-Reference-Format prints the `note` field. `wallet2025` has no confirmed authors or title ("TODO verify authors and final title").

- The reference list of the submitted PDF would contain the words "TODO verify" 36 times.
- Several entries are cited for specific claims (trust-score values, CVM costs, edge two-timescale structure) that the author has not checked against the source.

Fix: verify each entry against the publisher page or DBLP; move the marker to a BibTeX comment or a custom field that is not printed; remove any reference that cannot be verified and the claim that depends on it.

## X11 (m) Inconsistent count of calibration machines
> "All results come from simulation and one calibration machine" (`intro.tex`)

> "both machines we calibrated report TME off" (`trust.tex`)

> "a second bare-metal host (Intel i7-12700, firmware TPM, NVMe) quotes in 0.19\,s" (`method.tex`)

> "Calibration comes from one laptop with a hard disk" (`discussion.tex`)

Fix: say "start-up costs from one laptop; TPM quote time also measured on a desktop" until the multi-machine calibration is done, then replace all four.

## X12 (m) Section labels were stacked during merges, so cross-references point at whole sections
Evidence: `scheduling.tex` opens with eight `\label`s on `\section{Scheduling}`; `method.tex` with five; `faulttol.tex` with three.

> "by a result missing its predicted completion time (Section~\ref{sec:receipts})" (`background.tex`)

- `sec:receipts` resolves to all of Section 7; `sec:estimators`, `sec:planner`, `sec:placer` all resolve to "Section 5". A reader sent to "Section 5" for the estimator has six subsections to search.

Fix: one label per heading, placed on the subsection it names.

## X13 (m) Metaphor in place of mechanism (further instances)
> "The scheduler charges each candidate worker the transfer time over its own link" (`background.tex`)

> "churn throws its result away whenever a session ends" (`intro.tex`)

> "or walk away at the worst moment" (`intro.tex`)

> "how a machine earns a certificate" (`trust.tex`)

> "is shut out" ... "stops on its own" ... "a reliable referee" (`faulttol.tex`)

> "all systems compared on a seed face the same world" (`method.tex`)

- "walk away at the worst moment" is also in the wrong list: it is churn, listed under distrust.

Fix: "adds the predicted transfer time to each candidate's completion estimate"; "an attestation is valid for one session"; "is rejected by workers (stale epoch)"; "the same sessions, arrivals and faults".

## X14 (m) Numbers with more precision than the model supports
> "\RerunCommPNinetynineAzureTwentyDiff--\RerunCommPNinetynineLambdaTwentyDiff\,s higher" [0.109-0.165 s] (abstract)

> "\VossSuccAlpha\%" [99.95%] ... "paired ratio \RfourHtwelveMedRatio{}" [0.793] (`results.tex`)

- Three significant digits from a simulator validated to within 6-23% at the median.

Fix: two significant digits at most, with the interval. In the abstract: "0.1-0.2 s".

## X15 (m) Undefined terms in the abstract
> "at about 2.5 times their key exposure" ... "keeps \VossSuccAlpha\% of requests successful" (abstract)

- "Key exposure" is defined in the introduction, not the abstract. "Successful" is never defined in the text (D6).

Fix: "while giving each tenant's key to 2.5 times as many machines"; "completes N% of invocations within their deadline".

## X16 (m) Long list-sentences with one subject and many verbs
> "The \emph{router} is the public entry point: it chooses a cluster for each invocation, sends the invocation's metadata ..., keeps a copy until ..., resends or redirects it if ..., streams the input ..., returns the result, and stores the worker's signed receipt." (`design.tex`)

> "Owners control hardware, power and network and may boot modified software, replay, drop or delay messages; network attackers may read and change traffic; tenants may run malicious code, which microVMs isolate" (`design.tex`)

Fix: a numbered request path keyed to the figure (the caption already numbers the steps; the text should use the same numbers), and the threat table instead of the second sentence.

## X17 (m) Captions that define what the figure should show
> Figure 1 caption: "\emph{Boot microVM}: Firecracker starts a microVM directly ... \emph{Restore snapshot}: ... \emph{Reboot to kernel}: ... \emph{Power-on to attested worker}: ... \emph{Warm cache}: ...; \emph{cold}: ..." (`background.tex`)

- A 110-word caption repairs unclear bar labels. "grey: model value" places an unmeasured value in a measurement figure.

Fix: redraw as a stacked horizontal bar per start path, segments labelled on the figure (firmware, boot loader, kernel, image start-up, TPM quote, verifier), one group per machine. Measured values only. Caption: one sentence.

## X18 (m) Table 2 ("How often the scheduler's inputs change") mixes two tables
> "Input or decision & Changes or lasts & Learned from" (`scheduling.tex`)

- Column headers with "or" in them. Three rows are inputs, three are decisions; the third column means "source" for the first group and "basis" for the second.

Fix: two small tables, or one with the columns "Decision", "Takes effect after", "Lasts", "Inputs needed".

## X19 (m) Note-form and duplicated lead-ins in Results
> "\textbf{Scale.} Scalability (E18, original placement): success stays at ..." (`results.tex`)

> "Baselines, feasibility and scale" (subsection heading for four unrelated experiments)

Fix: full sentences; one subsection per question.

## X20 (m) Grammar and small errors
- "Provisioning considers the live, non-leaving workers in its view (at most 40) **and at the** 20 tenants" (`scheduling.tex`): broken sentence.
- "a second copy goes to the best worker" (`scheduling.tex`): the introduction was rewritten to avoid "second copy" (feedback round 10); the body still uses it.
- "\textbf{Simple baseline.} The simple baseline combines ..." (`results.tex`): heading repeated as the subject.
- "It holds \GeoExpRatio{} times the key exposure of a global scheduler with \GeoClusters{} clusters in Europe" (`results.tex`): "It" has no antecedent (the previous sentence is about the global scheduler); "a global scheduler with 9 clusters" reads as if the global scheduler has clusters.
- "plan actions take from a few hundred milliseconds to several seconds, so the period must be longer, and sessions last minutes to hours, so it must be much shorter" (`scheduling.tex`): shorter than what?
- Mixed spelling: "minimises", "initialisation", "idealised" with "datacenter", "center". Pick one variety.
- Experiment hardware for timings is missing: "It takes about 8\,ms per run", "about 4\,s per cluster" (on what CPU?).

## X21 (m) Submission format
> "\documentclass[acmsmall,screen,review=false]{acmart}" ... "\setcopyright{none}" ... "\institution{\todo{institution}}" (`main.tex`)

- TOIT submissions use `manuscript,screen,review` (line numbers on). No acknowledgements, no artifact or data-availability statement although reproducibility is a claimed contribution. CCS concept "Networks~Network protocols" does not match the content once the broker is cut.

## X22 (m) Dead content
- "We model five [trust technologies]" (`trust.tex`); the results use one. Confidential-VM scores, literature costs and four citations support nothing in the evaluation shown.
- "filler" invocations: defined, scheduled, never measured.
- Receipts: three sentences, no experiment in the paper.
- "Clusters and routing": three sentences on a design the paper rejects.

Fix: cut each, or give it a result. A journal paper may be long, but every described mechanism should be evaluated or removed.

## X23 (m) Remaining stylistic tics (counts over `sections/`)
- "only": 44. "about": 34. "rather than": 10. ", not": 10. Sentences opening with "And" or "So": 8.
- Colon-then-explanation sentences in nearly every paragraph ("Trust is perishable: it lasts ...", "The argument is short. ...").
- Anthropomorphic verbs for the system: "judges", "judging" (9), "suspects", "believes", "expects".

Fix: search each and rewrite half. "Judging workers by returned work" becomes "outcome-based failure detection" as a term, defined once.
