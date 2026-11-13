"""Shared helpers for trace tools: downloads with checksums, provenance records, file hashes."""

from __future__ import annotations

import datetime as dt
import hashlib
import subprocess
from pathlib import Path
from typing import Any

import yaml


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, dst: Path, attempts: int = 8) -> Path:
    """Fetch ``url`` to ``dst`` unless it is already there. Large archive files break mid-transfer (HTTP/2 stream
    resets from the Internet Archive), so the transfer uses HTTP/1.1 and resumes the partial file (``-C -``) on each
    attempt; curl follows redirects and fails on HTTP errors."""
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    cmd = ["curl", "-fsSL", "--http1.1", "-C", "-", "--retry", "5", "--retry-all-errors", "-o", str(tmp), url]
    for k in range(attempts):
        if subprocess.run(cmd, check=False).returncode == 0:
            tmp.rename(dst)
            return dst
        print(f"download attempt {k + 1} of {attempts} broke at {tmp.stat().st_size if tmp.exists() else 0} bytes")
    raise RuntimeError(f"could not download {url} after {attempts} attempts")


def write_provenance(out: Path, source: dict[str, Any], inputs: list[Path], params: dict[str, Any]) -> Path:
    """``provenance.yaml`` next to the derived files: source, inputs and outputs with SHA-256, derivation parameters."""
    outputs = sorted(p for p in out.iterdir() if p.is_file() and p.name != "provenance.yaml")
    rec = {
        "source": source,
        "retrieved_utc": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": {p.name: sha256(p) for p in inputs},
        "outputs": {p.name: sha256(p) for p in outputs},
        "params": params,
    }
    path = out / "provenance.yaml"
    path.write_text(yaml.safe_dump(rec, sort_keys=False))
    return path
