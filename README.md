# VOSS

Serverless functions with deadlines of seconds, run on volunteer machines that the provider neither owns nor trusts.
Each worker boots a measured image and is attested before it receives a function's decryption key. VOSS is the
architecture and the scheduler that make this work under machine departures and owners who drop or forge work.

The repository holds the scheduler (real policy code), a deterministic discrete-event simulator, baselines, the
calibration harness for real machines, and the experiments and manuscript.

**Status:** v2 rebuild in progress on branch `revision-v2` (`docs/REVISION_PLAN.md`). v1 is archived at `main` commit
`b0f2fb24`; its results are not reused.

## Read in this order

| Doc | What it answers |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Rules for coding agents, including the v2 guardrails (binding) |
| [`docs/REVISION_PLAN.md`](docs/REVISION_PLAN.md) | The v2 build plan, phase by phase: **start here to code** |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | v2 decisions (D-81 onward); v1 decisions as history |
| [`docs/PARAMETERS.md`](docs/PARAMETERS.md) | Every configuration constant and data file, with its source |
| [`docs/handoff/`](docs/handoff/) | Runbook and data contract for calibration on bare-metal machines |
| [`docs/architecture/`](docs/architecture/) | Design documents; each says which parts are v1 and which phase rewrites them |
| [`manuscript/WRITING_SPEC.md`](manuscript/WRITING_SPEC.md) | How the paper is written (binding for the manuscript) |
| [`manuscript/reviews/`](manuscript/reviews/) | The reviews of the v1 paper that motivated v2 |

## Checks

`make check` runs ruff, mypy, import-linter and pytest. `make repro-smoke` checks that a run reproduces its result hash.
