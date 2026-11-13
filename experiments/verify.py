"""Re-run a sample of a finished experiment and compare result hashes (docs/REVISION_PLAN.md V6, ``verify.yml``).

The configs are rebuilt from the spec at the current commit, so a match also checks that the spec, the code and the
calibration still produce the reported runs.
``python -m experiments.verify <spec> results/<spec>-<run id>/hashes.csv --frac 0.1 --salt <run id>``.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd
from voss.core.rng import stream
from voss.runtime.system import run_system

from experiments.sweep import plan


def sample(runs: list[str], frac: float, salt: int) -> list[str]:
    """A deterministic sample of ``max(1, ceil(frac·n))`` runs, chosen by ``salt``."""
    k = min(len(runs), max(1, math.ceil(frac * len(runs))))
    pick = stream(salt, "verify.sample").choice(len(runs), size=k, replace=False)
    return sorted(runs[i] for i in pick)


def verify(spec: str, hashes: Path, frac: float, salt: int) -> pd.DataFrame:
    """One row per sampled run: expected and recomputed result hash."""
    want = pd.read_csv(hashes, dtype=str).set_index("run")
    _, cfgs = plan(spec, Path("runs"))
    by_run = {c.config_hash()[:16]: c for c in cfgs}
    rows = []
    for run in sample(sorted(want.index), frac, salt):
        got = run_system(by_run[run]).recorder.result_hash() if run in by_run else "missing-from-spec"
        rows.append({"run": run, "expected": want.loc[run, "result_hash"], "got": got})
    df = pd.DataFrame(rows)
    return df.assign(ok=df.expected == df.got)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("spec")
    p.add_argument("hashes", type=Path)
    p.add_argument("--frac", type=float, default=0.1)
    p.add_argument("--salt", type=int, default=0)
    a = p.parse_args()
    df = verify(a.spec, a.hashes, a.frac, a.salt)
    print(df.to_string(index=False))
    if not df.ok.all():
        raise SystemExit(f"{(~df.ok).sum()} of {len(df)} runs do not reproduce")


if __name__ == "__main__":
    main()
