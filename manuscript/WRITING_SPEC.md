# Writing specification for the v2 manuscript

**Binding for every sentence of the v2 paper.** Sources: the author's feedback log (`HUMAN_FEEDBACK.md`, rounds 1-20, style
profile, heuristics 1-30), the reviews (`reviews/FABLE_PAPER_REVIEW_4` W1-W12 and `_6` X1-X23), and the v2 design
(`docs/REVISION_PLAN.md` §2).

The abstract, introduction and background were read and corrected by the author over twenty rounds. v2 changes their content
completely, so the text cannot be kept, but **every lesson from those rounds must hold in the new text**. §6 lists one check per
round. A draft that fails a check is not finished.

---

## 1. Reader and voice (from the author's style profile)

- **Reader:** a reviewer with a systems background and no serverless knowledge, reading cold. Every term must be understandable
  from the page.
- **Direct and literal.** Say what the system does or what was measured, in the plainest words an engineer would use.
  "The invocation also runs on a second worker and the first result is used", not "sends a second copy".
- **Established terms only.** No coined labels. If the literature has a word, use it; otherwise describe the thing.
- **Concrete over generic.** "Functions execute for well under a second", not "the useful work is small".
- **Every sentence states something checkable.** No filler, no connective sentences, no slogans, no rhetorical questions.
- **Technical-report register.** No story of how the work went, no beliefs or expectations, no replies to imagined objections.
- **Mechanism-accurate.** Do not claim what cannot be explained. Do not "fix" wording that is accurate.
- **One idea per sentence. Define a term before using it.** A definition says what the thing is and does, not what it resembles.
- **A paragraph's first sentence says specifically what the paragraph establishes.**

## 2. Process for every section

1. **Outline first.** One line per paragraph: the claim it makes and the evidence (figure, table, citation, design fact).
   Commit the outline before writing prose.
2. **Draft** from the outline using only terms from §4.
3. **Fact-check** every claim against the generated macros, `docs/PARAMETERS.md`, and the code. Numbers come only from
   `generated/macros.tex`. If the data disagree with the outline, change the outline and say so in the commit message.
4. **Cold-reader pass.** Reread as the reader of §1. For each sentence ask: is every term defined above this point? could a
   reviewer ask "what does this mean" or "how"? is this a reply to a question nobody on the page asked? Fix, then repeat once.
5. **Tests:** `make manuscript-check` (forbidden terms §4.2, patterns §5, no red markers, every figure and table referenced,
   every abstract number is a macro).
6. **Open problems stay visible** for the author: `\critical{...}` in the working PDF, removed only when resolved. Never in a
   submitted PDF.
7. **Author's read.** The abstract, introduction and background go to the author before the rest is polished. Log the
   response as a new round in `HUMAN_FEEDBACK.md` (request, what was done, lesson) and extend §6 with its check.

## 3. Paper structure

| # | Section | Must contain | Must not contain |
|---|---|---|---|
| — | Abstract | §7.1 | parameters, internal comparisons, calibration details, process |
| 1 | Introduction | §7.2 | serverless-specific words without a gloss; history of the project |
| 2 | Background and problem | §7.3 | defence of modelling choices; the simulator |
| 3 | Trust model | owner classes S, P, M (table); attestation exchange (figure); keys, rotation, holder budget; what a tenant must trust; sampled audit; limits (firmware reference values, runtime compromise) | "Property" claims without the owner class |
| 4 | Architecture and scheduler | components and request path numbered to the figure; provisioning (problem statement, Algorithm 1); request placement (Algorithm 2); failure handling; constants table generated from `docs/PARAMETERS.md` | any sentence about the simulator or experiments |
| 5 | Methodology | what is real code and what is modelled; machines and calibration (spec table, per-step table); traces and splits; network data; systems compared (source, deviations); experiments table (workers, load, utilisation, duration, warm-up, bundles, split, seeds); metrics with estimators; validation against the emulation | results |
| 6 | Results | one subsection per question; first sentence is the finding; then evidence; then the figure | process narrative, speculation, experiment codes |
| 7 | Discussion and limitations | when the results hold, why, what would change them; limitations as plain statements | praise of the paper's own evidence |
| 8 | Related work | 1.5-2 pages, comparison table; serverless keep-alive and autoscaling; edge serverless; harvested and spot capacity; volunteer and desktop-grid computing; confidential serverless; attestation on consumer machines and its attacks; failure detection from request outcomes | one-sentence dismissals without citation |
| 9 | Conclusion | what was built, what was measured, where it stops working | "the strongest we could build", future-work lists longer than two sentences |
| A | Appendix | every remaining grid cell; reproduction instructions | — |

