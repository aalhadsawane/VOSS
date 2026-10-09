"""P9 harness, node side (doc 10): output parsers, the reboot/BIOS safety gate, and dry runs of every suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.calibrate import run as harness
from tools.calibrate.fc import MARK, boot_args
from tools.calibrate.suites import appliance, caps, disk, sebs, tme

GETCAP = (
    'TPM2_PT_FAMILY_INDICATOR:\n  raw: 0x322E3000\n  value: "2.0"\n'
    'TPM2_PT_MANUFACTURER:\n  raw: 0x494E5443\n  value: "INTC"\n'
)
FIO = {
    "jobs": [
        {
            "read": {
                "io_bytes": 1 << 30,
                "bw_bytes": 3_000_000_000,
                "iops": 2861.0,
                "clat_ns": {"mean": 3e6, "percentile": {"50.000000": 2_500_000}},
            },
            "write": {"io_bytes": 0, "bw_bytes": 0, "iops": 0.0},
        }
    ]
}


def test_caps_parsers() -> None:
    assert caps.tpm_manufacturer(GETCAP) == "INTC"
    assert caps.tpm_manufacturer("") == ""
    assert caps.cpuid_tme("   0x00000007 0x00: eax=0x00000002 ebx=0x239c27eb ecx=0x98c027bc edx=0xfc184410") is True
    assert caps.cpuid_tme("   0x00000007 0x00: eax=0x00000002 ebx=0x239c27eb ecx=0x00000000 edx=0x0") is False
    assert caps.cpuid_tme("nothing") is None
    blk = {"blockdevices": [{"name": "nvme0n1", "rota": False, "size": 10**12, "type": "disk", "model": "X "}]}
    blk["blockdevices"].append({"name": "sda", "rota": True, "size": 2 * 10**12, "type": "disk", "model": "H"})
    blk["blockdevices"].append({"name": "loop0", "rota": False, "size": 1, "type": "loop"})
    d = caps.disks(json.dumps(blk))
    assert [(x["name"], x["rotational"], x["size_gb"]) for x in d] == [
        ("nvme0n1", False, 1000.0),
        ("sda", True, 2000.0),
    ]


def test_disk_parsers() -> None:
    r = disk.fio_result(json.dumps(FIO))
    assert r == {"MBps": 3000.0, "iops": 2861.0, "lat_p50_s": 0.0025}
    assert disk.verity_root_hash("VERITY header information\nRoot hash:      ab12cd\n") == "ab12cd"
    with pytest.raises(RuntimeError):
        disk.verity_root_hash("no hash")
    assert disk.sha256_MBps(8) > 1.0


def test_vm_and_guest_parsers() -> None:
    assert tme.triad_MBps("Copy: 1\nTriad:      41234.5 MB/s (best of 9)\n") == 41234.5
    lines = ["thumbnailer 200 0 0.150", "thumbnailer 200 1 0.149", "garbage"]
    assert sebs.parse(lines, "EXEC") == [("thumbnailer", 200, 0, 0.15), ("thumbnailer", 200, 1, 0.149)]
    m = MARK.search("[    0.4] VOSS_ACK ping")
    assert m is not None and m.group(1) == "ACK" and m.group(2) == "ping"
    assert "voss.mode=serve" in boot_args("serve") and "console=ttyS0" in boot_args("boot")


def test_appliance_log_parsers() -> None:
    line = (
        "Startup finished in 7.135s (firmware) + 2.009s (loader) + 1.512s (kernel) + 1min 3.2s (userspace) = 1min 13.8s"
    )
    parts = appliance.startup(line)
    assert parts == pytest.approx({"firmware": 7.135, "loader": 2.009, "kernel": 1.512, "userspace": 63.2})
    assert appliance.seconds("912ms") == pytest.approx(0.912)
    assert appliance.events("VOSS_T agent_ready 4.20\nVOSS_T verifier_ok 4.61\n") == {
        "agent_ready": 4.2,
        "verifier_ok": 4.61,
    }


def test_reboot_and_bios_suites_refuse_without_flags(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = harness.main(["--suite", "appliance", "--set", "step=arm", "--out", str(tmp_path)])
    assert rc == 1 and "refused" in capsys.readouterr().out
    rc = harness.main(["--suite", "tme", "--out", str(tmp_path)])
    assert rc == 1 and "BIOS" in capsys.readouterr().out
    assert not list(tmp_path.rglob("records.jsonl"))  # nothing ran


def test_appliance_arm_needs_allow_reboot_even_inside_the_suite(tmp_path: Path) -> None:
    from tools.calibrate.common import Records, Shell, SuiteSkipped
    from tools.calibrate.suites import Ctx

    ctx = Ctx(Shell(dry_run=True), Records(tmp_path / "r.jsonl", "appliance"), tmp_path, {"step": "arm"})
    with pytest.raises(SuiteSkipped):
        appliance.run(ctx)
    assert ctx.sh.log == []


@pytest.mark.parametrize("suite", ["caps", "disk", "fc_boot", "fc_snapshot", "qemu_vm", "sebs", "tpm", "attest_local"])
def test_dry_run_of_every_safe_suite(suite: str, tmp_path: Path) -> None:
    opts = ["kernel=/a/vmlinux", "rootfs=/a/r.ext4", "sebs_rootfs=/a/s.ext4", "ssd_dir=" + str(tmp_path / "ssd")]
    argv = ["--suite", suite, "--dry-run", "--quick", "--out", str(tmp_path)]
    for kv in opts:
        argv += ["--set", kv]
    assert harness.main(argv) == 0
    meta = json.loads(next(tmp_path.rglob("meta.json")).read_text())
    assert meta["status"] == "ok" and meta["dry_run"] is True
    assert meta["harness_version"] and meta["suite"] == suite
