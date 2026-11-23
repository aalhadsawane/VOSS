"""Calibrated fleet (plan V9.4, D-107): per-class run times, TPM entries shared from the reference, survey mix."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from experiments.analysis import fleet_mix
from voss.core.config import RunConfig, load_config
from voss.core.paths import CONFIGS, load_data_yaml
from voss.core.rng import RngFactory
from voss.world.execution import ExecParams, true_runtime
from voss.world.geo import load_metros
from voss.world.machines import TPM_KEYS, class_catalog, load_fleet, load_hw, survey_mix
from voss.world.workers import cap_slots_by_memory, generate_workers
from voss.world.workload import Catalog, FunctionSpec, TenantSpec

REF = "node02-i7-12700-64g-nvme_nvme"
OLD = "node04-i7-4790s-8g-hdd_hdd"
CAL = f"configs/calibration/measured/{REF}"


def _catalog() -> Catalog:
    rows = {f["name"]: f for f in load_data_yaml("functions.yaml")["functions"]}
    fns = (FunctionSpec.model_validate(rows["compression"]), FunctionSpec.model_validate(rows["thumbnailer"]))
    mapped = fns[0].model_copy(update={"name": "tr0001"})
    tenants = tuple(TenantSpec.model_validate(t) for t in load_data_yaml("tenants.yaml")["tenants"])
    return Catalog((*fns, mapped), tenants, profiles={"tr0001": ("compression", 8000.0)})


def _survey(root: Path) -> None:
    (root / "s").mkdir()
    rows = [(20, 64.0, "intel", 3), (8, 8.0, "amd", 5), (2, 1.0, "arm", 2), (12, 16.0, "intel", 2)]
    pd.DataFrame(rows, columns=["ncpus", "mem_gib", "vendor", "count"]).to_parquet(root / "s" / "hosts.parquet")


@pytest.fixture
def fleet(tmp_path: Path):  # type: ignore[no-untyped-def]
    _survey(tmp_path)
    raw = {"bundles": [REF, OLD], "survey": "s", "trace_root": str(tmp_path)}
    return load_fleet(raw, CAL, _catalog())


def _measured(bundle: str) -> dict[str, dict]:  # type: ignore[type-arg]
    return load_data_yaml(f"calibration/measured/{bundle}/functions.yaml")["functions"]


def test_each_class_runs_its_own_bundle_times(fleet) -> None:  # type: ignore[no-untyped-def]
    p = ExecParams()
    for b in (REF, OLD):
        fns, meas = {f.name: f for f in fleet.catalogs[b]}, _measured(b)
        assert fleet.hw[b].speed == 1.0  # no per-class speed scalar: differences are per function
        for name in ("compression", "thumbnailer"):
            assert fns[name].work_ref_s == pytest.approx(meas[name]["work_ref_s"])
            assert fns[name].init_s == pytest.approx(meas[name]["init_s"])
        f = fns["tr0001"]
        want = meas["compression"]["exec_by_size"][8000]["median_s"]
        assert f.work_ref_s == pytest.approx(want)
        run = true_runtime(f, int(f.in_kb * 1024), fleet.hw[b].speed, 1, 4, 1.0, 1.0, p)
        assert run == pytest.approx(want)
    ratios = [
        {f.name: f for f in fleet.catalogs[OLD]}[n].work_ref_s / {f.name: f for f in fleet.catalogs[REF]}[n].work_ref_s
        for n in ("compression", "thumbnailer")
    ]
    assert abs(ratios[0] - ratios[1]) > 0.1  # speed differences between classes are per function


def test_hardware_from_spec_and_bundle() -> None:
    old = load_hw(OLD)
    assert (old.cores, old.tpm, old.hdd_gb) == (8, "none", 0.0)
    disk = load_data_yaml(f"calibration/measured/{OLD}/hardware.yaml")["classes"]["C0"]
    assert old.ssd_read_MBps == disk["ssd_read_MBps"]
    assert load_hw(REF).cores == 20


def test_tpm_entries_of_tpm_less_class_are_shared_from_reference(fleet) -> None:  # type: ignore[no-untyped-def]
    old, ref = fleet.classes[OLD], fleet.classes[REF]
    for k in TPM_KEYS:
        assert old.provenance[k] == f"shared:{REF}"
        assert old.dists[k] == ref.dists[k]
        assert ref.provenance[k] == "measured"
    assert fleet.shared() == {OLD: sorted(TPM_KEYS)}
    assert old.provenance["fc_boot"] == "measured"
    assert old.dists["fc_boot"] != ref.dists["fc_boot"]


def test_mix_weights_sum_to_one(fleet) -> None:  # type: ignore[no-untyped-def]
    w = fleet.mix.weights
    assert sum(w.values()) == pytest.approx(1.0)
    # (20, 64) -> REF; (8, 8), (2, 1) -> OLD; (12, 16): log2 distances 1.16 to OLD, 2.13 to REF -> OLD
    assert w[REF] == pytest.approx(3 / 12)


def test_unrepresented_and_non_x86_shares() -> None:
    hw = {REF: load_hw(REF), OLD: load_hw(OLD)}
    t = pd.DataFrame(
        [(20, 64.0, "intel", 3), (8, 8.0, "amd", 5), (2, 1.0, "arm", 2), (12, 16.0, "intel", 2)],
        columns=["ncpus", "mem_gib", "vendor", "count"],
    )
    mix = survey_mix(t, hw, radius=1.0)
    # (2, 1): 2 and 3 doublings from OLD; (12, 16): 1.16 from OLD; both beyond one power-of-two step
    assert mix.unrepresented == pytest.approx(4 / 12)
    assert mix.non_x86 == pytest.approx(2 / 12)
    assert survey_mix(t, hw, radius=10.0).unrepresented == 0.0
    assert np.isclose(mix.buckets.distance.iloc[0], 0.0)


def test_identical_machines_share_a_bucket_equally() -> None:
    hdd = "node02-i7-12700-64g-nvme_hdd"
    hw = {REF: load_hw(REF), hdd: load_hw(hdd)}
    mix = survey_mix(pd.DataFrame([(20, 64.0, "intel", 4)], columns=["ncpus", "mem_gib", "vendor", "count"]), hw, 1.0)
    assert mix.weights == {hdd: 0.5, REF: 0.5}


def test_the_fleet_is_always_in_the_config_hash() -> None:
    """Checklist 1.3: the fleet is required, so it is always part of the config hash; another fleet is another run."""
    base = RunConfig.model_validate({"scenario": {"machines": {"bundles": [REF], "survey": "s"}}})
    other = RunConfig.model_validate({"scenario": {"machines": {"bundles": [OLD], "survey": "s"}}})
    assert base.config_hash() != other.config_hash()
    tree = base.model_dump(mode="json", exclude={"out_dir", "label"})
    assert tree["scenario"]["machines"] == {"bundles": [REF], "survey": "s"}


def test_reference_must_be_a_fleet_bundle(tmp_path: Path) -> None:
    _survey(tmp_path)
    with pytest.raises(ValueError, match="reference"):
        load_fleet({"bundles": [OLD], "survey": "s", "trace_root": str(tmp_path)}, CAL, _catalog())


def test_committed_mix_names_the_published_survey() -> None:
    """``configs/machines_mix.yaml`` was computed from the survey file the trace's provenance publishes."""
    mix = fleet_mix.load_mix()
    prov = yaml.safe_load((CONFIGS / "traces" / mix["survey"] / "provenance.yaml").read_text())
    assert mix["input_sha256"] == prov["outputs"]["hosts.parquet"]
    assert sum(c["weight"] for c in mix["classes"].values()) == pytest.approx(1.0, abs=1e-5)


