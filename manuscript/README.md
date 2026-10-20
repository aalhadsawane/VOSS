# Manuscript

First draft for an IEEE Transactions submission (`IEEEtran`, journal mode). `make manuscript` regenerates and builds `main.pdf`.

- `generated/` (do not edit): macros and table fragments written by `experiments/paper_tex.py` from `paper/tables/*` and the measured bundle. The generator
  asserts (`expect`) that each result still supports the sentence it backs; if a sweep changes, it fails instead of letting the text drift.
  `tests/unit/test_manuscript.py` checks that the committed files are fresh.
- `figures/` (do not edit): drawn by `experiments/paper_figs.py` from the same tables.
- `sections/*.tex`: prose, in the order introduction, background and problem, related work, system overview, trust, scheduling, fault tolerance, simulator and protocol, evaluation (by research question), discussion; use the macros (`\HOnePctNoneMed`, `\ViabAPThreeVoss`, ...) for every number. Macro names contain no digits.
- `diagrams/*.tex`, `diagram-styles.tex`: TikZ figures (architecture, invocation sequence, session and start-up tiers, attestation, control loops, failover); compile one on its own with a `standalone` wrapper to iterate on layout.
- `draft/voss-draft8.pdf`: built PDF of the current draft (25 pages): terminology and definitions added, the time to an attested worker corrected to 65 s from power-on (44 s was measured from kernel start), key-broker ownership and verifier trust stated, idempotence, planner sizes and charged decision latency disclosed, and E01 reported (drafts 4-7 kept for comparison) (rebuild with `make manuscript`).
- `refs.bib`: written from memory; **verify every entry** (entries marked "TODO verify" first) before submission.

Open items: author list and affiliations (`main.tex`), target-journal template (class options), related-work completeness, bibliography check, a real-testbed validation.

Length: the draft is 24 pages. Trimming candidates, least important first: the geo-clustering table (results RQ6), the scalability table, the soft-state table in the fault-tolerance section, the hedging and adversary table rows for the `all` regime, and the calibration table (keep the figure).
