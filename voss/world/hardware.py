"""One machine class of the calibrated fleet (doc 02 §1; plan V9.4, D-107).

Classes are built from calibration bundles only (``world/machines.py``); the v1 assumed hardware classes are deleted
(checklist 1.1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HwClass(BaseModel):
    """Threads, memory, disks and TPM kind of one measured machine class."""

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
    mem_encryption: bool = False  # active memory encryption (SEV-SNP/TDX): owner class M (plan V3.3)
