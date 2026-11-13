"""Node registry: duplicate detection and coverage (docs/handoff/NODE_PLAN.md)."""

from __future__ import annotations

from typing import Any

from tools.calibrate.nodes import DISTINCT, DUPLICATE, SIMILAR, compare, gaps, node_class


def spec(label: str, cpu: str, cores: int, gib: float, disks: list[tuple[str, bool]], tpm: str) -> dict[str, Any]:
    return {
        "host_label": label,
        "cpu": {"model": cpu, "cores_total": cores, "threads_total": 2 * cores},
        "memory": {"total_gib": gib},
        "storage": {"devices": [{"interface": i, "rotational": r} for i, r in disks]},
        "tpm": {"type": tpm, "manufacturer": "X vendor"},
    }


A = node_class(spec("a", "Intel i7-12700", 12, 62.5, [("NVME", False)], "firmware (PTT)"))
B = node_class(spec("b", "Intel i7-12700", 12, 60.0, [("NVME", False)], "firmware (PTT)"))
C = node_class(spec("c", "Intel i3-7020U", 2, 3.8, [("SATA", True)], "discrete TPM 2.0"))
D = node_class(spec("d", "AMD Ryzen 5 5600", 6, 15.6, [("SATA", False)], "firmware (fTPM)"))


def test_storage_and_tpm_kinds() -> None:
    assert A.storage == ("nvme",) and C.storage == ("hdd",) and D.storage == ("sata_ssd",)
    assert (A.tpm, C.tpm, D.tpm) == ("firmware", "discrete", "firmware") and D.vendor == "amd"


def test_same_machine_twice_is_a_duplicate() -> None:
    assert compare(A, B)[0] == DUPLICATE
    assert compare(A, C)[0] == DISTINCT
    bigger = node_class(spec("e", "Intel i7-12700", 12, 125.0, [("NVME", False)], "firmware (PTT)"))
    assert compare(A, bigger)[0] == SIMILAR  # same CPU, different memory: one sentence in the report


def test_gaps_name_what_the_node_set_lacks() -> None:
    assert any("at least 3" in g for g in gaps([A, B]))
    assert gaps([A, C, D]) == []
