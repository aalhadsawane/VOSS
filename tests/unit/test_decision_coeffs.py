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


def test_without_a_file_no_seed_coefficients_are_used() -> None:
    """Checklist 2.11: unit tests pass their own coefficients; the config has no seed default."""
    assert DecisionClockConfig().coeffs == {}
    own = DecisionClockConfig(coeffs={"plan": (0.02, 5e-5)})
    assert own.coeffs["plan"] == (0.02, 5e-5)


def test_the_base_config_charges_the_measured_provider_coefficients() -> None:
    """V10 exit: every run built on configs/base.yaml charges the coefficients timed on the provider CPU."""
    from voss.core.config import DECISION_KINDS, load_config
    from voss.core.paths import REPO_ROOT, config_path

    cfg = load_config(REPO_ROOT / "configs" / "base.yaml")
    dc = cfg.decision_clock
    assert dc.coeffs_file.startswith("calibration/provider/")
    measured = yaml.safe_load(config_path(dc.coeffs_file).read_text())
    assert measured["provenance"]["default"] == "measured"
    for kind in DECISION_KINDS:
        a, b = measured["coeffs"][kind]
        assert dc.coeffs[kind] == (float(a), float(b))
    clock = DecisionClock(dc)
    a, b = dc.coeffs["place"]
    assert clock.charge("place", work=1000) == pytest.approx(a + b * 1000)
