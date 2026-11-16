"""Quality rules (AGENTS.md rule 11): modules < 400 lines, functions < 50 lines, docstrings on modules."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = sorted(
    p for d in ("voss", "experiments", "tools") for p in (REPO / d).rglob("*.py") if "__pycache__" not in p.parts
)


def test_module_length() -> None:
    long = [str(p.relative_to(REPO)) for p in SOURCES if len(p.read_text().splitlines()) >= 400]
    assert not long, f"modules >= 400 lines: {long}"


def test_function_length() -> None:
    bad = []
    for p in SOURCES:
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                n = (node.end_lineno or node.lineno) - node.lineno + 1
                if n >= 50:
                    bad.append(f"{p.relative_to(REPO)}:{node.lineno} {node.name} ({n})")
    assert not bad, f"functions >= 50 lines: {bad}"


def test_module_docstrings() -> None:
    missing = [str(p.relative_to(REPO)) for p in SOURCES if ast.get_docstring(ast.parse(p.read_text())) is None]
    assert not missing, f"modules without docstrings: {missing}"


def test_randomness_follows_the_run_seed() -> None:
    """AGENTS.md rule 9: every stream in the simulator and the scheduler derives from the run seed; a literal master
    seed (as provisioning's failure scenarios once used) would give every seed the same draws."""
    import re

    lit = re.compile(r"\bstream\(\s*\d+\s*,|RngFactory\(\s*\d+\s*\)")
    sim = [p for p in SOURCES if p.relative_to(REPO).parts[0] == "voss" and p.relative_to(REPO).parts[1] != "core"]
    bad = [str(p.relative_to(REPO)) for p in sim if lit.search(p.read_text())]
    assert not bad, f"literal master seeds: {bad}"