Title: uses only words the paper defines. Working title: "VOSS: Serverless Functions on Attested Volunteer Machines".
State what "VOSS" stands for once, or state that it is a name.

## 4. Vocabulary

### 4.1 Glossary (one word per thing; the Terms table in the background section is generated from this list)

| Term | Meaning | Never write |
|---|---|---|
| function | a piece of tenant code run on request | — |
| invocation | one call of a function | task, job, work; "request" only in "request rate" and for the client's HTTP request |
| synchronous / asynchronous invocation | the client waits for the result / the result is delivered later | sync, async in prose; filler |
| tenant | a customer who deploys functions | customer (after the first definition) |
| provider | the organisation that runs the platform | — |
| owner | the person or organisation that lends a machine | donor, volunteer (for the person), host |
| volunteer machine | a machine lent by an owner | node, PC, box, donated machine |
| worker | a volunteer machine while it runs the VOSS image | node, host |
| session | from a worker's attestation until its owner takes the machine back | donation session |
| sandbox | the isolated environment one invocation runs in (here a Firecracker microVM) | environment, container (unless meant), VM for the worker itself |
| warm sandbox | started and idle, ready for an invocation | hot, pre-warmed instance |
| snapshot | memory and processor state of a sandbox written to disk | checkpoint |
| cold start | the delay to prepare a sandbox before a function executes | — |
| keep-alive | keeping a sandbox for some time after an invocation | — |
| deadline | time by which a synchronous invocation's result must reach the client | SLO, timeout (a timeout is the scheduler's per-attempt timer) |
| remote attestation, quote, verifier | standard meanings, defined once | — |
| function key | the key that decrypts one function's code and snapshots | tenant key (unless the root key is meant), secret |
| key holder | a worker that currently holds a function key | trusted worker, provisioned worker |
| holder budget | the largest number of key holders a tenant allows for a function | exposure, exposure budget, trust score |
| provisioning | the periodic choice of key holders, warm sandboxes and reserved concurrency | planner, planning, plan, slow loop |
| request placement | the choice of a worker for one invocation | fast loop, routing (routing is the router's forwarding) |
| concurrency limit | invocations a worker runs at once | slots |
| backup attempt | running an invocation on a second worker after the first attempt's timeout | hedge, duplicate, second copy |
| owner who drops work / who forges results | plain descriptions | Byzantine (unless citing), gray failure (cite once, then describe) |
| sampled audit | re-running a fraction of invocations on another worker and comparing results | spot check, voting |
| ISP | the worker's internet provider | provider (reserved for the platform) |
| deadlines met | share of synchronous invocations answered correctly within their deadline | success, success rate, goodput |

### 4.2 Forbidden in `sections/*.tex` (enforced by test; case-insensitive)
- v1 vocabulary: `planner`, `slow loop`, `fast loop`, `single-loop`, `two-timescale` (except inside a citation sentence), `slot`,
  `exposure`, `trust score`, `trust technology`, `start-up level` (write "state of the function on the worker"), `filler`,
  `early keys`, `perishable`, `referee`, `the front`, `judg` (judge, judging), `returned work`, `second copy`, `hedg`,
  `cluster` (except "computer cluster" in citations), `broker`, `blockchain`.
- Project internals: `E\d\d[a-z]*`, `H\d+`, `R\d\d` as experiment names, `round`, `rerun`, `placeholder`, `shipped`,
  `corrected placement`, `original placement`, `pre-registered`, `frozen`, `the world` (for the simulated environment).
- Vendor names for our own models: `Lambda-like`, `Azure-like`.
- Draft markers in a submission build: `\critical`, `\potrem`, `\todo`, `TODO`.

## 5. Sentence patterns to remove (each with the fix)

| Pattern | Example from v1 | Write instead |
|---|---|---|
| Rhetorical question | "If attested machines are honest, why limit exposure at all?" | "We bound the number of key holders because …" |
| Reply to an absent objection | "Compute is not why the scheduler runs on a volunteer machine" | delete, or state the design reason positively |
| Slogan or aphorism | "Trust costs thousands of times more than reuse"; "Exposure is the price of latency." | the two numbers and what they measure |
| "X, not Y" as rhetoric | "it buys tail latency, not success" | "it lowers P99 by N s and leaves deadlines met unchanged" |
| Metaphor | "churn throws its result away"; "earns a certificate"; "buys", "charges", "walks away" | the literal event: "an attestation is valid for one session" |
| Vague opener | "What attestation does not remove is cost"; "The wait … needs care." | the specific claim of the paragraph |
| Signpost about the text | "for each we say what it predicts and why we chose it"; "The argument is short." | delete |
| Process narrative | "Before any experiment we fixed a rule"; "we expected … it does not" | the comparison and its interval |
| Belief or speculation in Results | "Plausibly … but we did not test this" | delete, or one labelled sentence in Discussion |
| Self-assessment | "These are statements about mechanisms, backed by paired intervals" | delete |
| Hedged strength | "the strongest baselines we could build" | name the baselines and their sources |
| "about" on generated numbers | "about 21%" | the number and its interval |
| Sentence opening with "And" or "So" | — | join to the previous sentence or delete the conjunction |
| Colon followed by an explanation, repeatedly | "Trust is perishable: it lasts …" | two plain sentences, or one |
| Quoted colloquial speech | "I am running" | the formal term, defined once |
| Vague size or comparison in a definition | "a small virtual machine"; "restores faster than a sandbox boots" | what it contains and does |
| A number without what it measures and where | "65 s" | "N s from power-on until the worker is attested, on machine X (Section 5)" |
| Justifying a choice by our own tooling | "as in our calibration and emulation" | the design reason, or a row in the constants table |
| Anthropomorphic system verbs | "judges", "believes", "suspects" (as prose) | "marks as failed", "estimates", "stops assigning invocations to" |

## 6. Feedback regression checklist (one check per round of `HUMAN_FEEDBACK.md`)

Run this list against the abstract, introduction and background before they go to the author, and again before submission.

| Round | What the author objected to | Check for the v2 text |
|---|---|---|
| 1 | odd context-setting opening; arbitrary 30 s in the abstract; structure assumed known | The abstract's first sentence says plainly: serverless on volunteered machines. No tunable constant in the abstract. Nothing depends on a component not yet introduced. |
| 2 | "ahead of demand" was inaccurate | Describe provisioning by what it uses (request rates and departures over minutes) and what it decides. Check the wording against §4 of the paper before using it in the front matter. |
| 3 | "slow planner": engineered term | No coined component names. Components are named by what they do. |
| 4 | "calibrated on a laptop" confused; length spent on what the results did not favour | The abstract says "simulator calibrated on N machines" at most. Length follows findings: nothing the results do not support gets a paragraph. |
| 5 | abstract too long; internal comparisons | Abstract: problem, architecture and scheduler, headline results against established baselines. ≤ 170 words. |
| 6 | "stop or delay": how would an owner delay?; "What remains…"; cost claim | State owner capabilities by mechanism: switch the machine off, or drop or hold back its network messages. No "What remains". No cost claim. |
| 7 | is withholding the same as crashing? | Keep the distinction explicit once: a crash stops everything including liveness messages; an owner who drops messages leaves the machine attested and reachable while results do not arrive. |
| 8 | generic phrases; cold start definition; "hide"; abrupt transitions; first number unexplained; why a key is needed; "slots"; contributions listed tools and history | Cold start = prepare a sandbox, fetch code, load runtime and libraries, run initialisation; it precedes execution. Keep-alive defined. First number says what it measures, on which machine, with a section pointer. One clause on why a worker needs a key. Contributions are what was built and found; attestation is the premise. No project history. |
| 9 | one machine is one data point | Every measured cost names its machine or gives the range over the calibrated machines; the spec table exists. |
| 10 | Figure 1 unclear; "The two feed on each other"; "second copy" | The start-up figure shows every step named in the text, with self-explanatory labels and a one-sentence caption. No filler sentence. Backup attempts described literally. |
| 11 | quoted "I am running"; vague opener "cost" | "Periodic liveness messages (heartbeats)". The three-things paragraph opens with the specific claim and enumerates in order. |
| 12 | sandbox defined as "a small virtual machine"; snapshot definition by comparison; key and snapshot confusion | Sandbox = isolated environment; then our choice (microVM) and its reason. Snapshot = memory and processor state on disk. Say why snapshots are encrypted (they contain data the function handled). |
| 13 | "slot" in the introduction | The introduction uses no serverless-specific word without a gloss. Check every term against the reader of §1. |
| 14-16 | slots were not cores; capacity model | State the capacity model once, from the code: concurrency limit = physical cores, one vCPU per sandbox, measured co-run slowdown, memory admission. One table. No repeated values in prose. |
| 17 | "we do not overcommit" needed a reason | A choice that departs from common practice comes with its reason from the design. In v2 the reason is measured slowdown; state it with the number. |
| 18 | start-up states read as obvious | Name the familiar datacenter arrangement first (remote store, zone cache, host cache), then what differs here, then our states. |
| 19 | where deadlines come from; first invocation; arbitrary multiple | Say who sets the deadline, what the scheduler is told and what it estimates, and that the multiple is an axis of the evaluation. |
| 20 | section read as a fact dump; "filler" undefined; reply-to-reviewer tone | Each sentence follows from the section's question. Why an outside fact matters comes before the fact. Limits of the method are stated in the limitations section as statements. |

Things the author **praised** and that must survive in spirit:
- the introduction that defines every term at first use, states the premise instead of listing it as a contribution, names
  components by what they do, and contains no history (round 10: "looks amazing");
- the opening sequence: what serverless functions are, how short they are, what a cold start is, how providers avoid it;
- "Before a volunteer machine can run a tenant's function, three things must happen, and each takes time", followed by the
  three in order with measured numbers.

## 7. Outlines for the sections the author reviewed

Write these outlines into the section files as comments first. Numbers are macros; `N` below marks where one goes.

### 7.1 Abstract (≤ 170 words, 6-7 sentences, one paragraph)
1. *What we study.* Serverless functions that must finish within seconds, on volunteered home and office machines.
2. *Why it is hard.* An owner can switch a machine off at any time, and cannot be trusted with the code and data it runs.
3. *Premise, by mechanism.* Each worker boots a measured image and proves it by remote attestation before it receives a
   function's decryption key; an owner who does not physically attack the machine can then only switch it off or drop its
   messages.
4. *What we built.* VOSS: an architecture and a scheduler that (a) keeps each function's key and warm sandboxes on enough
   workers to survive departures, within a limit the tenant sets on how many machines may hold the key, (b) places each
   invocation by its chance of meeting its deadline, (c) re-runs an invocation on a second worker when the first does not
   answer in time.
5. *Headline result against established policies* (from `docs/REVISION_PLAN.md` V12.4): deadlines met at a stated holder
   limit, VOSS versus the best of keep-alive, histogram and autoscaling policies.
6. *Failure result*, if supported: deadlines met when N% of owners drop work, versus timeout-and-eject detection.
7. *Basis.* Simulator driven by public traces, calibrated on N machines, checked against an N-worker emulation.
Not in the abstract: constants, the exact solver, ablations, cost, the owner-class taxonomy, experiment sizes.

### 7.2 Introduction (5-6 paragraphs, about 1.2 pages)
- **P1 Serverless and the cold start** (keep the approved sequence). Functions; they run for well under a second (cite);
  before one runs the platform prepares a sandbox (define in a clause), fetches code, loads runtime and libraries, runs
  initialisation: the cold start, often longer than the execution; providers keep sandboxes alive and start them ahead of
  demand on machines they own. One sentence: edge platforms run functions in many cities, also on provider-owned machines.
  Last sentence: we ask whether machines the provider does not own can serve such invocations.
- **P2 The setting.** Millions of home and office machines are idle for hours; volunteer computing has used them for batch
  work with deadlines of hours (cite). An owner lends a machine by booting our image for a session. Define worker, tenant.
- **P3 Two problems, stated by mechanism.** Departures: the owner takes the machine back at any time and everything prepared
  on it is gone. Distrust: the owner controls the hardware. Then what existing work does not cover, one sentence each with a
  citation: volunteer computing replicates every task; serverless schedulers assume machines that stay; confidential computing
  assumes provider servers.
- **P4 Premise.** Remote attestation, in one sentence each: what is proved, what the owner can still do (switch off; drop or hold
  back messages while the machine stays attested), and the limit (an owner who physically reads memory; we handle integrity for
  that case by re-running a sample of invocations elsewhere).
- **P5 What it takes before a worker can run a function** (the approved "three things" paragraph, with v2 numbers): boot and
  attest (N-N s across our machines, Section 5); obtain the function's key (why a key: code and snapshots are encrypted so the
  provider stores only ciphertext); start a sandbox. All lost when the session ends. Each key holder is one more machine the
  key could leak from, so the tenant limits their number.
