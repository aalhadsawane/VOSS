"""Sampled audit end to end (docs/REVISION_PLAN.md V7.3 exit): a forging class-P owner is banned, no honest one."""

from __future__ import annotations

from pathlib import Path

from voss.core.config import load_config
from voss.metrics.schema import Table
from voss.runtime.system import run_system

REPO = Path(__file__).resolve().parents[2]
FORGE = [
    "horizon_s=240",
    "scenario.workers=200",
    "scenario.load.rate=16",
    "voss.planner.name=hetero",
    "scenario.physical_frac=0.5",
    "scenario.adversary={regime: adversary_all, alpha: 0.1, mix: {forge: 1.0}, params: {forge_p: 1.0}}",
    "voss.audit.p=0.5",
]


def test_forging_workers_are_banned_and_only_they() -> None:
    r = run_system(load_config(REPO / "configs/smoke.yaml", FORGE))
    ev = r.recorder.frame(Table.EVENTS)
    assert ev[ev.kind == "invariant_violation"].empty
    forgers = set(ev[ev.kind == "adv_forge"].worker.astype(int))
    banned = set(ev[ev.kind == "banned"].worker.astype(int))
    assert forgers and banned and banned <= forgers
    # a banned identity's session is revoked, and the forging stops
    assert len(ev[ev.kind == "cert_revoked"]) == len(banned)
    last_ban = ev[ev.kind == "banned"].t.max()
    late = ev[(ev.kind == "adv_forge") & ev.worker.isin(banned) & (ev.t > last_ban + 30)]
    assert late.empty


def test_forging_needs_class_p_owners() -> None:
    r = run_system(load_config(REPO / "configs/smoke.yaml", [*FORGE[:4], *FORGE[5:]]))  # physical_frac = 0
    ev = r.recorder.frame(Table.EVENTS)
    assert ev[ev.kind == "adv_forge"].empty


def test_forged_answers_count_as_misses() -> None:
    """Development log iteration 2: with no audit, forging owners must change the result. Answers that came from a
    forged result are counted (``wrong_answers``) and are not deadlines met; without class-P owners there are none."""
    from experiments.analysis.summary import summarize

    every_p = "scenario.adversary={regime: adversary_all, alpha: 1.0, mix: {forge: 1.0}, params: {forge_p: 1.0}}"
    no_audit = [every_p if o.startswith("scenario.adversary") else o for o in FORGE if not o.startswith("voss.audit")]
    forged = summarize(run_system(load_config(REPO / "configs/smoke.yaml", no_audit)).recorder.frame, 60.0, 240.0)
    benign = [*no_audit[:4], *no_audit[5:]]  # physical_frac = 0: nobody can forge (every class-P owner forges above)
    clean = summarize(run_system(load_config(REPO / "configs/smoke.yaml", benign)).recorder.frame, 60.0, 240.0)
    assert forged["forged_results"] > 0 and forged["wrong_answers"] > 0
    assert clean["forged_results"] == 0 and clean["wrong_answers"] == 0
    assert forged["deadline_met"] < clean["deadline_met"]
