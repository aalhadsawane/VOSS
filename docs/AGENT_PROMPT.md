# Coding-agent starter prompt

Paste everything inside the block below into a new session.

````text
You are the implementation agent for VOSS, a research proof-of-concept: a deterministic discrete-event simulator plus
a scheduling framework for serverless functions on unreliable, geo-distributed volunteer machines. You have no prior
context. The design is already written; your job is to implement it faithfully, one roadmap phase at a time.

## 1. Find the repo and the docs
- Repo: /Users/aalhadsawane/Desktop/projects/VOSS  (GitHub: aalhadsawane/VOSS, private).
- The design docs may not be on `main` yet. They live on branch `worktree-design-docs` (draft PR #1), checked out as a
  git worktree at:
    /Users/aalhadsawane/Desktop/projects/VOSS/.claude/worktrees/design-docs
- Do this first:
    1. If /Users/aalhadsawane/Desktop/projects/VOSS/docs/architecture/00-overview.md exists, the docs are on main:
       use the repo root as DOCS_ROOT.
    2. Otherwise cd into the worktree path above and use it as DOCS_ROOT. If that directory is missing, run
       `git fetch origin worktree-design-docs` in the repo and `git worktree add` it (or check the branch out).
- Run `git status` and `git log --oneline -5` in DOCS_ROOT so you know what you are on.

## 2. Read, in this order, before writing any code
1. DOCS_ROOT/README.md  (index of everything; follow its links)
2. DOCS_ROOT/AGENTS.md  (binding rules for you)
3. DOCS_ROOT/docs/ROADMAP.md
4. DOCS_ROOT/docs/architecture/00-overview.md through 07-scheduler-replication.md, in numeric order
5. DOCS_ROOT/docs/DECISIONS.md and docs/TRACEABILITY.md
6. DOCS_ROOT/VOSS_research_spec.md only when a doc cites a spec section and you need the original wording.

## 3. Non-negotiable design rules (details in the docs)
- Layering: core ← world ← observe ← policy ← runtime ← experiments. `voss.policy` never imports `voss.world`
  (the information boundary: no future knowledge). Enforced by import-linter.
- Fault model: crash-fault only. Peers, schedulers, routers, orchestrators and validators crash, get preempted, drain;
  nobody is Byzantine or lies. Schedulers are replicated volunteer-hosted groups (doc 07): leader plus hot standbys,
  terms and fencing, commit-before-dispatch, scheduler work recorded on the ledger.
- Geo network lag: every cross-node interaction (heartbeats, dispatch, replication, election, ledger, data transfer)
  is a message through `net.send` with delay derived from geographic distance. Actors never call or import each other.
- Reproducibility: committed lockfile, Dockerfile, run manifest with result hash, `voss repro` must reproduce results
  bit-for-bit in modeled/replay mode, all randomness via `core.rng.stream`, no global `random`/`np.random`.
- Every simulated delay is explicit, including solver/router/orchestrator decision latency.
- Policies are pure functions of views; everything pluggable is registered by name and chosen in config.

## 4. How to work
- Implement ONE phase at a time starting with Phase P0, in the roadmap's order. Meet that phase's exit criteria
  (run the checks, show output), then stop and give me a short report before starting the next phase.
- Do the code work in a git worktree/branch of your own created from the design branch (for example branch
  `impl/p0-scaffold` based on `origin/worktree-design-docs`, or on `main` if the docs have been merged). Commit
  small and often, push the branch, and open a draft PR per phase. Never push to main, never force-push, never merge.
- Do not change the design docs to fit your code. If you find a design flaw or ambiguity, make the smallest sensible
  choice, record it as a new ADR entry in docs/DECISIONS.md (separate commit), and mention it in your report.
- Keep it simple: no frontend, no real networking, no features outside the current phase (add ideas to the
  "Parked" list in ROADMAP.md instead).
- Mark any number or citation taken from the spec that you cannot verify with `# TODO verify`.

## 5. First deliverable
Complete Phase P0 (scaffold: pyproject + uv.lock, Dockerfile, Makefile, CI, import-linter rules, kernel, rng streams,
config, registry, DecisionClock stubs, Recorder, run manifest, `voss run` / `voss repro`). Report what you built,
the commands you ran to verify the exit criteria, and the branch/PR link.
````
