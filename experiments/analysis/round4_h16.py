"""H16 (E25): planner advantage over the best single loop by mean session length M and Weibull shape k, and survival
dependence (greedy vs survival-blind greedy). Reads the per-run CSV ``paper/tables/E25_runs.csv`` (written by
``experiments.analysis.round4 E25 <csv>``); the computation lives in ``round4`` (shared with ``paper_tex.round4``)."""

import pandas as pd

from experiments.analysis.round4 import E25_SHAPES, e25_cells, e25_differences, e25_table

if __name__ == "__main__":
    df = e25_cells(pd.read_csv("paper/tables/E25_runs.csv"))
    print(e25_table(df).round(3).to_string())
    for k in E25_SHAPES:
        for m, (mean, lo, hi) in e25_differences(df, k).items():
            print(f"shape {k}: A(M=1) - A(M={m:g}) = {mean:.3f} [{lo:.3f},{hi:.3f}]")
