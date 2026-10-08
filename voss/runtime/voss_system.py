"""Builds and runs the VOSS system on a scenario (doc 00 §6, doc 08 §2). Registered as system ``voss``."""

from __future__ import annotations

from typing import Any

import numpy as np

from voss.core.config import RunConfig
from voss.core.decision_clock import DecisionClock
from voss.core.ids import FnId, TenantId, WorkerId
from voss.core.kernel import Kernel
from voss.core.registry import register
from voss.core.rng import RngFactory
from voss.metrics.recorder import Recorder
from voss.metrics.schema import Table
from voss.runtime.actor import ActorContext, Directory
from voss.runtime.drivers import TraceDriver, client_handler, invocations, owner_event, session_events
from voss.runtime.invariants import check_invariants
from voss.runtime.opdb import OpDb
from voss.runtime.orchestrator import Orchestrator
from voss.runtime.registry import Registry
from voss.runtime.router import Router
from voss.runtime.scheduler_role import SchedulerRole
from voss.runtime.system import RunResult
from voss.runtime.tenant_kbs import TenantKbs
from voss.runtime.verifier import Verifier
from voss.runtime.worker_agent import WorkerAgent
from voss.runtime.workerlib.host import make_host
from voss.world.execution import ExecParams, noise_matrix
from voss.world.hardware import load_hw_classes
from voss.world.network import Network, NetworkParams
from voss.world.scenario import Scenario, generate
from voss.world.substrate import SubstrateProfile, load_bundle, load_substrate


