"""TLS suite (doc 10 §3): TLS 1.3 handshake CPU time and per-message overhead over loopback (channel costs).

A self-signed ECDSA certificate is made with ``openssl``; the server runs in a thread of this process. The
per-message overhead is the difference between 1 KiB echo round trips over TLS and over plain TCP.
"""

from __future__ import annotations

import socket
import ssl
import threading
import time
from collections.abc import Callable
from pathlib import Path

from tools.calibrate.suites import Ctx, Suite

MSG = b"x" * 1024


def make_cert(ctx: Ctx, d: Path) -> tuple[str, str]:
    d.mkdir(parents=True, exist_ok=True)
    key, crt = str(d / "tls.key"), str(d / "tls.crt")
    curve = ["-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes"]
    ctx.sh.run(["openssl", "req", "-x509", *curve, "-keyout", key, "-out", crt, "-days", "1", "-subj", "/CN=localhost"])
    return key, crt


def _serve(listener: socket.socket, wrap: Callable[[socket.socket], socket.socket], stop: threading.Event) -> None:
    listener.settimeout(0.2)
    while not stop.is_set():
        try:
            conn, _ = listener.accept()
        except TimeoutError:
            continue
        try:
            s = wrap(conn)
            while data := s.recv(65536):
                s.sendall(data)
        except (ssl.SSLError, OSError):
            pass
        finally:
            conn.close()


def _server(wrap: Callable[[socket.socket], socket.socket]) -> tuple[int, threading.Event]:
    ls = socket.create_server(("127.0.0.1", 0))
    stop = threading.Event()
    threading.Thread(target=_serve, args=(ls, wrap, stop), daemon=True).start()
    return ls.getsockname()[1], stop


def _echo(s: socket.socket, n: int) -> float:
    t0 = time.perf_counter()
    for _ in range(n):
        s.sendall(MSG)
        got = 0
        while got < len(MSG):
            got += len(s.recv(65536))
    return (time.perf_counter() - t0) / n


def run(ctx: Ctx) -> None:
    ctx.sh.need("openssl")
    if ctx.sh.dry_run:
        return
    key, crt = make_cert(ctx, ctx.out / "tls")
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.minimum_version = ssl.TLSVersion.TLSv1_3
    sctx.load_cert_chain(crt, key)
    cctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    cctx.load_verify_locations(crt)
    port, stop = _server(lambda c: sctx.wrap_socket(c, server_side=True))
    plain_port, stop_plain = _server(lambda c: c)
    try:
        for rep in range(ctx.reps(1000)):
            raw = socket.create_connection(("127.0.0.1", port))
            t0 = time.process_time(), time.perf_counter()
            s = cctx.wrap_socket(raw, server_hostname="localhost")
            ctx.rec.add("tls_handshake", time.perf_counter() - t0[1], rep=rep, version=s.version())
            ctx.rec.add("tls_handshake_cpu", time.process_time() - t0[0], rep=rep)
            if rep % 100 == 0:
                plain = socket.create_connection(("127.0.0.1", plain_port))
                ctx.rec.add("tls_msg_overhead", _echo(s, 200) - _echo(plain, 200), rep=rep, msg_bytes=len(MSG))
                plain.close()
            s.close()
    finally:
        stop.set()
        stop_plain.set()


SUITE = Suite("tls", run, "TLS 1.3 handshake time/CPU and per-message overhead over loopback")
