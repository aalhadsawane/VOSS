"""The calibration Firecracker driver's emulation hooks (plan V13): a placement prefix and a memory cgroup.

The calibration path passes neither, so its command line and behaviour are unchanged (the calibration suite tests cover
that path).
"""

from __future__ import annotations

from pathlib import Path

from tools.calibrate.fc import FcAssets, FcVm


def test_calibration_argv_is_unchanged() -> None:
    vm = FcVm(FcAssets("/usr/bin/firecracker", "k", "r"), Path("/tmp/w"), "vm-1")
    argv = vm._argv()
    assert argv[0] == "/usr/bin/firecracker"
    assert argv[1:3] == ["--api-sock", vm.sock]


def test_the_prefix_places_the_vmm_before_it_execs() -> None:
    assets = FcAssets(
        "/usr/bin/firecracker",
        "k",
        "r",
        prefix=("ip", "netns", "exec", "voss-emu-w2", "taskset", "-c", "4,5"),
    )
    vm = FcVm(assets, Path("/tmp/w"), "vm-2")
    assert vm._argv()[:8] == ["ip", "netns", "exec", "voss-emu-w2", "taskset", "-c", "4,5", "/usr/bin/firecracker"]


def test_a_spawned_vmm_is_moved_into_the_worker_cgroup(tmp_path: Path) -> None:
    procs = tmp_path / "cgroup.procs"
    vm = FcVm(FcAssets("/usr/bin/firecracker", "k", "r", cgroup_procs=str(procs)), Path("/tmp/w"), "vm-3")
    vm._adopt(4242)
    assert procs.read_text() == "4242"


def test_without_a_cgroup_nothing_is_written(tmp_path: Path) -> None:
    vm = FcVm(FcAssets("/usr/bin/firecracker", "k", "r"), Path("/tmp/w"), "vm-4")
    vm._adopt(1)  # no cgroup_procs: a no-op, not a crash
