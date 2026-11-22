# Brief for the paper-writing agent

Read this file first. It tells you what the project is, where everything lives, what you may and may not do, and what is
still open. Then read the files in section 3 in the order given.

## 1. The project in six lines

- VOSS runs serverless functions on volunteered machines. Owners may be malicious; remote attestation limits them to crashing
  a machine, withholding results or delaying messages (owner classes S and M), and class P can also read memory, so integrity
  there rests on a sampled audit.
- Two decisions are separate: **provisioning** (periodic; which workers hold each function's key, keep warm sandboxes and reserve
  concurrency) and **request placement** (per invocation).
- The evaluation is a deterministic discrete-event simulator driven by public traces, calibrated on measured machines, with
  a small real-hardware emulation as a check.
- This is the **v2 revision** for ACM TOIT. v1 was archived (tag `v1-archive`); nothing from v1 results is reused.
- Work lands by pull request into the long-lived branch `revision-v2`. It is merged into `main` once, at the end (V15). Never push
  to `main`, never force-push.
- Your job: the manuscript under `manuscript/`. You do not change code, configs, results or calibration data.

## 2. Rules that bind you

1. **Never invent a number.** A missing value is a to-do marker: `\todoitem{Tnn}{waits for}{what}`. Remove a marker only when its
   source exists and the value comes from a generated macro (`\V...`) or table.
2. **Every number comes from a macro** in `manuscript/generated/` (written by `experiments/analysis/paper_inputs.py`). Do not edit
   `generated/` by hand. Run `uv run python -m experiments.analysis.paper_inputs` to regenerate; the test
   `tests/unit/test_manuscript.py::test_generated_inputs_are_fresh` fails if the committed files are stale.
3. **Style is binding:** `manuscript/WRITING_SPEC.md` (forbidden words include `round` except "round-trip", `slot`, `exposure`,
   `hedg`, `planner`, `rerun`; outline before prose; §6 has one check per feedback round) and `manuscript/HUMAN_FEEDBACK.md`
   (style profile and heuristics 1-30, then the log). Reader: a systems reviewer with no serverless background, reading cold.
4. **Claims need measurements** (AGENTS.md rules 15-32). Nothing in the abstract or introduction unless a figure or table measures it.
   The design sections never mention the simulator; the method section says what is modelled.
5. **Fact-check every claim** against `sections/results.tex`, the macros and the code. Correct a wrong premise politely and say so.
6. **Privacy.** Node repository text has no IP addresses, MAC addresses, serials, user names, hostnames or other people's service
   names. Node codenames are allowed. Do not put the author's email or personal details anywhere.
7. **No model identifiers** in commits, PR text, code or the manuscript.
8. After every `.tex` change run `make manuscript-pdf` (rebuilds `manuscript/pdf/VOSS-v2-draft.pdf`, linked from the README).
9. Append every new round of author feedback to `HUMAN_FEEDBACK.md` (request, what was done, lesson) and extend the heuristics.
10. Held-out results (R01-R09) do not exist before the freeze tag `v2-freeze`. Do not write result sentences for them; keep the marker.
11. Commit footer: `Co-Authored-By: ...` and `Claude-Session: ...` lines as the session instructs. PR bodies end with the generated-with line.
    Open a PR into `revision-v2`; merge it when CI is green. Keep writing PRs `.tex`-only where possible so the generated-input
    freshness test does not clash with parallel branches.

## 3. Reading order

| # | File | Why |
|---|---|---|
| 1 | `README.md`, `AGENTS.md` | Workflow, rules 1-32 |
| 2 | `docs/REVISION_PLAN.md` | The v2 plan: §2 what v2 is, §4 guardrails, §5 phases, V9-V14 data and paper phases, §9 experiment mapping, §11 the core contribution |
| 3 | `manuscript/WRITING_SPEC.md`, `manuscript/HUMAN_FEEDBACK.md` | Voice and rules (binding) |
| 4 | `docs/DECISIONS.md` | Decisions D-1..D-108 with reasons. Recent: D-99 per-function utilisation, D-100 swap rule, D-101 `eviction_aware` baseline, D-102 watchdog timer, D-103 calibration contract, D-104 memory encryption not modelled, D-105 mapped trace function, D-106 request bytes and transfer-aware deadline, D-107 shared TPM entries, D-108 memory cap on slots |
| 5 | `docs/PARAMETERS.md` | Every constant with its class (measured, trace, literature, derived, axis, swept). "pending" rows are open |
| 6 | `docs/architecture/00-overview.md` to `11-component-contracts.md` | 03 scheduling, 04 trust and security, 07 fault tolerance, 06 experiments, 10 calibration |
| 7 | `manuscript/main.tex`, `manuscript/sections/*.tex` | The paper: intro, background, design, trust, method, results, discussion, related, conclusion, appendix |
| 8 | `manuscript/generated/*.tex`, `manuscript/TODO.md` | Macros and the list of open markers (38 at the time of writing) |
| 9 | `docs/validation/development-log.md` | What the development runs found (iterations 1 and 2) |
| 10 | `docs/validation/LITERATURE_START_COSTS.md` | Verified published boot, TPM, attestation and microVM timings, for related work only |

