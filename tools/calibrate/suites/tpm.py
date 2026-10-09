"""TPM suite (doc 10 §3): AK creation (once), ``tpm2_quote`` latency over PCRs 0-7, 10, 11, verifier-side
``tpm2_checkquote``, and PCR-policy seal/unseal. Feeds the ``Tpm`` resource and re-attestation cost.

Each probe is one tpm2-tools process, so it includes process start-up; ``baseline`` (``tpm2_getrandom``) measures
that floor so analyses can subtract it. ``--set tcti=swtpm:port=2321`` targets a software TPM (tests only).
"""

from __future__ import annotations

import secrets
from pathlib import Path

from tools.calibrate.common import Shell
from tools.calibrate.suites import Ctx, Suite

PCRS = "sha256:0,1,2,3,4,5,6,7,10,11"


class Tpm:
    def __init__(self, sh: Shell, work: Path, tcti: str = "") -> None:
        self.sh, self.work, self.tcti = sh, work, tcti
        work.mkdir(parents=True, exist_ok=True)

    def f(self, name: str) -> str:
        return str(self.work / name)

    def run(self, tool: str, *args: str) -> float:
        argv = [tool, *(["-T", self.tcti] if self.tcti else []), *args]
        try:
            return self.sh.run(argv).seconds
        finally:
            if self.tcti:  # no kernel resource manager (/dev/tpmrm0 flushes per process): flush ourselves
                for kind in ("-t", "-l", "-s"):  # transient objects, loaded and saved sessions
                    self.sh.run(["tpm2_flushcontext", "-T", self.tcti, kind], check=False)

    def make_ak(self) -> float:
        self.run("tpm2_createek", "-c", self.f("ek.ctx"), "-G", "rsa", "-u", self.f("ek.pub"))
        return self.run(
            "tpm2_createak",
            "-C", self.f("ek.ctx"),
            "-c", self.f("ak.ctx"),
            "-G", "rsa",
            "-g", "sha256",
            "-s", "rsassa",
            "-u", self.f("ak.pub"),
            "-n", self.f("ak.name"),
        )  # fmt: skip

    def quote(self, nonce: str) -> float:
        return self.run(
            "tpm2_quote",
            "-c", self.f("ak.ctx"),
            "-l", PCRS,
            "-q", nonce,
            "-m", self.f("quote.msg"),
            "-s", self.f("quote.sig"),
            "-o", self.f("quote.pcrs"),
            "-g", "sha256",
        )  # fmt: skip

    def checkquote(self, nonce: str) -> float:
        """Verifier side: signature and PCR digest check (no TPM access; tcti not needed)."""
        argv = ["tpm2_checkquote", "-u", self.f("ak.pub"), "-m", self.f("quote.msg"), "-s", self.f("quote.sig")]
        argv += ["-f", self.f("quote.pcrs"), "-g", "sha256", "-q", nonce]
        return self.sh.run(argv).seconds

    def seal(self) -> None:
        self.run("tpm2_createprimary", "-C", "o", "-c", self.f("prim.ctx"))
        self.run("tpm2_createpolicy", "--policy-pcr", "-l", "sha256:7,11", "-L", self.f("pcr.policy"))
        secret = self.f("secret.bin")
        if not self.sh.dry_run:
            Path(secret).write_bytes(secrets.token_bytes(32))
        self.run(
            "tpm2_create",
            "-C", self.f("prim.ctx"),
            "-L", self.f("pcr.policy"),
            "-i", secret,
            "-u", self.f("seal.pub"),
            "-r", self.f("seal.priv"),
        )  # fmt: skip
        self.run(
            "tpm2_load",
            "-C",
            self.f("prim.ctx"),
            "-u",
            self.f("seal.pub"),
            "-r",
            self.f("seal.priv"),
            "-c",
            self.f("seal.ctx"),
        )

    def unseal(self) -> float:
        return self.run("tpm2_unseal", "-c", self.f("seal.ctx"), "-p", "pcr:sha256:7,11", "-o", self.f("unsealed.bin"))


def run(ctx: Ctx) -> None:
    ctx.sh.need("tpm2_quote", "tpm2_createak", "tpm2_checkquote", "tpm2_unseal")
    t = Tpm(ctx.sh, ctx.out / "tpm", ctx.opt("tcti"))
    tcti = ctx.opt("tcti") or "device"
    for rep in range(ctx.reps(20)):
        ctx.rec.add("baseline", t.run("tpm2_getrandom", "--hex", "8"), rep=rep, tcti=tcti)
    ctx.rec.add("ak_create", t.make_ak(), tcti=tcti)
    for rep in range(ctx.reps(200)):
        nonce = secrets.token_hex(16)
        ctx.rec.add("tpm2_quote", t.quote(nonce), rep=rep, pcrs=PCRS, tcti=tcti)
        if rep % 4 == 0:
            ctx.rec.add("checkquote", t.checkquote(nonce), rep=rep, tcti=tcti)
    t.seal()
    for rep in range(ctx.reps(20)):
        ctx.rec.add("unseal", t.unseal(), rep=rep, pcrs="sha256:7,11", tcti=tcti)


SUITE = Suite("tpm", run, "tpm2_quote latency, AK creation, checkquote, PCR-policy unseal")