class VossSystem:
    """Owns the kernel, network, actors and drivers of one run."""

    def __init__(self, cfg: RunConfig, scn: Scenario) -> None:
        self.cfg, self.scn = cfg, scn
        self.kernel, self.rng, self.rec = Kernel(), RngFactory(cfg.seed), Recorder()
        net_params = NetworkParams.model_validate(cfg.scenario.network)
        self.net = Network(self.kernel, net_params, self.rng.stream("net.jitter"))
        self.bundle = load_bundle(cfg.calibration or "calibration/placeholder/c0")
        names = sorted(set(scn.workers.substrate_names))
        self.profiles: dict[str, SubstrateProfile] = {n: load_substrate(n, self.bundle) for n in names}
        self.directory = Directory()
        self.ctx = ActorContext(
            self.kernel, self.net, self.rec, self.rng, DecisionClock(cfg.decision_clock), cfg, self.directory
        )
        self.agents: dict[WorkerId, WorkerAgent] = {}
        self.scheds: dict[WorkerId, SchedulerRole] = {}
        self.routers: list[Router] = []
        self._infra()
        self._workers()

    # --- construction -------------------------------------------------------------------------------------------
    def _place(self, host: str, city: str) -> None:
        m = self.scn.metros
        i = m.index(city)
        self.net.add_host(host, float(m.lat[i]), float(m.lon[i]))

    def _attach(self, actor: Any) -> Any:
        self.net.attach(actor.addr, actor.on_message)
        return actor

    def _infra(self) -> None:
        inf = self.cfg.voss.infra
        self._place("orchestrator", inf.orchestrator)
        self._place("verifier", inf.verifier)
        self._place("registry", inf.registry)
        for city in inf.routers:
            self._place(f"router:{city}", city)
        self.directory.routers = tuple(("router", f"router:{c}") for c in inf.routers)
        for t in self.scn.catalog.tenants:
            self._place(f"kbs:{t.id}", t.kbs_city)
            self.directory.kbs[TenantId(t.id)] = ("kbs", f"kbs:{t.id}")
        for i, name in enumerate(self.scn.metros.name):
            self._place(f"client:{i}", name)
        valid = {n: (p.assurance_base, p.session.valid_s) for n, p in self.profiles.items()}
        self._attach(Verifier("verifier", self.ctx, valid))
        self._attach(OpDb("orchestrator", self.ctx))
        self._attach(Orchestrator("orchestrator", self.ctx))
        self._attach(Registry("registry", self.ctx))
        for t in self.scn.catalog.tenants:
            self._attach(TenantKbs(f"kbs:{t.id}", self.ctx, TenantId(t.id)))
        self.routers = [self._attach(Router(f"router:{c}", self.ctx, c)) for c in inf.routers]

    def _workers(self) -> None:
        wt, hw = self.scn.workers, load_hw_classes(list(self.scn.workers.hw_names))
        catalog = {FnId(f.name): f for f in self.scn.catalog.functions}
        touched = self.bundle["snapshot_touched_frac"].mean() if "snapshot_touched_frac" in self.bundle else 0.3
        ep = ExecParams.model_validate(self.cfg.scenario.execution)
        noise = noise_matrix(self.rng.stream("inv.exec.noise"), len(self.scn.arrivals), 4, ep)
        params = {"exec": ep, "touched_frac": touched, "noise": noise}
        for w in range(len(wt)):
            wid = WorkerId(w)
            prof = self.profiles[wt.substrate_names[int(wt.substrate[w])]]
            hc = hw[wt.hw_names[int(wt.hw[w])]]
            caps = {k: float(getattr(wt, k)[w]) for k in ("slots", "speed", "mem_mb", "ssd_mb", "hdd_mb")}
            host = make_host(
                self.kernel,
                self.rng,
                wid,
                wt.identity[w],
                prof,
                hc.model_dump(),
                caps,
                self.bundle.get("tpm2_quote"),
                (int(wt.domain[w]), bool(wt.known_good[w]), f"{hc.cpu_model}|k1|fc1"),
                self.cfg.voss.cache.hdd_tier,
            )
            g = self.rng.stream("host.slowdown", w)
            host.cpu_slowdown = _sample(prof.slowdown.get("cpu", 1.0), g) * _sample(prof.slowdown.get("mem", 1.0), g)
            host.io_slowdown = _sample(prof.slowdown.get("io", 1.0), g)
            self.net.add_host(
                wid,
                float(wt.lat[w]),
                float(wt.lon[w]),
                float(wt.last_mile_s[w]),
                float(wt.up_bps[w]),
                float(wt.down_bps[w]),
                bool(wt.relayed[w]),
                up=False,
            )
            self.agents[wid] = self._attach(WorkerAgent(host, self.ctx, catalog, params))
            self.scheds[wid] = self._attach(SchedulerRole(host, self.ctx))

    # --- running -------------------------------------------------------------------------------------------------
    def _owner(self, row: dict[str, Any]) -> None:
        w = WorkerId(int(row["worker"]))
        ev = owner_event(row)
        if ev.kind == "start":
            self.net.set_host_up(w, True)
        self.agents[w].on_message(ev)
        if ev.kind == "end":
            self.scheds[w].reset()
            self.net.set_host_up(w, False)

    def _sample(self) -> None:
        up = sum(1 for a in self.agents.values() if a.host.up)
        att = sum(1 for a in self.agents.values() if a.host.attested)
        pending = sum(len(r.pending) for r in self.routers)
        self.rec.log(Table.SAMPLES, t=self.kernel.now, hosts_up=up, attested=att, pending=pending)
        self.kernel.after(60.0, self._sample)

    def run(self) -> RunResult:
        TraceDriver(self.kernel, session_events(self.scn), self._owner).start()
        arr = invocations(self.scn)
        TraceDriver(self.kernel, arr, client_handler(self.net, self.scn, list(self.directory.routers))).start()
        self.kernel.at(0.0, self._sample)
        self.kernel.run(self.scn.horizon + self.cfg.drain_s)
        for r in self.routers:
            r.finalize_all()
        self.kernel.run(self.kernel.now + 5.0)
        for kind, st in sorted(self.net.stats.items()):
            self.rec.log(Table.MESSAGES, kind=kind, count=st.count, bytes=st.bytes, drops=st.drops)
        for v in check_invariants(self.rec, self.scn, len(arr)):
            self.rec.log(Table.EVENTS, t=self.kernel.now, kind="invariant_violation", worker=-1, value=0.0, detail=v)
        return RunResult(self.rec, self.scn.hash, self.kernel.events_run)


def _sample(ref: Any, g: np.random.Generator) -> float:
    if isinstance(ref, int | float):
        return float(ref)
    return float(ref.sample(g))


@register("system", "voss")
def run_voss(cfg: RunConfig) -> RunResult:
    return VossSystem(cfg, generate(cfg)).run()
