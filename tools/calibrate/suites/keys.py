"""Key release and bundle decryption on the worker (docs/handoff/CALIBRATION_DATA_CONTRACT.md §2).

- ``key_request``: a new TLS 1.3 connection to a local key server, one 256-byte request and its 256-byte reply (the
  wrapped key), over loopback; the network delay to the tenant's key service is modelled separately.
- ``key_unwrap``: one RSA-2048 private-key operation (unwrapping the function key with the session key), from
  ``openssl speed``.
- ``decrypt_per_MB``: seconds per MB of AES-256-GCM decryption (bundles and snapshots are ciphertext), from
  ``openssl speed -evp aes-256-gcm -decrypt`` on 1 MB blocks.

The bundle's ``key_release`` is ``key_request + key_unwrap`` (ingest).
"""

from __future__ import annotations

import re
import socket
import ssl
import time

from tools.calibrate.suites import Ctx, Suite
from tools.calibrate.suites.tls import _server, make_cert

WRAPPED = b"k" * 256


def speed_aes_mbps(out: str) -> float | None:
    """MB/s of the 1 MB column of ``openssl speed -evp aes-256-gcm -bytes 1048576`` (numbers in 1000s of bytes/s)."""
    for line in out.splitlines():
        if line.lower().startswith("aes-256-gcm"):
            nums = re.findall(r"([0-9.]+)k", line)
            if nums:
                return float(nums[-1]) * 1000 / 1e6
    return None


def speed_rsa_private_s(out: str) -> float | None:
    """Seconds per RSA-2048 private-key operation from ``openssl speed rsa2048`` (the ``sign`` column)."""
    for line in out.splitlines():
        m = re.match(r"\s*rsa\s+2048 bits\s+([0-9.]+)s", line)
        if m:
            return float(m.group(1))
    return None


def _request(cctx: ssl.SSLContext, port: int) -> float:
    t0 = time.perf_counter()
    raw = socket.create_connection(("127.0.0.1", port))
    s = cctx.wrap_socket(raw, server_hostname="localhost")
    s.sendall(WRAPPED)
    got = 0
    while got < len(WRAPPED):
        got += len(s.recv(4096))
    dt = time.perf_counter() - t0
    s.close()
    return dt


def run(ctx: Ctx) -> None:
    ctx.sh.need("openssl")
    aes = ctx.sh.run(["openssl", "speed", "-evp", "aes-256-gcm", "-decrypt", "-bytes", "1048576", "-seconds", "2"])
    rsa = ctx.sh.run(["openssl", "speed", "-seconds", "2", "rsa2048"])
    if ctx.sh.dry_run:
        return
    mbps, unwrap = speed_aes_mbps(aes.out), speed_rsa_private_s(rsa.out)
    if mbps:
        ctx.rec.add("decrypt_per_MB", 1.0 / mbps, unit="s/MB", cipher="aes-256-gcm")
    if unwrap is not None:
        ctx.rec.add("key_unwrap", unwrap, alg="rsa2048")
    key, crt = make_cert(ctx, ctx.out / "keys")
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.minimum_version = ssl.TLSVersion.TLSv1_3
    sctx.load_cert_chain(crt, key)
    cctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    cctx.load_verify_locations(crt)
    port, stop = _server(lambda c: sctx.wrap_socket(c, server_side=True))
    try:
        for rep in range(ctx.reps(200)):
            ctx.rec.add("key_request", _request(cctx, port), rep=rep)
    finally:
        stop.set()


SUITE = Suite("keys", run, "key release (loopback TLS request + RSA unwrap) and AES-GCM decryption per MB")
