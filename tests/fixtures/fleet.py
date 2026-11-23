"""Test fixtures shared by the unit and integration tests (not used by reported runs).

``FLEET`` is a calibrated fleet over the two measured machine models with a tiny synthetic survey under
``tests/fixtures/fleet``; it lets a test generate workers without the gitignored survey data (D-107).
"""

from __future__ import annotations

from typing import Any

BUNDLES = (
    "node02-i7-12700-64g-nvme_nvme",
    "node02-i7-12700-64g-nvme_hdd",
    "node04-i7-4790s-8g-hdd_hdd",
)
CALIBRATION = "configs/calibration/measured/node02-i7-12700-64g-nvme_nvme"
FLEET: dict[str, Any] = {"bundles": list(BUNDLES), "survey": "test", "trace_root": "tests/fixtures/fleet"}
PLACEHOLDER = "tests/fixtures/calibration/placeholder/c0"
