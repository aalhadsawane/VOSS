# Rules for coding agents

1. Read `docs/ROADMAP.md`, then the architecture doc for the phase you are building. Build **one phase at a time**
   and meet its exit criteria before starting the next.
2. **Respect the layering** in `docs/architecture/05-code-structure.md`. `voss.policy` must never import
   `voss.world`: this is the information boundary (no future knowledge). It is enforced by `import-linter` in CI.
3. Policies are **pure functions of views** (immutable snapshots), unit-testable without the simulator.
4. All randomness goes through `core.rng.stream(name, *keys)`. No global `random`/`np.random`.
5. Every simulated delay is explicit: network, disk, CPU, and **decision latency** (solver, router, orchestrator).
   Never let a decision be free.
6. Every pluggable behavior (placer, predictor, router, keep-alive, ...) is registered by name and chosen in
   config. Baselines and VOSS use the **same** interfaces and the same cost matrix where applicable.
7. Components record raw events through `metrics.Recorder`. Analysis reads logs only, never simulator objects.
8. No feature outside the current phase. If something seems needed, add it to `docs/ROADMAP.md` under "Parked".
9. Keep modules small (<400 lines) and typed. Tests: pytest, deterministic seeds. `make check` must pass
   (ruff, mypy, import-linter, pytest).
10. **Fault model is crash-only** (ADR-016): nodes crash, get preempted or drain; nothing is Byzantine. Lingo: orchestrator (provider-run,
    reliable), scheduler (a role on a worker), worker. Scheduler failure is handled by succession with soft state
    (`docs/architecture/07-fault-tolerance.md`).
11. **Every cross-node interaction is a message through `net.send`** with geo-derived delay. Actors never call each
    other's methods or import each other (`docs/architecture/01-simulation-core.md` §6).
12. **Reproducibility is a feature:** committed lockfile, run manifest, `voss repro` must reproduce the result hash,
    no unseeded randomness, sorted iteration where order matters (`01` §9).
13. Numbers from the spec (citations, trace names) are unverified. Mark them `# TODO verify` in code and docs.
