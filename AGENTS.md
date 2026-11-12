# Rules for coding agents

1. **Workflow.** Read `README.md`, then `docs/REVISION_PLAN.md` (the v2 build plan), `docs/DECISIONS.md` (v2
   decisions), `docs/PARAMETERS.md`, and the phase's architecture docs. Build **one phase at a time** and meet its exit
   criteria before the next. All v2 work lands on the long-lived branch `revision-v2`: cut a short branch
   `v2/V<n>-<slug>` from it per phase, open a PR **into `revision-v2`**, and merge it yourself when the checks pass.
   `revision-v2` is merged into `main` once, at the end of the plan (V15). Never force-push or push directly to `main`.
2. **Layering** (`docs/architecture/05-code-structure.md` §2). `voss.policy` never imports `voss.world`: this is the
   information boundary (no future knowledge), enforced by `import-linter`.
3. **Policies are pure functions of views** (immutable snapshots), unit-testable without the simulator. Actors are
   thin: decode message → call policy → send messages.
4. **Messages only.** Every cross-node interaction is a typed message via `net.send` with geo-derived delay. Actors
   never call or import each other (doc 01 §6).
5. **Data over code.** Substrates, hardware, regimes and experiments are YAML. One generic lifecycle engine interprets
   substrate profiles (doc 05 §5). Every pluggable behavior is registered by name and chosen in config. Baselines use
   the same interfaces, candidates and cost matrix as VOSS.
6. **Nothing is free.** Network, disk tiers, CPU, TPM quotes, attestation, key release and decision latency
   (provisioning, placement, router, orchestrator) are all simulated delays.
7. **Threat model** (D-84, doc 04): owners may be malicious. For owner classes S and M attestation reduces them to
   omission and timing faults; class P can also read memory, so integrity rests on the sampled audit. Treat liveness
   signals and owner notices as hints; use progress evidence (doc 07). Tenant keys never reach the scheduler or the
   orchestrator. **No blockchain.**
8. **Provisioning and request placement** (D-86, doc 03): which workers hold each function's key, keep warm sandboxes
   and reserve concurrency is decided periodically by provisioning; each invocation is placed by request placement. Do
   not put decisions about sets of workers into request placement.
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

## Guardrails for v2 (`docs/REVISION_PLAN.md` §4; a PR that violates one is not mergeable)

15. **Claims need measurements.** Nothing in the abstract or introduction unless a figure or table measures it.
16. **Equal budgets.** Every compared policy runs under the same key-holder budget `K`, the same timeouts and the same
    capacity; no weight converts key holders into latency.
17. **Baselines as published.** A baseline named after a paper implements that paper's algorithm and parameters; every
    deviation is listed in the paper; no vendor names for in-house models.
18. **Baselines get their class's standard mechanisms** (request timeouts, retry).
19. **Deadline-met is the primary metric.** Lost and late are both misses; latency percentiles include lost invocations.
20. **Report every grid cell** that was run for the paper.
21. **Experiment header.** Every experiment states workers, load, utilisation, duration, warm-up, calibration bundles,
    trace split and seeds.
22. **One code revision** (`v2-freeze`) for all reported results.
23. **Warm-up at least as long as the longest learning window** of any compared policy.
24. **Security claims name the owner class** (S, P, M) they hold for.
25. **Every mechanism described in the paper has a result**, or it is not described.
26. **Vocabulary and style** follow `manuscript/WRITING_SPEC.md` and `manuscript/HUMAN_FEEDBACK.md`.
27. **Every constant is in `docs/PARAMETERS.md`** with a class (measured, trace, literature, derived, axis, swept).
28. **Reported results use measured calibration bundles only.**
29. **No invented costs** (decision time, co-run slowdown, start-up and attestation costs are measured).
30. **Design text never mentions the simulator**; the methodology section says what is modelled.
31. **Development split for design, held-out split for results**; the held-out sweep runs once.
32. **Delete what is not evaluated.** No dormant options, no dead baselines.
