"""Host availability from the Failure Trace Archive (docs/REVISION_PLAN.md V9.2).

    uv run python -m tools.traces.fta --discover --out data/traces/fta-discovery   # list archived trace files
    uv run python -m tools.traces.fta --out data/traces/seti09 [--url <archived seti09_tab.tgz>]  # derive sessions

The live archive refuses automated clients (403); its pages and files are in the Internet Archive. ``--discover`` asks
the Internet Archive's CDX index for every archived URL of the archive's three domains that mentions SETI@home and
prints them, so the derivation can name an exact file. It writes no provenance (a discovery run publishes nothing).

Derivation (plan V9.2) from the SETI@home 2009 trace in the archive's tabular format (``seti09_tab.tgz``):
- the event file (``event_trace.tab``: event id, component id, node id, platform id, node name, event type, start,
  stop, end reason) is read in chunks; the log prints the archive's members, the file's first lines, and the count and
  median length of each event type, so the availability encoding (``--avail-type``, the archive's documented value 1)
  is checked against the data;
- a host's availability intervals (type 1: checked on 2026-11-14 against the paper's totals; the two types alternate
  without gaps) are its sessions, after joining the gaps of the client's 5-day benchmark. Splits: development = even
  host ids in week ``--weeks[0]``, held-out = odd host ids in week ``--weeks[1]`` (default 40 and 66: 21,969 and
  44,933 active hosts in the truncated copy). ``--hosts`` hosts are sampled per split (deterministic); intervals are
  clipped to the week and stored relative to its start.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import tarfile
from pathlib import Path
from typing import IO, Any

import numpy as np
import pandas as pd
from voss.core.rng import stream

from tools.traces.common import download, write_provenance

DOMAINS = ("fta.scem.westernsydney.edu.au", "fta.scem.uws.edu.au", "fta.inria.fr")
URL = "https://web.archive.org/web/20250311173327id_/http://fta.scem.westernsydney.edu.au/data/seti09/seti09_tab.tgz"
# Internet Archive snapshots of the same file, tried in order until one is complete (gzip integrity). The 2025 snapshot
# stopped at 1 GiB on every attempt from a GitHub runner; the 2015/2017 snapshots are earlier, smaller copies.
SNAPSHOTS = (
    "https://web.archive.org/web/20170215193011id_/http://fta.scem.uws.edu.au/data/seti09/seti09_tab.tgz",
    "https://web.archive.org/web/20150325220201id_/http://fta.scem.uws.edu.au/data/seti09/seti09_tab.tgz",
    "https://web.archive.org/web/20240305174607id_/http://fta.scem.westernsydney.edu.au/data/seti09/seti09_tab.tgz",
    URL,
)
SOURCE = {
    "name": "SETI@home host availability 2009, Failure Trace Archive (Javadi, Kondo, Vincent, Anderson)",
    "url": URL,
    "description": "Failure Trace Archive, fta.scem.westernsydney.edu.au (live site refuses automated clients); "
    "file retrieved from the Internet Archive snapshot named in url",
    "licence": "not stated in the file; TODO verify against the archive's terms page (archived) before publication; "
    "cite the archive and Javadi et al.",
}
EVENT_COLS = [
    "event_id",
    "component_id",
    "node_id",
    "platform_id",
    "node_name",
    "event_type",
    "start",
    "stop",
    "reason",
]
WEEK = 7 * 86400
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


def fetch_complete(urls: tuple[str, ...], work: Path, allow_prefix: bool = False) -> tuple[Path, str]:
    """The first snapshot that downloads completely and passes ``gzip -t``; prints why each other one was rejected.
    Every archived copy is truncated (2026-11-13: at 0.43, 0.66 and 1.07 GB on every attempt). With ``allow_prefix``
    the longest partial download is used instead; ``read_events`` then keeps the hosts it holds completely."""
    for k, url in enumerate(urls):
        dst = work / f"seti09_tab.{k}.tgz"
        try:
            download(url, dst, attempts=3)
        except RuntimeError as e:
            print(f"snapshot {k}: {e}")
            continue
        ok = subprocess.run(["gzip", "-t", str(dst)], capture_output=True, check=False).returncode == 0
        print(f"snapshot {k}: {dst.stat().st_size} bytes, gzip {'ok' if ok else 'TRUNCATED'} ({url})")
        if ok:
            return dst, url
        dst.unlink()
    parts = sorted(work.glob("seti09_tab.*.tgz.part"), key=lambda p: p.stat().st_size)
    if allow_prefix and parts:
        k = int(parts[-1].name.split(".")[1])
        print(f"using the longest truncated copy: snapshot {k}, {parts[-1].stat().st_size} bytes")
        return parts[-1], urls[k]
    raise SystemExit("no complete snapshot of seti09_tab.tgz")


class _Replay(io.RawIOBase):
    """A readable stream that returns ``head`` and then the rest of ``f`` (a tar member read as a stream)."""

    def __init__(self, head: bytes, f: IO[bytes]) -> None:
        self.head, self.f = head, f

    def readable(self) -> bool:
        return True

    def readinto(self, b: Any) -> int:
        if self.head:
            n = min(len(b), len(self.head))
            b[:n], self.head = self.head[:n], self.head[n:]
            return n
        data = self.f.read(len(b))
        b[: len(data)] = data
        return len(data)


def read_events(archive: Path, chunk: int = 1_000_000) -> pd.DataFrame:
    """(node, type, start, stop) of every event, with the archive's members and the file's first lines printed for
    the log. The archive is read as a stream, so a truncated copy is read up to the break; the last host read may be
    incomplete and is dropped, and the log says whether host ids are in non-decreasing order (if they are, the hosts
    kept are a prefix of the host list, chosen by id only)."""
    parts: list[pd.DataFrame] = []
    truncated = False
    with tarfile.open(archive, "r|gz") as tar:
        try:
            for m in tar:
                print(f"member {m.name} {m.size}")
                if not m.name.endswith("event_trace.tab"):
                    continue
                f = tar.extractfile(m)
                assert f is not None
                head = f.read(4096)
                print("event file head:", *head.decode(errors="replace").splitlines()[:5], sep="\n  ")
                skip = 0 if head.split(b"\t", 1)[0].strip().lstrip(b"-").isdigit() else 1
                reader = pd.read_csv(
                    io.BufferedReader(_Replay(head, f)),
                    sep="\t",
                    header=None,
                    names=EVENT_COLS,
                    skiprows=skip,
                    chunksize=chunk,
                    usecols=["node_id", "event_type", "start", "stop"],
                )
                for df in reader:
                    parts.append(
                        df.dropna().astype({"node_id": np.int64, "event_type": np.int8, "start": float, "stop": float})
                    )
                break
        except (EOFError, OSError, tarfile.ReadError, pd.errors.ParserError, ValueError) as e:
            truncated = True
            print(f"archive ends early ({type(e).__name__}: {str(e)[:80]}): keeping {sum(map(len, parts))} events")
    ev = pd.concat(parts, ignore_index=True)
    print(
        f"events {len(ev)}, hosts {ev.node_id.nunique()}, host ids non-decreasing: "
        f"{bool(ev.node_id.is_monotonic_increasing)}"
    )
    if truncated:
        ev = ev[ev.node_id != ev.node_id.iloc[-1]]  # the last host may be cut off
    return ev.reset_index(drop=True)


def inspect(ev: pd.DataFrame) -> None:
    """Facts the derivation must rest on, printed for the log (plan V9.2): time order and span, hosts per week,
    duration quantiles and total time per event type, and whether the two types alternate within a host."""
    d = (ev.stop - ev.start) / 3600
    print(
        f"start times non-decreasing: {bool(ev.start.is_monotonic_increasing)}; "
        f"span {pd.to_datetime(ev.start.min(), unit='s')} to {pd.to_datetime(ev.start.max(), unit='s')}"
    )
    q = [0.1, 0.25, 0.5, 0.75, 0.9, 0.99]
    for t, g in d.groupby(ev.event_type):
        print(
            f"event_type {t}: n={len(g)}, total {g.sum():.4g} h, quantiles (h) "
            + ", ".join(f"{x:g}:{g.quantile(x):.3g}" for x in q)
        )
    week = ((ev.start - ev.start.min()) // (7 * 86400)).astype(int)
    hosts = ev.groupby(week).node_id.nunique()
    print("active hosts per week:", ", ".join(f"w{int(k)}:{int(v)}" for k, v in hosts.items()))
    s = ev.sort_values(["node_id", "start"], kind="stable")
    same = s.node_id.to_numpy()[1:] == s.node_id.to_numpy()[:-1]
    alt = s.event_type.to_numpy()[1:] != s.event_type.to_numpy()[:-1]
    gap = (s.start.to_numpy()[1:] - s.stop.to_numpy()[:-1])[same]
    print(
        f"within a host: consecutive events alternate type {float(alt[same].mean()):.3f} of the time; "
        f"gap to next event (s) quantiles 0.5:{np.quantile(gap, 0.5):.3g} 0.99:{np.quantile(gap, 0.99):.3g}"
    )


BENCH_GAP_S, BENCH_RUN_S = 120.0, 4.9 * 86400  # the 5-day benchmark artefact (Javadi et al., section 3)


def merge_benchmark_gaps(a: pd.DataFrame) -> pd.DataFrame:
    """Join availability intervals split by the client's 5-day benchmark: an interval of at least ``BENCH_RUN_S``
    followed, after a gap under ``BENCH_GAP_S``, by the next one of the same host (the authors removed these gaps)."""
    a = a.sort_values(["node_id", "start"], kind="stable").reset_index(drop=True)
    same = a.node_id.eq(a.node_id.shift())
    join = same & ((a.start - a.stop.shift()) < BENCH_GAP_S) & ((a.stop - a.start).shift() >= BENCH_RUN_S)
    g = (~join).cumsum()
    out = a.groupby(g).agg(node_id=("node_id", "first"), start=("start", "first"), stop=("stop", "last"))
    print(f"benchmark gaps merged: {int(join.sum())}")
    return out.reset_index(drop=True)


def sessions(ev: pd.DataFrame, avail: int, hosts: int, weeks: tuple[int, int], seed: int) -> dict[str, pd.DataFrame]:
    """Development = even host ids in week ``weeks[0]``, held-out = odd host ids in week ``weeks[1]`` (weeks counted
    from the trace's first event); intervals clipped to the week, relative to its start."""
    for t, g in ev.groupby("event_type"):
        print(f"event_type {t}: {len(g)} events, median length {float((g.stop - g.start).median()) / 3600:.2f} h")
    a = merge_benchmark_gaps(ev[ev.event_type == avail][["node_id", "start", "stop"]])
    t0 = float(ev.start.min())
    out = {}
    for split, parity, week in (("dev", 0, weeks[0]), ("heldout", 1, weeks[1])):
        lo = t0 + week * WEEK
        hi = lo + WEEK
        w = a[(a.node_id % 2 == parity) & (a.stop > lo) & (a.start < hi)]
        ids = np.sort(w.node_id.unique())
        pick = np.sort(stream(seed, "traces.fta.hosts", split).choice(ids, size=min(hosts, len(ids)), replace=False))
        w = w[w.node_id.isin(pick)]
        out[split] = (
            pd.DataFrame(
                {
                    "host": w.node_id.to_numpy(),
                    "start_s": np.maximum(w.start.to_numpy(), lo) - lo,
                    "end_s": np.minimum(w.stop.to_numpy(), hi) - lo,
                }
            )
            .sort_values(["host", "start_s"])
            .reset_index(drop=True)
        )
        print(f"{split}: week {week}, {len(pick)} of {len(ids)} hosts, {len(out[split])} intervals, starts {lo:.0f}")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.traces.fta")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--discover", action="store_true")
    p.add_argument("--url", default=None, help="one snapshot to use (default: try SNAPSHOTS in order)")
    p.add_argument("--allow-prefix", action="store_true", help="use the longest truncated copy if none is complete")
    p.add_argument("--inspect", action="store_true", help="print facts about the events and stop (no derived files)")
    p.add_argument("--work", type=Path, default=Path("data/raw/fta"))
    p.add_argument("--avail-type", type=int, default=1)
    p.add_argument("--hosts", type=int, default=20000)
    p.add_argument("--weeks", type=int, nargs=2, default=(40, 66), help="development and held-out week numbers")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args(argv)
    if a.discover:
        for ts, url, status, length in sorted(discover(), key=lambda r: (r[1], r[0])):
            print(f"{status} {length:>12} https://web.archive.org/web/{ts}id_/{url}")
        return 0
    archive, used = fetch_complete((a.url,) if a.url else SNAPSHOTS, a.work, a.allow_prefix)
    ev = read_events(archive)
    if a.inspect:
        inspect(ev)
        return 0
    out = sessions(ev, a.avail_type, a.hosts, tuple(a.weeks), a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    for split, df in out.items():
        df.to_parquet(a.out / f"sessions_{split}.parquet", index=False)
    params = {
        "avail_type": a.avail_type,
        "hosts_per_split": a.hosts,
        "prefix_of_truncated_archive": archive.name.endswith(".part"),
        "week_s": WEEK,
        "weeks": list(a.weeks),
        "benchmark_gap": {"gap_s": BENCH_GAP_S, "run_s": BENCH_RUN_S},
        "seed": a.seed,
        "splits": "dev = even host ids in weeks[0]; heldout = odd host ids in weeks[1]",
    }
    write_provenance(a.out, {**SOURCE, "url": used}, [archive], params)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
