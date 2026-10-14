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


def _ctx(tmp_path: Path, **opts: str):  # type: ignore[no-untyped-def]
    from tools.calibrate.common import Records, Shell
    from tools.calibrate.suites import Ctx

    return Ctx(Shell(dry_run=True), Records(tmp_path / "r.jsonl", "t"), tmp_path, dict(opts))


def _skipped(ctx) -> list[str]:  # type: ignore[no-untyped-def]
    rows = [json.loads(line) for line in ctx.rec.path.read_text().splitlines()] if ctx.rec.path.exists() else []
    return [r["config"]["what"] for r in rows if r["probe"] == "skipped"]


def _ran(out: str) -> list[str]:
    return [
        line.split(" reps=")[0].removeprefix("DRY sebs ") for line in out.splitlines() if line.startswith("DRY sebs")
    ]


def test_sebs_leaves_out_guest_sets_over_the_ram_budget(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    opts = {"kernel": "/a/k", "sebs_rootfs": "/a/r", "firecracker": "/a/fc", "functions": "dna-visualisation,graph-bfs"}
    ctx = _ctx(tmp_path, mem_budget_mb="1100", **opts)
    sebs.run(ctx)
    # dna-visualisation: 1024 MB per guest → only 1 guest fits in 1100 MB; graph-bfs: 512 MB → 1 and 2 guests fit
    assert _ran(capsys.readouterr().out) == [
        "fn=dna-visualisation concurrency=1",
        "fn=graph-bfs concurrency=1",
        "fn=graph-bfs concurrency=2",
    ]
    assert "sebs fn=dna-visualisation concurrency=8" in _skipped(ctx)


def test_sebs_max_concurrency_option(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    opts = {"kernel": "/a/k", "sebs_rootfs": "/a/r", "firecracker": "/a/fc", "functions": "graph-bfs"}
    sebs.run(_ctx(tmp_path, mem_budget_mb="99999", max_concurrency="2", **opts))
    assert _ran(capsys.readouterr().out) == ["fn=graph-bfs concurrency=1", "fn=graph-bfs concurrency=2"]


def test_disk_leaves_out_tests_that_do_not_fit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert disk.size_mb("2G") == 2048 and disk.size_mb("512M") == 512 and disk.size_mb("1048576") == 1
    # fio needs 2048 MB, dm-crypt 3072, dm-verity 2200, each plus the 2048 MB reserve
    for free, expected in (
        (3000, ["disk fio tier=ssd", "disk dm-crypt tier=ssd", "disk dm-verity tier=ssd"]),
        (4500, ["disk dm-crypt tier=ssd"]),
        (9000, []),
    ):
        monkeypatch.setattr("tools.calibrate.suites.free_mb", lambda d, f=free: f)
        ctx = _ctx(tmp_path / str(free), ssd_dir=str(tmp_path / str(free) / "ssd"))
        disk.run(ctx)
        assert _skipped(ctx) == expected


def _fake_raw(root: Path, host_name: str = "labbox") -> Path:
    raw = root / "raw"
    for suite, status in (("caps", "ok"), ("disk", "skipped: pass --set ssd_dir"), ("tpm", "error")):
        for run_id in ("20261014T100000", "20261014T110000"):
            d = raw / "c0-abc" / suite / run_id
            d.mkdir(parents=True)
            st = ("error" if run_id.endswith("100000") else "ok") if suite == "tpm" else status
            meta = {"suite": suite, "status": st, "hostname": host_name, "options": {"kernel": "/home/alice/a/vmlinux"}}
            (d / "meta.json").write_text(json.dumps(meta))
            (d / "records.jsonl").write_text('{"probe": "x"}\n' * (3 if suite == "caps" else 1))
            (d / "commands.txt").write_text("ls /home/alice\n")
    (raw / "c0-abc" / "fc_boot").mkdir()
    (raw / "c0-abc" / "fc_boot" / "voss-rootfs.ext4").write_bytes(b"\0" * 1000)  # a scratch image must never ship
    (raw / "c0-abc" / "tpm" / "20261014T110000" / "ek.pub").write_text("endorsement key")  # hardware identifier
    (raw / "env.txt").write_text("user alice on labbox")
    return raw


def test_report_summary_uses_each_suites_newest_run(tmp_path: Path) -> None:
    from tools.calibrate import report

    text = report.summary(_fake_raw(tmp_path))
    assert "caps" in text and "all suites ok" not in text
    assert "not ok: disk" in text and "tpm" not in text.split("not ok:")[1]  # tpm failed once; its newest run is ok
    assert "no runs under" in report.summary(tmp_path / "empty")


def test_report_pack_scrubs_identifying_strings_and_leaves_out_images(tmp_path: Path) -> None:
    import tarfile

    from tools.calibrate import report

    raw = _fake_raw(tmp_path)
    out = report.pack(raw, tmp_path / "x.tar.gz", {"/home/alice": "/home/USER", "alice": "USER", "labbox": "HOST"})
    with tarfile.open(out) as tar:
        names = tar.getnames()
        members = [m for m in tar.getmembers() if m.isfile() and m.name.endswith((".json", ".txt"))]
        blob = "".join(str(tar.extractfile(m).read(), "utf-8") for m in members)  # type: ignore[union-attr]
    assert "raw/MANIFEST.sha256" in names and "raw/env.txt" in names
    assert not any(n.endswith(("ek.pub", ".ext4")) for n in names)  # only whitelisted result files are archived
    assert "alice" not in blob and "labbox" not in blob and "/home/USER/a/vmlinux" in blob
    assert (raw / "c0-abc" / "caps" / "20261014T110000" / "meta.json").read_text().count("labbox") == 1  # original kept


def test_scrub_is_whole_word_and_path_first() -> None:
    from tools.calibrate.report import scrub_text

    sec = {"/home/pi": "/home/USER", "pi": "USER", "alice": "USER", "box7": "HOST"}
    text = '{"hostname": "box7", "p": "/home/pi/x", "note": "pipeline for alice, alice-ng, rootfs"}'
    out = scrub_text(text, sec)
    assert '"hostname": "HOST"' in out and "/home/USER/x" in out and "pipeline" in out  # 'pi' is too short to match
    assert "for USER," in out and "alice-ng" in out  # whole words only
    # a user called "root": the word goes, the word "rootfs" stays
    assert scrub_text("root hash rootfs /root/a", {"/root": "/home/USER", "root": "USER"}) == (
        "USER hash rootfs /home/USER/a"
    )
