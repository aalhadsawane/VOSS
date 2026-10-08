"""Verifier + registrar actor (doc 04 §5): session certificates, periodic re-quotes, expiry → revocation."""

from __future__ import annotations

from voss.core.ids import NodeId, WorkerId
from voss.core.messages import Attest, Message, Requote, RevokeSession, SessionCert
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

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, Attest):
            self._attest(msg)
        elif isinstance(msg, Requote):
            self._requote(msg)

    def _attest(self, m: Attest) -> None:
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
        self.revoked.add(cert)
        w = self.owner[cert]
        self.ctx.rec.log(Table.EVENTS, t=self.now, kind="cert_expired", worker=w, cert=cert, value=0.0)
        for dst in (self.ctx.directory.orchestrator, *self.ctx.directory.routers):
            self.send(dst, RevokeSession(w, cert))