def test_committed_mix_agrees_with_the_survey() -> None:
    mp = fleet_mix.MachinesParams.model_validate(fleet_mix.load_config(fleet_mix.FLEET).scenario.machines)
    if not fleet_mix.survey_path(mp).exists():
        pytest.skip("survey not fetched (python -m tools.traces.fetch)")
    assert fleet_mix.compute() == fleet_mix.load_mix()


def test_no_fleet_class_exceeds_its_donated_memory_at_the_default_envelope() -> None:
    """D-108: the slot cap keeps ``slots x largest function memory`` within the donated memory of every class."""
    sc = RunConfig.model_validate({"scenario": {"machines": {"bundles": [REF], "survey": "s"}}}).scenario.model_copy(
        update={"workers": 60}
    )
    bundles = load_config(fleet_mix.FLEET).scenario.machines["bundles"]
    hw = {b: load_hw(b) for b in bundles}
    wt = generate_workers(sc, load_metros("geo/metros.csv"), hw, RngFactory(1), dict.fromkeys(bundles, 1.0))
    big = max(f["mem_mb"] for f in load_data_yaml("functions.yaml")["functions"])
    assert np.any(wt.slots * big > wt.mem_mb)  # node04 at cpu_frac 0.75: 6 slots x 1,024 MB > 4,424 MB
    capped = cap_slots_by_memory(wt, big)
    assert np.all(capped.slots * big <= capped.mem_mb)
    assert np.all(capped.slots >= 1)
    assert len(set(wt.hw[capped.slots < wt.slots].tolist())) == 1  # only the small-memory class is capped


def test_a_synthetic_function_copy_uses_the_base_profile(fleet) -> None:  # type: ignore[no-untyped-def]
    """The decision-timing bench appends -0, -1, ... to raise the function count; each copy uses the base profile."""
    cat = _catalog()
    base = next(f for f in cat.functions if f.name == "thumbnailer")
    syn = base.model_copy(update={"name": "thumbnailer-0"})
    cat = Catalog((*cat.functions, syn), cat.tenants, profiles=cat.profiles)
    out = {f.name: f for f in class_catalog(cat, fleet.classes[REF])}
    assert out["thumbnailer-0"].base == "thumbnailer"
    assert out["thumbnailer-0"].work_ref_s == out["thumbnailer"].work_ref_s
    mapped = base.model_copy(update={"name": "tr0099"})
    cat = Catalog((*cat.functions, mapped), cat.tenants, profiles={**cat.profiles, "tr0099": ("thumbnailer-0", None)})
    out = {f.name: f for f in class_catalog(cat, fleet.classes[REF])}
    assert out["tr0099"].base == "thumbnailer"
    assert out["tr0099"].work_ref_s == out["thumbnailer"].work_ref_s
