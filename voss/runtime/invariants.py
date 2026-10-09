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
    if ex.empty:
        return []
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


def no_lost(rec: Recorder, give_up: dict[int, float], end: float) -> list[str]:
    """Doc 07 exit: every invocation reaches a terminal outcome by its give-up time; ``unfinished`` is only allowed
    for invocations whose give-up time lies beyond the end of the run."""
    inv = rec.frame(Table.INVOCATIONS)
    if inv.empty:
        return []
    lim = inv.slo_class.map(give_up).astype(float)
    lost = inv[(inv.outcome == "unfinished") & (inv.t_arrive + lim < end - 1e-6)]
    return [
        f"lost invocation {int(r.inv)} (class {int(r.slo_class)}, t={r.t_arrive:.1f})"
        for r in lost.head(20).itertuples()
    ]


def no_stale_epoch(rec: Recorder) -> list[str]:
    acc = _events(rec, "dispatch_accepted")
    bad = acc[acc.epoch < acc.epoch_installed] if len(acc) else acc
    return [f"stale-epoch dispatch accepted: inv {r.inv}" for r in bad.itertuples()]


def receipts_complete(rec: Recorder) -> list[str]:
    inv = rec.frame(Table.INVOCATIONS)
    ok = inv[inv.outcome == "ok"] if len(inv) else inv
    rc = rec.frame(Table.RECEIPTS)
    rc = rc[rc.status == "ok"] if len(rc) else rc
    have = set(zip(rc.inv, rc.attempt, strict=True)) if len(rc) else set()
    missing = [int(r.inv) for r in ok.itertuples() if (r.inv, r.attempts - 1) not in have]
    return [f"{len(missing)} successful invocations without receipts (e.g. {missing[:5]})"] if missing else []


def receipts_match_ground_truth(rec: Recorder, end: float, result_drops: int) -> list[str]:
    """Doc 09 §3: a verified receipt exists iff an attested appliance produced the result. Sound: every ``ok`` or
    ``duplicate`` row matches a result the worker sent. Complete: every result sent before the end is logged unless
    the network lost it or its session certificate was revoked before it arrived."""
    sent = _events(rec, "result_sent")
    rc = rec.frame(Table.RECEIPTS)
    if sent.empty and rc.empty:
        return []
    if sent.empty or rc.empty:
        return [f"{len(sent)} results sent but {len(rc)} receipt rows"]
    paid = rc[rc.status.isin(["ok", "duplicate"])]
    truth = set(zip(sent.inv.astype(int), sent.value.astype(int), sent.worker.astype(int), strict=True))
    got = set(zip(paid.inv.astype(int), paid.attempt.astype(int), paid.worker.astype(int), strict=True))
    out = [f"receipt without a result: {r}" for r in sorted(got - truth)[:5]]
    if len(paid) != len(got):
        out.append(f"{len(paid) - len(got)} receipts logged twice")
    rej = _events(rec, "receipt_rejected")
    excused = set(zip(rej.inv.astype(int), rej.value.astype(int), strict=True)) if len(rej) else set()
    early = sent[sent.t < end - 2.0] if len(sent) else sent
    lost = [
        k
        for k in zip(early.inv.astype(int), early.value.astype(int), early.worker.astype(int), strict=True)
        if k not in got and (k[0], k[1]) not in excused
    ]
    if len(lost) > result_drops:
        out.append(f"{len(lost)} results without receipts ({result_drops} lost in the network), e.g. {lost[:5]}")
    return out


def check_invariants(
    rec: Recorder,
    scn: Scenario,
    n_invocations: int,
    give_up: dict[int, float] | None = None,
    end: float = 0.0,
    result_drops: int = 0,
) -> list[str]:
    return [
        *(no_lost(rec, give_up, end) if give_up else []),
        *(receipts_match_ground_truth(rec, end, result_drops) if end > 0 else []),
        *attested_execution(rec, scn),
        *keys_released(rec),
        *components_sum(rec),
        *one_terminal_outcome(rec, n_invocations),
        *no_stale_epoch(rec),
        *receipts_complete(rec),
    ]
