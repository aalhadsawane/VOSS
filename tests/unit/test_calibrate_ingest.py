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
    disk = [{"probe": "ssd_seq_read_MBps", "value": 5000.0, "unit": "MBps"}, {"probe": "sha256_MBps", "value": 2000.0}]
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


def test_ecs1_measured_table(raw: Path, tmp_path: Path) -> None:
    from experiments import ecs1_measured

    out = tmp_path / "ecs1.md"
    ecs1_measured.main(["--raw", str(raw), "--out", str(out)])
    text = out.read_text()
    assert "| TPM quote | — | 200 |" in text
    assert "mem_mb=256, tier=ssd, cache=warm" in text and "| Appliance reboot → kernel | not measured | 0 |" in text
