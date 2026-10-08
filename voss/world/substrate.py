"""Trust substrate profiles are data (doc 02 §5, doc 04 §3, doc 05 §5).

``load_substrate(name, bundle)`` validates ``configs/substrates/<name>.yaml`` and resolves every distribution
reference (``measured/<name>``) against the calibration bundle. ``world/lifecycle.py`` interprets the result; there
is no per-substrate code.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from voss.core.dist import Const, Dist
from voss.core.paths import config_path, load_data_yaml

SUBSTRATES: tuple[str, ...] = ("appliance_tpm", "cvm_snp", "coco_pool", "drtm_hv", "none")
Artifact = Literal["bundle", "rootfs", "snapshot", "snapshot_touched", "zygote"]
Endpoint = Literal["verifier", "tenant_kbs", "registry", "orchestrator"]
DistRef = Dist | str | float
_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}


def parse_size(v: int | float | str) -> int:
    """``"6KB"`` → 6144 bytes; numbers are bytes."""
    if isinstance(v, int | float):
        return int(v)
    m = re.fullmatch(r"\s*([0-9.]+)\s*([KMG]?B)\s*", v)
    if not m:
        raise ValueError(f"bad size '{v}'")
    return int(float(m.group(1)) * _UNITS[m.group(2)])


class _Op(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DelayOp(_Op):
    op: Literal["delay"]
    dist: DistRef


class TpmQuoteOp(_Op):
    op: Literal["tpm_quote"]


class PspOp(_Op):
    op: Literal["psp"]
    dist: DistRef


class RpcOp(_Op):
    op: Literal["rpc"]
    to: Endpoint
    size: int = 1024
    reply: int = 1024

    @field_validator("size", "reply", mode="before")
    @classmethod
    def _size(cls, v: Any) -> int:
        return parse_size(v)


class CpuOp(_Op):
    op: Literal["cpu"]
    work: DistRef
    per_mb: tuple[Artifact, ...] = ()


class FetchOp(_Op):
    op: Literal["fetch"]
    artifacts: tuple[Artifact, ...]


class DiskReadOp(_Op):
    op: Literal["disk_read"]
    what: Artifact


class DiskWriteOp(_Op):
    op: Literal["disk_write"]
    what: Artifact


Op = Annotated[
    DelayOp | TpmQuoteOp | PspOp | RpcOp | CpuOp | FetchOp | DiskReadOp | DiskWriteOp, Field(discriminator="op")
]


class SessionSpec(_Op):
    establish: tuple[Op, ...]
    reattest: tuple[Op, ...] = ()
    reattest_every_s: float = Field(gt=0)
    valid_s: float = Field(gt=0)


class LadderSpec(_Op):
    levels: tuple[str, ...]
    ready: str
    busy: str
    persistent: tuple[str, ...] = ()
    transitions: dict[str, tuple[Op, ...]]
    after_init: tuple[Op, ...] = ()

    @model_validator(mode="after")
    def _graph(self) -> LadderSpec:
        lv = set(self.levels)
        for name in (self.ready, self.busy, *self.persistent):
            if name not in lv:
                raise ValueError(f"unknown level '{name}'")
        for key in self.transitions:
            a, _, b = key.partition("->")
            if a not in lv or b not in lv:
                raise ValueError(f"transition '{key}' uses unknown levels")
        for lvl in self.levels[: self.levels.index(self.ready)]:
            if not self.path(lvl):
                raise ValueError(f"level '{lvl}' cannot reach ready level '{self.ready}'")
        return self

    def path(self, start: str) -> list[str]:
        """Transition keys from ``start`` to ``ready`` (fewest hops, ties by key order); [] if unreachable."""
        frontier: list[tuple[str, list[str]]] = [(start, [])]
        seen = {start}
        while frontier:
            nxt = []
            for lvl, keys in frontier:
                if lvl == self.ready:
                    return keys
                for key in sorted(self.transitions):
                    a, _, b = key.partition("->")
                    if a == lvl and b not in seen:
                        seen.add(b)
                        nxt.append((b, [*keys, key]))
            frontier = nxt
        return []


class OwnerActivity(_Op):
    rate_per_h: float = Field(ge=0)
    duration: DistRef
    cpu_factor: float = Field(ge=1)


class SubstrateProfile(_Op):
    """Doc 04 §3: how trust is established and lasts, the ladder, assurance and slowdowns."""

    name: str
    assurance_base: float = Field(ge=0, le=1)
    concurrent_owner_use: bool
    session: SessionSpec
    trust: tuple[Op, ...]
    ladder: LadderSpec
    slowdown: dict[Literal["cpu", "mem", "io"], DistRef]
    owner_activity: OwnerActivity | None = None


def load_bundle(path: str) -> dict[str, Dist]:
    """Distributions of a calibration bundle (``<path>/distributions.yaml``)."""
    raw = load_data_yaml(config_path(path) / "distributions.yaml")
    return {k: _as_dist(v) for k, v in raw.get("distributions", {}).items()}


def _as_dist(v: Any) -> Dist:
    from pydantic import TypeAdapter  # noqa: PLC0415

    adapter: TypeAdapter[Dist] = TypeAdapter(Dist)
    return adapter.validate_python(v)


def _resolve(v: Any, bundle: dict[str, Dist], where: str) -> Any:
    """``measured/<name>`` → bundle dist; numbers → const; inline dist mappings and ``fn.<attr>`` pass through."""
    if isinstance(v, str) and v.startswith("measured/"):
        key = v.removeprefix("measured/")
        if key not in bundle:
            raise ValueError(f"{where}: '{v}' missing from calibration bundle")
        return bundle[key].model_dump()
    if isinstance(v, str) and not v.startswith("fn."):
        raise ValueError(f"{where}: bad reference '{v}' (use measured/<name> or fn.<attr>)")
    if isinstance(v, int | float) and not isinstance(v, bool):
        return Const(value=float(v), tag="assumed").model_dump()
    return v


def _walk(tree: Any, bundle: dict[str, Dist], where: str) -> Any:
    """Resolve references in every ``dist``/``work``/``duration`` field and in ``slowdown``."""
    if isinstance(tree, dict):
        out = {}
        for k, v in tree.items():
            if k in ("dist", "work", "duration"):
                out[k] = _resolve(v, bundle, f"{where}.{k}")
            elif k == "slowdown":
                out[k] = {s: _resolve(x, bundle, f"{where}.slowdown.{s}") for s, x in v.items()}
            else:
                out[k] = _walk(v, bundle, f"{where}.{k}")
        return out
    if isinstance(tree, list):
        return [_walk(x, bundle, f"{where}[{i}]") for i, x in enumerate(tree)]
    return tree


def load_substrate(name: str, bundle: dict[str, Dist]) -> SubstrateProfile:
    raw = load_data_yaml(f"substrates/{name}.yaml")
    prof = SubstrateProfile.model_validate(_walk(raw, bundle, name))
    if prof.name != name:
        raise ValueError(f"substrates/{name}.yaml declares name '{prof.name}'")
    return prof
