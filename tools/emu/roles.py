"""Which ladder ops the emulation backend replaces by real work (doc 10 §4, P9b); see ``backend.py`` for the table."""

from __future__ import annotations

from collections.abc import Sequence

from voss.world.substrate import CpuOp, DelayOp, DiskReadOp, DiskWriteOp, LadderSpec, Op

NOOP, BOOT, RESTORE, CLAIM, SNAP = "noop", "boot", "restore", "claim", "snapshot"


def op_roles(lad: LadderSpec) -> dict[int, str]:
    """Role of every op object of the appliance ladder (by identity); anything else stays simulated."""
    t, roles = lad.transitions, {}

    def shape(ops: Sequence[Op], kinds: tuple[type, ...]) -> None:
        if len(ops) != len(kinds) or any(not isinstance(o, k) for o, k in zip(ops, kinds, strict=True)):
            raise ValueError(f"emulation supports the appliance ladder only (unexpected ops {ops!r})")

    shape(t["L1->L3"], (DiskReadOp, DelayOp, CpuOp))
    shape(t["L2->L3"], (DiskReadOp, DelayOp))
    shape(t["L3->L4"], (DelayOp,))
    shape(lad.after_init, (DelayOp, DiskWriteOp))
    for o, r in zip(t["L1->L3"], (NOOP, BOOT, NOOP), strict=True):
        roles[id(o)] = r
    for o, r in zip(t["L2->L3"], (NOOP, RESTORE), strict=True):
        roles[id(o)] = r
    roles[id(t["L3->L4"][0])] = CLAIM
    for o, r in zip(lad.after_init, (SNAP, NOOP), strict=True):
        roles[id(o)] = r
    return roles
