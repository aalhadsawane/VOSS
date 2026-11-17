"""P9 harness, local side (doc 10 §1): raw records → measured bundle, its use by the simulator, and SSH commands."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from tools.calibrate import ingest, remote
from voss.core.rng import RngFactory
from voss.world.hardware import load_hw_class
from voss.world.substrate import load_bundle

REPO = Path(__file__).resolve().parents[2]
PLACEHOLDER = REPO / "configs/calibration/placeholder/c0"


def _run(root: Path, suite: str, run_id: str, rows: list[dict[str, Any]], **meta: Any) -> None:
    d = root / "c0-test" / suite / run_id
    d.mkdir(parents=True)
    with (d / "records.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps({"suite": suite, "rep": 0, "unit": "s", "config": {}} | r) + "\n")
    info = {"run_id": run_id, "status": "ok", "dry_run": False, "harness_version": "test", "phase": None} | meta
    (d / "meta.json").write_text(json.dumps(info))


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    g = RngFactory(1).stream("test.ingest")
    root = tmp_path / "raw"
    quotes = g.lognormal(np.log(0.03), 0.2, 200)
    _run(root, "tpm", "r1", [{"probe": "tpm2_quote", "value": float(v)} for v in quotes])
    boot = [{"probe": "fc_boot", "value": 0.12, "config": {"mem_mb": 256, "tier": "ssd", "cache": "warm"}}]
    boot.append({"probe": "fc_boot", "value": 9.0, "config": {"mem_mb": 2048, "tier": "hdd", "cache": "cold"}})
    _run(root, "fc_boot", "r1", boot)
    disk = [
        {"probe": "ssd_seq_read_MBps", "value": 5000.0, "unit": "MBps"},
        {"probe": "hash_per_MB", "value": 1 / 2000.0},
    ]
    _run(root, "disk", "r1", disk)
    _run(root, "tme", "on", [{"probe": "stream_triad", "value": 90.0}], phase="on")
    _run(root, "tme", "off", [{"probe": "stream_triad", "value": 100.0}], phase="off")
    _run(root, "tpm", "broken", [{"probe": "tpm2_quote", "value": 99.0}], status="error")
    sebs = [
        {"probe": "sebs_exec", "value": 0.1 * s**0.5, "config": {"fn": "thumbnailer", "size_kb": s, "concurrency": n}}
        for s in (50, 200, 800)
        for n in (1, 4)
    ]
    sebs.append({"probe": "sebs_init", "value": 0.4, "config": {"fn": "thumbnailer", "size_kb": 0, "concurrency": 1}})
    _run(root, "sebs", "r1", sebs)
    return root


def test_bundle_is_complete_valid_and_tagged(raw: Path) -> None:
    fp, files = ingest.build(raw, None, PLACEHOLDER)
    assert fp == "c0-test"
    dists = files["distributions.yaml"]["distributions"]
    base = yaml.safe_load((PLACEHOLDER / "distributions.yaml").read_text())["distributions"]
    assert set(dists) == set(base)  # every entry the substrates reference is present
    assert dists["tpm2_quote"]["tag"] == "measured" and dists["tpm2_quote"]["dist"] == "empirical"
    assert max(dists["tpm2_quote"]["quantiles"]) < 1.0  # the errored run is ignored
    assert dists["fc_boot"]["quantiles"][0] == pytest.approx(0.12)  # `where` filter applied
    assert dists["verify_s_per_MB"] == pytest.approx({**dists["verify_s_per_MB"], "value": 1 / 2000.0})
    assert dists["tme_mem_factor"]["value"] == pytest.approx(100.0 / 90.0)
    assert dists["reboot_to_kernel"]["tag"] != "measured"  # not measured: placeholder kept
    assert "reboot_to_kernel" in files["meta.yaml"]["missing"]
    fit = files["fits.yaml"]["tpm2_quote"]
    assert fit["median"] == pytest.approx(0.03, rel=0.1) and fit["sigma"] == pytest.approx(0.2, rel=0.25)
    assert files["hardware.yaml"]["classes"]["C0"] == {"ssd_read_MBps": 5000.0}
    th = files["functions.yaml"]["functions"]["thumbnailer"]
    assert th["size_exp"] == pytest.approx(0.5) and th["init_s"] == pytest.approx(0.4)
    assert th["work_ref_s"] == pytest.approx(0.1 * 200**0.5)


def test_simulator_reads_the_measured_bundle(raw: Path, tmp_path: Path) -> None:
    fp, files = ingest.build(raw, None, PLACEHOLDER)
    out = tmp_path / "measured" / fp
    out.mkdir(parents=True)
    for name, data in files.items():
        (out / name).write_text(yaml.safe_dump(data))
    bundle = load_bundle(str(out))
    assert bundle["tpm2_quote"].tag == "measured"
    assert load_hw_class("C0", str(out)).ssd_read_MBps == 5000.0
    assert load_hw_class("C0").ssd_read_MBps != 5000.0  # placeholder default unchanged
    from voss.core.config import ScenarioConfig
    from voss.world.workload import load_catalog

    cat = {f.name: f for f in load_catalog(ScenarioConfig(), str(out)).functions}
    assert cat["thumbnailer"].work_ref_s == pytest.approx(0.1 * 200**0.5)
    assert cat["thumbnailer"].init_s == pytest.approx(0.4)


def test_remote_commands_quote_and_gate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a = remote.parse(
        ["--host", "u@c0", "--suite", "tpm", "--set", "ssd_dir=/mnt/a b", "--sudo", "--raw", str(tmp_path)]
    )
    cmd = remote.remote_cmd(a)
    outer = shlex.split(cmd)
    assert outer[:4] == ["sudo", "-n", "sh", "-c"]
    inner = shlex.split(outer[4].split("&& ", 1)[1])
    assert inner[:3] == ["python3", "-m", "tools.calibrate.run"] and "ssd_dir=/mnt/a b" in inner
    assert "--allow-reboot" not in cmd
    rc = remote.main(["--host", "u@c0", "--suite", "caps", "--print-only", "--raw", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0 and out.count("$ ") == 5 and "rsync" in out  # mkdir, 2 pushes, run, pull


def test_committed_measured_bundle_is_complete_and_its_hash_is_documented() -> None:
    """The laptop bundle (P9 exit): same entries as the placeholder, tagged, and the hash in the validation notes."""
    from voss.metrics.manifest import hash_dir
    from voss.world.substrate import load_bundle

    name = "laptop-b9212a4528"
    measured = load_bundle(f"calibration/measured/{name}")
    assert set(measured) >= set(load_bundle("calibration/placeholder/c0"))  # drtm_launch left the placeholder later
    assert {d.tag for d in measured.values()} >= {"measured", "assumed"}
    digest = hash_dir(REPO / "configs" / "calibration" / "measured" / name)
    assert digest in (REPO / "docs" / "validation" / "README.md").read_text()


def test_sebs_concurrencies_and_host_meta_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.calibrate.common import Records, Shell, host_meta
    from tools.calibrate.suites import Ctx, sebs

    monkeypatch.setattr("os.cpu_count", lambda: 20)
    rec = Records(tmp_path / "r.jsonl", "sebs")
    ctx_default = Ctx(Shell(dry_run=True), rec, tmp_path, {"physical_cores": "10"})
    assert sebs.concurrencies(ctx_default) == [1, 2, 4, 8, 10, 20]  # powers of two, physical cores, threads
    ctx_capped = Ctx(Shell(dry_run=True), rec, tmp_path, {"physical_cores": "10", "max_concurrency": "8"})
    assert sebs.concurrencies(ctx_capped) == [1, 2, 4, 8]
    ctx_exp = Ctx(Shell(dry_run=True), Records(tmp_path / "r.jsonl", "sebs"), tmp_path, {"concurrencies": "1,6,12"})
    assert sebs.concurrencies(ctx_exp) == [1, 6, 12]
    meta = host_meta(Shell(dry_run=True))
    assert {"cores", "threads", "tpm_vendor", "disks"} <= set(meta)
    assert int(meta["cores"]) >= 1 and int(meta["threads"]) >= 1


def test_ingest_label_versions_a_bundle_without_copying_raw(raw: Path) -> None:
    """A suite added later (the appliance run) re-ingests the same raw logs under a new bundle name."""
    name, files = ingest.build(raw, "c0-test", PLACEHOLDER, label="c0-test-v2")
    assert name == "c0-test-v2"
    assert files["distributions.yaml"]["host"] == "c0-test-v2"
    assert files["meta.yaml"]["bundle"] == "c0-test-v2" and files["meta.yaml"]["raw_host"] == "c0-test"
    assert all(k.startswith("c0-test/") for k in files["meta.yaml"]["raw_files"])  # raw paths stay real


def _rows(probe: str, scale: float, **cfg: Any) -> list[dict[str, Any]]:
    """200 samples spread +-10% around ``scale``."""
    return [
        {"probe": probe, "value": float(v) * scale, "rep": i, "config": cfg}
        for i, v in enumerate(np.linspace(0.9, 1.1, 200))
    ]


def _full_node(root: Path, tme_phases: tuple[str, ...] = ("on", "off")) -> Path:
    """Raw logs as one node's measuring stages write them: every probe a bundle entry comes from, with the suites'
    own probe names and config keys (NVMe tier)."""
    raw, fn = root / "raw", {"fn": "thumbnailer", "size_kb": 50}
    _run(raw, "tpm", "r1", _rows("tpm2_quote", 0.19) + _rows("tpm2_unseal", 0.1))
    _run(raw, "attest_local", "r1", _rows("attest_verify", 0.006))
    keys = _rows("key_request", 0.04) + _rows("kbs_check", 5e-4)
    _run(raw, "keys", "r1", [*keys, {"probe": "key_unwrap", "value": 4e-4}, {"probe": "decrypt_per_MB", "value": 1e-4}])
    disk = _rows("hash_per_MB", 4.4e-4) + _rows("nvme_seq_read_MBps", 6000.0) + _rows("nvme_seq_write_MBps", 4000.0)
    _run(raw, "disk", "r1", disk)
    _run(raw, "fc_boot", "r1", _rows("fc_boot", 0.045, mem_mb=256, tier="nvme", cache="warm"))
    snap = _rows("fc_restore_api", 0.0023, mem_mb=512, tier="nvme", cache="warm")
    _run(raw, "fc_snapshot", "r1", snap + _rows("fc_snapshot_create", 0.25, mem_mb=512, tier="nvme"))
    _run(raw, "fc_dispatch", "r1", _rows("dispatch_warm", 0.001, **fn))
    _run(raw, "fc_touched", "r1", _rows("snapshot_touched_frac", 0.2, tier="nvme", cache="cold", **fn))
    _run(raw, "appliance", "r1", _rows("reboot_to_kernel", 20.0) + _rows("appliance_userspace", 7.0))
    _run(raw, "fn_inputs", "r1", _rows("fn_input_gen", 0.01, **fn))
    _run(raw, "sebs", "r1", _rows("sebs_exec", 0.002, concurrency=1, **fn))
    for phase in tme_phases:
        slow = 1.05 if phase == "on" else 1.0
        tme = _rows("stream_triad", 100.0 / slow) + _rows("sebs_exec", 0.002 * slow, concurrency=1, **fn)
        _run(raw, "tme", phase, tme, phase=phase)
    _run(raw, "tpm", "quick", _rows("tpm2_quote", 9.0), quick=True)  # a smoke pass: never ingested
    return raw


def _write(files: dict[str, Any], out: Path) -> Path:
    out.mkdir()
    for name, data in files.items():
        (out / name).write_text(yaml.safe_dump(data))
    return out


def test_every_simulator_entry_has_a_probe() -> None:
    """Guardrails 28-29: each bundle entry a substrate or voss/ reads comes from a harness probe (mapping.yaml)."""
    from tools.calibrate import check_bundle

    mapping = yaml.safe_load((REPO / "tools/calibrate/mapping.yaml").read_text())
    have = set(mapping["distributions"]) | set(mapping["ratios"])
    entries = check_bundle.simulator_entries()
    assert {"dispatch", "kbs_check_s", "snapshot_touched_frac", "tme_cpu_factor", "tpm2_quote"} <= entries
    assert entries <= have, entries - have
    assert entries <= set(check_bundle.REQUIRED) | set(check_bundle.RATIOS)


def test_a_newly_ingested_bundle_has_every_simulator_entry_measured(tmp_path: Path) -> None:
    from tools.calibrate import check_bundle

    _, files = ingest.build(_full_node(tmp_path), "c0-test", PLACEHOLDER, tier="nvme")
    dists = files["distributions.yaml"]["distributions"]
    assert check_bundle.unmeasured(dists) == []
    assert dists["tpm2_quote"]["quantiles"][-1] < 1.0  # the quick run is left out
    assert dists["tme_cpu_factor"]["value"] == pytest.approx(1.05)
    assert files["hardware.yaml"]["classes"]["C0"]["ssd_read_MBps"] == pytest.approx(6000.0)  # the tier's own disk
    th = files["functions.yaml"]["functions"]["thumbnailer"]
    assert th["input_gen_by_size"] == {50: pytest.approx(0.01)}
    assert th["snapshot_touched_frac"] == pytest.approx(0.2)
    errors = check_bundle.check_distributions(_write(files, tmp_path / "bundle"))
    assert errors == [], errors


def test_tme_factors_stay_missing_with_one_phase(tmp_path: Path) -> None:
    """Both nodes so far had TME disabled in firmware: one phase gives no factor, and check_bundle says so."""
    from tools.calibrate import check_bundle

    _, files = ingest.build(_full_node(tmp_path, ("off",)), "c0-test", PLACEHOLDER, tier="nvme")
    dists = files["distributions.yaml"]["distributions"]
    assert check_bundle.unmeasured(dists) == ["tme_cpu_factor", "tme_mem_factor"]
    assert {"tme_cpu_factor", "tme_mem_factor"} <= set(files["meta.yaml"]["missing"])
    errors = check_bundle.check_distributions(_write(files, tmp_path / "bundle"))
    assert len(errors) == 2 and all("missing, not measured" in e and "--phase on" in e for e in errors)
