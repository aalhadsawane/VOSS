"""``python -m experiments.figures [--exp E19]``: render registered figures whose runs exist (``make figs``)."""

from __future__ import annotations

import argparse
from pathlib import Path

from experiments.figures import FIGURES, load_all, render


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--exp", default=None)
    p.add_argument("--runs", type=Path, default=Path("runs"))
    p.add_argument("--out", type=Path, default=Path("figures"))
    a = p.parse_args()
    load_all()
    for name in sorted(FIGURES):
        spec = FIGURES[name]
        if a.exp is not None and spec.exp != a.exp:
            continue
        path = render(spec, a.runs, a.out)
        print(f"{name}: {path if path is not None else 'no runs yet (make sweep EXP=' + spec.exp + ')'}")


if __name__ == "__main__":
    main()
