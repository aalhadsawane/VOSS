"""The VOSS system on a wall clock with real microVMs (doc 10 §4, P9b): same actors, policies, network and resource
models as the simulator; only the kernel, the start-up/execution steps and the decision clock differ."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from voss.core.config import RunConfig
from voss.core.ids import FnId
from voss.runtime.system import RunResult
from voss.runtime.voss_system import VossSystem
from voss.world.scenario import Scenario

from tools.emu.backend import EmuConfig, FcBackend
from tools.emu.kernel import RealtimeKernel
from tools.emu.vms import FnVm


class EmuSystem(VossSystem):
    kernel_cls: Any = RealtimeKernel

    def __init__(self, cfg: RunConfig, scn: Scenario, emu: EmuConfig, vm_factory: Callable[..., FnVm] = FnVm) -> None:
        super().__init__(cfg, scn)
        catalog = {FnId(f.name): f for f in scn.catalog.functions}
        self.backend = FcBackend(cast(RealtimeKernel, self.kernel), emu, self.rec, catalog, vm_factory)
        for agent in self.agents.values():
            self.backend.attach(agent.host)
        self.backend.start()

    def run(self) -> RunResult:
        try:
            return super().run()
        finally:
            self.backend.shutdown()
