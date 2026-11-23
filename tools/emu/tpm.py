"""A real TPM quote at every session start (plan V13, handoff Part E).

The simulator models the quote with the calibration bundle's ``tpm2_quote`` distribution. The emulation replaces that
delay with the machine's own TPM: :class:`Quoter` creates one attestation key (EK + AK, once per run) through the
calibration harness's ``tpm`` suite code, and :class:`RealTpm` is the ``Tpm`` resource the worker's session
establishment already uses, with the wait replaced by the real process. The measured quote times are logged as
``emu_tpm_quote`` events, so the report can show what the TPM cost during the run.
"""

from __future__ import annotations

import secrets
import statistics
import threading
import time
from pathlib import Path
from typing import Any, cast

from voss.core.dist import Dist
from voss.core.kernel import Kernel
from voss.world.resources import Job, Tpm

from tools.calibrate.common import Shell
from tools.calibrate.suites.tpm import Tpm as TpmProbe
from tools.emu.kernel import RealtimeKernel


class Quoter:
    """One attestation key and one ``tpm2_quote`` process per session start."""

    def __init__(self, workdir: Path, tcti: str = "", dry_run: bool = False) -> None:
        self.workdir = workdir
        self.probe = TpmProbe(Shell(dry_run=dry_run), workdir, tcti)
        self.dry_run = dry_run
        self.ak_s = 0.0
        self.samples: list[float] = []
        self._lock = threading.Lock()

    def prepare(self) -> float:
        """Create the EK and AK once (``tpm2_createek`` + ``tpm2_createak``); returns the seconds it took."""
        self.workdir.mkdir(parents=True, exist_ok=True)
        t0 = time.monotonic()
        self.probe.make_ak()
        self.ak_s = time.monotonic() - t0
        return self.ak_s

    def quote(self) -> float:
        """One quote over the PCR set the image uses; returns its wall seconds. Raises when the TPM fails."""
        secs = self.probe.quote(secrets.token_hex(16))
        with self._lock:
            self.samples.append(secs)
        return secs

    def stats(self) -> dict[str, Any]:
        with self._lock:
            s = list(self.samples)
        return {
            "ak_create_s": self.ak_s,
            "n": len(s),
            "median_s": statistics.median(s) if s else None,
            "max_s": max(s) if s else None,
            "tcti": getattr(self.probe, "tcti", "") or "device",
            "dry_run": self.dry_run,
        }


class RealTpm(Tpm):
    """The worker's ``Tpm`` resource with a real quote: one at a time, off the kernel thread (doc 10 §4, V13)."""

    def __init__(
        self,
        kernel: RealtimeKernel,
        quote: Dist,
        gen: Any,
        quoter: Quoter,
        pool: Any,
        log: Any,
    ) -> None:
        super().__init__(cast(Kernel, kernel), quote, gen)
        self.rtk = kernel  # the wall-clock kernel: the only one with ``post``
        self.quoter, self.pool, self.log = quoter, pool, log
        self._busy = False
        self.error: Exception | None = None

    def quote(self, cb: Any, *args: Any) -> Job:
        job = Job(0.0, cb, args)
        self.queue.append(job)
        self._start()
        return job

    @property
    def busy(self) -> int:
        return int(self._busy) + len(self.queue)

    def _start(self) -> None:
        if self._busy or not self.queue:
            return
        self._busy = True
        job = self.queue.popleft()

        def work() -> None:
            try:
                secs = self.quoter.quote()
            except Exception as e:  # a failed quote invalidates the run: stop it loudly
                self.rtk.post(self._failed, e)
                return
            self.rtk.post(self._done, job, secs)

        self.pool.submit(work)

    def _done(self, job: Job, secs: float) -> None:
        self._busy = False
        self.log(secs)
        job.cb(*job.args)
        self._start()

    def _failed(self, e: Exception) -> None:
        self._busy = False
        self.error = e
        raise RuntimeError(f"TPM quote failed: {e!r}") from e
