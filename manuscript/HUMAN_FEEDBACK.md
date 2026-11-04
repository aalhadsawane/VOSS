# Human feedback log

**Instruction to agents (read before editing any `.tex` file here).** This is the author's review feedback on the manuscript,
with what was asked and how it was fixed. Do not just apply each fix to the one place it was reported. For every entry, work
out the *underlying heuristic* and the author's *stylistic preferences*, then check the rest of the paper for the same problem.
Read "Heuristics so far" first, and add to it whenever new feedback reveals a pattern. Append every new round of feedback as a
new entry (request, what was done, lesson), then update the heuristics. Verify claims against `sections/results.tex` and the
generated macros before writing them; the author fact-checks and will catch overstatement.

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
5. **Use the paper's own later vocabulary** (workers, tenants, invocations, slots, warm, request placement, provisioning) and
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

## CRITICAL items (must be resolved before submission)

- **CRITICAL: repeat the calibration on a second machine with an SSD.** All start-up, boot and attestation costs come from one
  laptop with a hard disk. Marked with `\critical{...}` in `sections/intro.tex` and `sections/method.tex`. Running the calibration
  harness needs the user's approval (AGENTS.md rule 14).
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
