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
