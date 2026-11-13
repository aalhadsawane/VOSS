"""check_bundle enforces the calibration data contract (plan V1 step 8)."""

from __future__ import annotations

from pathlib import Path

import yaml
from tools.calibrate import check_bundle as cb
from tools.calibrate.suites.sebs import SIZES

REPO = Path(__file__).resolve().parents[2]


def _good(root: Path) -> Path:
    b = root / "bundle"
    b.mkdir()
    dists = {k: {"tag": "measured"} for k in [*cb.REQUIRED, *cb.CONSTANTS]}
    fits = {k: {"n": float(n)} for k, n in cb.REQUIRED.items()}
    times = iter([5e-4, 20.0])
    fns = {
        fn: {
            "exec_by_size": {s: {"median_s": next(times, 0.01), "n": 30, "sebs_class": c} for s, c in sizes},
            "rss_mb": 300.0,
            "snapshot_mb": 256.0,
            "init_s": 0.1,
        }
        for fn, sizes in SIZES.items()
    }
    (b / "distributions.yaml").write_text(yaml.safe_dump({"distributions": dists}))
    (b / "fits.yaml").write_text(yaml.safe_dump(fits))
    (b / "functions.yaml").write_text(yaml.safe_dump({"functions": fns}))
    return b


def test_a_complete_bundle_passes(tmp_path: Path) -> None:
    assert cb.main([str(_good(tmp_path))]) == 0


def test_missing_samples_functions_and_sizes_are_errors(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    b = _good(tmp_path)
    fits = yaml.safe_load((b / "fits.yaml").read_text())
    fits["tpm2_quote"]["n"] = 12.0
    (b / "fits.yaml").write_text(yaml.safe_dump(fits))
    fns = yaml.safe_load((b / "functions.yaml").read_text())
    del fns["functions"]["uploader"]
    fns["functions"]["graph-bfs"]["exec_by_size"].pop(10)
    (b / "functions.yaml").write_text(yaml.safe_dump(fns))
    assert cb.main([str(b)]) == 1
    out = capsys.readouterr().out
    assert "tpm2_quote: n=12.0 < 200" in out and "function uploader: missing" in out
    assert "function graph-bfs: no handler time at size 10" in out


def test_narrow_span_is_a_warning_and_numbers_keep_their_exponent(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    b = _good(tmp_path)
    fns = yaml.safe_load((b / "functions.yaml").read_text())
    for prof in fns["functions"].values():
        for row in prof["exec_by_size"].values():
            row["median_s"] = 2.5e-05
    (b / "functions.yaml").write_text(yaml.safe_dump(fns))
    assert cb.main([str(b)]) == 0
    assert "span 2.5e-05-2.5e-05 s" in capsys.readouterr().out


def test_the_existing_spec_file_has_every_contract_field() -> None:
    assert cb.check_spec(REPO / "calibration" / "specs" / "i7-12700-64g") == []
