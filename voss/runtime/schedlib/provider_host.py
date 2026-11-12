"""The host of the provider-hosted scheduler (D-83, docs/REVISION_PLAN.md V3.1).

The scheduler role reads a few attributes of the machine it runs on. On a provider server these are fixed: the machine
is always up and needs no attestation, and its speed is that of the provider CPU class used to charge decision time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from voss.core.ids import WorkerId

PROVIDER_CERT = "provider"
NODE = "scheduler"
NOT_A_WORKER = WorkerId(-1)


@dataclass
class ProviderHost:
    speed: float = 1.0
    worker: WorkerId = NOT_A_WORKER  # -1 in logs
    session: int = 1
    cert_id: str = PROVIDER_CERT
    attested: bool = True
    extra: dict[str, Any] = field(default_factory=dict)
