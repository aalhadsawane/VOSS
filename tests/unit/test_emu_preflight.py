"""Preflight of the emulation host (plan V13): missing capabilities are one-line messages with a fix, before anything
starts. The checks that need root, a TPM or /dev/kvm are exercised through their pure parts.
"""

from __future__ import annotations

import platform
from pathlib import Path

import pytest
from tools.emu import preflight
from tools.emu import scenario as spec_mod
from tools.emu.topology import KIND_PERFORMANCE, Cpu, Topology


def test_off_linux_the_run_is_refused_with_one_line() -> None:
    spec = spec_mod.load("configs/emu/s1_central.yaml")
    problems = preflight.check(spec, spec.run_config("voss", 1), isolation=False, tpm=False)
    if platform.system() == "Linux":
        pytest.skip("this test checks the non-Linux message")
    assert len(problems) == 1 and problems[0].level == "fail" and "not Linux" in problems[0].what


def test_every_problem_names_a_fix() -> None:
    p = preflight.Problem("fail", "/dev/kvm is missing", "enable VT-x")
    assert p.line().startswith("[FAIL] /dev/kvm is missing")
    assert "fix: enable VT-x" in p.line()


def test_a_host_with_too_few_cores_is_a_blocking_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = spec_mod.load("configs/emu/s1_central.yaml")
    tiny = Topology(tuple(Cpu(i, i, 0, KIND_PERFORMANCE) for i in range(3)))
    monkeypatch.setattr(preflight, "read_topology", lambda: tiny)
    problems = preflight._layout(spec)
    assert len(problems) == 1 and problems[0].level == "fail"
    assert "need 8 P core" in problems[0].what and "emu.workers" in problems[0].fix


def test_enough_cores_is_not_a_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = spec_mod.load("configs/emu/s1_central.yaml")
    ok = Topology(tuple(Cpu(i, i, 0, KIND_PERFORMANCE) for i in range(16)))
    monkeypatch.setattr(preflight, "read_topology", lambda: ok)
    assert preflight._layout(spec) == []


def test_no_real_tpm_is_a_warning_only_when_it_was_switched_off() -> None:
    assert preflight._tpm(False)[0].level == "warn"
    if not Path("/dev/tpmrm0").exists() and not Path("/dev/tpm0").exists():
        assert preflight._tpm(True)[0].level == "fail"


def test_a_full_disk_is_a_blocking_problem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil as sh

    monkeypatch.setattr(sh, "disk_usage", lambda _p: type("U", (), {"free": 10 * 2**30})())
    problems = preflight._disk(tmp_path)
    assert problems and problems[0].level == "fail" and "50 GB" in problems[0].fix


def test_the_traced_inputs_are_named_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = spec_mod.load("configs/emu/s1_central.yaml")
    cfg = spec.run_config("voss", 1)
    problems = preflight._inputs(cfg)
    assert problems and all(p.level == "fail" and "data/traces" in p.what for p in problems)
    assert any("hosts.parquet" in p.what for p in problems)  # the fleet survey
    assert any("sessions_dev.parquet" in p.what for p in problems)  # the session trace
    assert any("links.parquet" in p.what for p in problems)  # the measured links


def test_missing_assets_are_named(tmp_path: Path) -> None:
    spec = spec_mod.load("configs/emu/s1_central.yaml")
    problems = preflight._assets(spec, tmp_path)
    assert {p.level for p in problems} == {"fail"}
    assert any("firecracker" in p.what for p in problems)
    assert any("vmlinux" in p.what for p in problems)
