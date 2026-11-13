"""Host availability from the Failure Trace Archive (docs/REVISION_PLAN.md V9.2).

    uv run python -m tools.traces.fta --discover --out data/traces/fta-discovery   # list archived trace files
    uv run python -m tools.traces.fta --url <file url> --out data/traces/seti      # derive sessions (next step)

The live archive refuses automated clients (403); its pages and files are in the Internet Archive. ``--discover`` asks
the Internet Archive's CDX index for every archived URL of the archive's three domains that mentions SETI@home and
prints them, so the derivation can name an exact file. It writes no provenance (a discovery run publishes nothing).
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

DOMAINS = ("fta.scem.westernsydney.edu.au", "fta.scem.uws.edu.au", "fta.inria.fr")
CDX = "https://web.archive.org/cdx/search/cdx?url={d}/*&output=json&fl=timestamp,original,statuscode,length&limit=5000"


def discover() -> list[list[str]]:
    rows: list[list[str]] = []
    for d in DOMAINS:
        p = subprocess.run(
            ["curl", "-fsSL", "--retry", "3", "--max-time", "120", CDX.format(d=d)],
            capture_output=True,
            text=True,
            check=False,
        )
        if p.returncode != 0 or not p.stdout.strip():
            print(f"{d}: CDX query failed ({p.returncode}) {p.stderr.strip()[:200]}")
            continue
        data = json.loads(p.stdout)[1:]
        hits = [r for r in data if "seti" in r[1].lower()]
        print(f"{d}: {len(data)} archived URLs, {len(hits)} mention SETI")
        rows += hits
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.traces.fta")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--discover", action="store_true")
    p.add_argument("--url", default=None)
    a = p.parse_args(argv)
    if a.discover:
        for ts, url, status, length in sorted(discover(), key=lambda r: (r[1], r[0])):
            print(f"{status} {length:>12} https://web.archive.org/web/{ts}id_/{url}")
        return 0
    raise SystemExit("derivation is added once --discover has named the trace file (plan V9.2)")


if __name__ == "__main__":
    raise SystemExit(main())
