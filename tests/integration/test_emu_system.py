"""Emulation wiring (plan V13): the full VOSS system on a wall-clock kernel with fake microVMs, a fake isolation layer
and a fake TPM, so the orchestration is exercised without Firecracker, root, namespaces or a TPM.

Checks what the testbed adds around the simulator: the real-time kernel drives every actor, ladder ops are claimed by
the backend, invocations execute through it, each worker's VMs are placed through its own assets (namespace, cores,
cgroup), session starts and ends reach the isolation layer, every session start asks for a real quote, and nothing is
left running afterwards.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar

import pytest
from tools.calibrate.fc import FcAssets
from tools.emu import scenario as spec_mod
from tools.emu.backend import EmuConfig
from tools.emu.system import EmuSystem
from tools.emu.vms import ExecResult
from voss.runtime.voss_system import VossSystem
from voss.world.scenario import generate

from tests.fixtures.emu import FIXTURE, sessions_trace

LIVE: set[int] = set()


@pytest.fixture(autouse=True)
def _no_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    """The simulator's per-hour progress line reads /proc/self/statm; it is not part of the emulation."""
    monkeypatch.setattr(VossSystem, "_progress", lambda self, now: None)


class FakeVm:
    """Sleeps instead of booting; tracks which fake VMs are alive."""

    n = 0
    assets: ClassVar[list[FcAssets]] = []

    def __init__(self, assets: FcAssets, workdir: Path, vm_id: str, fn: str, mem_mb: int) -> None:
        FakeVm.n += 1
        FakeVm.assets.append(assets)
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

    def prep(self, size_kb: int) -> None:
        pass

    def run(self, size_kb: int, tag: str, timeout_s: float) -> ExecResult:
        time.sleep(0.02)
        return ExecResult(True, 0.02, 0.015, 0.018)

    def kill(self) -> None:
        self.alive = False
        LIVE.discard(self.id)


class FakeIsolation:
    """Records what the backend asks of the isolation layer (the real one needs root)."""

    def __init__(self) -> None:
        self.setups: list[int] = []
        self.sessions: list[tuple[int, bool, int]] = []
        self.closed = False

    def setup(self, w: int) -> None:
        self.setups.append(w)

    def session(self, w: int, up: bool, session: int) -> None:
        self.sessions.append((w, up, session))

    def assets(self, w: int, base: FcAssets) -> FcAssets:
        return FcAssets(base.firecracker, base.kernel, base.rootfs, prefix=("netns", str(w)))

    def close(self) -> None:
        self.closed = True


class FakeQuoter:
    def __init__(self) -> None:
        self.quotes = 0

    def prepare(self) -> float:
        return 0.0

    def quote(self) -> float:
        self.quotes += 1
        time.sleep(0.005)
        return 0.005

    def stats(self) -> dict[str, Any]:
        return {"n": self.quotes}


def short_cfg(trace_root: Path | None = None, extra: list[str] | None = None) -> Any:
    """The scenario at a test horizon, on the test fixtures (no gitignored trace data)."""
    spec = spec_mod.load("configs/emu/s1_central.yaml")
    churn = [f"scenario.churn={{trace: test, trace_root: {trace_root}, split: dev}}"] if trace_root is not None else []
    return spec.run_config("voss", 1, [*FIXTURE, *churn, "scenario.load.rate=3", *(extra or [])])


def test_emulated_run_places_vms_follows_sessions_and_quotes(tmp_path: Path) -> None:
    # warm-up 25 s: the sessions start before t=0 (prebooted, no boot delay) and are attested at t=0
    cfg = short_cfg(extra=["horizon_s=25", "drain_s=5", "scenario.warmup_s=25"])
    iso, quoter = FakeIsolation(), FakeQuoter()
    emu = EmuConfig("fc", "k", "r", tmp_path, threads=8, min_free_gb=0.0, isolation=iso, tpm=quoter)
    sysm = EmuSystem(cfg, generate(cfg), emu, FakeVm)  # type: ignore[arg-type]
    t0 = time.monotonic()
    res = sysm.run()
    assert time.monotonic() - t0 >= 29  # real time: horizon + drain
    inv = res.recorder.frame("invocations")
    assert len(inv) > 20 and (inv.outcome == "ok").sum() >= 15
    kinds = set(res.recorder.frame("events").kind)
    assert {"emu_boot", "emu_exec", "emu_tpm_quote", "session_attested"} <= kinds
    assert "invariant_violation" not in kinds
    assert set() == LIVE  # shutdown killed every VM
    assert sysm.backend.failed is None
    # every session start reached the isolation layer, and VMs were only placed on workers of this run
    assert {w for w, up, _s in iso.sessions if up} == set(range(cfg.scenario.workers))
    assert iso.setups and set(iso.setups) <= set(range(cfg.scenario.workers))
    assert iso.closed
    # one real quote per attested session, and every VM was placed through its worker's assets
    assert quoter.quotes == int((res.recorder.frame("events").kind == "session_attested").sum())
    assert FakeVm.assets and all(a.prefix and a.prefix[0] == "netns" for a in FakeVm.assets)


def test_a_session_end_kills_the_worker_tree_through_the_isolation_layer(tmp_path: Path) -> None:
    # a session trace of seconds, so sessions end inside the run and the harness must tear the worker down
    root = sessions_trace(tmp_path / "traces", [(0.0, 8.0), (9.0, 60.0)])
    cfg = short_cfg(root, extra=["horizon_s=25", "drain_s=5", "scenario.warmup_s=0"])
    iso = FakeIsolation()
    emu = EmuConfig("fc", "k", "r", tmp_path, threads=8, min_free_gb=0.0, isolation=iso)
    res = EmuSystem(cfg, generate(cfg), emu, FakeVm).run()  # type: ignore[arg-type]
    assert "session_attested" in set(res.recorder.frame("events").kind)
    assert any(not up for _w, up, _s in iso.sessions), "a session end must tear the worker down"
    assert iso.closed
