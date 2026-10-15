"""The committed ``manuscript/generated`` files equal a fresh run of the generator, so the paper text cannot drift
from the result tables (doc 06 §6; D-65). Regenerate with ``make manuscript-gen``."""

from __future__ import annotations

from pathlib import Path

from experiments import paper_tex

GENERATED = Path(__file__).resolve().parents[2] / "manuscript" / "generated"


def test_generated_files_are_fresh(tmp_path: Path) -> None:
    paper_tex.main(["--out", str(tmp_path)])
    fresh = {p.name: p.read_text() for p in tmp_path.iterdir()}
    committed = {p.name: p.read_text() for p in GENERATED.iterdir()}
    assert fresh.keys() == committed.keys()
    stale = sorted(n for n in fresh if fresh[n] != committed[n])
    assert not stale, f"stale manuscript files {stale}: run `make manuscript-gen` and commit"


def test_macro_names_are_latex_safe() -> None:
    g = paper_tex.build()
    assert all(n.isalpha() for n in g.macros), [n for n in g.macros if not n.isalpha()]
    assert len(g.macros) > 100
