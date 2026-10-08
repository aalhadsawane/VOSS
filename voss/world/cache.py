"""Worker caches: three tiers, content-addressed (doc 02 §6). Mechanics only; value policies live in
``policy/cache_value.py`` (P4). P2 uses LRU among unpinned entries.

- Disk tiers (SSD, HDD) hold bundles, rootfs and snapshots keyed by digest; they survive session end (ciphertext).
- RAM holds idle warm VMs per function (L3) and running VMs; it is wiped at session end.
- SSD pressure demotes the least valuable unpinned entry to HDD before evicting; HDD pressure evicts.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

DiskTier = str  # "ssd" | "hdd"


def digest(*parts: object) -> str:
    """Content address of an artifact: ``digest(fn, version, kind, snapshot_class)`` (doc 02 §6)."""
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:24]


@dataclass
class Entry:
    digest: str
    kind: str
    size_mb: float
    tier: DiskTier
    last_used: float
    hits: int = 0
    pinned: bool = False


@dataclass
class WarmVm:
    fn: str
    mem_mb: float
    idle_since: float


@dataclass
class CacheStats:
    hits: dict[str, int] = field(default_factory=dict)
    evictions: int = 0
    demotions: int = 0
    promotions: int = 0
    bytes_written: dict[str, float] = field(default_factory=lambda: {"ssd": 0.0, "hdd": 0.0})


class WorkerCache:
    """Three-tier cache of one worker. ``value`` ranks unpinned entries for eviction (lowest first)."""

    def __init__(self, ssd_mb: float, hdd_mb: float, mem_mb: float, hdd_tier: bool = True) -> None:
        self.budget = {"ssd": ssd_mb, "hdd": hdd_mb if hdd_tier else 0.0}
        self.mem_mb = mem_mb
        self.disk: dict[str, Entry] = {}
        self._used = {"ssd": 0.0, "hdd": 0.0}
        self.warm: dict[str, list[WarmVm]] = {}
        self.running_mb = 0.0
        self.version = 0
        self.stats = CacheStats()
        self.value: Callable[[Entry], float] = lambda e: e.last_used  # LRU

    # --- disk tiers ------------------------------------------------------------------------------------------
    def used(self, tier: DiskTier) -> float:
        return self._used.get(tier, 0.0)

    def _set_tier(self, e: Entry, tier: DiskTier) -> None:
        self.version += 1
        if e.tier in self._used:
            self._used[e.tier] -= e.size_mb
        e.tier = tier
        if tier in self._used:
            self._used[tier] += e.size_mb

    def free(self, tier: DiskTier) -> float:
        return self.budget[tier] - self.used(tier)

    def tier_of(self, d: str) -> DiskTier | None:
        e = self.disk.get(d)
        return e.tier if e else None

    def touch(self, d: str, now: float) -> Entry | None:
        e = self.disk.get(d)
        if e is not None:
            e.last_used, e.hits = now, e.hits + 1
            self.stats.hits[e.tier] = self.stats.hits.get(e.tier, 0) + 1
        return e

    def insert(self, d: str, kind: str, size_mb: float, now: float) -> DiskTier | None:
        """Insert on SSD (demoting/evicting as needed), else on HDD; ``None`` if it fits nowhere."""
        if d in self.disk:
            self.touch(d, now)
            return self.disk[d].tier
        for tier in ("ssd", "hdd"):
            if size_mb <= self.budget[tier] and self._make_room(tier, size_mb, now):
                self.disk[d] = Entry(d, kind, size_mb, "new", now)
                self._set_tier(self.disk[d], tier)
                self.stats.bytes_written[tier] += size_mb
                return tier
        return None

    def promote(self, d: str, now: float) -> bool:
        """Move an HDD entry to SSD (the caller pays the I/O). Returns whether it moved."""
        e = self.disk.get(d)
        if e is None or e.tier != "hdd" or e.size_mb > self.budget["ssd"]:
            return False
        self._set_tier(e, "promoting")
        ok = self._make_room("ssd", e.size_mb, now)
        self._set_tier(e, "ssd" if ok else "hdd")
        self.stats.promotions += int(ok)
        return ok

    def remove(self, d: str) -> None:
        e = self.disk.pop(d, None)
        if e is not None:
            self._set_tier(e, "gone")

    def pin(self, d: str, pinned: bool = True) -> None:
        if d in self.disk:
            self.disk[d].pinned = pinned

    def _victims(self, tier: DiskTier) -> list[Entry]:
        cand = [e for e in self.disk.values() if e.tier == tier and not e.pinned]
        return sorted(cand, key=lambda e: (self.value(e), e.digest))

    def _make_room(self, tier: DiskTier, size_mb: float, now: float) -> bool:
        need = size_mb - self.free(tier)
        if need <= 0:
            return True
        victims = self._victims(tier)
        if sum(e.size_mb for e in victims) < need:
            return False
        for e in victims:
            if self.free(tier) >= size_mb:
                break
            if tier == "ssd" and self.budget["hdd"] > 0 and self._demote(e, now):
                continue
            self.remove(e.digest)
            self.stats.evictions += 1
        return self.free(tier) >= size_mb

    def _demote(self, e: Entry, now: float) -> bool:
        self._set_tier(e, "demoting")
        ok = e.size_mb <= self.budget["hdd"] and self._make_room("hdd", e.size_mb, now)
        self._set_tier(e, "hdd" if ok else "ssd")
        if ok:
            self.stats.demotions += 1
            self.stats.bytes_written["hdd"] += e.size_mb
        return ok

    # --- RAM: warm VMs -------------------------------------------------------------------------------------
    def _all_warm(self) -> list[WarmVm]:
        return [v for vs in self.warm.values() for v in vs]

    def warm_mb(self) -> float:
        return sum(v.mem_mb for vs in self.warm.values() for v in vs)

    def mem_free(self) -> float:
        return self.mem_mb - self.warm_mb() - self.running_mb

    def warm_count(self, fn: str) -> int:
        return len(self.warm.get(fn, ()))

    def take_warm(self, fn: str) -> WarmVm | None:
        """Most recently idle warm VM of ``fn`` (removed from the idle pool)."""
        vs = self.warm.get(fn)
        if not vs:
            return None
        self.version += 1
        v = vs.pop()  # lists are kept in idle_since order
        if not vs:
            del self.warm[fn]
        return v

    def park_warm(self, fn: str, mem_mb: float, now: float) -> bool:
        """Keep a finished VM warm if RAM allows (evicting the least recently idle VMs)."""
        while self.mem_free() < mem_mb and self.warm:
            oldest = min(self._all_warm(), key=lambda v: (v.idle_since, v.fn))
            self.version += 1
            self.warm[oldest.fn].remove(oldest)
            if not self.warm[oldest.fn]:
                del self.warm[oldest.fn]
            self.stats.evictions += 1
        if self.mem_free() < mem_mb:
            return False
        self.warm.setdefault(fn, []).append(WarmVm(fn, mem_mb, now))
        self.version += 1
        return True

    def expire_warm(self, now: float, ttl: float) -> int:
        dropped = 0
        for fn in sorted(self.warm):
            keep = [v for v in self.warm[fn] if now - v.idle_since < ttl]
            dropped += len(self.warm[fn]) - len(keep)
            if keep:
                self.warm[fn] = keep
            else:
                del self.warm[fn]
        self.version += int(dropped > 0)
        return dropped

    def session_end(self) -> None:
        """RAM state is lost; disk state survives as ciphertext (doc 02 §5)."""
        self.warm.clear()
        self.running_mb = 0.0
        self.version += 1
