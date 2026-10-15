# Manuscript

First draft for an IEEE Transactions submission (`IEEEtran`, journal mode). `make manuscript` regenerates and builds `main.pdf`.

- `generated/` (do not edit): macros and table fragments written by `experiments/paper_tex.py` from `paper/tables/*` and the measured bundle. The generator
  asserts (`expect`) that each result still supports the sentence it backs; if a sweep changes, it fails instead of letting the text drift.
  `tests/unit/test_manuscript.py` checks that the committed files are fresh.
- `figures/` (do not edit): drawn by `experiments/paper_figs.py` from the same tables.
- `sections/*.tex`: prose; use the macros (`\HOnePctNoneMed`, `\ViabAPThreeVoss`, ...) for every number. Macro names contain no digits.
- `refs.bib`: written from memory; **verify every entry** (entries marked "TODO verify" first) before submission.

Open items: author list and affiliations (`main.tex`), target-journal template (class options), related-work completeness, bibliography check, a real-testbed validation.
