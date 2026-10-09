"""Calibration harness entry point on the node (doc 10 §1): ``python3 -m tools.calibrate.run --suite <name>``.

Idempotent and unattended: each invocation writes ``<out>/<fingerprint>/<suite>/<run_id>/`` with ``records.jsonl``,
``meta.json`` and ``commands.txt``; re-running adds a new run directory. Suites that reboot the node or need a BIOS
change refuse to run without ``--allow-reboot`` / ``--phase`` (AGENTS.md rule 14: only with the user's approval).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from tools.calibrate.common import Records, Shell, SuiteSkipped, fingerprint, host_meta
from tools.calibrate.suites import Ctx, Suite, registry

SAFE_DEFAULT = ("caps", "disk", "tpm", "attest_local", "tls", "fc_boot", "fc_snapshot", "qemu_vm", "sebs")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tools.calibrate.run", description=__doc__)
    p.add_argument("--suite", action="append", help="suite name (repeatable); 'all' = every non-manual suite")
    p.add_argument("--list", action="store_true", help="list suites and exit")
    p.add_argument("--out", type=Path, default=Path("raw"))
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="suite option (assets, dirs)")
    p.add_argument("--quick", action="store_true", help="10%% of the repetitions (smoke check)")
    p.add_argument("--dry-run", action="store_true", help="print commands instead of running them")
    p.add_argument("--allow-reboot", action="store_true", help="manual 'appliance' suite only, with user approval")
    p.add_argument("--phase", choices=("on", "off"), help="manual 'tme' suite: current BIOS TME setting")
    return p.parse_args(argv)


def gate(s: Suite, a: argparse.Namespace) -> str | None:
    """Why a manual suite may not run now (``None`` = allowed)."""
    if s.manual == "reboot" and not a.allow_reboot and _step(a) == "arm":
        return "reboots the node: needs --allow-reboot and the user's explicit approval"
    if s.manual == "bios" and a.phase is None:
        return "needs a BIOS change by the owner first, then --phase on|off"
    return None


def _step(a: argparse.Namespace) -> str:
    opts = dict(kv.split("=", 1) for kv in a.set)
    return str(opts.get("step", "collect"))


def run_suite(s: Suite, a: argparse.Namespace, meta: dict[str, object], host: str) -> str:
    run_id = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    out = a.out / host / s.name / run_id
    out.mkdir(parents=True, exist_ok=True)
    sh = Shell(dry_run=a.dry_run)
    opts = dict(kv.split("=", 1) for kv in a.set)
    ctx = Ctx(sh, Records(out / "records.jsonl", s.name), out, opts, 0.1 if a.quick else 1.0, a.allow_reboot, a.phase)
    status = "ok"
    try:
        s.run(ctx)
    except SuiteSkipped as e:
        status = f"skipped: {e}"
    except Exception:  # record the failure, keep going with the next suite
        status = "error"
        (out / "error.txt").write_text(traceback.format_exc())
    finally:
        info = meta | {"suite": s.name, "run_id": run_id, "status": status, "options": opts, "phase": a.phase}
        (out / "meta.json").write_text(json.dumps(info, indent=2, sort_keys=True))
        (out / "commands.txt").write_text("\n".join(sh.log) + "\n")
    return status


def main(argv: list[str] | None = None) -> int:
    a = parse_args(sys.argv[1:] if argv is None else argv)
    suites = registry()
    if a.list or not a.suite:
        for name, s in suites.items():
            print(f"{name:13s} {'[manual: ' + s.manual + '] ' if s.manual else ''}{s.summary}")
        return 0
    names = list(SAFE_DEFAULT) if a.suite == ["all"] else a.suite
    unknown = [n for n in names if n not in suites]
    if unknown:
        print(f"unknown suites: {unknown}", file=sys.stderr)
        return 2
    meta = host_meta(Shell(dry_run=a.dry_run))
    host = fingerprint(meta)
    worst = 0
    for n in names:
        why = gate(suites[n], a)
        status = f"refused: {why}" if why else run_suite(suites[n], a, meta, host)
        print(f"{n}: {status}")
        worst = max(worst, 1 if status == "error" or status.startswith("refused") else 0)
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
