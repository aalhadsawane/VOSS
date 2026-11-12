# Fable Paper Review 4: structure, writing, style

Format per item: quote, problem, fix. Severity: **F** fatal, **M** major, **m** minor.

## S. Structure

### S1 (F) Two sections say the same thing, with the same labels, and disagree
> "\textbf{Property 1.} Under these assumptions, everything a worker or scheduler machine does ..." (`design.tex`) and again verbatim (`trust.tex`)

> "We limit it even though attested workers are honest for two reasons." (`design.tex`) vs "why limit exposure at all? Three reasons." (`trust.tex`)

- `main.tex` inputs both `sections/design` and `sections/trust`. Threat model, Property 1, key release and key exposure each appear twice. Labels `sec:trust`, `sec:threat`, `sec:exposure`, `sec:provisioning`, `sec:substrates` are defined twice, so cross-references resolve arbitrarily.
- `trust.tex` opens "This section states the claim and its limits" right after the previous section stated them.
- Fix: keep one. Merge the threat table and the attestation exchange into `design.tex`, delete the rest.

### S2 (F) Unfinished-draft markers in the body
> "\critical{calibration covers one laptop with a hard disk ...}" (`intro.tex`), "\critical{redraw as a per-step breakdown ...}" (`background.tex`), "\potrem{cost analysis; removed from the abstract}" (`results.tex`), "\institution{\todo{institution}}" (`main.tex`)

- Not submittable. Each marks real missing work (E2, A2).

### S3 (M) The title uses a phrase the paper never uses
> "VOSS: Scheduling Attested Session State for Serverless Computing on Volunteer Machines" (`main.tex`)

- "Attested session state" appears nowhere in the body. "VOSS" is never expanded.
- Fix: title from the paper's vocabulary, e.g. "Provisioning keys and warm sandboxes for serverless functions on attested volunteer machines".

### S4 (M) The abstract advertises what the paper refutes
> "runs schedulers on volunteer machines reached through a publish/subscribe broker, replacing failed ones without agreement among volunteers" (abstract)

- The body finds this design slower and 5x more exposed (B1). The abstract omits that finding (it is in the introduction).
- The system sentence is one 75-word sentence with five verbs and an unreadable clause: "provisions keys and warm environments on workers with spare capacity for those that disappear".
- Fix: three sentences: what is provisioned; how failures are detected; headline numbers with the exposure cost.

### S5 (M) Related work is 300 words for a journal
> `related.tex` (four paragraphs)

- TOIT expects a positioned survey. Missing bodies of work: volunteer/edge clouds (Nebula, Cloud@Home, desktop grids, HTCondor); decentralised compute markets with TEEs (iExec, Golem, Akash); confidential FaaS beyond three citations (S-FaaS, Clemmys); cold-start prediction and autoscaling (Knative, IceBreaker); fail-slow and observation-based detection (Panorama, IASO); late-launch attestation (Flicker, TrustVisor) for the "hypervisor under the owner's OS" option; TPM attacks on consumer hardware.
- "All assume trusted machines that stay up" is false for the harvest-VM work cited two paragraphs later.
- Fix: 1.5-2 pages, one comparison table (system x churn x untrusted host x deadline class x key management).

### S6 (M) No formal problem statement, no algorithm listing
> "Subject to this, provisioning minimises the memory and disk the plan uses, key exposure, and the number of new key releases, minus the start-up time that warm sandboxes save." (`scheduling.tex`)

- The core optimisation is prose. Greedy provisioning is one paragraph. A reader cannot reimplement it.
- Fix: notation table, the optimisation problem, Algorithm 1 (greedy provisioning), Algorithm 2 (placement).

### S7 (M) Background is 1,800 words, much of it defence of modelling choices
> "We do not overcommit the CPU. ... This is a choice made for volunteer machines. ..." (`background.tex`, 180 words)

