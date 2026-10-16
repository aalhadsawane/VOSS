"""Calibration tables and macros: measured bundle, E-CS1 and E24 (doc 10; doc 06 §5)."""

from __future__ import annotations

from typing import Any

import pandas as pd
from tools.calibrate.ingest import load_raw

from experiments import ecs1_measured
from experiments.paper_tex.core import HOST, REPO, Gen, T, esc, expect, ms, rows, tab, tabular


# --- calibration ---------------------------------------------------------------------------------------------------
def calibration(g: Gen) -> None:
    from voss.world.substrate import load_bundle  # noqa: PLC0415

    meas, plc = load_bundle(f"calibration/measured/{HOST}"), load_bundle("calibration/placeholder/c0")
    names = {
        "tpm2_quote": ("TPM quote", "s", "TPM"),
        "verify_s": ("Verifier (check quote + signature)", "s", "attest"),
        "verify_s_per_MB": ("SHA-256 per MB", "s", "sha"),
        "fc_boot": ("Firecracker boot to init (warm cache, HDD)", "s", "fcboot"),
        "fc_restore": ("Firecracker snapshot load (warm, HDD)", "s", "fcrestore"),
        "fc_snapshot_create": ("Snapshot create (512 MB, HDD)", "s", "snap"),
        "reboot_to_kernel": ("Reboot to kernel start (firmware+loader+kernel)", "s", "reboot"),
        "appliance_userspace": ("Kernel start to agent ready", "s", "userspace"),
    }
    body = []
    for k, (label, _, _) in ((k, v) for k, v in names.items()):
        p, m = plc[k], meas[k]
        pv, mv = p.quantile(0.5), m.quantile(0.5)
        body.append(rows(label, f"{pv:.4g}", esc(p.tag), f"{mv:.4g}", f"{mv / pv:.1f}$\\times$"))
    g.files["tab_calibration.tex"] = tabular("lrlrr", ["Entry", "Placeholder", "Tag", "Measured", "Ratio"], body)

    def q(k: str) -> float:
        return float(meas[k].quantile(0.5))

    g.mac("CalQuote", f"{q('tpm2_quote'):.2f}")
    g.mac("CalQuotePh", f"{plc['tpm2_quote'].quantile(0.5):.2f}")
    g.mac("CalVerifyMs", f"{1000 * q('verify_s'):.0f}")
    g.mac("CalShaMBps", f"{1 / q('verify_s_per_MB'):.0f}")
    g.mac("CalReboot", f"{q('reboot_to_kernel'):.0f}")
    g.mac("CalRebootPh", f"{plc['reboot_to_kernel'].quantile(0.5):.0f}")
    g.mac("CalUserspace", f"{q('appliance_userspace'):.0f}")
    g.mac("CalFcBootWarmMs", f"{1000 * q('fc_boot'):.0f}")
    g.mac("CalSnapCreate", f"{q('fc_snapshot_create'):.1f}")
    df, _, _ = load_raw(REPO / "calibration" / "raw", HOST)
    tbl = pd.DataFrame(ecs1_measured.rows(df))
    g.files["tab_ecs1_measured.tex"] = tabular(
        "llrrr",
        ["Path", "Configuration", "n", "p50 (s)", "p99 (s)"],
        [rows(esc(r.path), esc(r.config), int(r.n), f"{r.p50:.3f}", f"{r.p99:.3f}") for r in tbl.itertuples() if r.n],
    )
    att = tbl[(tbl.path == "Appliance userspace → attested") & (tbl.n > 0)].iloc[0]
    g.mac("CalAttested", f"{att.p50:.0f}")
    g.mac("CalAttestedN", int(att.n))
    cold = tbl[tbl.config.str.contains("mem_mb=256, tier=hdd, cache=cold") & tbl.path.str.contains("boot")].iloc[0]
    g.mac("CalFcBootColdS", f"{cold.p50:.2f}")
    g.mac("CalCpu", "Intel Core i3-7020U")
    _cost_ladder(g, tbl, meas, float(att.p50), float(cold.p50))


def _cost_ladder(g: Gen, tbl: pd.DataFrame, meas: Any, att_s: float, cold_boot_s: float) -> None:
    """Restore-cost macros and ``cost_ladder.csv`` (time to reach each state; Fig. cost)."""

    def q(k: str) -> float:
        return float(meas[k].quantile(0.5))

    restore = tbl[tbl.path.str.contains("restore") & tbl.config.str.contains("mem_mb=512, tier=hdd")]
    cold_r = restore[restore.config.str.contains("cache=cold")].iloc[0]
    warm_r = restore[restore.config.str.contains("cache=warm")].iloc[0]
    expect(att_s / warm_r.p50 > 1e3, "attested-session establishment is >3 orders above a warm snapshot restore")
    g.mac("CalRestoreColdS", f"{cold_r.p50:.2f}")
    g.mac("CalRestoreWarmMs", f"{1000 * warm_r.p50:.0f}")
    g.files["cost_ladder.csv"] = (
        "\n".join(
            ["state,seconds,source"]
            + [
                f'"{k}",{v:.6g},{src}'
                for k, v, src in (
                    ("Resume warm microVM (L3), model", 0.002, "simulated"),
                    ("Restore snapshot, warm page cache", warm_r.p50, "measured"),
                    ("Boot microVM, warm page cache", q("fc_boot"), "measured"),
                    ("TPM quote", q("tpm2_quote"), "measured"),
                    ("Restore snapshot, cold cache (HDD)", cold_r.p50, "measured"),
                    ("Boot microVM, cold cache (HDD)", cold_boot_s, "measured"),
                    ("Create 512 MB snapshot (HDD)", q("fc_snapshot_create"), "measured"),
                    ("Reboot to kernel", q("reboot_to_kernel"), "measured"),
                    ("Reboot to attested worker", att_s, "measured"),
                )
            ]
        )
        + "\n"
    )


