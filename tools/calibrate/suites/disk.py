"""Disk suite (doc 10 §3): SSD and HDD sequential/random read/write with ``fio``, dm-crypt and dm-verity overhead,
and SHA-256 throughput (artifact verification cost). Feeds the cache tier speeds of doc 02 §6 and hardware ``C0``.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from tools.calibrate.common import Shell, SuiteSkipped, is_root
from tools.calibrate.suites import Ctx, Suite

JOBS: dict[str, list[str]] = {
    "seq_read": ["--rw=read", "--bs=1M", "--iodepth=8"],
    "seq_write": ["--rw=write", "--bs=1M", "--iodepth=8"],
    "rand_read_4k": ["--rw=randread", "--bs=4k", "--iodepth=32"],
    "rand_write_4k": ["--rw=randwrite", "--bs=4k", "--iodepth=32"],
}


def fio_result(text: str) -> dict[str, float]:
    """Bandwidth (MB/s), IOPS and completion-latency median (s) of the job's active direction."""
    job = json.loads(text)["jobs"][0]
    side = job["read"] if job["read"].get("io_bytes", 0) > 0 else job["write"]
    pct = side.get("clat_ns", {}).get("percentile", {})
    p50 = next((v for k, v in pct.items() if k.startswith("50.")), side.get("clat_ns", {}).get("mean", 0.0))
    return {"MBps": side["bw_bytes"] / 1e6, "iops": float(side["iops"]), "lat_p50_s": float(p50) / 1e9}


def fio(sh: Shell, target: str, job: str, size: str, runtime_s: int) -> list[str]:
    return [
        "fio",
        f"--name={job}",
        f"--filename={target}",
        f"--size={size}",
        "--direct=1",
        "--ioengine=libaio",
        f"--runtime={runtime_s}",
        "--time_based",
        "--output-format=json",
        *JOBS[job],
    ]


def _bench(ctx: Ctx, target: str, prefix: str, jobs: tuple[str, ...], **cfg: Any) -> None:
    for job in jobs:
        for rep in range(ctx.reps(5)):
            c = ctx.sh.run(fio(ctx.sh, target, job, ctx.opt("fio_size", "2G"), int(ctx.opt("fio_runtime", "15"))))
            if ctx.sh.dry_run:
                continue
            for metric, v in fio_result(c.out).items():
                unit = "MBps" if metric == "MBps" else ("iops" if metric == "iops" else "s")
                ctx.rec.add(f"{prefix}_{job}_{metric}", v, unit=unit, rep=rep, **cfg)


CRYPT_MB, VERITY_MB = 3072, 2200  # image file sizes of the dm-crypt and dm-verity tests


def size_mb(text: str) -> float:
    """fio-style size (``2G``, ``512M``) in MB; plain numbers are bytes."""
    t = text.strip().upper()
    scale = {"K": 1 / 1024, "M": 1.0, "G": 1024.0, "T": 1024.0**2}
    return float(t[:-1]) * scale[t[-1]] if t[-1] in scale else float(t) / 2**20


def sha256_MBps(mb: int = 256) -> float:
    buf = bytes(range(256)) * (mb * 4096)
    t0 = time.perf_counter()
    hashlib.sha256(buf).digest()
    return mb / (time.perf_counter() - t0)


def _crypt(ctx: Ctx, d: Path) -> None:
    """LUKS2 on a loop device over a file on the tier (the appliance's encrypted cache partition, doc 04 §4)."""
    sh = ctx.sh
    img, key = d / "voss-crypt.img", d / "voss-crypt.key"
    sh.run(["truncate", "-s", "3G", str(img)])
    key.write_bytes(b"voss-calibration-only") if not sh.dry_run else None
    loop = sh.run(["losetup", "--find", "--show", str(img)]).out.strip() or "/dev/loopX"
    try:
        sh.run(["cryptsetup", "luksFormat", "--batch-mode", "--type", "luks2", "--key-file", str(key), loop])
        sh.run(["cryptsetup", "open", "--key-file", str(key), loop, "voss-crypt"])
        _bench(ctx, "/dev/mapper/voss-crypt", f"{d.name}_crypt", ("seq_read", "seq_write"), layer="dm-crypt")
    finally:
        sh.run(["cryptsetup", "close", "voss-crypt"], check=False)
        sh.run(["losetup", "-d", loop], check=False)
        img.unlink(missing_ok=True)
        key.unlink(missing_ok=True)


def verity_root_hash(format_out: str) -> str:
    m = re.search(r"Root hash:\s*([0-9a-f]+)", format_out)
    if not m:
        raise RuntimeError("veritysetup format printed no root hash")
    return m.group(1)


def _verity(ctx: Ctx, d: Path) -> None:
    """dm-verity read path (the appliance's verified root and artifact store)."""
    sh = ctx.sh
    data, hashes = d / "voss-verity.data", d / "voss-verity.hash"
    sh.run(["dd", "if=/dev/urandom", f"of={data}", "bs=1M", "count=2048", "status=none"])
    try:
        out = sh.run(["veritysetup", "format", str(data), str(hashes)]).out
        root = "0" * 64 if sh.dry_run else verity_root_hash(out)
        sh.run(["veritysetup", "open", str(data), "voss-verity", str(hashes), root])
        _bench(ctx, "/dev/mapper/voss-verity", f"{d.name}_verity", ("seq_read",), layer="dm-verity")
    finally:
        sh.run(["veritysetup", "close", "voss-verity"], check=False)
        data.unlink(missing_ok=True)
        hashes.unlink(missing_ok=True)


def run(ctx: Ctx) -> None:
    ctx.sh.need("fio")
    dirs = ctx.dirs()
    if not dirs:
        raise SuiteSkipped("pass --set ssd_dir=<dir on the NVMe> --set hdd_dir=<dir on the HDD>")
    for rep in range(ctx.reps(5)):
        ctx.rec.add("sha256_MBps", 0.0 if ctx.sh.dry_run else sha256_MBps(), unit="MBps", rep=rep)
    for tier, d in sorted(dirs.items()):
        d.mkdir(parents=True, exist_ok=True)
        need = size_mb(ctx.opt("fio_size", "2G"))
        if not ctx.has_room(d, need):
            ctx.skip(f"disk fio tier={tier}", need, "not enough free disk")
            continue
        target = str(d / "voss-fio.dat")
        _bench(ctx, target, tier, tuple(JOBS), tier=tier)
        Path(target).unlink(missing_ok=True)
    missing = [t for t in ("cryptsetup", "veritysetup", "losetup") if not ctx.sh.have(t)]
    if not (is_root() or ctx.sh.dry_run) or missing:
        ctx.rec.add("crypt_skipped", 1.0, unit="bool", reason="needs root" if not missing else f"missing {missing}")
        return
    for tier, d in sorted(dirs.items()):
        for what, need, fn in (("dm-crypt", CRYPT_MB, _crypt), ("dm-verity", VERITY_MB, _verity)):
            if ctx.has_room(d, need):
                fn(ctx, d)
            else:
                ctx.skip(f"disk {what} tier={tier}", need, "not enough free disk")


SUITE = Suite("disk", run, "fio on SSD/HDD (+ dm-crypt, dm-verity), SHA-256 throughput")
