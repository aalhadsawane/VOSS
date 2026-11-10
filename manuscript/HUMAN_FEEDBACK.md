# Human feedback log

**Instruction to agents (read before editing any `.tex` file here).** This is the author's review feedback on the manuscript,
with what was asked and how it was fixed. Do not just apply each fix to the one place it was reported. For every entry, work
out the *underlying heuristic* and the author's *stylistic preferences*, then check the rest of the paper for the same problem.
Read the style profile and "Heuristics so far" first, and extend both whenever new feedback reveals a pattern. Append every new round of feedback as a
new entry (request, what was done, lesson), then update the heuristics. Verify claims against `sections/results.tex` and the
generated macros before writing them; the author fact-checks and will catch overstatement.

## The author's writing style (read this first; refine it after every round)

This profile is inferred from all the feedback below. Treat it as the default voice for every edit, and update it when a new
round shows something it misses. Before finishing any edit, reread your own text as the reviewer described below, and fix what
would confuse them. The author has repeatedly praised text that follows this profile ("looks amazing") and rejected text that
does not.

**Reader.** A reviewer with a systems background and no serverless knowledge, reading cold. Every term must be understandable
from the page alone.

**Voice.**
- Direct and straight forward. Say what the system does or what was found, in the plainest literal words.
- Established, self-explanatory technical terms only. No coined labels ("slow loop", "planner", "single-loop", "second copy"), and
  no jargon without a one-clause definition at first use. If a term exists in the literature, use it; if not, describe the thing.
- Concrete over generic: "functions execute for well under a second" beats "the useful work is small".
- No filler, vague or rhetorical sentences ("The two feed on each other", "What remains is...", "providers hide cold starts",
  "feels abrupt"). Every sentence must state something a reader can check.
- Neutral, technical-report register. No narrative about how we got here, no embarrassment-inducing details (arbitrary
  parameters), no story of defects in the intro or abstract.
- Mechanism-accurate: do not claim a capability you cannot explain; do not "fix" accurate wording.

**Structure.**
- Abstract: short and crisp; problem, major architectural novelty, and headline results against established research and industry
  baselines. Nothing internal (greedy versus exact, ablations, cost, tuning).
- Introduction: build context in the order the reader needs it; define a term before using it; one idea per sentence.
- Contributions are what we built and found, each self-explanatory. Not the tools we used, not the history, not process claims
  ("hypotheses fixed before the runs") the reader cannot parse.
- Numbers come with what they measure and the hardware they come from, linked to the calibration section.
- Figures must show every step the text claims, with labels that define themselves; captions define every term.

**Working style.**
- Fact-check each claim against `sections/results.tex` and the macros; correct the author's premise politely when the data
  disagree (and say so), and do not adopt a wrong premise silently.
- A reported problem is a pattern: fix it everywhere (text, tables, figure labels, diagrams, explainer), not just where it was cited.
- Keep open problems visible in the PDF: `\critical{...}` for must-fix, `\potrem{...}` for possible removal.
- When feedback needs new experiments or code, do not implement it unasked: record it in `docs/EXPERIMENT_TODO.md`, mark it in the
  paper, and say so. Docs-only requests mean no code changes.
- Be self-critical: after writing, ask "would a systems reviewer without serverless knowledge be confused here?" and revise.

## Heuristics so far

1. **The abstract and intro serve a cold reader.** Define nothing by an in-house term; do not use engineered labels ("slow
   planner") as if they were established vocabulary. Describe a component by what it does. Introduce a project term only
   after the reader has the context for it.
2. **Abstract = problem, major architectural novelty, headline results against established baselines** (research baselines such
   as the Azure histogram policy, and industry references such as Lambda-like and Azure-like). Leave out tuning details,
   internal comparisons (greedy vs. exact, ablations), parameter values, and secondary analyses (cost). Keep it short.
3. **Never expose arbitrary parameters in the abstract** (e.g. the 30 s planning period, which was not swept). It reads as a
   weakness and is not a contribution.
4. **Do not assume the reader knows the system's structure.** Introduce the two deployments (global scheduler, clustered
   schedulers) before saying anything that depends on them (such as failed schedulers being replaced).