> "Such short deadlines match what developers use: AWS Lambda's default timeout is 3\,s ... (90 minutes for asynchronous and event-source invocations on Lambda Managed Instances)" (`background.tex`)

- These paragraphs read as answers to questions put to the author, inserted where the question arose. A reviewer reading top to bottom meets a defence before knowing what is being defended.
- Lambda's default timeout is cited three times (introduction, twice in background). A configuration default is not evidence that functions "are expected to finish in seconds"; the next sentence concedes "A timeout stops the function and a deadline is a latency target".
- Fix: background = terms, cost breakdown, failure model, problem statement. Move capacity-model justifications to the method section's assumptions table. State the Lambda default once or not at all.

### S8 (m) Section 6 is a 400-word section for a transport choice; Section 7 is three bold paragraphs
- Fix: fold both into the design section (or delete with B1).

### S9 (m) Introduction, discussion and conclusion each restate the results
> "In simulation, provisioning lowers ..." (`intro.tex`), "\textbf{What the evidence supports.} ..." (`discussion.tex`), "Against the strongest keep-alive policies we could build ..." (`conclusion.tex`)

- Same numbers four times including the abstract. No roadmap paragraph in the introduction.
- Fix: discussion should interpret (why, when it breaks), not re-list.

### S10 (m) Table of donated shares adds nothing
> "CPU threads & 0.75 & assumed \\ Memory & 0.6 & assumed \\ SSD & 0.2 & assumed \\ Hard disk & 0.2 & assumed" (`method.tex`)

- Four constants, all "assumed", in a float. Replace with one table of *all* assumed constants (B10).

## W. Writing

### W1 (M) Lab-notebook identifiers leak into the paper
> "(E04b; 10 seeds for the exact program)", "(E19, original placement)", "(E10b, corrected placement)", "(E24b)", "(E17b)", "(E20ab, corrected placement)", "(H12 supported)", "(H15, weak)", "for the round of provisioning comparisons (H12--H16)", "with placeholders", "For the shipped worker classes"

- A reader has no key for E-numbers, `b` suffixes or H-numbers (the scorecard is not even included, E13). "Round", "rerun", "placeholders", "shipped" describe the project's history.
- Fix: refer to experiments by table/figure number. Delete H-numbers or list hypotheses in one included table.

### W2 (M) Rhetorical questions and answers to an absent questioner
> "If attested machines are honest, why limit exposure at all? Three reasons." (`trust.tex`)

> "What part of this is provisioning, and what is merely holding keys?" (`results.tex`)

> "Compute is not why the scheduler runs on a volunteer machine:" (`network.tex`)

> "A blockchain would protect against no adversary here" (`trust.tex`) and "a blockchain would add nothing, since anyone can check a signed receipt" (`faulttol.tex`)

- Each reads as a reply in a conversation. Nobody in the paper proposed a blockchain; rebutting it twice is absurd to a cold reader. Nobody claimed compute was the reason.
- Fix: state the claim directly ("We bound exposure because ..."). Delete both blockchain sentences.

### W3 (M) Question-style and chatty headings
> "How We Evaluate", "Where the time goes", "What each part minimises", "Is provisioning needed?", "Where the gain comes from", "What the evidence supports." / "What it does not.", "Threat model and what attestation buys"

- Blog register. Fix: "Evaluation Methodology", "Start-up Cost Breakdown", "Objectives", "Provisioning versus Keep-alive", "Sources of the Improvement", "Summary of Findings".

### W4 (M) Process narrative instead of results
> "Before any experiment we fixed a rule: if the exact program lowered P99 by less than 5\% in every setting, greedy would be the method. The data could not show this" (`scheduling.tex`)

> "On a homogeneous, stable pool we expected it to match \voss{} ...; it does not." (`results.tex`)

> "Two things we believed about provisioning did not survive its own experiments." (`discussion.tex`)

> "We also derived a provisioning algorithm with more structure." (`scheduling.tex`)

