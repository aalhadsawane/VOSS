"""Invariants checked after every integration run (doc 05 §7). Each returns human-readable violations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from voss.metrics.recorder import Recorder
from voss.metrics.schema import Table
from voss.world.scenario import Scenario

COMPONENTS = ("route", "retry", "batch_wait", "decide", "net_in", "wait", "trust", "startup", "exec", "net_out")


def _events(rec: Recorder, kind: str) -> pd.DataFrame:
    ev = rec.frame(Table.EVENTS)
    return ev[ev.kind == kind] if len(ev) else ev


def attested_execution(rec: Recorder, scn: Scenario) -> list[str]:
    """No execution on an unattested, expired or powered-off worker."""
    ex = _events(rec, "exec_start")
    if ex.empty:
        return []
    out = [f"exec on expired cert: inv {r.inv}" for r in ex.itertuples() if not (r.cert and r.value > r.t)]
    s = scn.sessions.sessions.sort_values(["worker", "start"])
    by_worker = {int(w): (g.start.to_numpy(), g.end.to_numpy()) for w, g in s.groupby("worker")}
    for w, t, inv in zip(ex.worker.astype(int), ex.t, ex.inv, strict=True):
        starts, ends = by_worker.get(w, (np.zeros(0), np.zeros(0)))
        i = int(np.searchsorted(starts, t, side="right")) - 1
        if i < 0 or ends[i] <= t:
            out.append(f"exec outside a session: worker {w} inv {inv} t={t:.3f}")
    return out


def keys_released(rec: Recorder) -> list[str]:
    """No tenant key used on a worker without a successful ``KEY_REQUEST`` in the same session, and not after the
    key was dropped (``RELEASE`` + linger) unless it was released again."""
    ex = _events(rec, "exec_start")
    hist: dict[tuple[int, str, str], list[tuple[float, int]]] = {}
    for kind, sign in (("key_release", 1), ("key_dropped", -1)):
        ev = _events(rec, kind)
        if ev.empty:
            continue
        cert = ev.cert if "cert" in ev else pd.Series([""] * len(ev), index=ev.index)
        for w, c, t, ten in zip(ev.worker, cert, ev.t, ev.tenant, strict=True):
            hist.setdefault((int(w), str(c) if sign > 0 else "*", str(ten)), []).append((float(t), sign))
    out = []
    for r in ex[ex.needs_key == True].itertuples():  # noqa: E712
        rel = [t for t, _ in hist.get((int(r.worker), r.cert, r.tenant), []) if t <= r.t]
        drop = [t for t, _ in hist.get((int(r.worker), "*", r.tenant), []) if t <= r.t]
        if not rel or (drop and max(drop) > max(rel)):
            out.append(f"key used without release: worker {r.worker} tenant {r.tenant} inv {r.inv}")
    return out


def components_sum(rec: Recorder) -> list[str]:
    inv = rec.frame(Table.INVOCATIONS)
    ok = inv[inv.outcome == "ok"] if len(inv) else inv
    if ok.empty:
        return []
    total = ok[list(COMPONENTS)].sum(axis=1).to_numpy()
    bad = np.flatnonzero(np.abs(total - ok.e2e.to_numpy()) > 1e-6)
    return [f"components do not sum: inv {ok.inv.iloc[i]}" for i in bad[:20]]


def one_terminal_outcome(rec: Recorder, n: int) -> list[str]:
    inv = rec.frame(Table.INVOCATIONS)
    out = []
    if len(inv) != n:
        out.append(f"{len(inv)} terminal rows for {n} invocations")
    if len(inv) and inv.inv.duplicated().any():
        out.append(f"duplicate terminal rows: {inv.inv[inv.inv.duplicated()].head().tolist()}")
    return out


def no_stale_epoch(rec: Recorder) -> list[str]:
    acc = _events(rec, "dispatch_accepted")
    bad = acc[acc.epoch < acc.epoch_installed] if len(acc) else acc
    return [f"stale-epoch dispatch accepted: inv {r.inv}" for r in bad.itertuples()]


def receipts_complete(rec: Recorder) -> list[str]:
    inv = rec.frame(Table.INVOCATIONS)
    ok = inv[inv.outcome == "ok"] if len(inv) else inv
    rc = rec.frame(Table.RECEIPTS)
    have = set(zip(rc.inv, rc.attempt, strict=True)) if len(rc) else set()
    missing = [int(r.inv) for r in ok.itertuples() if (r.inv, r.attempts - 1) not in have]
    return [f"{len(missing)} successful invocations without receipts (e.g. {missing[:5]})"] if missing else []


def check_invariants(rec: Recorder, scn: Scenario, n_invocations: int) -> list[str]:
    return [
        *attested_execution(rec, scn),
        *keys_released(rec),
        *components_sum(rec),
        *one_terminal_outcome(rec, n_invocations),
        *no_stale_epoch(rec),
        *receipts_complete(rec),
    ]
