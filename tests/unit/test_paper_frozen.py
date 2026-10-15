"""P10 protocol checks (doc 06 §6, D-63): every paper spec has >= 10 seeds except the documented ones, and the specs the
committed results were produced from are unchanged (``paper/manifest.json`` holds their hashes)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from experiments import paper

REPO = Path(__file__).resolve().parents[2]
EXCEPTIONS = {"E18": {"n30k", "n100k"}}  # 3 seeds: 6-20 wall minutes and up to 9 GB per run (D-63)


def test_every_paper_spec_has_ten_seeds_or_a_documented_exception() -> None:
    for exp in paper.ORDER:
        spec = yaml.safe_load((REPO / "configs" / "experiments" / f"{exp}.yaml").read_text())
        assert len(spec["seeds"]) >= 10, exp
        short = {k for k, v in spec.get("seeds_by_system", {}).items() if len(v) < 10}
        assert short == EXCEPTIONS.get(exp, set()), exp


def test_every_experiment_spec_is_in_the_paper_or_is_the_documented_pilot() -> None:
    specs = {p.stem for p in (REPO / "configs" / "experiments").glob("E*.yaml")}
    assert specs - set(paper.ORDER) == {"E02"}


def test_committed_results_come_from_the_current_specs() -> None:
    manifest = json.loads((REPO / "paper" / "manifest.json").read_text())
    assert manifest["specs"] == paper.spec_hashes(), "a frozen spec changed after `make paper`: rerun it"
