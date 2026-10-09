"""Raw calibration logs → measured bundle (doc 10 §1): ``python -m tools.calibrate.ingest --raw calibration/raw``.

Writes ``configs/calibration/measured/<fingerprint>/``:
- ``distributions.yaml``: bundle entries per ``mapping.yaml`` as empirical quantiles (tag ``measured``); entries
  without data keep the placeholder's value and tag, so a partial calibration is still a complete bundle;
- ``fits.yaml``: lognormal fit, sample size and KS distance of every measured entry;
- ``hardware.yaml``: measured fields of hardware class C0 (disk speeds);
- ``functions.yaml``: per-function ``init_s``, ``work_ref_s``, ``size_exp`` and interference from ``sebs``;
- ``meta.yaml``: host metadata and SHA-256 of every raw file used.
Runs locally (needs the project environment); nothing here touches the calibration node.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from voss.core.dist import Const, Empirical

HERE = Path(__file__).resolve().parent
QUANTILES = 21


def load_raw(root: Path, host: str | None = None) -> tuple[pd.DataFrame, dict[str, Any], dict[str, str]]:
    """Every ``records.jsonl`` of successful runs, with run metadata (phase, run id) as columns."""
    rows, meta, digests = [], {}, {}
    for rec in sorted(root.glob("*/*/*/records.jsonl")):
        run = rec.parent
        info = json.loads((run / "meta.json").read_text())
        if (host and run.parents[1].name != host) or info.get("dry_run") or str(info.get("status")) == "error":
            continue
        meta = info
        digests[str(rec.relative_to(root))] = hashlib.sha256(rec.read_bytes()).hexdigest()
        for line in rec.read_text().splitlines():
            r = json.loads(line)
            rows.append(r | {"phase": info.get("phase"), "run_id": info["run_id"], "host": run.parents[1].name})
    cols = ["suite", "probe", "rep", "value", "unit", "config", "phase", "run_id", "host"]
    return pd.DataFrame(rows, columns=cols), meta, digests


def select(df: pd.DataFrame, spec: dict[str, Any], **extra: Any) -> pd.DataFrame:
    """Rows of ``spec['suite']``/``spec['probe']`` whose config matches ``where`` (and ``extra`` run columns)."""
    d = df[(df.suite == spec["suite"]) & (df.probe == spec["probe"])]
    for k, v in sorted((spec.get("where") or {}).items()):
        d = d.loc[d.config.map(lambda c, k=k, v=v: c.get(k) == v).astype(bool)]
    for k, v in sorted(extra.items()):
        d = d.loc[(d[k] == v).astype(bool)]
    return d


def empirical(x: np.ndarray, source: str) -> dict[str, Any]:
    q = np.quantile(x, np.linspace(0.0, 1.0, QUANTILES))
    return Empirical(quantiles=tuple(float(v) for v in q), tag="measured", source=source).model_dump()


def lognormal_fit(x: np.ndarray) -> dict[str, float]:
    """Median and sigma of log values, plus the KS distance between the sample and the fit."""
    x = np.sort(x[x > 0])
    if len(x) < 2:
        return {"n": float(len(x))}
    lx = np.log(x)
    mu, sigma = float(lx.mean()), float(lx.std(ddof=1))
    ecdf = np.arange(1, len(x) + 1) / len(x)
    z = (lx - mu) / max(sigma, 1e-12)
    fitted = 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))
    return {"median": math.exp(mu), "sigma": sigma, "n": float(len(x)), "ks": float(np.abs(ecdf - fitted).max())}


def _source(spec: dict[str, Any], meta: dict[str, Any]) -> str:
    where = ", ".join(f"{k}={v}" for k, v in sorted((spec.get("where") or {}).items()))
    head = f"{spec['suite']}/{spec['probe']}" + (f" [{where}]" if where else "")
    return f"{head}; harness {meta.get('harness_version', '?')}" + (f"; {spec['note']}" if spec.get("note") else "")


def distributions(
    df: pd.DataFrame, mapping: dict[str, Any], meta: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    out, fits = {}, {}
    for key, spec in sorted(mapping.get("distributions", {}).items()):
        x = select(df, spec).value.to_numpy(dtype=float)
        if len(x) == 0:
            continue
        if spec.get("transform") == "inverse":  # e.g. MB/s → s per MB
            x = 1.0 / x[x > 0]
        if spec.get("as") == "const":
            out[key] = Const(value=float(np.median(x)), tag="measured", source=_source(spec, meta)).model_dump()
        else:
            out[key] = empirical(x, _source(spec, meta))
        fits[key] = lognormal_fit(x)
    for key, spec in sorted(mapping.get("ratios", {}).items()):
        r = ratio(df, spec)
        if r is not None:
            out[key] = Const(value=r, tag="measured", source=_source(spec, meta)).model_dump()
    return out, fits


def ratio(df: pd.DataFrame, spec: dict[str, Any]) -> float | None:
    """Median(num)/median(den) per group, geometric mean over groups (``None`` without both phases)."""
    num, den = select(df, spec, **spec["num"]), select(df, spec, **spec["den"])
    if not len(num) or not len(den):
        return None
    group = spec.get("group") or []
    key = (lambda d: d.config.map(lambda c: tuple(c.get(g) for g in group))) if group else (lambda d: 0)
    a = num.assign(g=key(num)).groupby("g").value.median()
    b = den.assign(g=key(den)).groupby("g").value.median()
    both = a.index.intersection(b.index)
    if not len(both):
        return None
    return float(np.exp(np.mean(np.log(a[both].to_numpy() / b[both].to_numpy()))))


def hardware(df: pd.DataFrame, mapping: dict[str, Any]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for cls, fields in sorted(mapping.get("hardware", {}).items()):
        vals = {f: float(select(df, s).value.median()) for f, s in sorted(fields.items()) if len(select(df, s))}
        if vals:
            out[cls] = vals
    return out


def functions(df: pd.DataFrame, ref_kb: dict[str, float]) -> dict[str, dict[str, Any]]:
    """Per-function profile from ``sebs`` (concurrency 1): init, execution at the catalog's reference input size
    (log-log interpolation), size exponent (log-log slope), and slowdown at each concurrency."""
    sebs = df[df.suite == "sebs"]
    if not len(sebs):
        return {}
    cfg = pd.DataFrame(list(sebs.config)).set_index(sebs.index)
    sebs = sebs.join(cfg)
    out: dict[str, dict[str, Any]] = {}
    for fn, g in sebs.groupby("fn"):
        alone = g[(g.probe == "sebs_exec") & (g.concurrency == 1)]
        if not len(alone):
            continue
        med = alone.groupby("size_kb").value.median()
        sizes, times = np.log(med.index.to_numpy(dtype=float)), np.log(med.to_numpy(dtype=float))
        slope = float(np.polyfit(sizes, times, 1)[0]) if len(med) > 1 else 0.0
        ref = math.log(ref_kb.get(str(fn), float(med.index[0])))
        work = float(math.exp(np.interp(ref, sizes, times) + (slope * (ref - sizes[-1]) if ref > sizes[-1] else 0.0)))
        init = g[(g.probe == "sebs_init") & (g.concurrency == 1)].value
        slow = {}
        for n, h in g[g.probe == "sebs_exec"].groupby("concurrency"):
            m = h.groupby("size_kb").value.median()
            slow[int(n)] = float(np.exp(np.mean(np.log(m / med.reindex(m.index)))))
        out[str(fn)] = {
            "init_s": float(init.median()) if len(init) else None,
            "work_ref_s": work,
            "size_exp": slope,
            "interference": slow,
            "n": len(alone),
            "tag": "measured",
        }
    return out


def build(raw: Path, host: str | None, placeholder: Path) -> tuple[str, dict[str, Any]]:
    df, meta, digests = load_raw(raw, host)
    if df.empty:
        raise SystemExit(f"no usable records under {raw}")
    fp = host or str(df.host.iloc[0])
    mapping = yaml.safe_load((HERE / "mapping.yaml").read_text())
    measured, fits = distributions(df, mapping, meta)
    base = yaml.safe_load((placeholder / "distributions.yaml").read_text())
    merged = dict(base["distributions"]) | measured
    catalog = yaml.safe_load((HERE.parents[1] / "configs" / "functions.yaml").read_text())
    ref_kb = {f["name"]: float(f["in_kb"]) for f in catalog["functions"]}
    missing = sorted(set(base["distributions"]) - set(measured))
    files = {
        "distributions.yaml": {
            "provenance": {"default": "measured", "note": "entries tagged literature/assumed were not measured"},
            "host": fp,
            "harness_version": meta.get("harness_version"),
            "measured": True,
            "distributions": merged,
        },
        "fits.yaml": fits,
        "hardware.yaml": {"classes": hardware(df, mapping)},
        "functions.yaml": {"functions": functions(df, ref_kb)},
        "meta.yaml": {
            "host": meta,
            "raw_files": digests,
            "missing": missing,
        },
    }
    return fp, files


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--raw", type=Path, required=True, help="directory with <fingerprint>/<suite>/<run>/ trees")
    p.add_argument("--host", default=None, help="fingerprint to ingest (default: the first found)")
    p.add_argument("--out", type=Path, default=Path("configs/calibration/measured"))
    p.add_argument("--placeholder", type=Path, default=Path("configs/calibration/placeholder/c0"))
    a = p.parse_args(argv)
    fp, files = build(a.raw, a.host, a.placeholder)
    out = a.out / fp
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / name).write_text(yaml.safe_dump(data, sort_keys=True, width=120))
    print(out)


if __name__ == "__main__":
    main()
