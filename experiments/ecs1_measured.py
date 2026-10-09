"""E-CS1, measured side (doc 06 §5, ROADMAP P9 exit): start-up and trust-establishment latencies measured on the
calibration node, per path and configuration, from raw harness logs (``tools/calibrate``). Pairs with the simulated
table of ``experiments/ecs1.py``. Usage: ``python -m experiments.ecs1_measured --raw calibration/raw``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from tools.calibrate.ingest import load_raw

ROWS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    # (path, suite, probe, config keys that split rows)
    ("Firecracker spawn → API", "fc_boot", "fc_spawn", ()),
    ("Firecracker boot → init (L1→L3)", "fc_boot", "fc_boot", ("mem_mb", "tier", "cache")),
    ("Firecracker snapshot create", "fc_snapshot", "fc_snapshot_create", ("mem_mb", "tier")),
    ("Firecracker restore, load API (L2→L3)", "fc_snapshot", "fc_restore_api", ("mem_mb", "tier", "cache")),
    ("Firecracker restore → first response", "fc_snapshot", "fc_restore", ("mem_mb", "tier", "cache")),
    ("QEMU boot → init", "qemu_vm", "qemu_boot", ("machine",)),
    ("Appliance reboot → kernel", "appliance", "reboot_to_kernel", ()),
    ("Appliance userspace → agent", "appliance", "appliance_userspace", ()),
    ("Appliance userspace → attested", "appliance", "appliance_attested", ()),
    ("TPM quote", "tpm", "tpm2_quote", ()),
    ("Local attestation round trip", "attest_local", "attest_roundtrip", ()),
    ("TLS 1.3 handshake", "tls", "tls_handshake", ()),
)


def rows(df: pd.DataFrame) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for path, suite, probe, keys in ROWS:
        d = df[(df.suite == suite) & (df.probe == probe)]
        if not len(d):
            out.append({"path": path, "config": "not measured", "n": 0})
            continue
        label = d.config.map(lambda c, keys=keys: ", ".join(f"{k}={c.get(k)}" for k in keys) if keys else "—")
        for cfg, g in d.groupby(label, sort=True):
            x = g.value.to_numpy(dtype=float)
            q = np.quantile(x, [0.5, 0.9, 0.99])
            out.append({"path": path, "config": cfg, "n": len(x), "p50": q[0], "p90": q[1], "p99": q[2]})
    return out


def report(table: list[dict[str, object]], host: str) -> str:
    lines = [
        "# E-CS1 (measured)",
        "",
        f"Calibration node `{host}`; seconds; raw logs from `tools/calibrate` (doc 10 §3). Rows marked *not measured* "
        "keep literature values in the simulator (doc 10 §2).",
        "",
        "| Path | Configuration | n | p50 | p90 | p99 |",
        "|---|---|---|---|---|---|",
    ]
    for r in table:
        if not r["n"]:
            lines.append(f"| {r['path']} | {r['config']} | 0 | | | |")
            continue
        lines.append(f"| {r['path']} | {r['config']} | {r['n']} | {r['p50']:.4f} | {r['p90']:.4f} | {r['p99']:.4f} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--host", default=None)
    p.add_argument("--out", type=Path, default=Path("docs/pilots/ECS1-measured.md"))
    a = p.parse_args(argv)
    df, _, _ = load_raw(a.raw, a.host)
    a.out.write_text(report(rows(df), a.host or (str(df.host.iloc[0]) if len(df) else "?")))
    print(a.out)


if __name__ == "__main__":
    main()
