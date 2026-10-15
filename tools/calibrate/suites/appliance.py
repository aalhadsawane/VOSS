"""Reboot-to-attested (doc 10 §3 ``appliance``, §3.1; manual, ``--allow-reboot``): the core ``appliance_tpm``
session-establishment cost.

Steps (``--set step=...``):
- ``build``: build the appliance image (UKI + dm-verity root) with ``mkosi`` from ``tools/calibrate/appliance/``;
- ``arm``: reboot **once** into the appliance boot entry; its one-shot service logs ``systemd-analyze`` and
  attestation timestamps to the log directory and reboots back. The harness never installs a reboot loop: repeat
  ``arm`` per boot (``remote.py --boots N`` waits for SSH between boots);
- ``collect``: parse the logs into records. Two sources: image mode (``appliance-*.log``) and the host-mode probe
  (``probe-*.log``, D-60), which runs the same TPM attestation round in a minimal one-shot systemd target on the
  machine's own kernel and measures reboot time from wall-clock stamps (±1 s). The bounded reboot loop for host mode
  lives in ``appliance/host/`` and is driven by ``laptop/voss-calib.sh appliance``, never by this module.

Rebooting the user's machine needs ``--allow-reboot`` **and** the user's explicit approval (AGENTS.md rule 14).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tools.calibrate.common import SuiteSkipped
from tools.calibrate.suites import Ctx, Suite

APPLIANCE_DIR = Path(__file__).resolve().parents[1] / "appliance"
STARTUP = re.compile(r"Startup finished in (.*)= ([0-9.]+)(ms|s|min)")
PART = re.compile(r"([0-9.]+(?:min|ms|s)(?: [0-9.]+(?:ms|s))?) \((\w+)\)")


def seconds(text: str) -> float:
    """systemd durations: ``1min 2.5s``, ``912ms``, ``7.1s``."""
    total = 0.0
    for num, unit in re.findall(r"([0-9.]+)(min|ms|s)", text):
        total += float(num) * {"min": 60.0, "s": 1.0, "ms": 1e-3}[unit]
    return total


def startup(line: str) -> dict[str, float]:
    """``Startup finished in 7.1s (firmware) + 2.0s (loader) + 1.5s (kernel) + 3.2s (userspace) = 13.8s``."""
    m = STARTUP.search(line)
    if not m:
        return {}
    return {name: seconds(val) for val, name in PART.findall(m.group(1))}


def events(log: str) -> dict[str, float]:
    """``VOSS_T <event> <CLOCK_MONOTONIC seconds>`` lines from the appliance's one-shot service."""
    return {e: float(t) for e, t in re.findall(r"^VOSS_T (\w+) ([0-9.]+)$", log, re.M)}


def wall(log: str) -> dict[str, float]:
    """``VOSS_E <name> <epoch seconds>`` evidence lines of the host-mode probe (D-60); ``none`` values are dropped."""
    return {e: float(t) for e, t in re.findall(r"^VOSS_E (\w+) (-?[0-9.]+)$", log, re.M)}


def collect(ctx: Ctx, log_dir: Path) -> int:
    """Parse ``probe-*.log`` (host mode, D-60: wall-clock stamps, ±1 s) and legacy ``appliance-*.log`` (image mode)."""
    n = 0
    for i, f in enumerate(sorted([*log_dir.glob("probe-*.log"), *log_dir.glob("appliance-*.log")])):
        text = f.read_text(errors="replace")
        parts, ev, ws = startup(text), events(text), wall(text)
        if "verifier_ok" not in ev and "agent_ready" not in ev:
            ctx.rec.add("boot_incomplete", 1.0, unit="bool", rep=i, file=f.name)
            continue
        kernel = parts.get("kernel", 0.0)
        extra: dict[str, Any] = dict(sorted(parts.items()))
        if "firmware" in parts:  # image mode: the firmware/loader times come from systemd-analyze
            ctx.rec.add("reboot_to_kernel", parts["firmware"] + parts.get("loader", 0.0) + kernel, rep=i, **extra)
        elif {"arm", "btime", "prev_end"} <= ws.keys():  # host mode: wall clock, GRUB gives systemd no firmware time
            fw = ws["btime"] - ws["prev_end"]
            if not 0.0 <= fw <= 600.0:  # the clock was stepped between the two boots (RTC in local time, NTP): unusable
                ctx.rec.add("boot_incomplete", 1.0, unit="bool", rep=i, file=f.name, why=f"clock step ({fw:.0f} s)")
                continue
            ctx.rec.add("shutdown", ws["prev_end"] - ws["arm"], rep=i, method="wallclock")
            ctx.rec.add("firmware_loader", fw, rep=i, method="wallclock")
            ctx.rec.add("reboot_cmd_to_kernel", ws["btime"] - ws["arm"], rep=i, method="wallclock")
            ctx.rec.add("reboot_to_kernel", fw + kernel, rep=i, method="wallclock", **extra)
        else:
            ctx.rec.add("boot_incomplete", 1.0, unit="bool", rep=i, file=f.name, why="no timing evidence")
            continue
        # CLOCK_MONOTONIC starts at kernel start, so userspace-to-attested is the verifier-OK stamp minus kernel time
        ctx.rec.add("appliance_userspace", ev["agent_ready"] - kernel, rep=i)
        if "verifier_ok" in ev:
            ctx.rec.add("appliance_attested", ev["verifier_ok"] - kernel, rep=i)
        n += 1
    return n


def run(ctx: Ctx) -> None:
    step = ctx.opt("step", "collect")
    log_dir = Path(ctx.opt("appliance_log_dir", "/var/lib/voss-calib/appliance"))
    if step == "collect":
        if collect(ctx, log_dir) == 0:
            raise SuiteSkipped(f"no complete appliance logs in {log_dir}")
        return
    if step == "build":
        ctx.sh.need("mkosi")
        ctx.sh.run(["mkosi", "-C", str(APPLIANCE_DIR), "--force", "build"], timeout=7200)
        return
    if step == "arm":
        if not ctx.allow_reboot:
            raise SuiteSkipped("refusing to reboot without --allow-reboot (and the user's explicit approval)")
        entry = ctx.opt("boot_entry", "voss-appliance.conf")
        ctx.sh.run(["systemctl", "reboot", f"--boot-loader-entry={entry}"])
        return
    raise SuiteSkipped(f"unknown step {step!r} (build | arm | collect)")


SUITE = Suite("appliance", run, "reboot → UKI → dm-verity userspace → agent → quote → verifier OK", manual="reboot")
