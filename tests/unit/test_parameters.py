"""The parameter ledger (docs/PARAMETERS.md, plan V0.6) lists exactly the existing configuration keys and data files."""

from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from voss.core.config import RunConfig
from voss.policy.plan.types import PlanParams

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "docs" / "PARAMETERS.md"
CLASSES = re.compile(r"^(M|T|L|D|A|S|pending( V[\d/V]+)?)$")


def _keys(model: type[BaseModel], prefix: str = "") -> list[str]:
    out: list[str] = []
    for name, f in model.model_fields.items():
        key, ann = f"{prefix}{f.alias or name}", f.annotation
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            out += _keys(ann, key + ".")
        else:
            out.append(key)
    return out


def _rows() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in LEDGER.read_text().splitlines():
        m = re.match(r"^\| `([^`]+)` \|(.*)\|\s*$", line)
        if m:
            rows[m.group(1)] = [c.strip() for c in m.group(2).split("|")]
    return rows


def _data_files() -> set[str]:
    return {
        str(p.relative_to(REPO))
        for p in (REPO / "configs").rglob("*.yaml")
        if "calibration" not in p.parts and "experiments" not in p.parts
    }


def test_every_config_key_has_exactly_one_row() -> None:
    keys = set(_keys(RunConfig)) | {f"voss.planner.params.{f.name}" for f in fields(PlanParams)}
    listed = {k for k in _rows() if not k.startswith("configs/")}
    assert sorted(keys - listed) == [], "add these keys to docs/PARAMETERS.md"
    assert sorted(listed - keys) == [], "these ledger rows name keys that no longer exist"


def test_every_data_file_has_exactly_one_row() -> None:
    listed = {k for k in _rows() if k.startswith("configs/")}
    files = _data_files()
    assert sorted(files - listed) == [], "add these data files to docs/PARAMETERS.md"
    assert sorted(listed - files) == [], "these ledger rows name files that no longer exist"


def test_every_row_has_a_valid_class() -> None:
    bad: list[Any] = []
    for key, cols in _rows().items():
        cls = cols[-2] if not key.startswith("configs/") else cols[0]
        if not CLASSES.match(cls):
            bad.append((key, cls))
    assert bad == []
