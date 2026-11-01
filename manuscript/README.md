# Manuscript

Draft for **ACM Transactions on Internet Technologies** (`acmart`, `acmsmall`, journal template). `make manuscript` regenerates and builds `main.pdf`
(needs `acmart` plus the Libertine and newtx fonts, for example Debian `texlive-fonts-extra` and `texlive-plain-generic`).

- `generated/` (do not edit): macros and table fragments written by `experiments/paper_tex.py` from `paper/tables/*` and the measured bundle. The generator
  asserts (`expect`) that each result still supports the sentence it backs; if a sweep changes, it fails instead of letting the text drift.
  `tests/unit/test_manuscript.py` checks that the committed files are fresh.
- `figures/` (do not edit): drawn by `experiments/paper_figs.py` from the same tables.
- `sections/*.tex`: prose, in the order introduction, background and problem, system design, trust, scheduling, reaching the scheduler (broker networking and
  scheduler placement), fault tolerance, evaluation method, results (by question), discussion and limits, related work, conclusion, appendix (reproduction,
  hypothesis summary). Use the macros (`\HOnePctNoneMed`, `\ViabAPThreeVoss`, ...) for every number; macro names contain no digits.
  Style rule for this version: every paragraph follows from the problem or motivation just stated, terms are explained at first use, and equations are kept to the few the argument needs.
- `diagrams/*.tex`, `diagram-styles.tex`: TikZ figures sized for the 139 mm `acmsmall` column (architecture with the broker, session and start-up levels,
  attestation, control loops, failover, broker topics). Compile one on its own with a `standalone` wrapper to iterate on layout.
  `diagrams/lifecycle.tex` is kept but no longer included in the text.
- `draft/voss-draft12.pdf`: built PDF of the current draft. Draft 12 answers the round-3 review (`docs/critique/CRITIQUE.md` C-34 to C-45):
  plain, direct wording with one defined name per thing; why two loops (how often inputs change and how long decisions last); encryption at rest
  before the key service; mutual TLS and the certificate lifecycle; the two architectures (global on provider hardware, clustered with a broker);
  the router's role; end-to-end signed broker messages (MQTT-I); slow volunteer links; why exposure is kept; each estimator justified against
  alternatives; new related work (two-timescale edge scheduling, Falcon, ALPS). Results are unchanged from draft 11. Drafts 4-11 are kept for comparison.
- `ieee-draft9/`: the IEEE draft 9 sources, kept for reference. They use the old diagram files and no longer build; the PDF is `draft/voss-draft9.pdf`.
- `refs.bib`: written from memory; **verify every entry** (entries marked "TODO verify" first) before submission.

Open items: author list and affiliations (`main.tex`), related-work completeness, bibliography check, a real-testbed validation.

Length: draft 12 is 34 pages in `acmsmall` (about 30 of body) against the recommended 20-25. Trimming candidates, least important first: Appendix B (move it online), the planner and fault tables in the results, the attestation figure, the information-horizon table.