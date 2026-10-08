"""Repository paths and data-file loading (doc 05 §1: data over code)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS = REPO_ROOT / "configs"


def config_path(p: str | Path) -> Path:
    """Resolve a config-relative path: absolute paths stay, ``configs/...`` and bare names resolve from the repo."""
    path = Path(p)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "configs":
        return REPO_ROOT / path
    return CONFIGS / path


def load_data_yaml(p: str | Path) -> dict[str, Any]:
    """Load a data YAML, dropping its ``provenance`` block (AGENTS.md rule 13 tags live there)."""
    data = yaml.safe_load(config_path(p).read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{p}: top level must be a mapping")
    data.pop("provenance", None)
    return data
