"""Mechanical checks of the manuscript text (manuscript/WRITING_SPEC.md §4.2 and §5; plan V14).

Draft markers (``\\critical``, ``\\todo``) are allowed in the working text and forbidden when ``VOSS_SUBMISSION=1``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml
from experiments.analysis import calibration, paper_inputs
from experiments.analysis import traces as trace_stats
from experiments.analysis.macros import render

MS = Path(__file__).resolve().parents[2] / "manuscript"
FILES = [*sorted((MS / "sections").glob("*.tex")), MS / "main.tex"]

FORBIDDEN = [
    r"planner", r"slow loop", r"fast loop", r"single-loop", r"two-timescale", r"\bslots?\b", r"exposure",
    r"trust score", r"trust technology", r"start-up level", r"filler", r"early keys", r"perishable", r"referee",
    r"the front\b", r"judg", r"returned work", r"second copy", r"hedg", r"\bclusters?\b", r"broker", r"blockchain",
    r"\bE\d\d[a-z]*\b", r"\bH\d+\b", r"\bR\d\d\b", r"\brounds?\b(?![- ]trip)", r"rerun", r"placeholder", r"shipped",
    r"pre-registered", r"frozen", r"the world\b", r"Lambda-like", r"Azure-like",
]  # fmt: skip
PATTERNS = {
    "rhetorical question": r"\?\s",
    "sentence opening with And or So": r"(?:^|[.!]\s+)(?:And|So)\s",
    "'about' before a generated number": r"\babout\s+\\V[A-Za-z]+",
}
MARKERS = r"\\critical|\\potrem|\\todo\{|\\todoitem|TODO"


def prose(path: Path) -> str:
    """Text without comments, macro definitions and citation or label keys."""
    lines = [re.sub(r"(?<!\\)%.*", "", ln) for ln in path.read_text().splitlines()]
    text = "\n".join(ln for ln in lines if not ln.lstrip().startswith("\\newcommand"))
    return re.sub(r"\\(?:cite[a-z]*|ref|label|input|bibliography)\{[^}]*\}", "", text)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_forbidden_terms_or_patterns(path: Path) -> None:
    text = prose(path)
    found = [t for t in FORBIDDEN if re.search(t, text, re.IGNORECASE)]
    found += [name for name, rx in PATTERNS.items() if re.search(rx, text, re.MULTILINE)]
    assert not found, f"{path.name}: {found}"


@pytest.mark.skipif(os.environ.get("VOSS_SUBMISSION") != "1", reason="draft markers are allowed in the working text")
@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_draft_markers_in_a_submission(path: Path) -> None:
    assert not re.search(MARKERS, prose(path))


def test_numbers_in_the_abstract_are_macros() -> None:
    text = prose(MS / "main.tex")
    abstract = text[text.index("\\begin{abstract}") : text.index("\\end{abstract}")]
    abstract = re.sub(r"\\todoitem\{T\d+\}\{[^}]*\}\{[^}]*\}", "", abstract)
    assert not re.search(r"\d", abstract), "type no number in the abstract: use a generated macro"


def test_every_figure_and_table_is_referenced() -> None:
    text = "\n".join(p.read_text() for p in FILES)
    labels = set(re.findall(r"\\label\{((?:fig|tab|alg):[^}]+)\}", text))
    refs = set(re.findall(r"\\ref\{([^}]+)\}", text))
    assert labels <= refs, f"never referenced: {sorted(labels - refs)}"


def test_generated_inputs_are_fresh() -> None:
    assert (MS / "generated" / "inputs.tex").read_text() == render(paper_inputs.build())
    assert (MS / "generated" / "constants.tex").read_text() == paper_inputs.constants_table()
    for name, render_table in paper_inputs.TABLES.items():
        assert (MS / "generated" / name).read_text() == render_table(), name
    assert (MS / "TODO.md").read_text() == paper_inputs.todo_list()


def test_calibration_macros_come_from_the_bundles() -> None:
    """T03-T05, T09, T13, T26, T44, T49: the machine and cost macros are the bundles' measured medians."""
    values = paper_inputs.build()
    assert values["MachCount"] == len(calibration.MACHINES) == 2
    assert values["MachClasses"] == len(calibration.CLASSES) == 3
    assert values["MachProcClasses"] == 2
    assert values["MachFns"] == len(calibration.functions(calibration.REFERENCE)) == 10
    assert values["MachPairs"] == sum(
        len(f["exec_by_size"]) for f in calibration.functions(calibration.REFERENCE).values()
    )
    assert calibration.power_on_s(calibration.REFERENCE) == pytest.approx(39.75, abs=0.01)
    assert calibration.power_on_s("node04-i7-4790s-8g-hdd_hdd") == pytest.approx(27.47, abs=0.01)
    assert calibration.measured(calibration.REFERENCE, "fc_boot") * 1e3 == pytest.approx(44.07, abs=0.01)
    assert calibration.measured("node04-i7-4790s-8g-hdd_hdd", "fc_boot") * 1e3 == pytest.approx(75.65, abs=0.01)
    assert values["MachPowerOnHi"] == round(calibration.power_on_s(calibration.REFERENCE))
    assert values["MachBootHi"] == round(calibration.measured("node04-i7-4790s-8g-hdd_hdd", "fc_boot") * 1e3)


def test_trace_macros_come_from_the_committed_summary() -> None:
    """T08 and T15: the summary is the release's, and the macros are its statistics."""
    summary = trace_stats.load()
    prov = yaml.safe_load(trace_stats.PROVENANCE.read_text())
    assert summary["source"] == trace_stats.RELEASE
    assert summary["splits"]["dev"]["sha256"] == prov["outputs"]["sessions_dev.parquet"]
    assert summary["splits"]["heldout"]["sha256"] == prov["outputs"]["sessions_heldout.parquet"]
    values = paper_inputs.build()
    assert values["TraceIntervalMedianLoMin"] == round(summary["splits"]["dev"]["median_h"] * 60)
    assert values["TraceAvailableHiPct"] == round(summary["splits"]["dev"]["available_frac"] * 100)


def test_todo_ids_are_unique() -> None:
    ids = [m for p in FILES for m in re.findall(r"\\todoitem\{(T\d+)\}", p.read_text())]
    assert len(ids) == len(set(ids)) and ids, "every to-do marker has its own id"


def test_every_macro_used_is_defined() -> None:
    defined = set(re.findall(r"\\newcommand\{\\(V[A-Za-z]+)\}", (MS / "generated" / "inputs.tex").read_text()))
    used = {m for p in FILES for m in re.findall(r"\\(V[A-Z][A-Za-z]+)\b", prose(p))}
    assert used <= defined, f"undefined macros: {sorted(used - defined)}"
