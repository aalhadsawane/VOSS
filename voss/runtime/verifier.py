"""Verifier + registrar actor (doc 04 §5): session certificates, periodic re-quotes, expiry → revocation, and bans of
TPM identities that failed an audit (plan V7.3)."""

from __future__ import annotations

from voss.core.ids import NodeId, WorkerId
from voss.core.messages import Attest, Ban, Message, Requote, RevokeSession, SessionCert
from voss.metrics.schema import Table
from voss.runtime.actor import Actor, ActorContext


class Verifier(Actor):
    """Issues ``SESSION_CERT(identity, assurance, expiry)``; expiry extends on each re-quote (perishability)."""

    role = "verifier"

    def __init__(self, host: NodeId, ctx: ActorContext, profiles: dict[str, tuple[float, float]]) -> None:
        super().__init__(host, ctx)
        self.profiles = profiles  # substrate → (assurance_base, valid_s)
        self.expiry: dict[str, float] = {}
        self.owner: dict[str, WorkerId] = {}
        self.revoked: set[str] = set()
        self.valid: dict[str, float] = {}
        self.assurance: dict[str, float] = {}
        self.banned: set[str] = set()  # TPM identities

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, Attest):
            self._attest(msg)
        elif isinstance(msg, Requote):
            self._requote(msg)
        elif isinstance(msg, Ban):
            self._ban(msg)

    def _ban(self, m: Ban) -> None:
        ident = m.cert_id.split(":")[0]
        if ident in self.banned:
            return
        self.banned.add(ident)
        self.ctx.rec.log(Table.EVENTS, t=self.now, kind="banned", worker=m.worker, cert=m.cert_id, value=0.0)
        if m.cert_id in self.expiry and m.cert_id not in self.revoked:
            self._revoke(m.cert_id, "cert_revoked")

    def _attest(self, m: Attest) -> None:
        if m.identity in self.banned:
            self.send(m.reply_to, SessionCert(m.worker, m.session, "", 0.0, 0.0, ok=False))
            return
        base, valid = self.profiles[m.substrate]
        f_policy = 1.0 if m.known_good else self.ctx.cfg.voss.worker.assurance_tofu_factor
        cert = f"{m.identity}:{m.session}"
        expiry = self.now + valid
        self.expiry[cert], self.owner[cert] = expiry, m.worker
        self.valid[cert], self.assurance[cert] = valid, base * f_policy
        self.ctx.rec.log(Table.EVENTS, t=self.now, kind="attested", worker=m.worker, cert=cert, value=base * f_policy)
        self.send(m.reply_to, SessionCert(m.worker, m.session, cert, base * f_policy, expiry))
        self.after(valid, self._check, cert, expiry)

    def _requote(self, m: Requote) -> None:
        if m.cert_id in self.revoked or m.cert_id not in self.expiry:
            self.send(m.reply_to, SessionCert(m.worker, m.session, m.cert_id, 0.0, 0.0, ok=False))
            return
        expiry = self.now + self.valid[m.cert_id]
        self.expiry[m.cert_id] = expiry
        self.send(m.reply_to, SessionCert(m.worker, m.session, m.cert_id, self.assurance[m.cert_id], expiry))
        self.after(self.valid[m.cert_id], self._check, m.cert_id, expiry)

    def _check(self, cert: str, expiry: float) -> None:
        if self.expiry.get(cert) != expiry or cert in self.revoked:
            return
        self._revoke(cert, "cert_expired")

    def _revoke(self, cert: str, kind: str) -> None:
        self.revoked.add(cert)
        w = self.owner[cert]
        self.ctx.rec.log(Table.EVENTS, t=self.now, kind=kind, worker=w, cert=cert, value=0.0)
        kbs = sorted(set(self.ctx.directory.kbs.values()))  # key services free the worker's places in holder budgets
        for dst in (self.ctx.directory.orchestrator, *self.ctx.directory.routers, *kbs):
            self.send(dst, RevokeSession(w, cert))
