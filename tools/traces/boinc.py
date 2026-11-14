"""Volunteer hardware from a BOINC project's public host export (docs/REVISION_PLAN.md V9.4, machine mix).

    uv run python -m tools.traces.boinc --out data/traces/boinc-rosetta --project rosetta

BOINC projects publish ``stats/host.gz`` (one XML record per host, for third-party statistics sites). This tool streams
it and keeps the hosts that contacted the project in the ``--active-days`` before the newest contact in the file. It
writes **counts only** (``hosts.parquet``: logical CPUs, memory bucket, CPU vendor, OS family, count, median
benchmark per CPU); no host, user or CPU id is kept. Plan V9.4 assigns each (CPUs, memory) bucket to the nearest
calibrated machine; disk type is not in the export.

Some projects' exports shift the CPU fields by one (vendor in ``p_model``, model in ``os_name``), so vendor and OS are
read from all four text fields together.
"""

from __future__ import annotations

import argparse
import gzip
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd

from tools.traces.common import download, write_provenance

PROJECTS = {
    "rosetta": ("Rosetta@home", "https://boinc.bakerlab.org/rosetta/stats/host.gz"),
    "milkyway": ("MilkyWay@home", "https://milkyway.cs.rpi.edu/milkyway/stats/host.gz"),
}
TEXT = ("p_vendor", "p_model", "os_name", "os_version")
NUM = ("rpc_time", "ncpus", "m_nbytes", "p_fpops")
VENDORS = (
    ("intel", r"genuineintel|intel"),
    ("amd", r"authenticamd|amd |amd\(|ryzen|epyc"),
    ("apple", r"apple"),
    ("arm", r"arm|aarch64|qualcomm|cortex"),
)
OSES = (("windows", r"windows"), ("android", r"android"), ("macos", r"darwin|mac os"), ("linux", r"linux"))


def _first(text: str, rules: tuple[tuple[str, str], ...]) -> str:
    return next((name for name, rx in rules if re.search(rx, text)), "other")


def hosts(path: Path) -> Iterator[dict[str, float | str]]:
    """One record per ``<host>``; a truncated file ends the stream (reported by the caller's count)."""
    with gzip.open(path, "rb") as f:
        try:
            for _, el in ET.iterparse(f, events=("end",)):
                if el.tag != "host":
                    continue
                text = " ".join((el.findtext(k) or "") for k in TEXT).lower()
                rec: dict[str, float | str] = {k: float(el.findtext(k) or "nan") for k in NUM}
                rec["vendor"], rec["os"] = _first(text, VENDORS), _first(text, OSES)
                el.clear()
                yield rec
        except (EOFError, ET.ParseError) as e:
            print(f"host export ends early ({type(e).__name__}); keeping the hosts read")


def mem_bucket_gib(nbytes: np.ndarray) -> np.ndarray:
    """Memory rounded to the nearest power of two GiB (0.5 GiB minimum)."""
    gib = np.maximum(nbytes / 2**30, 0.5)
    out: np.ndarray = 2.0 ** np.round(np.log2(gib))
    return out


def survey(rows: pd.DataFrame, active_days: float) -> tuple[pd.DataFrame, dict[str, float]]:
    newest = float(rows.rpc_time.max())
    ok = (rows.rpc_time >= newest - active_days * 86400) & (rows.ncpus >= 1) & (rows.m_nbytes > 0)
    a = rows[ok].assign(ncpus=rows.ncpus[ok].astype(int), mem_gib=mem_bucket_gib(rows.m_nbytes[ok].to_numpy()))
    a = a.assign(fpops_per_cpu=a.p_fpops)  # BOINC's Whetstone benchmark is per CPU already
    g = a.groupby(["ncpus", "mem_gib", "vendor", "os"], sort=True)
    out = g.agg(count=("ncpus", "size"), fpops_median=("fpops_per_cpu", "median")).reset_index()
    stats = {"hosts_in_file": len(rows), "hosts_active": int(ok.sum()), "newest_rpc_time": newest}
    return out, stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.traces.boinc")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--project", choices=sorted(PROJECTS), required=True)
    p.add_argument("--gz", type=Path, default=None)
    p.add_argument("--work", type=Path, default=Path("data/raw/boinc"))
    p.add_argument("--active-days", type=float, default=30.0)
    a = p.parse_args(argv)
    name, url = PROJECTS[a.project]
    src = a.gz or download(url, a.work / a.project / "host.gz")
    tab, st = survey(pd.DataFrame.from_records(hosts(src)), a.active_days)
    a.out.mkdir(parents=True, exist_ok=True)
    tab.to_parquet(a.out / "hosts.parquet", index=False)
    n = tab["count"].to_numpy()
    for col in ("ncpus", "mem_gib", "vendor", "os"):
        share = tab.groupby(col)["count"].sum().sort_values(ascending=False) / n.sum()
        print(col, ", ".join(f"{k}: {v:.1%}" for k, v in share.head(8).items()))
    print(
        f"{st['hosts_active']:.0f} of {st['hosts_in_file']:.0f} hosts active in the {a.active_days:g} days before "
        f"{pd.Timestamp(st['newest_rpc_time'], unit='s'):%Y-%m-%d}"
    )
    source = {
        "name": f"{name} host statistics export (BOINC db_dump)",
        "url": url,
        "description": "BOINC statistics export for third-party statistics sites",
        "licence": "none stated; only counts per hardware bucket are kept, no host or user ids",
    }
    params = {"active_days": a.active_days, "memory": "nearest power of two GiB", "cpus": "logical (BOINC ncpus)"}
    write_provenance(a.out, source, [src], params | st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
