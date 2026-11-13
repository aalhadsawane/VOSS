"""Fetch every published trace (``configs/traces/<name>/provenance.yaml`` with a ``release`` tag) into
``data/traces/<name>/`` and check each file against the SHA-256 in its provenance (docs/REVISION_PLAN.md V9).

    uv run python -m tools.traces.fetch [--only azure2019]      # needs the gh CLI and GH_TOKEN on GitHub Actions
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

from tools.traces.common import sha256

REPO = Path(__file__).resolve().parents[2]


def fetch(name: str, prov: dict[str, object], dst: Path) -> list[str]:
    """Download the release assets of one trace; return the files whose hash does not match."""
    outputs = dict(prov.get("outputs") or {})  # type: ignore[call-overload]
    dst.mkdir(parents=True, exist_ok=True)
    have = all((dst / f).exists() and sha256(dst / f) == h for f, h in outputs.items())
    if not have:
        subprocess.run(["gh", "release", "download", str(prov["release"]), "-D", str(dst), "--clobber"], check=True)
    return [f for f, h in sorted(outputs.items()) if not (dst / f).exists() or sha256(dst / f) != h]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.traces.fetch")
    p.add_argument("--only", action="append", default=None)
    a = p.parse_args(argv)
    bad = 0
    for path in sorted((REPO / "configs" / "traces").glob("*/provenance.yaml")):
        name = path.parent.name
        prov = yaml.safe_load(path.read_text())
        if (a.only and name not in a.only) or not prov.get("release"):
            continue
        wrong = fetch(name, prov, REPO / "data" / "traces" / name)
        print(f"{name}: {'ok' if not wrong else 'HASH MISMATCH ' + ', '.join(wrong)}")
        bad += len(wrong)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
