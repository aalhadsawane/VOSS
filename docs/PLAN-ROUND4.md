# Round 4 plan: stronger baselines, planner v2, a 25-page paper

This is the working plan and the single source of truth for round 4. Agents read this file first. It replaces chat context.

## 0. State at the start of round 4 (main = `e2131f6`, PR #40)

- Simulator, 21 frozen experiments, 2,366 bit-reproducible runs (D-70). Paper numbers come from `manuscript/generated/` via
  `experiments/paper_tex`; `tests/unit/test_manuscript.py` checks freshness.
- Manuscript draft 12 (`manuscript/`, ACM `acmsmall`, 34 pages). Explainer 46 slides (`docs/explainer/voss-explained.md`).
- Critique register `docs/critique/CRITIQUE.md` (C-01 to C-45), action plan `docs/critique/ACTION.md` (major change M6),
  planner v2 proposal `docs/proposals/planner-v2.md`, decisions up to D-76.
- Planners registered in `voss/policy/plan/`: `none`, `keepalive_ttl` (empty plan, worker TTL 600 s does the work),
  `greedy` (default), `milp`. `PlanInput` is built in `voss/runtime/schedlib/planning.py`.
- E04 compares planners (`configs/experiments/E04.yaml`, 200 workers, 900 s, churn_med and churn_high, seeds 1-10).
- The `paper-rerun` workflow reruns any subset of experiments on GitHub runners (input `experiments`, e.g. `E04,E19`).

## 1. Decisions from the author (round 4)

1. **Keep** the slow planner and all existing work. **Add** baselines to compare against, in particular a strong single loop
   in the style of Azure Functions' hybrid histogram policy (Shahrad et al., ATC 2020): per function, learn the idle-time
   distribution and set a **pre-warm window** (unload after use, reload just before the next predicted call) and a
   **keep-alive window**; fall back to a fixed timer when the histogram is not representative.
2. **Implement planner v2** (the loss-model planner of `docs/proposals/planner-v2.md`) next to greedy and MILP.
3. The paper must stress what the slow planner captures that a single loop cannot: **state that lives for a session spans
   many requests**. A key release or a warm sandbox is paid once and serves every request for the rest of the session, so
   its value is (request rate) × (expected remaining session time) × (time saved per request), discounted by the chance the
   machine leaves. Only a planner that knows session survival can weigh that; a per-function TTL cannot.
4. The paper must fit **25 pages including the new experiments**. Length goes to what is new: the scheduling problem and
   planner, session-spanning state, exposure, failure detection by returned work, the two architectures and the broker.
   What we only use (TPM quotes, attestation protocol, Keylime, MQTT basics, discrete-event simulation) gets a few sentences
   and a citation.
5. The coined terms listed in round 3 were examples only; the whole manuscript must be audited for undefined or
   engineered terms.
6. Agents: mostly Sonnet (all code writing); at most two Opus (planning, design review, critique defence).

## 2. Work packages

### WP1 Strong single-loop baseline (Sonnet, code)
- New registered planner `histogram_prewarm` with an empty trust plan (no key planning), plus per-function keep-alive and
  pre-warm windows learned online from idle times, following the hybrid histogram policy:
  - per function, histogram of idle times (gap between the end of one invocation and the next arrival), 1-minute bins up to
    a range (Azure used 4 hours; we scale to the simulated horizon, configurable);
  - pre-warm window = a low percentile (5th) of idle time minus a margin; keep-alive window = a high percentile (99th) plus
    a margin; if the histogram has too few samples or its coefficient of variation is too low, fall back to a fixed TTL
    (the existing 600 s);
  - "pre-warm" means: after an invocation, release the warm sandbox, then re-warm it on the same worker when the pre-warm
    window elapses, keeping it until the keep-alive window ends. Only workers that already hold the tenant's key re-warm
    (no planned key releases: this is a single loop).
- Where it runs (worker-side TTL vs scheduler-sent WARM actions): implementer decides, documents in a decision entry, keeps
  modules < 400 lines, functions < 50 lines, policies pure and unit-testable (AGENTS.md).
- Tests: histogram windows on synthetic idle-time sequences; fallback path; an integration smoke run.

### WP2 Planner v2 (Sonnet, code)
- `voss/policy/plan/erlang.py`, registered `erlang_greedy` and `erlang_dpp`, same inputs and outputs as `greedy`.
- Add to `PlanInput` what the loss model needs (per-function arrival rate and mean service time; per-tenant load), built in
  `voss/runtime/schedlib/planning.py` from the scheduler's existing estimates (no ground truth; layering contract).
- Stage A (key holders): utility `U_t(S) = λ_t Δ_t E[1 − B(C_t(S), a_t)]`, `C_t` = surviving slots (independent
  Bernoulli survival `e_j`), exact distribution by convolution; distorted greedy with exposure + memory as the modular cost;
  robust buffer of the `f_t` largest single contributions (Orlin-Schulz-Udwani style). Must still respect assurance floor,
  freshness, domain cap, slots.
- Session value (decision 3): a key or warm sandbox on worker j is weighted by the expected time j stays (from `S_j`), so a
  long-lived worker is preferred for state that serves many requests.
- Stage B (warm sandboxes, snapshots): marginal allocation by Erlang-B gain per MB with a heap; snapshots in the same heap
  with value `λ_f B(w_f, a_f)(τ_boot − τ_restore)`.
