"""check_bundle enforces the calibration data contract (plan V1 step 8)."""

from __future__ import annotations

from pathlib import Path

import yaml
from tools.calibrate import check_bundle as cb
from tools.calibrate.suites.sebs import SIZES

REPO = Path(__file__).resolve().parents[2]


def _good(root: Path) -> Path:
    b = root / "bundle"
    b.mkdir(parents=True)
    dists = {k: {"tag": "measured"} for k in [*cb.REQUIRED, *cb.RATIOS, *cb.simulator_entries()]}
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
    hw = {"classes": {"C0": {"ssd_read_MBps": 6000.0, "ssd_write_MBps": 4000.0}}}
    (b / "hardware.yaml").write_text(yaml.safe_dump(hw))
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


def test_placeholder_entries_are_reported_missing(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A bundle entry the simulator reads that still holds the placeholder (tag assumed) is an error, by name."""
    b = _good(tmp_path)
    d = yaml.safe_load((b / "distributions.yaml").read_text())
    d["distributions"]["dispatch"] = {"tag": "assumed", "dist": "lognormal", "median": 0.002, "sigma": 0.3}
    del d["distributions"]["tme_cpu_factor"]
    (b / "distributions.yaml").write_text(yaml.safe_dump(d))
    (b / "hardware.yaml").write_text(yaml.safe_dump({"classes": {}}))
    assert cb.unmeasured(d["distributions"]) == ["dispatch"]  # TME factors are not read (D-104)
    assert cb.main([str(b)]) == 1
    out = capsys.readouterr().out
    assert "dispatch: missing, not measured (the bundle holds the placeholder, tag assumed)" in out
    assert "tme_cpu_factor" not in out
    assert "hardware C0 ssd_read_MBps: missing" in out


def test_unused_entries_are_not_demanded() -> None:
    """Rule 32: entries no substrate or simulator code reads are not part of the contract check (D-103)."""
    for gone in ("drtm_launch", "image_mem_mb", "boot_total", "boot_firmware", "fn_corun_mixed"):
        assert gone not in cb.REQUIRED and gone not in cb.simulator_entries()


def test_tpm_entries_shared_from_the_reference_are_not_errors(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """D-107: a class without a TPM takes tpm2_quote, tpm2_unseal and verify_s from the reference bundle."""
    ref = _good(tmp_path / "ref")
    b = _good(tmp_path / "node")
    d = yaml.safe_load((b / "distributions.yaml").read_text())
    for key in cb.TPM_KEYS:
        d["distributions"][key] = {"tag": "assumed", "dist": "constant", "value": 0.0}
    (b / "distributions.yaml").write_text(yaml.safe_dump(d))
    shared: list[str] = []
    assert cb.check_distributions(b, ref, shared) == []
    assert {s.split(":")[0] for s in shared} == set(cb.TPM_KEYS)
    assert cb.main([str(b), "--shared-from", str(ref)]) == 0
    out = capsys.readouterr().out
    assert "SHARED tpm2_quote: shared from" in out


def test_sharing_does_not_hide_another_missing_entry(tmp_path: Path) -> None:
    """Only the TPM entries are shared; a missing dispatch remains an error."""
    ref = _good(tmp_path / "ref")
    b = _good(tmp_path / "node")
    d = yaml.safe_load((b / "distributions.yaml").read_text())
    for key in cb.TPM_KEYS:
        d["distributions"][key] = {"tag": "assumed", "dist": "constant", "value": 0.0}
    d["distributions"]["dispatch"] = {"tag": "assumed", "dist": "constant", "value": 0.0}
    (b / "distributions.yaml").write_text(yaml.safe_dump(d))
    errors = cb.check_distributions(b, ref)
    assert any(e.startswith("dispatch: missing") for e in errors)
    assert not any(e.startswith("tpm2_quote:") for e in errors)
