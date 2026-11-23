"""The VOSS system on a wall clock with real microVMs (doc 10 §4, plan V13): same actors, policies, network and
resource models as the simulator; only the kernel, the start-up/execution steps, the session's TPM quote, the worker
isolation (cores, memory, namespace) and the decision clock differ."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from voss.core.config import RunConfig
from voss.core.ids import FnId
from voss.metrics.schema import Table
from voss.runtime.system import RunResult
from voss.runtime.voss_system import VossSystem
from voss.world.scenario import Scenario

from tools.emu.backend import EmuConfig, FcBackend
from tools.emu.host_backend import HostBackend
from tools.emu.kernel import RealtimeKernel
from tools.emu.tpm import RealTpm
from tools.emu.vms import FnVm


class EmuSystem(VossSystem):
    kernel_cls: Any = RealtimeKernel

    def __init__(self, cfg: RunConfig, scn: Scenario, emu: EmuConfig, vm_factory: Callable[..., FnVm] = FnVm) -> None:
        super().__init__(cfg, scn)
        self.emu = emu
        catalog = {FnId(f.name): f for f in scn.catalog.functions}
        self.backend = FcBackend(cast(RealtimeKernel, self.kernel), emu, self.rec, catalog, vm_factory)
        for agent in self.agents.values():
            HostBackend(self.backend, agent.host)
        self.backend.start()
        if emu.tpm is not None:  # a real TPM quote at every session start (handoff Part E)
            self._real_tpm()

    def _real_tpm(self) -> None:
        for agent in self.agents.values():
            host, w = agent.host, int(agent.host.worker)

            def log(secs: float, worker: int = w) -> None:
                self.rec.log(Table.EVENTS, t=self.kernel.now, kind="emu_tpm_quote", worker=worker, value=secs)

            quoter = self.emu.tpm
            assert quoter is not None
            kernel = cast(RealtimeKernel, self.kernel)
            host.tpm = RealTpm(kernel, host.tpm.quote_dist, host.tpm.gen, quoter, self.backend.pool, log)

    def run(self) -> RunResult:
        try:
            return super().run()
        finally:
            self.backend.shutdown()
            if self.emu.isolation is not None:
                self.emu.isolation.close()
