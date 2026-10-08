"""Hardware classes (doc 02 §1). C0 is the calibration node; other classes are scaled by benchmark ratios."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from voss.core.paths import load_data_yaml


class HwClass(BaseModel):
    """One hardware class (``configs/hardware/<name>.yaml``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    speed: float = Field(gt=0)
    cores: int = Field(gt=0)
    mem_gb: float = Field(gt=0)
    ssd_gb: float = Field(ge=0)
    hdd_gb: float = Field(ge=0)
    ssd_read_MBps: float = Field(ge=0)
    ssd_write_MBps: float = Field(ge=0)
    hdd_read_MBps: float = Field(ge=0)
    hdd_write_MBps: float = Field(ge=0)
    cpu_model: str
    tpm: str


def load_hw_class(name: str) -> HwClass:
    return HwClass.model_validate(load_data_yaml(f"hardware/{name}.yaml"))


def load_hw_classes(names: list[str]) -> dict[str, HwClass]:
    return {n: load_hw_class(n) for n in sorted(names)}
