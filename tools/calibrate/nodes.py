"""Node registry for multi-machine calibration (docs/handoff/NODE_PLAN.md).

Every bare-metal node writes ``calibration/specs/<label>/spec.yaml`` (``spec.sh``). This module reduces a spec to the
attributes that move a measured cost (CPU, cores, memory, storage classes, TPM kind, memory encryption), flags pairs
of nodes that would be one data point twice, and reports which kinds of heterogeneity the node set covers.

    uv run python -m tools.calibrate.nodes table [--branches]       # all nodes, coverage, duplicate pairs
    uv run python -m tools.calibrate.nodes check <label> [--branches]  # exit 3 if <label> duplicates another node

``--branches`` also reads the specs pushed on every ``origin/calib/*`` branch (nodes measured in parallel sessions).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
SPECS = REPO / "calibration" / "specs"
DUPLICATE, SIMILAR, DISTINCT = "duplicate", "similar", "distinct"
NODE = re.compile(r"^node\d{2}-")  # only v2 nodes take part; older specs (e.g. i7-12700-64g) are history


@dataclass(frozen=True)
class NodeClass:
    label: str
    cpu: str
    vendor: str
    cores: int
    threads: int
    mem_gib: float
    storage: tuple[str, ...]  # sorted subset of ("hdd", "nvme", "sata_ssd")
    tpm: str  # "firmware" | "discrete" | "none"
    tpm_maker: str
    mem_encryption: bool


def _storage(spec: dict[str, Any]) -> tuple[str, ...]:
    out = set()
    for d in (spec.get("storage") or {}).get("devices") or []:
        iface = str(d.get("interface", "")).lower()
        out.add("hdd" if d.get("rotational") else "nvme" if "nvme" in iface else "sata_ssd")
    return tuple(sorted(out))


def _tpm(spec: dict[str, Any]) -> tuple[str, str]:
    t = spec.get("tpm") or {}
    if not t:
        return "none", ""
    kind = str(t.get("type", "")).lower()
    maker = str(t.get("manufacturer", "")).split()[0] if t.get("manufacturer") else ""
    return ("firmware" if "firmware" in kind or "ftpm" in kind or "ptt" in kind else "discrete"), maker


def _encrypted(spec: dict[str, Any]) -> bool:
    text = yaml.safe_dump(spec.get("cpu", {})) + yaml.safe_dump(spec.get("firmware", {}))
    return bool(re.search(r"(tme_bios_enabled|sev_snp_enabled|sme_enabled|tdx_enabled): true", text))


def node_class(spec: dict[str, Any]) -> NodeClass:
    cpu = spec.get("cpu") or {}
    model = re.sub(r"\s+", " ", str(cpu.get("model", "unknown"))).strip()
    vendor = "amd" if "amd" in model.lower() else "intel" if "intel" in model.lower() else "other"
    mem = spec.get("memory") or {}
    gib = float(mem.get("total_gib") or float(mem.get("total_kb", 0)) / 2**20)
    tpm, maker = _tpm(spec)
    return NodeClass(
        str(spec.get("host_label", "?")),
        model,
        vendor,
        int(cpu.get("cores_total") or 0),
        int(cpu.get("threads_total") or 0),
        round(gib, 1),
        _storage(spec),
        tpm,
        maker,
        _encrypted(spec),
    )


def compare(a: NodeClass, b: NodeClass) -> tuple[str, list[str]]:
    """``duplicate``: same CPU model, memory within 25%, same storage classes and TPM kind (one data point twice).
    ``similar``: same CPU model, or three of the four checks; worth a sentence in the report. Else ``distinct``."""
    same_cpu = a.cpu == b.cpu
    mem_close = max(a.mem_gib, b.mem_gib) <= 1.25 * max(min(a.mem_gib, b.mem_gib), 1e-9)
    if same_cpu and mem_close and a.storage == b.storage and a.tpm == b.tpm:
        return DUPLICATE, ["same CPU model", "memory within 25%", "same storage classes", "same TPM kind"]
    why = [
        r
        for r, ok in [
            ("same CPU model", same_cpu),
            ("same core/thread count", (a.cores, a.threads) == (b.cores, b.threads)),
            ("memory within 25%", mem_close),
            ("same TPM kind", a.tpm == b.tpm),
        ]
        if ok
    ]
    return (SIMILAR if same_cpu or len(why) >= 3 else DISTINCT), why


def coverage(nodes: list[NodeClass]) -> dict[str, list[str]]:
    """Which values of each heterogeneity axis the node set covers (docs/handoff/NODE_PLAN.md §2)."""
    return {
        "cpu vendor": sorted({n.vendor for n in nodes}),
        "storage class": sorted({s for n in nodes for s in n.storage}),
        "tpm kind": sorted({n.tpm for n in nodes}),
        "memory encryption": sorted({str(n.mem_encryption).lower() for n in nodes}),
        "core count": sorted({str(n.cores) for n in nodes}, key=int),
        "memory (GiB)": sorted({f"{n.mem_gib:g}" for n in nodes}, key=float),
    }


def gaps(nodes: list[NodeClass]) -> list[str]:
    """Plan minimums (NODE_PLAN.md §2) the node set does not meet yet."""
    cov, out = coverage(nodes), []
    if len(nodes) < 3:
        out.append(f"{len(nodes)} node(s): at least 3 distinct nodes are needed")
    if len(set(cov["storage class"]) & {"hdd", "sata_ssd", "nvme"}) < 2:
        out.append("fewer than 2 storage classes")
    if len(cov["tpm kind"]) < 2:
        out.append("one TPM kind only (firmware and discrete both wanted)")
    cores = sorted(n.cores for n in nodes)
    if cores and cores[-1] < 2 * max(cores[0], 1):
        out.append("core counts within 2x of each other")
    return out


def load_local() -> dict[str, dict[str, Any]]:
    paths = sorted(p for p in SPECS.glob("*/spec.yaml") if NODE.match(p.parent.name))
    return {p.parent.name: yaml.safe_load(p.read_text()) for p in paths}


def load_branches() -> dict[str, dict[str, Any]]:
    """Specs on every ``origin/calib/*`` branch (fetched first)."""
    git = ["git", "-C", str(REPO)]
    subprocess.run([*git, "fetch", "-q", "origin", "+refs/heads/calib/*:refs/remotes/origin/calib/*"], check=False)
    refs = subprocess.run(
        [*git, "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/calib/"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    out: dict[str, dict[str, Any]] = {}
    for ref in sorted(refs):
        ls = subprocess.run(
            [*git, "ls-tree", "-r", "--name-only", ref, "calibration/specs/"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
        for path in sorted(p for p in ls if p.endswith("/spec.yaml") and NODE.match(Path(p).parent.name)):
            text = subprocess.run([*git, "show", f"{ref}:{path}"], capture_output=True, text=True, check=False).stdout
            out.setdefault(Path(path).parent.name, yaml.safe_load(text) or {})
    return out


def table(specs: dict[str, dict[str, Any]]) -> str:
    nodes = [node_class(s) for _, s in sorted(specs.items())]
    lines = ["| node | CPU | cores/threads | memory GiB | storage | TPM | memory encryption |", "|" + "---|" * 7]
    lines += [
        f"| {n.label} | {n.cpu} | {n.cores}/{n.threads} | {n.mem_gib:g} | {', '.join(n.storage)} | "
        f"{n.tpm} {n.tpm_maker} | {str(n.mem_encryption).lower()} |"
        for n in nodes
    ]
    lines += ["", "Coverage:"] + [f"- {k}: {', '.join(v)}" for k, v in coverage(nodes).items()]
    pairs = [(a, b, *compare(a, b)) for i, a in enumerate(nodes) for b in nodes[i + 1 :]]
    flagged = [p for p in pairs if p[2] != DISTINCT]
    lines += ["", "Pairs to look at:"] + (
        [f"- {a.label} / {b.label}: {r} ({', '.join(w)})" for a, b, r, w in flagged] or ["- none"]
    )
    lines += ["", "Gaps against NODE_PLAN.md §2:"] + ([f"- {g}" for g in gaps(nodes)] or ["- none"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.calibrate.nodes")
    p.add_argument("cmd", choices=["table", "check"])
    p.add_argument("label", nargs="?")
    p.add_argument("--branches", action="store_true", help="also read specs on origin/calib/* branches")
    a = p.parse_args(argv)
    specs = load_local()
    if a.branches:
        specs = {**load_branches(), **specs}
    if a.cmd == "table":
        print(table(specs))
        return 0
    if a.label not in specs:
        print(f"no spec for {a.label!r}; run spec.sh first", file=sys.stderr)
        return 2
    me = node_class(specs[a.label])
    dup = [
        (k, w)
        for k, s in sorted(specs.items())
        if k != a.label
        for r, w in [compare(me, node_class(s))]
        if r == DUPLICATE
    ]
    print(yaml.safe_dump(asdict(me), sort_keys=False))
    for k, w in dup:
        print(f"DUPLICATE of {k}: {', '.join(w)}. Stop and tell the human (NODE_PLAN.md §3).")
    return 3 if dup else 0


if __name__ == "__main__":
    raise SystemExit(main())