5. **Use the paper's own later vocabulary** (workers, tenants, invocations, concurrency limit, warm, request placement, provisioning) and
   check how the body actually describes a thing before describing it in the front matter.
6. **Claims must match the results.** Check `results.tex` before characterising a finding. Stress what the results show
   (e.g. global beat clustered; exact was not better than greedy), not what the design effort emphasised. Keep length in
   proportion to what was found.
7. **Plain, mechanism-accurate wording.** If a capability cannot be explained ("how would an owner delay?"), rephrase to what
   is certain (crash, withhold results).
8. **Abstract register is not intro register.** Avoid narrative connectives such as "What remains is...". Fold the motivation
   into the sentence that introduces the system.
9. **Do not cut context the reader needs, and do not clutter.** Do not mention calibration details ("calibrated on a laptop
   with a TPM") where they confuse; they belong in the method and limits sections.
10. **Explain every domain term for a systems reader without serverless background** (cold start, keep-alive, slot, warm,
    snapshot, why a decryption key is needed). One short clause at first use is enough; never assume the term is known.
11. **Contributions are what we built and found, not tools we used.** Using remote attestation (and its consequence that owners
    can only crash, drop or delay) is our premise, not a contribution. Do not list a method's development history ("a first
    version did X until we corrected it") in the intro or conclusion; that belongs, if anywhere, in the limits section.
12. **Every number needs its provenance at first use**: what it measures (e.g. power-on to attested and ready, not attestation
    alone) and on what hardware, with a pointer to the calibration section.
13. **Contributions must be self-explanatory.** "Hypotheses fixed before the runs" told a reviewer nothing; say what the reader
    gains (identical conditions for every system, exact reproducibility).
14. **No vague connective or filler sentences.** If a sentence cannot be checked or does not add a fact ("The two feed on each
    other"), delete it, and join its neighbours directly.
15. **Say literally what the system does.** "Sends a second copy of an invocation" was opaque; the real behaviour is "the
    invocation also runs on a second worker, in a different city or internet provider, and the first result to arrive is used".
    Describe the mechanism in the words an engineer would use, and check the paper's body that it is what we really do.
16. **A figure must be as detailed as the claim it supports.** If the text says "power-on to attested worker", the figure shows
    each step from power-on to the verifier's acceptance, including attestation itself, and the caption defines each label
    (e.g. direct microVM kernel boot versus a traditional firmware, boot-loader and kernel boot).
17. **Separate wording fixes from experiment and code work.** Wording goes into the `.tex` files; anything that needs new
    measurements or generator or harness changes goes into `docs/EXPERIMENT_TODO.md` and is marked in the paper with `\critical{}`.
18. **Praise tells you the target.** The rewritten introduction was called "amazing" after: defining every term at first use,
    stating the premise (not listing it as a contribution), naming components by what they do, and removing history. Match it.
19. **No colloquial quotations or casual phrasing in a technical paper.** Replace a quoted paraphrase ("I am running") with the
    formal term (liveness message, heartbeat) and define it once.
20. **A paragraph opener must be specific.** "What attestation does not remove is cost" left "cost" open to a hundred meanings.
    Open with the concrete claim the paragraph proves (three things must happen before a machine can run a function, each
    takes time), then enumerate them.
21. **Define a term by what it is, not by a vague size or a conflation.** "A sandbox is a small virtual machine" equated the
    concept with one implementation and used "small". Define the concept (isolated environment), then state the choice we made
    and why (virtual machine, for strong isolation between distrusting tenants).
22. **State modelling assumptions where the terms are defined** (serial execution: concurrency of one per sandbox), and say
    which real platforms differ.
24. **The introduction uses no serverless-specific vocabulary a general systems reader lacks.** "Slot" belongs in the background
    Terms; the intro says "capacity, counted as invocations a worker can run at the same time". Heuristic 5 (use the paper's later
    vocabulary) applies only to terms that are general or already defined in the intro; check every intro term against that.
25. **Define model quantities from the code, not from a doc or a guess.** For slots, read `voss/world` first; state assumed shares
    (donor envelope) as assumed and unswept.
26. **State each assumed parameter once, in a table, and do not name other platforms' behaviour without a verified citation.**
23. **A definition sentence must be readable on its own**; define a term by what it contains and does ("memory and processor state
    written to disk; loading it resumes the sandbox"), not by comparison alone ("restores faster than a sandbox boots").

## CRITICAL items (must be resolved before submission)

Items that need experiments or code are tracked in `docs/EXPERIMENT_TODO.md` (X-1 multi-machine calibration, X-2 per-step start-up
times, X-3 redraw Figure 1).

- **CRITICAL (MAJOR TODO): make the calibration cover many kinds of volunteer machine, not one.** All start-up, boot and
  attestation costs come from one laptop with a hard disk. The goal is to show how long each step takes on the different
  machines volunteers could offer: SSD and NVMe machines, laptops and desktops, different CPU generations and TPMs. Each
  machine's specification (CPU, board, BIOS, memory, disk type and measured throughput, TPM, kernel) is listed in the method
  section, as is done now for the first machine (i3-7020U, HDD; macros `Cal*` generated from the bundle's `meta.yaml` and
  `hardware.yaml` by `experiments/paper_tex/measured.py`). Each new machine gets its own bundle under
  `configs/calibration/measured/`, and the paper should compare them (a table of step times per machine, and a sensitivity run of
  the simulator per machine class). Marked with `\critical{...}` in `sections/intro.tex` and `sections/method.tex`. Running the
  calibration harness needs the user's approval (AGENTS.md rule 14). Plan: `docs/EXPERIMENT_TODO.md` X-1 and X-2.
- **CRITICAL: terminology for the two parts of the scheduler** (decided in round 8; keep it consistent everywhere):
  - **Provisioning** = the periodic, set-level decision (which workers hold each tenant's key, warm environments, reserved slots).
    Formerly "planner", "slow loop", "planning". Algorithms: *greedy provisioning*, *exact provisioning* (integer program),
    *loss-model provisioning*, *loss-model provisioning with an exposure budget*.
  - **Request placement** = the per-invocation decision. Formerly "fast loop".
  - **Keep-alive baselines** = on demand (formerly "no planner"), 10-minute keep-alive, unbounded keep-alive, histogram keep-alive.
    Formerly "single-loop baselines". *Early keys* stays as the name of the baseline that gives keys early to reliable workers.
  - Do not use: slow/fast loop, single loop, two-part/two-loop scheduler, planner. "Two-timescale" only when citing the edge
    literature that uses it. Labels in tables and figures come from `PLAIN_NAMES` in `experiments/analysis/round4.py`.
  - The explainer (`docs/explainer/voss-explained.md`) and the diagrams (`arch`, `sim`, `loops`) use the same terms. Code identifiers
    and configs (`planner`, `plan_greedy`, ...) are deliberately unchanged; only the paper and its companion docs were renamed.

## Log

### Round 1: abstract opening, 30 s, scheduler types
- **Said:** (a) The opening is a weird way to set context; say plainly that we do serverless on a volunteered compute pool.
  (b) "Every 30 seconds" is arbitrary (chosen without a sweep) and is not a contribution; keep it out of the abstract.
  (c) "Failed schedulers are replaced" is followed by "a global scheduler", which assumes the reader already knows there are two
  kinds of scheduling (clustered schedulers and a global one).
- **Did:** Rewrote the abstract to open with the volunteered-pool goal; removed the 30 s; introduced the global and clustered
  deployments first and then said why clustered schedulers need replacement. Applied the same fixes to the matching intro paragraph.
- **Lesson:** heuristics 1, 3, 4.

### Round 2: "ahead of demand"
- **Said:** The planner does not work ahead of demand; it uses a longer history. Use the paper's later wording.
- **Did:** Read `scheduling.tex`; described it in terms of request rates and session lengths averaged over minutes to hours,
  which keys, warm functions and reserved slots, and "request placement".
- **Lesson:** heuristics 5, 6. Read the whole paper before characterising a component.

### Round 3: "slow planner"
- **Said:** "Slow planner" is an engineered term, not an accepted one; it makes no sense without context. Calling it a planner is
  awkward too.
- **Did:** Abstract and intro now say the system "provisions workers" and describe what it does; the intro names the planner once,
  as a pointer to Section 5. The rest of the paper still says "planner" (a global rename is open).
- **Lesson:** heuristic 1.

### Round 4: calibration clause and emphasis
- **Said:** (a) "Calibrated on a laptop" is confusing; keep it to "simulator". (b) The paper spends so much length on two
  deployments, yet the results favour one choice; reframe as an evaluation of deployments and scheduling algorithms. (The
  author said "greedy" was much better; the fact check found greedy is much better than keep-alive baselines but not than the exact
  solver, while global was clearly better than clustered, so the wording followed the data.)
- **Did:** Dropped the calibration and TPM clause; framed the work as an evaluation of provisioning algorithms and deployments;
  stated the global-vs-cluster result.
- **Lesson:** heuristics 6, 9. Correct a misremembered premise explicitly, without silently adopting it.

### Round 5: shorten the abstract
- **Said:** Readers do not care that greedy beat other internal methods. Make the abstract short and crisp; show major
  architectural novelties and comparisons against industry or established research baselines.
- **Did:** Cut the greedy/exact/cluster detail; kept novelty, keep-alive/Azure-histogram comparison, heartbeat comparison, and the
  Lambda-like/Azure-like datacenter references.
- **Lesson:** heuristic 2.

### Round 6: "stop or delay", "What remains", cost
- **Said:** (a) "Stop or delay": how would an owner delay a machine? Rephrase. (b) "What remains..." is intro phrasing, not abstract.
  (c) Drop the cost claim from the abstract, and mark the cost analysis in later sections for potential removal.
- **Did:** Now "can crash a machine or withhold its results but not read or forge anything"; merged the motivation into the
  sentence that introduces VOSS; removed cost from the abstract; marked the cost paragraph in `results.tex` with the red
  `\potrem{...}` macro (defined in `main.tex`).
- **Open:** the same "stop or delay" phrasing (Property 1: "crash, dropped message or delayed message") appears in the intro and
  `design.tex`; the cost columns of `generated/tab_*commercial.tex` are not included in the text but still generated; `faulttol.tex`
  mentions paying donors. None changed yet.
- **Lesson:** heuristics 2, 7, 8.

### Round 7: is "withhold its results" just crashing?
- **Asked:** Is withholding results the same as crashing, given the owner can neither read nor forge anything?
- **Answer / did:** No, no wording change. The owner controls the power and the network, not the software. Crashing stops everything
  (including heartbeats). Withholding is selective: the attested image keeps running and keeps sending heartbeats, but the owner
  drops or holds back particular result messages on the network path. That is the omission/timing failure the paper builds its
  detector around (`background.tex`, "How volunteer machines fail"; `faulttol.tex`). Likewise "delay" is possible by holding
  messages; it was dropped from the abstract only because it was unexplained there, not because it is wrong.
- **Lesson:** heuristic 7 cuts both ways: keep wording mechanism-accurate, and do not "fix" wording that is accurate. When a
  question is a question, answer it before editing.

### Round 8: introduction (MAJOR)
- **Said:** (1) "The useful work is small" is generic; say the function's execution is short. (2) A cold start is more than loading
  the language runtime. (3) "The cold start can take longer than the function" makes no sense if the cold start includes execution.
  (4) Providers "hide" cold starts: bad wording; explain keep-alive and starting ahead of demand. (5) "They can do little about
  distance" is abrupt. (6) Attestation does not include boot-up; the 65 s is power-on to a running attested worker; it is the first
  number, so say what it was measured on and point to the calibration section; **CRITICAL**: calibrate on a second machine with an
  SSD. (7) Explain briefly why a worker needs the tenant's decryption key (code and snapshots are encrypted at rest). (8) "Slots
  reserved for a tenant" needs explaining for non-serverless readers. (9, MAJOR) Contributions: attestation is a tool we use, not a
  contribution; "two-part scheduler", "slow loop" and "single-loop" appear from nowhere and are engineered terms; rename across the
  paper (**CRITICAL**); "hypotheses fixed before the runs" is too dense; the placement-defect story does not belong in the intro.
- **Did:** Rewrote the intro. Cold start is now "start a sandbox, fetch the code, load the runtime and libraries, run
  initialisation code". On (3) the fact check went the other way: in the literature and in this paper (background, explainer) the
  cold start is the start-up delay *before* execution, so the comparison is valid; it is now worded unambiguously ("this start-up
  delay ... often exceeds the function's own execution time"). Keep-alive and pre-warming are defined. The 65 s is now "from
  power-on until it has booted the image, passed attestation and can run invocations", on the calibration laptop (Section 8), with
  a red `\critical` marker. Worker, tenant, snapshot, warm, slot, heartbeat and key exposure are defined at first use. Attestation
  moved from the contributions into the premise. Applied the terminology decision above across scheduling, results, discussion,
  method, related work, conclusion and the generated table/figure labels. Contribution (5) now says what the simulator gives the
  reader. Removed the defect story from the intro and the conclusion; reworded `scheduling.tex` as design rationale; the factual
  disclosure stays in the limits section. The paper grew from 21 to 22 pages.
- **Why these names:** "provisioning" is the standard systems term for preparing resources ahead of use (as in capacity
  provisioning); "request placement" was already the paper's term and is self-explanatory; the baselines are all keep-alive
  policies, so naming them by what they are beats naming them by what they lack. "Two-step scheduler" and "single-step" were
  rejected: they describe structure, not purpose, and "single-step" is no clearer than "single-loop".
- **Lesson:** heuristics 10--13. When a term is reported as confusing in one place, fix it everywhere it appears, including
  generated labels.

### Round 9: calibration must cover many machines (MAJOR TODO)
- **Said:** Instead of just a second machine with an SSD, calibrate on multiple machines, to show how long things take on the
  different sorts of machine volunteers could offer. List the specifications (CPU, etc.) of the hard-disk machine already done, and
  of every further machine, so the calibration is comprehensive.
- **Did:** The method section now lists the first machine's hardware (CPU, mainboard, BIOS, memory, disk speeds, TPM, kernel), taken
  from the calibration bundle through new generated macros. The CRITICAL markers in the intro and method section now ask for
  several machine kinds, each with its specification. The CRITICAL item above was rewritten.
- **Lesson:** heuristic 12 extends to hardware: a measured number is credible only with the machine it came from, and one machine
  is one data point. When a TODO is sharpened, replace the old marker instead of adding another.

### Round 10: Figure 1, "The two feed on each other", "second copy"
- **Said:** (a) Figure 1 is confusing: what does "boot microVM" mean (a direct kernel boot from an image?), and what does "reboot to
  kernel" mean when it is a traditional boot rather than a direct kernel boot? There is also no time for attestation, although the
  text says "power on to attested worker". There are many steps and the diagram is not verbose enough. When the calibration is
  rerun on several machines, the whole process needs per-step times for each start process. (b) Delete "The two feed on each
  other": vague, not for a technical report. (c) "Sends a second copy of an invocation": what does this mean, do we even do that?
  (d) Otherwise the introduction now looks amazing. (e) Put the inferred style and heuristics at the top of this doc and keep refining.
- **Did:** (a) Fact check: the user's reading is right. "Boot microVM" is a Firecracker direct kernel boot (kernel plus root file
  system image, no firmware or boot loader); "reboot to kernel" is the physical machine restarting through firmware and boot loader
  until the OS kernel starts. The figure is generated by code and cannot be fixed with wording, so: the caption in `background.tex`
  now defines these terms and the 65 s; a red `\critical` note under the figure asks for the per-step redraw; and the work is
  planned in `docs/EXPERIMENT_TODO.md` (X-2 per-step times for every start process, X-3 redraw, X-1 across machines). No code or
  experiment was changed. The bundle already hints that about 13 s between "agent ready" (31 s after kernel start) and "verifier
  accepted" (44 s) is unexplained, which the new breakdown must account for. (b) Removed, and the two neighbouring sentences joined.
  (c) Yes, we do this (`scheduling.tex`, hedging of at-risk idempotent invocations); the intro now says the invocation also runs on a
  second worker in a different city or internet provider, the first result is used, and only for idempotent functions. (e) Added the
  style profile at the top and heuristics 14--18.
- **Lesson:** heuristics 14--18. When a figure label is unclear to the author it will be unclear to a reviewer: define every label in
  the caption, and make the figure match the level of detail of the claim.

### Round 11: informal phrasing, vague opener
- **Said:** (a) ``I am running'' in quotes is not formal enough for a technical paper. (b) "What attestation does not remove is cost"
  is an unspecific paragraph opener; "cost" could mean a hundred things.
- **Did:** (a) Replaced with "periodic liveness messages (heartbeats)" in the intro, and fixed the same phrase in the background
  section (where heartbeats were not even defined) and in the explainer. (b) The paragraph now opens "Before a volunteer machine can
  run a customer's function, three things must happen, and each takes time", then gives the three in order: boot and attest (65 s on
  the calibration laptop), obtain the tenant's key, start an environment.
- **Lesson:** heuristics 19, 20. Check every paragraph opener against: does it say specifically what the paragraph will establish?

### Round 12: Background "Terms" paragraph
- **Said:** (a) "A sandbox is a small virtual machine" makes sandbox mean virtual machine; we choose a VM for strong isolation; do not
  use "small". (b) "Slots" was not explained. (c) "A snapshot is a saved copy of a started sandbox that restores faster than a
  sandbox boots" is odd. (d) "A key decrypts code and snapshots" is confusing since a snapshot already captures the code; fact-check.
  Also state that we assume serial execution (concurrency of one per sandbox, as in AWS Lambda), unlike Cloud Run functions or
  "AWS Lambda web functions", where one sandbox serves several invocations at once.
- **Did:** Rewrote the Terms paragraph in `background.tex`. Sandbox: the isolated environment; implemented as a Firecracker
  microVM (a VM, with the reason for choosing one, and what "microVM" means). Slot: one per donated CPU core, runs one invocation at a
  time. Snapshot: memory and processor state of a running sandbox written to disk, resumed on load. Key: fact check, the user's
  premise is only partly right. A snapshot holds the running sandbox's memory, which includes the loaded code, but it also holds data
  the function handled, which is why it is encrypted; and the code bundle is still needed to boot the first sandbox (a snapshot is
  made from one) and on any worker with no snapshot. So the key decrypts both, and the text now says why. Serial execution is stated
  as an assumption with the AWS Lambda / Cloud Run functions contrast. I did not name "AWS Lambda web functions": as far as I know
  Lambda (including with the Web Adapter) still runs one request per execution environment, so only Cloud Run functions (and
  similar) is named. No citation added for either platform's concurrency model; add one if wanted.
- **Lesson:** heuristics 21--23. Slot concurrency is not defined elsewhere in the paper (intro line 47 says only "one per slot").

### Round 13: PDF not refreshing; "slot" in the intro
- **Said:** (a) LaTeX Workshop shows the old PDF; make the changes appear. (b) The intro must not use lingo that systems readers
  outside serverless would not understand, e.g. "slot".
- **Did:** (a) My earlier check built into a scratch folder, so `manuscript/main.pdf` (git-ignored) was stale. Rebuilt it in place
  with the same tectonic command LaTeX Workshop uses (`.vscode/settings.json`); `latexmk`/`pdflatex` are not installed here.
  (b) Removed "slot" from the intro (two places): provisioning reserves "capacity, counted as the number of invocations a worker
  can run at the same time", and the contribution says "reserved capacity". "Sandbox" in the intro is now glossed as a virtual
  machine or container, and "snapshots" as saved memory and processor state of a started environment.
- **Lesson:** heuristic 24. After any edit, rebuild `manuscript/main.pdf` in place so the viewer shows it.

### Round 14: slots are not CPU cores
- **Said:** "Slot = one per CPU core" is wrong; verify against the document. Slots do not correspond to cores at all; there can
  be several per core.
- **Did:** The manuscript never ties slots to cores (`scheduling.tex` uses them only as concurrent-invocation capacity), so my
  Round 12 sentence was an unsupported import from `docs/architecture/02-environment-model.md` ("slots = vCPUs"). Terms now
  define a slot as the capacity to run one invocation at a time and say it is a unit of concurrency, not of hardware.
  **Open conflict, not changed (tex-only request):** the simulator derives slots as `int(cores x cpu_frac)`
  (`voss/world/workers.py:128`; `configs/hardware/E0.yaml` "three cores give two slots"), and doc 02 §4 and the explainer say
  the same, so in the code a slot is roughly a donated core. If slots should be independent of cores, the code and those docs
  need to change.
- **Lesson:** do not take a definition from the architecture docs or code into the paper without checking it against the paper
  body; and say when the paper's definition and the implementation disagree.

### Round 15: what a slot is (codebase author's account)
- **Said:** Understand what a slot means and how it is modelled; the code's author answered. Slots = `max(1, int(threads x 0.75))`,
  an assumed donor envelope (`cpu_frac`, with memory 0.6 and SSD/HDD 0.2); every invocation takes one slot; memory is not an
  admission check; the 0.75 has no derivation or decision record.
- **Did:** Terms: a slot runs one invocation at a time, every invocation takes exactly one slot, slots are derived from CPU threads
  and are not a guest vCPU, do not account for memory, and a warm sandbox holds memory but no slot. `method.tex`: the donor shares
  are stated as assumed, unmeasured and unswept, with the slot formula. `discussion.tex`: new limit (assumed shares, memory-blind
  slots, hyperthreads counted, no owner load, over-commit not yet measured).
- **Not done (outside tex-only scope):** doc 02 §4 still says "vCPUs"; `docs/DECISIONS.md` has no entry for `cpu_frac`; no
  `cpu_frac` sweep and no measurement of peak `running_mb / mem_mb`; ROADMAP Parked items (memory admission, per-function vCPU).
- **Lesson:** heuristic 25. Never define a model quantity from one doc or from the user's word alone; confirm with the code, and
  record what is assumed versus measured.

### Round 16: "slot" replaced by "concurrency limit"; capacity model
- **Said:** Replace "slot" with "concurrency limit" (and "reserved concurrency" for the per-tenant reservation); define once "A worker
  runs at most c_j invocations at a time"; add a short Capacity model paragraph (CPU bounds running invocations, memory bounds warm
  sandboxes, one vCPU per invocation, worst case 83% of the memory budget, slot held through key fetch/boot/execution, no
  time-sharing or preemption of running work so warm sandboxes are the overcommitted resource); state 0.75 once, in a table, next
  to the memory/SSD/HDD shares; no new defence; keep code identifier `slots` out of prose; no claimed equivalence with Lambda,
  OpenWhisk or Firecracker without a verified citation; do not call the planner's lead independent of the capacity model before
  H17/H18 are run.
- **Did:** No "slot" remains in the sections. `background.tex`: new Terms definition of $c_j$; new "Capacity model" paragraph; the
  Lambda and Cloud Run comparisons are removed (no verified citation); Firecracker now cited (`agache2020firecracker`, already in
  `design.tex`). `method.tex`: new Table `tab:donated` (CPU 0.75, memory 0.6, SSD 0.2, hard disk 0.2, all assumed); the earlier
  prose repeat of 75% is gone. `scheduling.tex`: reserved concurrency, $c_{tj}\le c_j$. `discussion.tex`: the limit item shortened; the
  unmeasured over-commit sentence is dropped because the 83% worst case replaces it. Checked: 83% = E0, 2 limit x 1024 MB
  (largest function) / 2457.6 MB; other classes 20-62%. Filler is preempted by sync (`scheduler_role.py`); the interference factor is
  1 + 0.1(busy-1)/limit, at most 1.1.
- **Lesson:** heuristic 26. A parameter value appears once, in a table, not repeated in prose.