`manuscript/README.md` still describes the v1 paper: ignore it. `manuscript/refs.bib` was written partly from memory: verify an
entry before citing it. Known gaps: `agache2020firecracker` lacks author Andreea Florescu; `ao2022faasnap` lacks its DOI.

## 4. Where the code lives (read to verify claims, never to change)

| Topic | Path |
|---|---|
| Provisioning (greedy maximisation, Erlang-B, swap rule, warm reuse) | `voss/policy/plan/` (`hetero.py`, `hetero_planner.py`) |
| Request placement | `voss/policy/place/` |
| Failure handling: timers, probes, drop estimate, detector | `voss/policy/detect.py`, `omission.py`, `retry.py`, `survival.py`, `voss/runtime/schedlib/` |
| Audit of results | `voss/policy/audit.py` |
| Keys and the holder budget | `voss/policy/keys/`, `voss/runtime/tenant_kbs.py` |
| Baselines (keep-alive, histogram, `eviction_aware`, heartbeat, etc.) | `voss/policy/keepalive_hist.py`, `configs/baselines.yaml`, `voss/runtime/reference_system.py` |
| The simulator world: hardware, network, lifecycle, workers, traces | `voss/world/` (`calibration.py`, `machines.py`, `trace_load.py`, `lifecycle.py`, `workers.py`, `workload.py`) |
| Layering rule | `voss.policy` never imports `voss.world` (enforced by import-linter) |
| Scenario and experiment config | `configs/` (`base.yaml`, `machines.yaml`, `machines_mix.yaml`, `request_bytes.yaml`, `experiments/`) |
| Experiment runner, sweeps, analysis | `experiments/` (`runner.py`, `sweep.py`, `analysis/paper_inputs.py`, `analysis/fleet_mix.py`, `analysis/machines.py`) |
| Calibration harness | `tools/calibrate/` (`node_run.sh`, `suites/`, `check_bundle.py`, `spec.py`), data in `calibration/` and `configs/calibration/measured/` |
| Trace tools | `tools/traces/` |
| Real-hardware emulation (V13) | `tools/emu/` |

## 5. Where the facts are

- **Calibration:** machines node02 (i7-12700, 64 GB, NVMe and hard-disk scratch bundles) and node04 (Haswell i7-4790S, 8 GB,
  hard disk). Per-machine write-ups: `docs/validation/node02-*.md`, `node04-*.md`. node01 is retired (guest daemon broke the
  reboot suite; see `node01-partC-failures.md`). No further machines are available: the paper states this.
- **Fleet:** one class per bundle; weights from the BOINC host survey by log-distance in (threads, memory); 57% of survey hosts are not
  represented well (radius 1), 11% are not x86 (`configs/machines_mix.yaml`, macros `\VFleet...`). TPM entries a class did not
  measure are shared from node02 (D-107) and labelled so. Memory encryption is not modelled (D-104).
- **Between-machine spread:** `experiments/analysis/machines.py` and macros `\VMach...`.
- **Trace mapping:** each trace function maps to the nearest measured (function, input size) profile by log run time; 21.9% of
  trace functions lie outside the measured range (`tools/traces/mapping.py`).
- **Literature values** are context only; never write one into a calibration bundle or present it as a measurement.

## 6. What is open and what unlocks it

`manuscript/TODO.md` groups the markers by what they wait for:

| Group | Unlocked by |
|---|---|
| calibration bundles and trace statistics | already available: replace these markers now, through new macros in `paper_inputs.py` (ask the repository owner's lead agent if a macro is missing) |
| parameter ledger | the `pending` rows of `docs/PARAMETERS.md` (about 89) resolved before the freeze |
| code revision of the results | the `v2-freeze` tag |
| emulation on real machines | V13 (`tools/emu/`) |
| held-out experiments | R01-R09, run once after the freeze |

Work you can do now, in order: (1) replace every marker whose source exists; (2) write outlines, then prose, for sections that
need no held-out result (background, design, trust, method, related work, limitations); (3) keep the remaining markers
specific ("waits for R01 deadline-met at K=4"), one per missing value; (4) re-derive the concurrency-limit definition from the code,
because D-108 caps slots by donated memory.

## 7. Check before every PR

- [ ] No forbidden word from `WRITING_SPEC.md`; no coined label.
- [ ] Every number is a macro; `paper_inputs` regenerated; `make manuscript-check` passes.
- [ ] Every new claim has a figure, table or citation that supports it; every cited source was read.
- [ ] Each paragraph opens with the concrete claim it proves; each term is defined at first use.
- [ ] The PDF is rebuilt and the PR is `.tex`/docs only unless a macro was added.
