"""The decision clock charges measured provider coefficients (docs/REVISION_PLAN.md V10)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from voss.core.config import DecisionClockConfig
from voss.core.decision_clock import DecisionClock


def test_the_clock_charges_the_coefficients_of_the_file(tmp_path: Path) -> None:
    f = tmp_path / "decision.yaml"
    coeffs = {"plan": [0.5, 0.01], "place": [0.001, 2e-6], "route": [1e-7, 0.0], "verify": [0.0, 9e-5]}
    f.write_text(yaml.safe_dump({"coeffs": coeffs}))
    cfg = DecisionClockConfig.model_validate({"coeffs_file": str(f)})
    assert cfg.coeffs["plan"] == (0.5, 0.01) and cfg.coeffs["place"] == (0.001, 2e-6)
    clock = DecisionClock(cfg)
    assert clock.charge("plan", work=100) == pytest.approx(0.5 + 0.01 * 100)
    assert clock.charge("place", work=10, host_speed=2.0) == pytest.approx((0.001 + 2e-5) / 2)
    assert clock.charge("verify", work=10) == pytest.approx(9e-4)


def test_a_file_that_misses_a_charged_kind_is_rejected(tmp_path: Path) -> None:
    f = tmp_path / "decision.yaml"
    f.write_text(yaml.safe_dump({"coeffs": {"plan": [0.5, 0.01]}}))
    with pytest.raises(ValueError, match="place"):
        DecisionClockConfig.model_validate({"coeffs_file": str(f)})


def test_without_a_file_the_seed_coefficients_stay() -> None:
    assert DecisionClockConfig().coeffs["plan"] == (0.02, 5e-5)
