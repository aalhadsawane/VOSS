"""Multi-worker isolation layer of the emulation testbed (plan V13): core allocation, injected links, cgroups.

No root, no ``ip``, no ``tc``: the plan and the exact command lines are pure, and ``Isolation`` runs them through the
calibration harness's ``Shell`` in ``dry_run`` mode.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.calibrate.common import Shell
from tools.emu.isolation import Isolation, netem_argv, setup_commands, teardown_commands
from tools.emu.topology import (
    KIND_EFFICIENCY,
    KIND_PERFORMANCE,
    Cpu,
    Topology,
    cpulist,
    plan,
    read_topology,
)


def hybrid() -> Topology:
    """A 12-core Alder Lake like node02: 8 P-cores with SMT, 4 E-cores without."""
    cpus = [Cpu(cpu=2 * i, core=i, package=0, kind=KIND_PERFORMANCE) for i in range(8)]
    cpus += [Cpu(cpu=2 * i + 1, core=i, package=0, kind=KIND_PERFORMANCE) for i in range(8)]
    cpus += [Cpu(cpu=16 + i, core=8 + i, package=0, kind=KIND_EFFICIENCY) for i in range(4)]
    return Topology(tuple(sorted(cpus, key=lambda c: c.cpu)))


def test_cpulist_parses_the_kernel_format() -> None:
    assert cpulist("0-3,8,10-11") == {0, 1, 2, 3, 8, 10, 11}
    assert cpulist("") == set()


def test_topology_groups_threads_into_physical_cores() -> None:
    topo = hybrid()
    p = topo.cores(KIND_PERFORMANCE)
    assert len(p) == 8 and all(len(c.cpus) == 2 for c in p)
    assert [c.cpus for c in p[:2]] == [(0, 1), (2, 3)]
    assert len(topo.cores(KIND_EFFICIENCY)) == 4
    assert topo.kinds() == (KIND_EFFICIENCY, KIND_PERFORMANCE)


def test_read_topology_from_a_sysfs_tree(tmp_path: Path) -> None:
    """core_type 1 = performance, 2 = efficiency (the kernel's hybrid CPU types)."""
    spec = {0: (0, 1), 1: (0, 1), 2: (1, 2), 3: (1, 2)}
    for cpu, (core, kind) in spec.items():
        d = tmp_path / f"cpu{cpu}" / "topology"
        d.mkdir(parents=True)
        (d / "core_id").write_text(f"{core}\n")
        (d / "physical_package_id").write_text("0\n")
        (d / "core_type").write_text(f"{kind}\n")
    topo = read_topology(tmp_path)
    assert [(c.core, c.cpus, c.kind) for c in topo.cores()] == [
        (0, (0, 1), KIND_PERFORMANCE),
        (1, (2, 3), KIND_EFFICIENCY),
    ]


def test_read_topology_rejects_an_empty_tree(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no cpu"):
        read_topology(tmp_path)


def test_plan_never_shares_a_core_and_uses_one_kind() -> None:
    lay = plan(hybrid(), 6, kind=KIND_PERFORMANCE, cores_per_worker=1, infra_cores=2, mem_mb=4096)
    worker_cpus = [c for s in lay.slots for c in s.cpus]
    assert len(lay.slots) == 6
    assert len(set(worker_cpus)) == len(worker_cpus) == 12  # six P-cores, both threads each
    assert not set(worker_cpus) & set(lay.infra_cpus)
    assert len(lay.infra) == 2
    assert all(c.kind == KIND_PERFORMANCE for c in lay.infra)
    assert all(s.mem_mb == 4096 and s.ns == f"voss-emu-w{s.index}" for s in lay.slots)


def test_plan_fails_clearly_when_the_machine_is_too_small() -> None:
    with pytest.raises(ValueError, match="8 P core"):
        plan(hybrid(), 10, kind=KIND_PERFORMANCE, cores_per_worker=1, infra_cores=2)
    with pytest.raises(ValueError, match="4 E core"):
        plan(hybrid(), 6, kind=KIND_EFFICIENCY, cores_per_worker=1, infra_cores=2)


def test_plan_takes_the_link_from_the_scenario_worker() -> None:
    lay = plan(
        hybrid(),
        2,
        last_mile_s=[0.004, 0.020],
        up_bps=[10e6, 40e6],
        down_bps=[100e6, 500e6],
    )
    assert [round(s.delay_ms, 3) for s in lay.slots] == [4.0, 20.0]
    assert [round(s.up_mbps, 1) for s in lay.slots] == [10.0, 40.0]
    assert [round(s.down_mbps, 1) for s in lay.slots] == [100.0, 500.0]
    with pytest.raises(ValueError, match="must have 2 entries"):
        plan(hybrid(), 2, last_mile_s=[0.01])


def test_netem_injects_the_delay_and_the_rate() -> None:
    argv = netem_argv("voss-emu-w3-v", 12.5, 30.0)
    assert argv[:6] == ["tc", "qdisc", "add", "dev", "voss-emu-w3-v", "root"]
    assert argv[argv.index("delay") + 1] == "12.500ms"
    assert argv[argv.index("rate") + 1] == "30.000mbit"


def test_setup_commands_cover_namespace_link_limits_and_cgroup() -> None:
    lay = plan(hybrid(), 1, mem_mb=2048, last_mile_s=[0.01], up_bps=[20e6], down_bps=[200e6])
    slot = lay.slot(0)
    text = [" ".join(c) for c in setup_commands(slot, Path("/sys/fs/cgroup/voss-emu"))]
    assert "ip netns add voss-emu-w0" in text
    assert any("veth" in t and "voss-emu-w0-v" in t for t in text)
    assert "ip netns exec voss-emu-w0 ip addr add 10.213.0.1/30 dev voss-emu-w0-v" in text
    # both directions: the worker's uplink on its side, the downlink on the root side
    assert (
        "ip netns exec voss-emu-w0 tc qdisc add dev voss-emu-w0-v root netem delay 10.000ms rate 20.000mbit"
        in " ".join(text)
    )
    assert any(t.startswith("tc qdisc add dev voss-emu-w0-r root netem delay 10.000ms rate 200.000mbit") for t in text)
    assert any("2147483648 > /sys/fs/cgroup/voss-emu/voss-emu-w0/memory.max" in t for t in text)
    assert any("+memory" in t for t in text)


def test_teardown_kills_the_process_tree_and_removes_the_namespace() -> None:
    lay = plan(hybrid(), 1)
    text = [" ".join(c) for c in teardown_commands(lay.slot(0))]
    assert any("cgroup.kill" in t for t in text)
    assert "ip netns del voss-emu-w0" in text


def test_isolation_is_idempotent_and_follows_sessions() -> None:
    lay = plan(hybrid(), 2)
    iso = Isolation(lay, sh=Shell(dry_run=True))
    iso.setup(0)
    n = len(iso.log)
    iso.setup(0)  # already up: no command
    assert len(iso.log) == n
    iso.session(0, up=True, session=1)  # the first session keeps the namespace the coordinator created
    assert not any("netns del voss-emu-w0" in c for c in iso.log[n:])
    iso.session(0, up=True, session=1)  # unchanged: nothing
    before = len(iso.log)
    iso.session(0, up=True, session=2)  # a new session starts from a clean namespace
    assert any("netns del voss-emu-w0" in c for c in iso.log[before:])
    iso.session(0, up=False, session=1)  # session end
    assert any("netns del voss-emu-w0" in c for c in iso.log[before:])
    assert iso.state[0] == (False, 1)
    iso.close()


def test_assets_place_the_vmm_in_the_namespace_core_and_cgroup() -> None:
    lay = plan(hybrid(), 1)
    iso = Isolation(lay, sh=Shell(dry_run=True))
    from tools.calibrate.fc import FcAssets

    a = iso.assets(0, FcAssets("/fc", "/k", "/r"))
    assert a.prefix == ("ip", "netns", "exec", "voss-emu-w0", "taskset", "-c", "0,1")
    assert a.cgroup_procs.endswith("/voss-emu/voss-emu-w0/cgroup.procs")
    assert (a.firecracker, a.kernel, a.rootfs) == ("/fc", "/k", "/r")
