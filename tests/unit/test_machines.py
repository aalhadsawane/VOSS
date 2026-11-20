"""T11 measurements come from the merged bundles and raw records (experiments/analysis/machines.py)."""

from __future__ import annotations

from experiments.analysis import machines as m


def test_repeatability_and_class_ratios_cover_every_function() -> None:
    cov = m.repeat_cov(m.REFERENCE)
    assert len(cov) >= 40 and (cov >= 0).all()
    ratios = m.class_ratios(m.OTHER, m.REFERENCE)
    assert len(ratios) == 10 and all(len(r) >= 3 and min(r) > 0 for r in ratios.values())
    values: dict[str, float | int | str] = {}
    m.machines(values)
    assert values["MachRatioSpread"] == values["MachRatioHi"] / values["MachRatioLo"]  # type: ignore[operator]