- `erlang_dpp`: per-tenant exposure budget with a virtual queue updated once per planning round (state kept in the planner
  object; must be checkpointable or documented as soft state).
- Tests: Erlang-B recursion vs closed form; convexity; submodularity of `U_t` on random instances (property test);
  marginal allocation equals brute force on small instances; robust slack holds; runtime under 50 ms for 40 workers.

### WP3 Experiments (Sonnet runs, Opus reviews)
- New `configs/experiments/E04.yaml` systems: `histogram_prewarm`, `erlang_greedy`, `erlang_dpp` added to the existing four.
  Same seeds, same regimes. Add a third regime only if cheap.
- Pre-stated hypotheses (write into `docs/architecture/06-experiments.md` before running):
  - H12: greedy planner beats `histogram_prewarm` on synchronous P99 by at least 5% at medium and high churn.
  - H13: `erlang_greedy` beats `greedy` on synchronous P99 by at least 5% at medium and high churn, at no more warm memory.
  - H14: `erlang_dpp` keeps time-average exposure within its budget, with P99 within 5% of `erlang_greedy`.
- Decision rule: if H13 is supported, `erlang_greedy` becomes the VOSS default and all 21 experiments are rerun on the
  `paper-rerun` workflow; otherwise greedy stays default and planner v2 is reported in E04 and E23 only.
- Charge measured planner solve time to the simulated clock for the planner comparison (C-16), or state why not.

### WP4 Manuscript to 25 pages (main session writes; Sonnet audits terms; Opus reviews)
- Term audit (Sonnet, read-only): list every coined, undefined or once-used term in `manuscript/sections/*.tex` with line
  and a plain replacement.
- Page budget (acmsmall, including references and appendix): intro 1.5, background 1.5, design 3, scheduling and planner 5,
  networking 1.5, failures 1.5, evaluation method 1.5, results 5, related 1, discussion and limits 1.5, conclusion 0.3,
  references 1.7. Attestation background shrinks to one paragraph; attestation figure and threat table go; appendix B moves
  to the artifact.
- New emphasis: session-spanning state (decision 3), the planner's math, the new baselines.
- The explainer follows the paper (< 50 slides).

### WP5 Review (Opus, one agent)
- Before code: review WP1 and WP2 designs as a systems reviewer would (is the baseline faithful to Azure's policy? is the
  planner v2 math right and does it fit the inputs we have? are the hypotheses fair?).
- After results: critique the outcome and the 25-page outline; update `docs/critique/CRITIQUE.md` and `ACTION.md`.

## 2b. Revisions after the design review (`docs/proposals/round4-review.md`)

Verified by the main session against `paper/tables/E04.csv`: the planner beats keep-alive in 19 of 20 seeds, but the large
headline gains come from seeds 2, 8 and 10; elsewhere the gap is about 5-15%. Trust-cold starts are about 0.1% for every
system. So the mechanism behind the planner's gain must be shown, not assumed.

- **E04 v2:** 1800 s runs, 300 s warm-up, 20 seeds (exact MILP 10). Systems: `plan_none`, `keepalive_ttl`, `keepalive_inf`
  (config only), `hist_prewarm` (WP1, scheduler-side, idle times per sandbox, re-warm on any key holder),
  `provisioned_keys` (new: keys held ahead on the N most reliable workers, exposure matched to greedy), `plan_greedy`,
  `plan_milp`, `erlang_greedy`, `erlang_dpp`.
- **Decision rule (non-inferiority, replaces H13's superiority test):** adopt `erlang_greedy` as default if its P99 is no worse
  than greedy by more than 5% (medium churn) and 10% (high churn) with no more warm memory or exposure; then rerun all
  experiments inheriting `configs/pilot.yaml`. Holm correction across H12-H15.
- **H12** is against the best single loop per regime (max of `keepalive_ttl`, `keepalive_inf`, `hist_prewarm`), not the TTL.
- **E25 (new):** session-length and session-shape sweep, with a `survival_blind` planner ablation. Pre-registered expectation:
  the planner's advantage over the best single loop is an inverted U in session length (too short: nothing survives to pay
  back; very long: reactive key fetches also persist), and depends on falling hazard (Weibull shape < 1).
- **Tail breakdown** of the slowest 1% of requests in E04 seeds 2, 8, 10 before writing the session-spanning argument.
- **Math claims:** only the per-tenant (1-1/e) bound (cardinality limit, non-negative modular cost) and submodularity
  (which holds even with correlated survival) are claimed; robust-submodular and drift-plus-penalty constants are motivation
  only (review §2.2 has the wording). Fix C-44 accordingly.
- **Paper:** 25-page outline in review §5 is the starting point.

## 3. Order

1. WP5 design review, WP1 and WP2 implementation, WP4 term audit, in parallel.
2. Merge WP1 and WP2 (separate PRs, `make check` green, repro-smoke hash unchanged for existing systems).
3. WP3: run extended E04 (locally or on the workflow), apply the decision rule.
4. WP4 rewrite to 25 pages with the new results; explainer; WP5 critique; final PR.

## 4. Rules for every agent

- Read `AGENTS.md`, this file, and the files named in your package. Branch per package; never push to main; no force-push.
- `make check` must pass. Existing systems' result hashes must not change (`make repro-smoke`).
- Numbers in the paper come only from generated macros. Literature numbers are tagged `literature` / `# TODO verify`.
- Report back: what changed, tests run with results, open questions. Do not claim results you did not run.