def ecs1_sim(g: Gen) -> None:
    d = pd.read_csv(T / "ECS1-sim.csv")
    d = d[(d.range_at == 0.5) & d.fn.isin(["-", "dynamic-html"])]
    sub = {
        "appliance_tpm": "appliance (TPM)",
        "drtm_hv": "DRTM hypervisor",
        "cvm_snp": "CVM (SEV-SNP)",
        "coco_pool": "CoCo pool",
        "none": "no attestation",
    }
    cols = ["session_establish", "start_L0", "start_L1", "start_L2", "start_L3"]
    body = []
    for s, label in sub.items():
        vals = []
        for c in cols:
            v = d[(d.substrate == s) & (d.what == c)].p50_s
            vals.append(f"{v.iloc[0]:.3g}" if len(v) else "--")
        body.append(rows(label, *vals))
    g.files["tab_ecs1_sim.tex"] = tabular("lrrrrr", ["Substrate", "Session", "L0", "L1", "L2", "L3"], body)

    def p(sub: str, what: str) -> float:
        return float(d[(d.substrate == sub) & (d.what == what)].p50_s.iloc[0])

    g.mac("SimApplSession", f"{p('appliance_tpm', 'session_establish'):.0f}")
    g.mac("SimCvmSession", f"{p('cvm_snp', 'session_establish'):.1f}")
    g.mac("SimCocoSession", f"{p('coco_pool', 'session_establish'):.1f}")
    g.mac("SimCvmZeroStart", f"{p('cvm_snp', 'start_L0'):.1f}")
    expect(
        p("appliance_tpm", "session_establish") > p("cvm_snp", "session_establish"),
        "appliance session is the costliest",
    )


def calibration_sensitivity(g: Gen) -> None:
    e24 = tab("E24")
    body = []
    for b, bn in (("placeholder", "placeholder (C0 design)"), ("measured", "measured (laptop)")):
        for lab, ln in (("voss", "VOSS"), ("simple", "simple baseline")):
            x = e24[(e24.label == lab) & e24.calibration.str.contains(b)]
            body.append(rows(bn, ln, ms(x.p50_sync, 3), ms(x.p99_sync), ms(x.met, 3), ms(x.exposure, 0)))
    g.files["tab_calibsens.tex"] = tabular(
        "llrrrr", ["Bundle", "System", "P50 (s)", "P99 (s)", "Met", "Exposure"], body
    )
    m = e24[e24.calibration.str.contains("measured")]
    pl = e24[e24.calibration.str.contains("placeholder")]
    g.mac("CalSensVossP99Meas", f"{m[m.label == 'voss'].p99_sync.mean():.2f}")
    g.mac("CalSensVossP99Plc", f"{pl[pl.label == 'voss'].p99_sync.mean():.2f}")
    g.mac("CalSensSimpleP99Meas", f"{m[m.label == 'simple'].p99_sync.mean():.1f}")
    g.mac("CalSensSimpleP99Plc", f"{pl[pl.label == 'simple'].p99_sync.mean():.1f}")
    acc = tab("E13")
    n0 = acc[acc["scenario.faults"] == "none"]
    g.mac("RecvRows", f"{acc.receipts_s.mean():.0f}")
    g.mac("RecvKBs", f"{acc.db_kb_s.mean():.1f}")
    g.mac("RecvVerifyMs", f"{acc.verify_ms_s.mean():.1f}")
    g.mac("RecvSettleMs", f"{acc.settle_ms.mean():.0f}")
    g.mac("RecvLatTen", f"{acc[acc.label == 's10_b1'].lat_p50.mean():.0f}")
    g.mac("RecvLatSixty", f"{acc[acc.label == 's60_b1'].lat_p50.mean():.0f}")
    g.mac("RecvLatThreeHundred", f"{acc[acc.label == 's300_b1'].lat_p50.mean():.0f}")
    g.mac("RecvUnexplained", f"{int(acc.unexplained.sum())}")
    g.mac("RecvMissingMax", f"{acc.missing.max():.0f}")
    g.mac("RecvRuns", len(acc))
    _ = n0
    e12 = tab("E12")
    g.mac("RepGini", f"{e12.gini.mean():.2f}")
    g.mac("RepTopTen", f"{100 * e12.top10.mean():.0f}")
    g.mac("RepStarved", f"{100 * e12.starved.mean():.0f}")
    r = g.hyp[(g.hyp.id == "E12") & (g.hyp.metric == "p99_sync")].iloc[0]
    g.mac("RepP99Pct", f"{abs(100 * r.delta / r.base):.1f}")
    expect(
        r.verdict in ("weak", "inconclusive") and abs(r.delta / r.base) < 0.05,
        "E12 reputation: at most a small P99 effect",
    )
