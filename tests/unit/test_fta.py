"""SETI@home availability derivation (docs/REVISION_PLAN.md V9.2) on a synthetic archive in the FTA tab format."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

from tools.traces.fta import WEEK, read_events, sessions


def _archive(tmp: Path, header: bool) -> Path:
    rows = [  # event_id component_id node_id platform_id node_name event_type start stop reason
        "1\t0\t2\t0\th2\t1\t1000\t5000\t0",
        "2\t0\t2\t0\th2\t0\t5000\t9000\t0",
        "3\t0\t3\t0\th3\t1\t2000\t700000\t0",
        f"4\t0\t4\t0\th4\t1\t{1000 + 3 * 86400}\t{1000 + 3 * 86400 + 600}\t0",
    ]
    text = ("event_id\tcomponent_id\tnode_id\n" if header else "") + "\n".join(rows) + "\n"
    path = tmp / ("h.tgz" if header else "n.tgz")
    with tarfile.open(path, "w:gz") as tar:
        data = text.encode()
        info = tarfile.TarInfo("seti09/event_trace.tab")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return path


def test_sessions_are_availability_intervals_clipped_to_the_week(tmp_path: Path) -> None:
    for header in (False, True):
        ev = read_events(_archive(tmp_path, header))
        assert len(ev) == 4 and set(ev.event_type) == {0, 1}
        out = sessions(ev, avail=1, hosts=10, heldout_day=0.0, seed=1)
        dev = out["dev"]  # even hosts: 2 and 4
        assert sorted(dev.host.unique()) == [2, 4]
        assert dev.iloc[0].start_s == 0.0 and dev.iloc[0].end_s == 4000.0  # relative to the first event (t0 = 1000)
        odd = out["heldout"]
        assert list(odd.host.unique()) == [3] and odd.end_s.max() <= WEEK


def test_a_truncated_archive_keeps_the_hosts_it_holds_completely(tmp_path: Path) -> None:
    rows = "".join(f"{i}\t0\t{i // 3}\t0\th\t1\t{1000 + i}\t{2000 + i}\t0\n" for i in range(30000))
    data = rows.encode()
    full = tmp_path / "full.tgz"
    with tarfile.open(full, "w:gz") as tar:
        info = tarfile.TarInfo("seti09/event_trace.tab")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    cut = tmp_path / "cut.tgz"
    cut.write_bytes(full.read_bytes()[: full.stat().st_size // 2])
    ev = read_events(cut, chunk=1000)
    assert 0 < len(ev) < 30000 and ev.node_id.is_monotonic_increasing
    assert (ev.groupby("node_id").size() == 3).all()  # the cut-off last host is dropped
