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
- `draft/voss-draft10.pdf`: built PDF of the current draft, a rewrite for ACM TOIT in plain language with a problem-to-solution narrative, shorter text, and a
  new section on reaching the scheduler (a provider-hosted publish/subscribe broker with one topic per cluster; a provider-hosted scheduler as the alternative;
  the simulator models network delay only). Drafts 4-9 are kept for comparison.
- `ieee-draft9/`: the IEEE draft 9 sources, kept for reference. They use the old diagram files and no longer build; the PDF is `draft/voss-draft9.pdf`.
- `refs.bib`: written from memory; **verify every entry** (entries marked "TODO verify" first) before submission.

Open items: author list and affiliations (`main.tex`), related-work completeness, bibliography check, a real-testbed validation.

Length: draft 10 is 29 pages in `acmsmall` (about 25 of body, 1.5 of references, 2 of appendices) against the recommended 20-25. Trimming candidates, least
important first: Appendix B (move it online), the planner and fault tables in the results, the attestation figure.
