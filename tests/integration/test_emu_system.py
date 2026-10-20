"""Emulation wiring (doc 10 §4): the full VOSS system on a wall-clock kernel with fake microVMs that sleep.

Checks what the testbed adds around the simulator: the real-time kernel drives every actor, ladder ops are claimed by
the backend, invocations execute through it, VM reconciliation keeps real VMs in line with the logical warm pool, and
nothing is left running afterwards. No Firecracker or KVM needed.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from tools.calibrate.fc import FcAssets
from tools.emu.backend import EmuConfig
from tools.emu.system import EmuSystem
from tools.emu.vms import ExecResult
from voss.core.config import load_config
from voss.world.scenario import generate

LIVE: set[int] = set()


class FakeVm:
    """Sleeps instead of booting; tracks which fake VMs are alive."""

    n = 0

    def __init__(self, assets: FcAssets, workdir: Path, vm_id: str, fn: str, mem_mb: int) -> None:
        FakeVm.n += 1
        self.id, self.fn, self.mem_mb, self.alive = FakeVm.n, fn, mem_mb, True

    def boot(self, rootfs: str, timeout: float = 0) -> float:
        time.sleep(0.03)
        LIVE.add(self.id)
        return 0.03

    def restore(self, state: Path, mem: Path, timeout: float = 0) -> float:
        time.sleep(0.01)
        LIVE.add(self.id)
        return 0.01

    def snapshot(self, state: Path, mem: Path) -> float:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_bytes(b"s")
        mem.write_bytes(b"m")
        time.sleep(0.02)
        return 0.02

    def run(self, size_kb: int, tag: str, timeout_s: float) -> ExecResult:
        time.sleep(0.02)
        return ExecResult(True, 0.02, 0.015, 0.018)

    def kill(self) -> None:
        self.alive = False
        LIVE.discard(self.id)


def small_cfg() -> Any:
    return load_config(
        "configs/e01/s1_stable.yaml",
        [
            "horizon_s=20",
            "drain_s=5",
            "scenario.workers=6",
            "scenario.load={regime: load_default, rate: 3}",
            "decision_clock.mode=measured",
            "decision_clock.cpu_scale=0.0",
        ],
    )


def test_emulated_run_completes_through_the_backend(tmp_path: Path) -> None:
    cfg = small_cfg()
    emu = EmuConfig("fc", "k", "r", tmp_path, threads=8, min_free_gb=0.0)
    sysm = EmuSystem(cfg, generate(cfg), emu, FakeVm)  # type: ignore[arg-type]
    t0 = time.monotonic()
    res = sysm.run()
    assert time.monotonic() - t0 >= 25  # real time: horizon + drain
    inv = res.recorder.frame("invocations")
    ok = inv[inv.outcome == "ok"]
    print(inv.outcome.value_counts().to_dict(), inv.start_level.value_counts().to_dict())
    assert len(inv) > 20 and len(ok) >= 15
    ev = res.recorder.frame("events")
    kinds = set(ev.kind)
    assert {"emu_boot", "emu_exec"} <= kinds
    assert not [e for e in ev.kind if e == "invariant_violation"]
    assert set() == LIVE  # shutdown killed every VM
    assert sysm.backend.failed is None
