"""Workers accept a DISPATCH only from the appointed scheduler of their cluster (doc 07 §3, critique SEC-2)."""

from __future__ import annotations

from voss.core.ids import FnId, InvId, TenantId
from voss.core.messages import Dispatch
from voss.core.types import Invocation, SloClass
from voss.runtime.worker_agent import accepts_dispatch


def _d(epoch: int, cert: str, cluster: int = 3) -> Dispatch:
    inv = Invocation(InvId(1), FnId("f"), TenantId("t"), 0, 0.0, 10, SloClass.SYNC, 1.0)
    return Dispatch(inv, epoch, 0, ("router", 0), cert, 0.0, 0.0, ("sched", 0), cluster=cluster)


def test_appointed_scheduler_is_accepted() -> None:
    assert accepts_dispatch(3, 5, "c-good", _d(5, "c-good"))


def test_same_epoch_other_certificate_is_rejected() -> None:
    assert not accepts_dispatch(3, 5, "c-good", _d(5, "c-clone"))


def test_older_epoch_and_other_cluster_are_rejected() -> None:
    assert not accepts_dispatch(3, 5, "c-good", _d(4, "c-good"))
    assert not accepts_dispatch(3, 5, "c-good", _d(5, "c-good", cluster=4))


def test_newer_epoch_before_install_is_accepted() -> None:
    assert accepts_dispatch(3, 5, "c-good", _d(6, "c-next"))
