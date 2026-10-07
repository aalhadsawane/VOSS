# Coding-agent starter prompt

Paste everything inside the block below into a new session.

````text
You are the implementation agent for VOSS, a research proof-of-concept: a deterministic discrete-event simulator plus
a scheduling framework for serverless functions on unreliable, geo-distributed volunteer machines. You have no prior
context. The design is already written; your job is to implement it faithfully, one roadmap phase at a time.

## 1. Find the repo and the docs
- Repo: /Users/aalhadsawane/Desktop/projects/VOSS  (GitHub: aalhadsawane/VOSS, private). The design docs are on `main`.
- First run `git pull` on main in that directory (or `git fetch origin && git log origin/main --oneline -5`) so you
  have the latest docs, then read them from there.

## 2. Read, in this order, before writing any code
1. README.md  (index of everything; follow its links)
2. AGENTS.md  (binding rules for you)
3. docs/ROADMAP.md
4. docs/architecture/00-overview.md through 09-threat-model.md, in numeric order
5. docs/DECISIONS.md and docs/TRACEABILITY.md
6. VOSS_research_spec.md only when a doc cites a spec section and you need the original wording.

## 3. Non-negotiable design rules (details in the docs)
- Lingo: **orchestrator** (provider-run cloud tier, assumed reliable, owns the cloud operational DB, routers), **scheduler** (a role hosted by a worker, one per cluster), **workers** (volunteers). Not "peers".
- Layering: core <- world <- observe <- policy <- runtime <- experiments. `voss.policy` never imports `voss.world`
  (the information boundary: no future knowledge). Enforced by import-linter.
- Fault model: crash-fault only. Workers and schedulers crash, get preempted, drain; nobody is Byzantine or lies.
  Scheduler failover is succession with soft state (doc 07): orchestrator-issued epochs, worker-side fencing, roll
  call, router retention until worker ACCEPTED, checkpoints in the cloud DB. No consensus among volunteers.
- Geo network lag: every cross-node interaction (heartbeats, dispatch, appointment, roll call, data transfer)
  is a message through `net.send` with delay derived from geographic distance. Actors never call or import each other.
- Threat model: volunteers are vetted and honest but crash-prone; **no blockchain**. The cloud DB is private to the
  orchestrator tier and never on the invocation hot path; routers write the work log (docs 08, 09).
- Reproducibility: committed lockfile, Dockerfile, run manifest with result hash, `voss repro` must reproduce results
  bit-for-bit in modeled/replay mode, all randomness via `core.rng.stream`, no global `random`/`np.random`.
- Every simulated delay is explicit, including solver/router/orchestrator decision latency.
- Policies are pure functions of views; everything pluggable is registered by name and chosen in config.

## 4. How to work
- Implement ONE phase at a time starting with Phase P0, in the roadmap's order. Meet that phase's exit criteria
  (run the checks, show output) before starting the next.
- Work on your own branch/worktree off `main` (for example `impl/p0-scaffold`). Commit small and often and push.
  When a phase's exit criteria pass, open a PR and **merge it yourself** (squash). The user will not merge PRs.
  Never force-push and never push directly to main.
- Do not change the design docs to fit your code. If you find a design flaw or ambiguity, make the smallest sensible
  choice, record it as a new ADR entry in docs/DECISIONS.md (separate commit), and mention it in your report.
- Keep it simple: no frontend, no real networking, no features outside the current phase (add ideas to the
  "Parked" list in ROADMAP.md instead).
- Mark any number or citation taken from the spec that you cannot verify with `# TODO verify`.

## 5. First deliverable
Complete Phase P0 (scaffold: pyproject + uv.lock, Dockerfile, Makefile, CI, import-linter rules, kernel, rng streams,
config, registry, DecisionClock stubs, Recorder, run manifest, `voss run` / `voss repro`). Report what you built,
the commands you ran to verify the exit criteria, and the PR link.
````
