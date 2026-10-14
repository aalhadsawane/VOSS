"""Run summary and a shareable archive of the raw logs (doc 10 §1): ``python3 -m tools.calibrate.report summary RAW``
shows each suite's latest status; ``... pack RAW OUT.tar.gz`` writes an archive of the result files only, with the user
name, home directory and host name removed, plus a SHA-256 manifest. Standard library only (runs on the node)."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import platform
import re
import sys
import tarfile
import tempfile
from pathlib import Path

# Only what ``ingest`` and a human reviewer need. Everything else in a run directory (TPM key contexts, the endorsement
# key, private keys of the TLS/attestation tests, disk images, Firecracker sockets) never leaves the machine.
MIN_NAME = 4
KEEP = {"records.jsonl", "meta.json", "commands.txt", "error.txt", "caps.json"}
TOP = {"env.txt"}


def latest_runs(raw: Path) -> list[tuple[str, str, str, int, str]]:
    """``(host, suite, run_id, records, status)`` of the newest run of every suite, from ``meta.json`` files."""
    newest: dict[tuple[str, str], Path] = {}
    for meta in sorted(raw.glob("*/*/*/meta.json")):
        key = (meta.parents[2].name, meta.parents[1].name)
        newest[key] = meta.parent
    out = []
    for (host, suite), run in sorted(newest.items()):
        status = str(json.loads((run / "meta.json").read_text()).get("status", "?"))
        rec = run / "records.jsonl"
        n = len(rec.read_text().splitlines()) if rec.exists() else 0
        out.append((host, suite, run.name, n, status))
    return out


def summary(raw: Path) -> str:
    rows = latest_runs(raw)
    if not rows:
        return f"no runs under {raw}"
    lines = [f"{'suite':13s} {'records':>7s}  status", *(f"{s:13s} {n:7d}  {st}" for _, s, _, n, st in rows)]
    bad = [s for _, s, _, _, st in rows if st != "ok"]
    lines.append("")
    lines.append("all suites ok" if not bad else f"not ok: {', '.join(bad)} (see error.txt next to meta.json)")
    return "\n".join(lines)


def scrub_text(text: str, secrets: dict[str, str]) -> str:
    """Replace identifying strings: paths verbatim (longest first), names only as whole words of 4+ characters (shorter
    ones would damage other words), and the ``hostname`` field of ``meta.json`` always."""
    for old in sorted(secrets, key=len, reverse=True):
        if old.startswith("/"):
            text = text.replace(old, secrets[old])
        elif len(old) >= MIN_NAME:
            text = re.sub(rf"(?<![\w.-]){re.escape(old)}(?![\w.-])", secrets[old], text)
    return re.sub(r'("hostname":\s*")[^"]*(")', r"\1HOST\2", text)


def local_secrets() -> dict[str, str]:
    home = str(Path.home())
    out = {home: "/home/USER", getpass.getuser(): "USER", platform.node(): "HOST"}
    sudo_user = os.environ.get("SUDO_USER")  # run through sudo: the invoking user is the person to hide
    if sudo_user:
        out[sudo_user] = "USER"
    return out


def pack(raw: Path, out: Path, secrets: dict[str, str] | None = None) -> Path:
    """Archive ``raw`` (top-level directory ``raw/``): the whitelisted files only, identifying strings scrubbed, with a
    ``MANIFEST.sha256`` over the archived (scrubbed) files."""
    sec = local_secrets() if secrets is None else secrets
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "raw"
        for f in sorted(p for p in raw.rglob("*") if p.is_file()):
            rel = f.relative_to(raw)
            if f.name in (TOP if len(rel.parts) == 1 else KEEP):
                out_rel = Path(*(scrub_text(part, sec) for part in rel.parts))  # the host label may carry the user name
                (dst / out_rel).parent.mkdir(parents=True, exist_ok=True)
                (dst / out_rel).write_text(scrub_text(f.read_text(errors="replace"), sec))
        files = sorted(p for p in dst.rglob("*") if p.is_file())
        manifest = "".join(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(dst)}\n" for f in files)
        (dst / "MANIFEST.sha256").write_text(manifest)
        with tarfile.open(out, "w:gz") as tar:
            tar.add(dst, arcname="raw")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.calibrate.report", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summary")
    s.add_argument("raw", type=Path)
    k = sub.add_parser("pack")
    k.add_argument("raw", type=Path)
    k.add_argument("out", type=Path)
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    if a.cmd == "summary":
        print(summary(a.raw))
        return 0
    if not a.raw.is_dir():
        print(f"{a.raw} is not a directory", file=sys.stderr)
        return 2
    print(pack(a.raw, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