- **P6 VOSS.** Architecture in two sentences (provider runs routers, one scheduler, verifier and registry; workers connect
  outward; the provider never holds keys or reads requests). Scheduler in three sentences (provisioning; request placement;
  backup attempts and removing workers that drop work). Then contributions as a short list, each self-explanatory:
  (1) the architecture; (2) the scheduler; (3) an evaluation on public traces with measured costs, showing N. Then the main
  numbers, and one sentence on what is simulated and what is measured. No roadmap paragraph longer than one sentence.

### 7.3 Background and problem (about 1.5 pages)
- **Terms** as a table (generated from §4.1), not a paragraph. The text around it defines only relationships the table cannot.
- **2.1 What starting a function costs.** First the familiar datacenter picture (function images in a storage hierarchy;
  cite), then what differs on a volunteer machine (no shared tier; ciphertext only at the provider; snapshots stay on the
  worker), then the states a function can be in on one worker (nothing; code on disk; snapshot on disk; warm sandbox) with
  measured times per machine. Figure: stacked per-step bars for power-on → attested worker, sandbox boot, snapshot restore, per
  machine; labels readable without the caption.
- **2.2 Remote attestation in brief.** What a TPM quote is, what the verifier checks, what the key service does; what
  attestation does not give (it lasts one boot; it does not show the machine keeps working; it does not protect memory from a
  physical attacker).
