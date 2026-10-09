"""Local attestation round trip (doc 10 §3 ``attest_local``): nonce → quote on the node's TPM → verifier check →
session-certificate signature, all on one host so the network RTT can be added in simulation.

The verifier side is tpm2-tools' ``tpm2_checkquote`` plus an Ed25519 certificate signature (``openssl``): the same
cryptographic work as a Keylime-style verifier. Policy evaluation of a full Keylime install is not covered; the
``verify_s`` entry it feeds keeps that limitation in its ``source``.
"""

from __future__ import annotations

import secrets
import time

from tools.calibrate.suites import Ctx, Suite
from tools.calibrate.suites.tpm import Tpm


def _sign(ctx: Ctx, key: str, msg: str) -> float:
    return ctx.sh.run(
        ["openssl", "pkeyutl", "-sign", "-inkey", key, "-rawin", "-in", msg, "-out", msg + ".sig"]
    ).seconds


def run(ctx: Ctx) -> None:
    ctx.sh.need("tpm2_quote", "tpm2_checkquote", "openssl")
    work = ctx.out / "attest"
    t = Tpm(ctx.sh, work, ctx.opt("tcti"))
    t.make_ak()
    key = str(work / "verifier.key")
    ctx.sh.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", key])
    for rep in range(ctx.reps(50)):
        t0 = time.monotonic()
        nonce = secrets.token_hex(16)
        quote_s = t.quote(nonce)
        check_s = t.checkquote(nonce)
        cert_s = _sign(ctx, key, t.f("quote.msg"))
        total = time.monotonic() - t0
        ctx.rec.add("attest_roundtrip", total, rep=rep)
        ctx.rec.add("attest_quote", quote_s, rep=rep)
        ctx.rec.add("attest_verify", check_s + cert_s, rep=rep, parts="checkquote+ed25519")


SUITE = Suite("attest_local", run, "quote → checkquote → certificate signature on one host (no network)")
