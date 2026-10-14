"""P9 harness, node side (doc 10): output parsers, the reboot/BIOS safety gate, and dry runs of every suite."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from tools.calibrate import run as harness
from tools.calibrate.common import Records, Shell
from tools.calibrate.fc import MARK, boot_args
from tools.calibrate.suites import Ctx, appliance, caps, disk, sebs, tme

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
    from tools.calibrate.common import SuiteSkipped

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


HOST = Path(__file__).resolve().parents[2] / "tools" / "calibrate" / "appliance" / "host"
PROBE_LOG = (
    "VOSS_E arm 1000.0\nVOSS_E btime 1012\nVOSS_E prev_end 1004.5\nVOSS_T agent_ready 9.0\n"
    "VOSS_T quote_done 9.4\nVOSS_T verifier_ok 9.5\nVOSS_ANALYZE_BEGIN\n"
    "Startup finished in 2.0s (kernel) + 6.0s (userspace) = 8.0s\nVOSS_ANALYZE_END\n"
)


def test_appliance_host_probe_log_becomes_wallclock_records(tmp_path: Path) -> None:
    """D-60: no firmware/loader in systemd-analyze under GRUB, so reboot time comes from wall-clock stamps."""
    (tmp_path / "probe-0001.log").write_text(PROBE_LOG)
    (tmp_path / "probe-0002.log").write_text("VOSS_E arm 2000.0\nVOSS_ERR createek\n")
    ctx = Ctx(Shell(dry_run=True), Records(tmp_path / "r.jsonl", "appliance"), tmp_path, {})
    assert appliance.collect(ctx, tmp_path) == 1
    rows = {r["probe"]: r for r in map(json.loads, (tmp_path / "r.jsonl").read_text().splitlines())}
    assert rows["shutdown"]["value"] == pytest.approx(4.5)
    assert rows["firmware_loader"]["value"] == pytest.approx(7.5)
    assert rows["reboot_cmd_to_kernel"]["value"] == pytest.approx(12.0)
    assert (
        rows["reboot_to_kernel"]["value"] == pytest.approx(9.5)
        and rows["reboot_to_kernel"]["config"]["method"] == "wallclock"
    )
    assert rows["appliance_userspace"]["value"] == pytest.approx(7.0)
    assert rows["appliance_attested"]["value"] == pytest.approx(7.5)
    assert rows["boot_incomplete"]["config"]["file"] == "probe-0002.log"


def _driver(tmp_path: Path, n: int = 3, **env: str) -> tuple[str, Path]:
    conf = tmp_path / "config"
    conf.write_text(f"ORIG_TARGET=graphical.target\nN={n}\nSETTLE=0\n")
    d = tmp_path / "d"
    e = {
        "PATH": os.environ["PATH"],
        "VOSS_DRY": "1",
        "VOSS_CALIB_CONF": str(conf),
        "VOSS_CALIB_DIR": str(d),
        "VOSS_CALIB_BIN": str(HOST),
        **env,
    }
    out = subprocess.run(["sh", str(HOST / "voss-calib-driver")], env=e, capture_output=True, text=True, check=True)
    return out.stdout, d


def _arm(tmp_path: Path) -> None:
    e = {"PATH": os.environ["PATH"], "VOSS_DRY": "1", "VOSS_CALIB_DIR": str(tmp_path / "d")}
    subprocess.run(["sh", str(HOST / "voss-calib-arm")], env=e, check=True, capture_output=True)


def test_driver_arms_then_finishes_after_n_completed_boots(tmp_path: Path) -> None:
    out, d = _driver(tmp_path)
    assert "boot 1 of 3" in out and "voss-calib-arm" in out
    for i in (1, 2, 3):
        _arm(tmp_path)
        (d / f"complete-{i:04d}").touch()
    out, d = _driver(tmp_path)
    assert "finished" in out and "set-default graphical.target" in out and (d / "DONE").exists()


def test_driver_stops_on_two_unfinished_boots_and_on_stop_file(tmp_path: Path) -> None:
    _driver(tmp_path)
    _arm(tmp_path)
    _arm(tmp_path)
    out, d = _driver(tmp_path)
    assert "two unfinished boots" in out and (d / "STOP").exists()
    out, _ = _driver(tmp_path)
    assert "STOP file present" in out


def test_probe_without_arm_stamp_fails_and_with_one_completes(tmp_path: Path) -> None:
    d = tmp_path / "d"
    d.mkdir()
    e = {"PATH": os.environ["PATH"], "VOSS_CALIB_DIR": str(d)}
    bad = subprocess.run(["sh", str(HOST / "voss-calib-probe")], env=e, capture_output=True, text=True, check=False)
    assert bad.returncode == 1 and "VOSS_ERR" in (d / "probe-0000.log").read_text()
    _arm(tmp_path)
    ok = subprocess.run(["sh", str(HOST / "voss-calib-probe")], env=e, capture_output=True, text=True, check=False)
    assert ok.returncode == 0 and (d / "complete-0001").exists()
    assert "VOSS_E arm" in (d / "probe-0001.log").read_text()


def test_systemd_units_are_one_shot_and_bounded() -> None:
    probe = (HOST / "voss-calib-probe.service").read_text()
    assert "SuccessAction=reboot" in probe and "RuntimeMaxSec=600" in probe
    assert "STOP" in (HOST / "voss-calib-driver.service").read_text()


def test_host_install_and_uninstall_into_a_staging_tree(tmp_path: Path) -> None:
    e = {"PATH": os.environ["PATH"], "DESTDIR": str(tmp_path), "SETTLE": "5"}
    sh = ["sh", str(HOST / "install.sh")]
    subprocess.run([*sh, "install", "7"], env=e, check=True, capture_output=True)
    conf = (tmp_path / "var/lib/voss-calib/config").read_text()
    assert "N=7" in conf and "SETTLE=5" in conf and "ORIG_TARGET=" in conf
    assert (tmp_path / "usr/local/sbin/voss-calib-driver").stat().st_mode & 0o111
    assert (tmp_path / "etc/systemd/system/voss-calib.target").exists()
    subprocess.run([*sh, "uninstall"], env=e, check=True, capture_output=True)
    assert not (tmp_path / "etc/systemd/system/voss-calib.target").exists()
    assert (
        not (tmp_path / "var/lib/voss-calib/config").exists() and (tmp_path / "var/lib/voss-calib/appliance").is_dir()
    )


def test_auto_stage_machine_resumes_across_reboots(tmp_path: Path) -> None:
    """The one-command flow: stages persist in a state dir, the appliance stage hands over to the reboot loop and the
    next boot continues where it left off (stubs for main script and systemctl; nothing is installed or rebooted)."""
    auto = HOST.parents[1] / "laptop" / "voss-calib-auto.sh"
    root, home = tmp_path / "root", tmp_path / "home"
    (root / "etc/voss-calib").mkdir(parents=True)
    home.mkdir()
    (root / "etc/voss-calib/auto.env").write_text(f"TARGET_USER=tester\nTARGET_HOME={home}\nBOOTS=2\n")
    calib = root / "var/lib/voss-calib"
    stub = tmp_path / "main.sh"
    stub.write_text(
        f'#!/bin/sh\necho "$@" >>{tmp_path}/calls\n'
        f'case "$1 $2" in\n'
        f'  "appliance run") mkdir -p {calib}/appliance; touch {calib}/config;;\n'
        f'  "pack ") mkdir -p {home}/voss-calib-work; echo x >{home}/voss-calib-work/voss-calib-t-1.tar.gz;;\n'
        f"esac\n"
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("systemctl", "wall", "sh"):
        if tool != "sh":
            (bindir / tool).write_text("#!/bin/sh\nexit 0\n")
            (bindir / tool).chmod(0o755)
    env = {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "VOSS_AUTO_ROOT": str(root),
        "VOSS_AUTO_MAIN": f"sh {stub}",
        "VOSS_AUTO_REBOOT_WAIT": "0",
    }
    run = ["bash", str(auto), "stages"]
    subprocess.run(run, env=env, check=True, capture_output=True)  # boot 1: setup, full, then the reboot test starts
    state = root / "var/lib/voss-calib/auto"
    assert (state / "stage").read_text().strip() == "appliance" and not (state / "DONE").exists()
    (calib / "appliance").mkdir(parents=True, exist_ok=True)
    (calib / "appliance" / "DONE").touch()  # the reboot loop finished by itself
    subprocess.run(run, env=env, check=True, capture_output=True)  # a later boot: tme, finish
    assert (state / "DONE").exists()
    calls = (tmp_path / "calls").read_text().splitlines()
    assert calls[0].startswith("setup") and "full" in calls and "appliance run 2" in calls
    assert calls.index("full") < calls.index("appliance run 2") < calls.index("pack")
    assert list(home.glob("voss-calib-tester-*.tar.gz")) and "SHA-256" in (home / "VOSS-CALIB-DONE.txt").read_text()


def test_fingerprint_ignores_memtotal_jitter_and_uses_the_node_label(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seen on the stand-in laptop: MemTotal differed by a few kB between boots and split one machine into 3 folders."""
    from tools.calibrate.common import fingerprint

    meta = {"cpu_model": "x", "board": "b", "bios_version": "v", "mem_kb": 3907364}
    monkeypatch.setenv("VOSS_NODE", "alice")
    assert fingerprint(meta) == fingerprint({**meta, "mem_kb": 3907376}) and fingerprint(meta).startswith("alice-")
    assert fingerprint(meta) != fingerprint({**meta, "mem_kb": 7814728})


def test_appliance_collect_rejects_a_stepped_clock(tmp_path: Path) -> None:
    (tmp_path / "probe-0001.log").write_text(PROBE_LOG.replace("prev_end 1004.5", "prev_end -18800.0"))
    ctx = Ctx(Shell(dry_run=True), Records(tmp_path / "r.jsonl", "appliance"), tmp_path, {})
    assert appliance.collect(ctx, tmp_path) == 0
    assert "clock step" in (tmp_path / "r.jsonl").read_text()


def test_firecracker_socket_path_stays_short_in_deep_directories(tmp_path: Path) -> None:
    """AF_UNIX paths are limited to 107 bytes; a deep results directory broke rep 10 of fc_snapshot on the laptop."""
    from tools.calibrate.fc import FcAssets, FcVm

    deep = tmp_path / ("d" * 60) / ("e" * 60)
    vm = FcVm(FcAssets("/bin/true", "k", "r"), deep, "snapr-128-hdd-warm-10")
    with contextlib.suppress(RuntimeError):  # /bin/true exits at once: only the chosen socket path matters here
        vm.spawn()
    assert len(vm.sock.encode()) < 100
