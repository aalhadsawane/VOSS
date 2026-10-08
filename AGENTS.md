# Rules for coding agents

1. **Workflow.** Read `README.md`, then `docs/ROADMAP.md`, then the architecture docs for your phase. Build **one phase
   at a time** and meet its exit criteria before the next. Work on a branch, open a PR per phase, and **merge it
   yourself** when the checks pass. Never force-push or push directly to `main`.
2. **Layering** (`docs/architecture/05-code-structure.md` §2). `voss.policy` never imports `voss.world`: this is the
   information boundary (no future knowledge), enforced by `import-linter`.
3. **Policies are pure functions of views** (immutable snapshots), unit-testable without the simulator. Actors are
   thin: decode message → call policy → send messages.
4. **Messages only.** Every cross-node interaction is a typed message via `net.send` with geo-derived delay. Actors
   never call or import each other (doc 01 §6).
5. **Data over code.** Substrates, hardware, regimes and experiments are YAML. One generic lifecycle engine interprets
   substrate profiles (doc 05 §5). Every pluggable behavior is registered by name and chosen in config. Baselines use
   the same interfaces, candidates and cost matrix as VOSS.
6. **Nothing is free.** Network, disk tiers, CPU, TPM quotes, attestation, key release and decision latency (planner,
   placer, router, orchestrator) are all simulated delays.
7. **Threat model** (doc 04): owners may be malicious, and attestation reduces them to omission/timing faults. Treat
   liveness signals and owner notices as hints; use progress evidence (doc 07). Tenant keys never reach the scheduler
   or the orchestrator. **No blockchain.**
8. **Two-timescale scheduling** (doc 03): trust and warm state are planned by the slow loop; invocations are placed by
   the fast loop. Do not put set-coupled decisions in the fast loop.
9. **Reproducibility is a feature** (doc 01 §8):
   - all randomness via `core.rng.stream`;
   - sorted iteration where order matters;
   - committed lockfile;
   - manifests with scenario and calibration hashes;
   - `voss repro` must reproduce result hashes.
10. **Log raw** through `metrics.Recorder`; analysis reads logs only.
11. **Quality.** Modules < 400 lines, functions < 50 lines, typed, no globals. `make check` (ruff, mypy, import-linter,
    pytest) must pass. Docstrings cite the doc section they implement.
12. **Scope.** No feature outside the current phase; add ideas to `docs/ROADMAP.md` → Parked. If a design flaw blocks
    you, make the smallest sensible choice and add a decision to `docs/DECISIONS.md` in a separate commit.
13. **Numbers** from the spec or literature are unverified seeds: tag them `literature` in YAML and `# TODO verify` in
    code. Measured values come only from calibration bundles (doc 10).
14. **The calibration harness runs on a real machine.** Never run reboot or BIOS-dependent suites without explicit
    user approval (doc 10 §1).
