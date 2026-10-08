"""Every data YAML carries a provenance block (AGENTS.md rule 13: literature/assumed/measured tags)."""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
DATA_DIRS = ("substrates", "hardware", "regimes", "calibration")


def test_data_files_have_provenance() -> None:
    files = [CONFIGS / "functions.yaml", CONFIGS / "tenants.yaml"]
    for d in DATA_DIRS:
        files += sorted((CONFIGS / d).rglob("*.yaml"))
    missing = []
    for f in files:
        data = yaml.safe_load(f.read_text())
        prov = data.get("provenance") if isinstance(data, dict) else None
        if not prov or prov.get("default") not in ("measured", "literature", "assumed"):
            missing.append(str(f.relative_to(CONFIGS)))
    assert not missing, missing
