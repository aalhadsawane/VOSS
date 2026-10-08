"""Host-local state of one worker appliance: resources, cache, session identity (doc 02 §1, §6; doc 04 §4).

The worker agent and the latent scheduler role run in the same appliance and share this object (same host, same
memory); nothing here crosses the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from voss.core.dist import Const, Dist
from voss.core.ids import WorkerId
from voss.core.kernel import Kernel
from voss.core.rng import RngFactory
from voss.core.types import WorkerStatic
from voss.world.cache import WorkerCache
from voss.world.resources import Disk, Psp, Slots, Tpm
from voss.world.substrate import SubstrateProfile


@dataclass
class HostLocal:
    """Static description plus resources of one worker host."""

    worker: WorkerId
    identity: str
    profile: SubstrateProfile
    speed: float
    n_slots: int
    domain: int
    known_good: bool
    snapshot_class: str
    slots: Slots
    disks: dict[str, Disk]
    tpm: Tpm
    psp: Psp
    cache: WorkerCache
    cpu_slowdown: float = 1.0
    io_slowdown: float = 1.0
    session: int = 0
    up: bool = False
    cert_id: str = ""
    cert_expiry: float = 0.0
    assurance: float = 0.0
    attested: bool = False
    extra: dict[str, float] = field(default_factory=dict)
    static_base: WorkerStatic | None = None
    static: WorkerStatic | None = None

    def cert_valid(self, now: float) -> bool:
        return self.attested and self.cert_expiry > now

    def reset_session(self) -> None:
        """Host power loss: RAM state and in-flight resource work vanish; disk caches survive."""
        self.slots.reset()
        for d in self.disks.values():
            d.reset()
        self.tpm.reset()
        self.psp.reset()
        self.cache.session_end()
        self.up = False
        self.attested = False
        self.cert_id = ""
        self.cert_expiry = 0.0


def make_host(
    kernel: Kernel,
    rng: RngFactory,
    w: WorkerId,
    identity: str,
    profile: SubstrateProfile,
    hw: dict[str, float],
    caps: dict[str, float],
    quote: Dist | None,
    meta: tuple[int, bool, str],
    hdd_tier: bool,
) -> HostLocal:
    """Build a worker host.

    ``hw``: disk speeds; ``caps``: slots/speed/mem/ssd/hdd; ``meta``: (domain, known_good, snapshot class).
    """
    gen = rng.stream("host.tpm", w)
    disks = {
        "ssd": Disk(kernel, "ssd", hw["ssd_read_MBps"], hw["ssd_write_MBps"]),
        "hdd": Disk(kernel, "hdd", max(hw["hdd_read_MBps"], 1e-3), max(hw["hdd_write_MBps"], 1e-3)),
    }
    tpm = Tpm(kernel, quote if quote is not None else Const(value=0.0), gen)
    return HostLocal(
        worker=w,
        identity=identity,
        profile=profile,
        speed=caps["speed"],
        n_slots=int(caps["slots"]),
        domain=meta[0],
        known_good=meta[1],
        snapshot_class=meta[2],
        slots=Slots(int(caps["slots"])),
        disks=disks,
        tpm=tpm,
        psp=Psp(kernel),
        cache=WorkerCache(caps["ssd_mb"], caps["hdd_mb"] if hdd_tier else 0.0, caps["mem_mb"], hdd_tier),
    )