> "\textbf{A placement defect, corrected late.}" (`discussion.tex`)

- The author's own style guide forbids "narrative about how we got here". These are diary entries. "The data could not show this" is also unclear (show what?).
- Fix: report the comparison and its interval. Remove beliefs, expectations and rules fixed in advance.

### W5 (M) Aphorisms and slogan sentences (the main "generated text" tell)
> "Trust costs thousands of times more than reuse" (`background.tex`)

> "What the owner keeps is the power switch and the network cable" (`intro.tex`)

> "Exposure is the price of latency." (`discussion.tex`)

> "an attested machine can stop but not lie" (`related.tex`)

> "The argument is short." ... "What remains is the power switch, the network path, and the choice of when to stop answering." (`trust.tex`)

> "It buys spare capacity on many holders rather than a few durable ones." (`results.tex`)

> "it buys tail latency, not success" (`results.tex`)

- Short balanced "X, not Y" sentences, triads and metaphor ("buys", "price", "earns a certificate", "referee", "walk away at the worst moment") recur every few paragraphs. "Trust costs ..." compares a duration to an abstract noun. "What remains is" was already rejected by the author in round 6 and is back in `trust.tex`.
- Fix: replace each with the literal statement and number ("Power-on to attested takes 65 s; dispatch to a warm sandbox takes N ms").

### W6 (M) Coined or undefined terms, several used once
| Term | Where | Problem |
|---|---|---|
| "filler" invocations | `background.tex` | Defined, given scheduling rules, never appears in the evaluation. |
| "domain caps" | `scheduling.tex` | Undefined, used once. |
| "robust cover" | `results.tex` | Undefined, used once; elsewhere "the cover against losing $f$ workers". |
| "the front" | `results.tex`, `discussion.tex` | Pareto front never introduced. |
| "perishable" | `trust.tex` | Coined, italicised, used once. |
| "trust technology", "trust score", "trust floor" | several | Three coined terms; "trust floor" appears once, earlier called "minimum trust score". |
| "start-up levels" | several | Coined; "cache tier" or "sandbox state" are established. |
| "relayed end" | `network.tex` | Undefined. |
| "reference machine" | `background.tex` | Never identified. |
| "referee" | `faulttol.tex` | Metaphor for coordinator. |
| "Cost-aware caching and the reliability score" | `discussion.tex` | Neither is mentioned anywhere before this sentence. |
| "exposure units", "exposure term" | `results.tex` | Unit of an undefined scale (C5). |
| "early keys" | several | Baseline name that needs its definition every time; "pre-released keys". |
| "provisioned" | `trust.tex` | Redefined as "holds the tenant's key", clashing with "provisioning" = keys + warm sandboxes + reserved concurrency. |
| "feasible" | `method.tex` | Private definition with an "or" in it ("its share of deadlines met, or its P99, meets a target"). |

- Fix: delete single-use terms; use one name per concept; define "key holders" and use it throughout.

### W7 (M) The banned terminology is still in the text
> "plan actions take ...", "greedy planning for $10^5$ workers", "removed from the plan", "and plans again", "depend on the plan", "The difference to the previous plan becomes actions" (`scheduling.tex`, `network.tex`, `faulttol.tex`)

- The author's decision (feedback round 8) was "provisioning", never "planner/plan". The rename was partial.
- Fix: grep `plan` across `sections/`.

### W8 (m) Odd, indirect or over-technical framing
> "A decision that outlasts the refresh period of its inputs has to be made from a forecast, ahead of time." (`scheduling.tex`)

- Abstract framing of a simple point. Direct: "Releasing a key takes seconds and lasts a session, so it must be done before requests arrive."

> "We minimise each invocation's own miss probability rather than P99 because P99 describes many invocations together and cannot be assigned to one decision." (`scheduling.tex`)

- Explains the obvious; reads as an answer to "why not minimise P99?".

> "The wait for the concurrency limit needs care." (`scheduling.tex`)