- **2.3 How volunteer machines fail.** Sessions and how they end (from the trace: lengths, time of day); crash, dropped
  result, late result; why liveness messages do not detect dropped results. Why this matters: each synchronous invocation has a
  deadline set by the tenant; state who sets it and what the scheduler knows; a failure must be found and repaired within that
  deadline. Retrying requires that the function may safely run twice; the tenant declares this per function.
- **2.4 Capacity of a worker.** One paragraph and one table: concurrency limit, memory, measured co-run slowdown.
- **2.5 Problem statement.** What the scheduler decides, the goals in measurable terms (deadlines met; key holders within the
  tenant's limit; no result accepted from a worker that forged one, up to the audit's detection probability).
No sentence in this section defends a choice; reasons that need more than a clause go to Section 4 or the limitations.

## 8. Figures, tables, numbers

- A figure shows every step the text claims, with labels that define themselves; captions are one or two sentences.
- Measured and modelled values never share a figure without distinct marking; prefer measured only.
- Every experiment's caption or first sentence carries: workers, load or utilisation, duration, trace split, machines' bundles.
- Two significant digits with a 95% interval; no more precision than the validation supports.
- Each parameter value appears once, in the constants table.
- Each claim in the abstract has a figure or table in Results.

## 9. Honesty statements that must appear

- Introduction and methodology: what is real (scheduler code, worker image, measured costs, emulation) and what is simulated
  (network, sessions, scale).
- Trust section: which owner class each guarantee holds for; what a tenant must trust (the provider's image and verifier).
- Methodology: every deviation of a baseline from its published form; the development and held-out splits; any bug fix made
  after the freeze.
- Limitations: what the availability trace does and does not represent; idempotence as a tenant declaration; one scheduler's
  measured limit.
