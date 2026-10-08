"""Merge a regime file with inline config overrides (doc 05 §6: regimes are YAML)."""

from __future__ import annotations

from typing import Any

from voss.core.config import deep_merge


def merged(regime: dict[str, Any], inline: dict[str, Any]) -> dict[str, Any]:
    """Regime file values, overridden by inline values (``regime`` key kept as the name)."""
    return deep_merge(regime, inline)
