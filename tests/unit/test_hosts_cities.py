"""BOINC host survey and WUP metro populations (docs/REVISION_PLAN.md V9.4) on synthetic inputs."""

from __future__ import annotations

import gzip
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from tools.traces.boinc import hosts, mem_bucket_gib, survey
from tools.traces.wup import match
from voss.world.geo import load_metros, with_traced_pop

HOST = (
    "<host><id>{i}</id><userid>9</userid><p_vendor>{v}</p_vendor><p_model>{m}</p_model><os_name>{o}</os_name>"
    "<os_version>{ov}</os_version><rpc_time>{t}</rpc_time><ncpus>{n}</ncpus><m_nbytes>{b}</m_nbytes>"
    "<p_fpops>1e9</p_fpops><host_cpid>secret</host_cpid></host>"
)


def _export(tmp: Path, truncate: bool, filler: int = 0) -> Path:
    recs = [
        HOST.format(
            i=1, v="", m="GenuineIntel", o="Intel Core i5", ov="Microsoft Windows 10", t=10_000_000, n=4, b=7.8 * 2**30
        ),
        HOST.format(
            i=2, v="AuthenticAMD", m="AMD Ryzen 7", o="Linux Ubuntu", ov="6.1", t=10_000_000, n=16, b=31 * 2**30
        ),
        HOST.format(i=3, v="", m="GenuineIntel", o="Pentium III", ov="Linux", t=1_000, n=1, b=128 * 2**20),
    ] + [HOST.format(i=10 + k, v="", m="", o="", ov="", t=k, n=2, b=2**31) for k in range(filler)]
    data = ('<?xml version="1.0"?>\n<hosts>\n' + "\n".join(recs) + "\n</hosts>\n").encode()
    path = tmp / ("t.gz" if truncate else "h.gz")
    comp = gzip.compress(data)
    path.write_bytes(comp[: len(comp) // 2] if truncate else comp)
    return path


def test_survey_keeps_active_hosts_as_counts_only(tmp_path: Path) -> None:
    rows = pd.DataFrame.from_records(hosts(_export(tmp_path, truncate=False)))
    assert list(rows.vendor) == ["intel", "amd", "intel"] and list(rows.os) == ["windows", "linux", "linux"]
    tab, st = survey(rows, active_days=30)
    assert st["hosts_in_file"] == 3 and st["hosts_active"] == 2  # host 3 last contacted long before the others
    assert set(tab.columns) == {"ncpus", "mem_gib", "vendor", "os", "count", "fpops_median"}  # no ids
    assert sorted(zip(tab.ncpus, tab.mem_gib, strict=True)) == [(4, 8.0), (16, 32.0)]


def test_truncated_export_keeps_complete_hosts(tmp_path: Path) -> None:
    rows = list(hosts(_export(tmp_path, truncate=True, filler=5000)))
    assert 3 < len(rows) < 5003 and rows[0]["ncpus"] == 4


def test_memory_buckets() -> None:
    assert list(mem_bucket_gib(np.array([0.1, 1.4, 1.6, 7.8, 12.0]) * 2**30)) == [0.5, 1.0, 2.0, 8.0, 16.0]


def test_wup_cities_go_to_their_nearest_metro_within_the_radius() -> None:
    cities = pd.DataFrame({"name": ["A", "B"], "lat": [0.0, 0.0], "lon": [0.0, 1.0], "pop": [1.0, 2.0]})
    wup = pd.DataFrame(
        {
            "wup_name": ["a", "a2", "mid", "far"],
            "lat": [0.0, 0.1, 0.0, 5.0],
            "lon": [0.0, 0.0, 0.6, 5.0],  # mid is 67 km from A and 44 km from B: outside 30 km of both
            "pop": [5e5, 1e5, 9e5, 1e6],
        }
    )
    out = match(cities, wup, radius_km=30)
    assert list(out["pop"]) == [6e5, 0.0] and list(out.largest) == ["a", ""] and list(out.wup_cities) == [2, 0]


def test_traced_pop_replaces_the_table_and_rejects_a_stale_file(tmp_path: Path) -> None:
    m = load_metros()
    path = tmp_path / "metro_pop.parquet"
    pd.DataFrame({"city": list(m.name), "pop": np.arange(1, len(m) + 1) * 1e6}).to_parquet(path)
    t = with_traced_pop(m, path)
    assert t.pop[0] == 1.0 and t.pop[-1] == float(len(m)) and t.name == m.name
    pd.DataFrame({"city": list(m.name[1:]), "pop": 1e6}).to_parquet(path)
    with pytest.raises(ValueError, match=m.name[0]):
        with_traced_pop(m, path)
