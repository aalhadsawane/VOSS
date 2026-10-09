"""Builds the cost model's static inputs from public data: substrate profiles, the calibration bundle, the function
catalogue, tenant configs and orchestrator-tier locations (doc 03 §5.2)."""

from __future__ import annotations

from voss.core.config import RunConfig
from voss.core.dist import Dist
from voss.policy.cost.inputs import CostContext, FnInfo, StartupModel, TenantInfo
from voss.policy.predict.base import FnPrior
from voss.world.geo import Metros
from voss.world.substrate import CpuOp, DelayOp, SubstrateProfile
from voss.world.workload import Catalog


def _mean(ref: object) -> float:
    if isinstance(ref, int | float):
        return float(ref)
    if isinstance(ref, str):
        return 0.0
    m = getattr(ref, "mean", None)
    return float(m()) if callable(m) else 0.0


def _delays(ops: tuple[object, ...]) -> float:
    return sum(_mean(op.dist) for op in ops if isinstance(op, DelayOp))


def startup_model(p: SubstrateProfile, touched: float) -> StartupModel:
    t = p.ladder.transitions
    boot = next(
        (
            _delays(ops)
            for k, ops in sorted(t.items())
            if k.endswith(f"->{p.ladder.ready}") and any(isinstance(o, CpuOp) and o.work == "fn.init_s" for o in ops)
        ),
        0.0,
    )
    restore = _delays(t.get(f"L2->{p.ladder.ready}", ()))
    dispatch = _delays(t.get(f"{p.ladder.ready}->{p.ladder.busy}", ()))
    verify = sum(_mean(o.work) for ops in t.values() for o in ops if isinstance(o, CpuOp) and o.per_mb)
    trust = sum(_mean(o.work) for o in p.trust if isinstance(o, CpuOp)) if p.trust else 0.0
    cpu = _mean(p.slowdown.get("cpu", 1.0)) * _mean(p.slowdown.get("mem", 1.0))
    return StartupModel(
        boot, restore, dispatch, trust if p.trust else 0.0, verify, touched, cpu or 1.0, "L2" in p.ladder.persistent
    )


def cost_context(
    cfg: RunConfig, catalog: Catalog, metros: Metros, profiles: dict[str, SubstrateProfile], bundle: dict[str, Dist]
) -> CostContext:
    touched = bundle["snapshot_touched_frac"].mean() if "snapshot_touched_frac" in bundle else 0.3
    fns = {
        f.name: FnInfo(
            f.name,
            f.tenant,
            f.mem_mb,
            f.bundle_mb,
            f.rootfs_mb,
            f.snapshot_mb,
            f.init_s,
            f.out_kb * 1024,
            f.idempotent,
            f.work_ref_s,
        )
        for f in catalog.functions
    }
    sig = cfg.voss.cost.sigma
    ten = {}
    for t in catalog.tenants:
        i = metros.index(t.kbs_city)
        ten[t.id] = TenantInfo(
            sig.get(t.sensitivity, 1.0), float(metros.lat[i]), float(metros.lon[i]), t.assurance_floor, t.f
        )
    reg = metros.index(cfg.voss.infra.registry)
    routers = {
        f"router:{c}": (float(metros.lat[metros.index(c)]), float(metros.lon[metros.index(c)]))
        for c in cfg.voss.infra.routers
    }
    c = cfg.voss.cost
    return CostContext(
        {n: startup_model(p, touched) for n, p in profiles.items()},
        fns,
        ten,
        (float(metros.lat[reg]), float(metros.lon[reg])),
        routers,
        sync_weight=c.sync_weight,
        eps=c.eps,
        lambda_exposure=c.lambda_exposure,
        K=cfg.voss.placer.K,
    )


def fn_priors(catalog: Catalog) -> dict[str, FnPrior]:
    return {f.name: FnPrior(f.work_ref_s, f.in_kb * 1024, f.size_exp) for f in catalog.functions}
