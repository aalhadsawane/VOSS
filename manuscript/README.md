# Manuscript

Draft for **ACM Transactions on Internet Technologies** (`acmart`, `acmsmall`, journal template). `make manuscript` regenerates and builds `main.pdf`
(needs `acmart` plus the Libertine and newtx fonts, for example Debian `texlive-fonts-extra` and `texlive-plain-generic`).

- `generated/` (do not edit): macros and table fragments written by `experiments/paper_tex.py` from `paper/tables/*` and the measured bundle. The generator
  asserts (`expect`) that each result still supports the sentence it backs; if a sweep changes, it fails instead of letting the text drift.
  `tests/unit/test_manuscript.py` checks that the committed files are fresh.
- `figures/` (do not edit): drawn by `experiments/paper_figs.py` from the same tables.
- `sections/*.tex`: prose, in the order introduction, background and problem, system design, trust, scheduling, reaching the scheduler (broker networking and
  scheduler placement), fault tolerance, evaluation method, results (by question), discussion and limits, related work, conclusion, appendix (reproduction,
  hypothesis summary; draft 13 no longer includes the trust and appendix sections). Use the macros (`\HOnePctNoneMed`, `\ViabAPThreeVoss`, ...) for every number; macro names contain no digits.
  Style rule for this version: every paragraph follows from the problem or motivation just stated, terms are explained at first use, and equations are kept to the few the argument needs.
- `diagrams/*.tex`, `diagram-styles.tex`: TikZ figures sized for the 139 mm `acmsmall` column (architecture with the broker, session and start-up levels,
  attestation, control loops, failover, broker topics). Compile one on its own with a `standalone` wrapper to iterate on layout.
  `diagrams/lifecycle.tex` is kept but no longer included in the text.
- `draft/voss-draft13.pdf`: built PDF of the current draft (21 pages in `acmsmall`, references included). Draft 13 is the round-4 rewrite: the slow
  planner is compared with strong single-loop baselines (fixed and unbounded keep-alive, Azure-style histogram) in E04b; the paper stresses state that
  lasts across many requests; page budget goes to the planner, session state, key exposure, failure detection and the two architectures, and attestation
  and TPM quotes are cut to a short background. Request placement was corrected (D-78), and E10b, E17b, E20ab, E24b and the session-length
  experiment E25 supply the numbers in the baseline, feasibility and calibration paragraphs. Older drafts are kept for comparison.
- `ieee-draft9/`: the IEEE draft 9 sources, kept for reference. They use the old diagram files and no longer build; the PDF is `draft/voss-draft9.pdf`.
- `HUMAN_FEEDBACK.md`: the author's review feedback with how each point was fixed, and the heuristics and style preferences drawn from it. **Read it before editing the text, and append to it after every feedback round.**
- `../docs/EXPERIMENT_TODO.md`: review feedback that needs new measurements or code changes (multi-machine calibration, per-step start-up times, Figure 1 redraw). Planning only.
- `refs.bib`: written from memory; **verify every entry** (entries marked "TODO verify" first) before submission.

Open items: author list and affiliations (`main.tex`), related-work completeness, bibliography check, a real-testbed validation.

Length: draft 13 is 21 pages against the 20-25 target.
