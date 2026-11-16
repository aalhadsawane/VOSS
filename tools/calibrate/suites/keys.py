"""Key release and bundle decryption on the worker, and the key service's check (contract §2, doc 04 §6).

- ``key_request``: a new TLS 1.3 connection to a local key server, one 256-byte request and its 256-byte reply (the
  wrapped key), over loopback; the network delay to the tenant's key service is modelled separately.
- ``key_unwrap``: one RSA-2048 private-key operation (unwrapping the function key with the session key), from
  ``openssl speed``.
- ``decrypt_per_MB``: seconds per MB of AES-256-GCM decryption (bundles and snapshots are ciphertext), from
  ``openssl speed -evp aes-256-gcm -decrypt`` on 1 MB blocks.
- ``kbs_check``: the key service's own work for one request, timed on the server from the moment the request is read
  until its reply is ready: parse the session certificate, verify the verifier's Ed25519 signature on it, check expiry,
  appliance measurement and policy version, check the holder budget, and wrap the 32-byte function key to the
  session's RSA-2048 public key (OAEP, SHA-256). TLS and the network are not part of it (the substrate's ``rpc`` to
  the key service models them). Feeds the bundle's ``kbs_check_s``.

The bundle's ``key_release`` is ``key_request + key_unwrap`` (ingest). Parts (``--set only=``): ``release``
(``key_request``, ``key_unwrap``, ``decrypt_per_MB``) and ``kbs_check``.
"""

from __future__ import annotations

import json
import re
import socket
import ssl
import struct
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from tools.calibrate.common import SuiteSkipped
from tools.calibrate.suites import Ctx, Suite
from tools.calibrate.suites.tls import _server, make_cert

WRAPPED = b"k" * 256
KBS_REPS = 200  # contract §2: kbs_check n >= 200
MEASUREMENT = "ab" * 32  # the appliance measurement the test policy accepts


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


def _contexts(ctx: Ctx, name: str) -> tuple[ssl.SSLContext, ssl.SSLContext]:
    key, crt = make_cert(ctx, ctx.out / name)
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.minimum_version = ssl.TLSVersion.TLSv1_3
    sctx.load_cert_chain(crt, key)
    cctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    cctx.load_verify_locations(crt)
    return sctx, cctx


def _release(ctx: Ctx) -> None:
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
    sctx, cctx = _contexts(ctx, "keys")
    port, stop = _server(lambda c: sctx.wrap_socket(c, server_side=True))
    try:
        for rep in range(ctx.reps(200)):
            ctx.rec.add("key_request", _request(cctx, port), rep=rep)
    finally:
        stop.set()


@dataclass
class Kbs:
    """The key service's per-request work (doc 04 §6): one function key and a holder budget ``k``."""

    verifier_pub: Any
    k: int = 8
    min_version: int = 1
    fn_key: bytes = b"f" * 32
    holders: set[str] = field(default_factory=set)

    def check(self, request: bytes) -> bytes:
        """Verify the session certificate and the policy; return the function key wrapped to the session key."""
        from cryptography.hazmat.primitives import hashes, serialization  # noqa: PLC0415
        from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: PLC0415

        msg = json.loads(request)
        cert = msg["cert"].encode()
        self.verifier_pub.verify(bytes.fromhex(msg["sig"]), cert)  # raises InvalidSignature
        c = json.loads(cert)
        if c["expiry"] <= time.time() or c["measurement"] != MEASUREMENT or c["policy_version"] < self.min_version:
            return b"refused: policy"
        if c["worker"] not in self.holders and len(self.holders) >= self.k:
            return b"refused: budget"
        self.holders.add(c["worker"])
        pub = serialization.load_pem_public_key(c["session_pub"].encode())
        assert isinstance(pub, rsa.RSAPublicKey)
        oaep = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        return pub.encrypt(self.fn_key, oaep)


def session_request(verifier_key: Any, session_pub_pem: str, worker: str) -> bytes:
    """A worker's key request: its verifier-signed session certificate and the function it asks for."""
    cert = {"worker": worker, "measurement": MEASUREMENT, "policy_version": 1, "expiry": time.time() + 900}
    raw = json.dumps(cert | {"session_pub": session_pub_pem}, sort_keys=True).encode()
    return json.dumps({"cert": raw.decode(), "sig": verifier_key.sign(raw).hex(), "fn": "f"}).encode()


def _framed_read(s: socket.socket) -> bytes:
    head = b""
    while len(head) < 4:
        chunk = s.recv(4 - len(head))
        if not chunk:
            return b""
        head += chunk
    (n,) = struct.unpack("!I", head)
    body = b""
    while len(body) < n:
        body += s.recv(n - len(body))
    return body


def _kbs_serve(
    listener: socket.socket,
    wrap: Callable[[socket.socket], socket.socket],
    kbs: Kbs,
    times: list[float],
    stop: threading.Event,
) -> None:
    listener.settimeout(0.2)
    while not stop.is_set():
        try:
            conn, _ = listener.accept()
        except TimeoutError:
            continue
        try:
            s = wrap(conn)
            while req := _framed_read(s):
                t0 = time.perf_counter()
                reply = kbs.check(req)
                times.append(time.perf_counter() - t0)
                s.sendall(struct.pack("!I", len(reply)) + reply)
        except (ssl.SSLError, OSError):
            pass
        finally:
            conn.close()


def _kbs(ctx: Ctx) -> None:
    try:
        from cryptography.hazmat.primitives import serialization  # noqa: PLC0415
        from cryptography.hazmat.primitives.asymmetric import ed25519, rsa  # noqa: PLC0415
    except ImportError as e:
        raise SuiteSkipped("kbs_check needs the project's Python environment (cryptography)") from e
    verifier = ed25519.Ed25519PrivateKey.generate()
    session = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    pem = session.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    kbs, stop = Kbs(verifier.public_key()), threading.Event()
    times: list[float] = []
    sctx, cctx = _contexts(ctx, "kbs")
    ls = socket.create_server(("127.0.0.1", 0))
    port = ls.getsockname()[1]
    threading.Thread(
        target=_kbs_serve, args=(ls, lambda c: sctx.wrap_socket(c, server_side=True), kbs, times, stop), daemon=True
    ).start()
    try:
        for rep in range(ctx.reps(KBS_REPS)):
            req = session_request(verifier, pem, f"w{rep % kbs.k}")  # holders within the budget: always released
            s = cctx.wrap_socket(socket.create_connection(("127.0.0.1", port)), server_hostname="localhost")
            s.sendall(struct.pack("!I", len(req)) + req)
            reply = _framed_read(s)
            s.close()
            if reply.startswith(b"refused"):
                raise RuntimeError(f"kbs_check refused a valid request: {reply!r}")
            ctx.rec.add("kbs_check", times[-1], rep=rep, sig="ed25519", wrap="rsa2048-oaep-sha256", budget=kbs.k)
    finally:
        stop.set()


def run(ctx: Ctx) -> None:
    if ctx.part("release"):
        _release(ctx)
    if ctx.part("kbs_check") and not ctx.sh.dry_run:
        _kbs(ctx)


SUITE = Suite("keys", run, "key release (loopback TLS + RSA unwrap), AES-GCM decryption, key service check")
