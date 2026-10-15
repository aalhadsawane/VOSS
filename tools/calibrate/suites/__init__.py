"""Measurement suites (doc 10 §2-3). Each module exposes ``SUITE``; ``run.py`` looks them up by name.

``manual`` marks suites that reboot the node or need a BIOS change: they refuse to run without ``--allow-reboot``
(or ``--phase`` for BIOS toggles), and the coding agent must have the user's explicit approval before passing those
flags (AGENTS.md rule 14).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tools.calibrate.common import Records, Shell, free_mb, mem_available_mb

RESERVE_MB = 2048  # space always left free on a scratch filesystem
MEM_SHARE = 0.6  # share of the available RAM that guests may use together


@dataclass
class Ctx:
    sh: Shell
    rec: Records
    out: Path
    opts: dict[str, str] = field(default_factory=dict)
    reps_scale: float = 1.0
    allow_reboot: bool = False
    phase: str | None = None

    def reps(self, n: int) -> int:
        """``--quick`` scales repetitions down (smoke checks); never below 2 so spread is still recorded."""
        return max(2, round(n * self.reps_scale))

    def opt(self, key: str, default: str = "") -> str:
        return self.opts.get(key, default)

    def dirs(self) -> dict[str, Path]:
        """Scratch directories on each disk tier (``--set ssd_dir=... --set hdd_dir=...``)."""
        out = {}
        for tier in ("ssd", "hdd"):
            d = self.opts.get(f"{tier}_dir")
            if d:
                out[tier] = Path(d)
        return out

    def mem_budget_mb(self) -> int:
        """RAM the guests of one measurement may use together: ``--set mem_budget_mb=N`` or 60% of what is free."""
        if "mem_budget_mb" in self.opts:
            return int(self.opts["mem_budget_mb"])
        return int(MEM_SHARE * mem_available_mb())

    def has_room(self, d: Path, need_mb: float) -> bool:
        """``need_mb`` plus a 2 GB reserve is free on ``d``'s filesystem (scratch files never fill a disk)."""
        return free_mb(d) >= need_mb + RESERVE_MB

    def skip(self, what: str, need_mb: float, reason: str) -> None:
        """Record a measurement left out because the machine is too small (it never fails the suite)."""
        self.rec.add("skipped", float(need_mb), unit="MB", what=what, reason=reason)
        print(f"skip {what}: {reason} (needs {need_mb:.0f} MB)")


@dataclass(frozen=True)
class Suite:
    name: str
    run: Callable[[Ctx], None]
    summary: str
    manual: str | None = None  # "reboot" | "bios"


def registry() -> dict[str, Suite]:
    from tools.calibrate.suites import (  # noqa: PLC0415
        appliance,
        attest_local,
        caps,
        disk,
        fc_boot,
        fc_snapshot,
        qemu_vm,
        sebs,
        tls,
        tme,
        tpm,
    )

    mods = (caps, disk, fc_boot, fc_snapshot, qemu_vm, sebs, tpm, attest_local, tls, tme, appliance)
    return {m.SUITE.name: m.SUITE for m in mods}