- Empty opener. Start with the mechanism.

> "Four small estimators turn past outcomes into the numbers above; for each we say what it predicts and why we chose it." (`scheduling.tex`)

- Signposting sentence about the text itself. Delete.

> "everything a worker or scheduler machine does that others can observe, and that its owner can cause through software, is a crash, a dropped message or a delayed message" (`design.tex`)

- A "Property" should be a checkable statement. "through software" contradicts the mechanism: the owner drops messages through the network and power, not software. Rewrite: "An attested worker deviates from the protocol only by omission or timing faults."

> "The design rests on one claim: attestation turns a hostile owner into an unreliable one." (`trust.tex`)

- Same sentence as abstract and introduction, third time.

### W9 (m) Overloaded and hedge-heavy result sentences
> "at shape 1.0 it peaks at mean length and exceeds the longest sessions' by \RfourEtwentyfiveKoneAdiffFour{} [...], but the same comparison to the shortest sessions is not distinguishable from zero" (`results.tex`)

> "which excludes 1 but not our 5\% threshold (H15, weak)" (`results.tex`)

- Unreadable without the table (which is absent). Fix: a small table for the session-length sweep; one sentence of conclusion.

### W10 (m) Numbers without a visible source
> "making placement ignore start-up levels costs \AblLifecycleP\,s of P99, removing provisioning \AblPlanningP\,s ..." (`results.tex`)

- Ablation, detection, geographic and scale results are prose only; their tables exist in `generated/` and are not included. `tab_ablation.tex` still has internal row names ("lifecycle", "reputation\_in\_cost", "hdd" with all zeros).
- Fix: include one cleaned ablation table and one detection table.

### W11 (m) Vague quantifiers in headline claims
> "about 2.5 times", "about \RfourDecompGreedyMed\%", "about 30", "about 100 cities", "about 30\,Mbit/s", "about one processor core", "about 0.46\,KB/s"

- "About" appears on most numbers, including macro-generated exact values. Give the value and interval.

### W12 (m) Inconsistent subject of the paper
> "We present \voss{}, a scheduler for this setting." (`intro.tex`) vs "The \voss{} architecture" (router, verifier, registry, broker; `design.tex`) vs "an evaluation of provisioning algorithms and deployments" (feedback round 4)

- Scheduler, platform, or evaluation study? The contributions list mixes all three.
- Fix: choose. Given the null results (B8) and the refuted deployment (B1), the honest framing is an evaluation study with one positive finding (number of key holders) and one detector.

## Unresolved items from `HUMAN_FEEDBACK.md` that a reviewer will also hit
- Multi-machine calibration (CRITICAL since round 9): still one laptop (E2).
- Per-step Figure 1 redraw (round 10): not done; the 13 s gap between "agent ready" and "verifier accepted" is unexplained.
- Cost analysis (round 6): still in the text with a red marker (E15).
- "stop or delay" (round 6): still in the threat table (C12).
- "What remains is" (round 6): reintroduced in `trust.tex` (W5).
- Concurrency limit vs cores (rounds 14-15): hyperthreads counted with an assumed 1.1x slowdown (C13).
- 30 s period (round 1): no longer in the abstract, but the body now narrates "We did not sweep the 30\,s period" (B10).
- "The paper spends so much length on two deployments, yet the results favour one" (round 4): still true (B1).

## Minimum to reach "major revision" instead of "reject"
1. One deployment model and one motivation that the results support (A1-A3, B1).
2. Property 1 restated truthfully; abstract fixed (C1, C3).
3. Equal-exposure comparison with the missing baselines (B6, B7, E7).
4. All experiments on one implementation, 24 h runs, trace-driven churn and workload (E3, E5, E6).
5. Deadline-met rate as the primary metric; success defined (C9, E9).
6. A real multi-machine measurement, however small (E1, E2).
7. One trust section, no red markers, no E/H identifiers (S1, S2, W1).
