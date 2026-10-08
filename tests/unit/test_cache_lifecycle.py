"""Worker cache mechanics and the generic lifecycle engine (doc 02 §5-6)."""

from __future__ import annotations

import pytest
from voss.core.dist import Const
from voss.core.kernel import Kernel
from voss.core.rng import stream
from voss.world.cache import WorkerCache
from voss.world.lifecycle import OpEnv, OpRun, cache_level, split_path
from voss.world.resources import Disk, Tpm
from voss.world.substrate import CpuOp, DelayOp, DiskReadOp, LadderSpec, TpmQuoteOp, load_bundle, load_substrate
from voss.world.workload import FunctionSpec

FN = FunctionSpec(
    name="f",
    tenant="t",
    runtime="py",
    rootfs_mb=100,
    bundle_mb=10,
    snapshot_mb=50,
    mem_mb=128,
    init_s=0.5,
    work_ref_s=0.1,
    in_kb=1,
    in_sigma=0.1,
    size_exp=0.0,
    out_kb=1,
    idempotent=True,
    slo_class="sync",
    slo_k=5,
)


def test_ssd_pressure_demotes_then_evicts() -> None:
    c = WorkerCache(ssd_mb=100, hdd_mb=150, mem_mb=1000)
    assert c.insert("a", "bundle", 60, now=1) == "ssd"
    assert c.insert("b", "bundle", 60, now=2) == "ssd"  # a demoted to HDD
    assert c.tier_of("a") == "hdd" and c.stats.demotions == 1
    assert c.insert("c", "bundle", 60, now=3) == "ssd"  # b demoted
    assert c.insert("d", "bundle", 60, now=4) == "ssd"  # c demoted; HDD full → a (LRU) evicted
    assert c.tier_of("a") is None and c.stats.evictions == 1
    assert c.used("ssd") <= 100 and c.used("hdd") <= 150


def test_pins_and_promotion() -> None:
    c = WorkerCache(ssd_mb=100, hdd_mb=100, mem_mb=1000)
    c.insert("a", "snapshot", 80, now=1)
    c.pin("a")
    assert c.insert("b", "snapshot", 80, now=2) == "hdd"  # cannot displace a pinned entry
    c.pin("a", False)
    assert c.promote("b", now=3) and c.tier_of("b") == "ssd" and c.tier_of("a") == "hdd"
    assert c.insert("huge", "rootfs", 500, now=4) is None


def test_warm_vms_respect_memory() -> None:
    c = WorkerCache(ssd_mb=0, hdd_mb=0, mem_mb=300)
    assert c.park_warm("f", 128, now=1) and c.park_warm("g", 128, now=2)
    assert c.park_warm("h", 128, now=3)  # evicts f (oldest idle)
    assert c.warm_count("f") == 0 and c.warm_count("h") == 1
    assert c.take_warm("g") is not None and c.warm_count("g") == 0
    assert c.expire_warm(now=1000, ttl=10) == 1
    c.park_warm("x", 100, now=1)
    c.session_end()
    assert c.warm_mb() == 0


def test_cache_level_ladder() -> None:
    prof = load_substrate("appliance_tpm", load_bundle("calibration/placeholder/c0"))
    c = WorkerCache(ssd_mb=1000, hdd_mb=1000, mem_mb=1000)
    lad = prof.ladder
    assert cache_level(c, FN, lad, "cls") == ("L0", "")
    from voss.world.lifecycle import artifact_digests

    d = artifact_digests(FN, "cls")
    c.insert(d["bundle"], "bundle", 10, 0)
    c.insert(d["rootfs"], "rootfs", 100, 0)
    assert cache_level(c, FN, lad, "cls") == ("L1", "ssd")
    c.insert(d["snapshot"], "snapshot", 50, 0)
    assert cache_level(c, FN, lad, "cls")[0] == "L2"
    assert cache_level(c, FN, lad, "other-class")[0] == "L1"  # snapshots are per snapshot class
    c.park_warm("f", 128, 0)
    assert cache_level(c, FN, lad, "cls") == ("L3", "ram")
    assert split_path(lad, "L0") == (["L0->L1"], ["L1->L3"])
    assert split_path(lad, "L2") == ([], ["L2->L3"])


def test_op_run_sums_resource_costs() -> None:
    k = Kernel()
    disk = Disk(k, "ssd", read_MBps=100.0, write_MBps=100.0)
    tpm = Tpm(k, Const(value=0.25), stream(1, "t"))
    env = OpEnv(
        k,
        stream(1, "ops"),
        speed=2.0,
        tpm=tpm,
        disks={"ssd": disk},
        sizes={"rootfs": 50e6},
        tiers={"rootfs": "ssd"},
        fn=FN,
    )
    ops = (
        DelayOp(op="delay", dist=Const(value=1.0)),
        TpmQuoteOp(op="tpm_quote"),
        DiskReadOp(op="disk_read", what="rootfs"),
        CpuOp(op="cpu", work="fn.init_s"),
    )
    got: list[float] = []
    OpRun(ops, env, got.append).start()
    k.run(10.0)
    assert got == [pytest.approx(1.0 + 0.25 + 0.5 + 0.25)]


def test_ladder_requires_reachability() -> None:
    lad = LadderSpec(
        levels=("L0", "L1", "L3", "L4"), ready="L3", busy="L4", transitions={"L0->L1": (), "L1->L3": (), "L3->L4": ()}
    )
    assert lad.path("L0") == ["L0->L1", "L1->L3"]
