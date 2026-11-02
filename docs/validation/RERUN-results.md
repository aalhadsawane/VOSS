# Rerun results: E10b, E17b, E24b (E20ab pending)

Corrected request placement (`voss.cost.wait_model=per_worker`, `voss.worker.sync_priority=true`; C-46, D-77) on the
grids, systems and seeds (1-10) of E10, E17, E24 and E20a. Raw logs: release `paper-runs-41422666939`. Per-run tables:
`paper/tables/E10b_runs.csv`, `E17b_runs.csv`, `E24b_runs.csv` (`python -m experiments.analysis.rerun`, 60 s warm-up
like the original specs, same per-run function as `experiments.analysis.round4.per_run`). Macros and tables:
`experiments/paper_tex/rerun.py` -> `manuscript/generated/` (prefix `Rerun`, old macros untouched). All paired by seed;
a ratio is the mean of per-seed ratios with a 95% bootstrap CI (10 pairs). "Old" = frozen E10/E17/E24 CSVs.

Headline: the corrected placement leaves every qualitative conclusion unchanged, and every number moves by a few
percent. The baselines were not hobbled enough by the old slot-wait estimate for the correction to close the gap.

## E10b (RQ16, H11): homogeneous benign null

| hardware | system | P99 (s) new | P99 old | met new | exposure new | exposure old |
|---|---|---|---|---|---|---|
| homogeneous | simple | 3.478 | 3.898 | 0.965 | 62.5 | 63.5 |
| homogeneous | VOSS | 2.204 | 2.381 | 0.978 | 120.9 | 122.0 |
| mixed | simple | 2.623 | 2.656 | 0.970 | 53.8 | 53.8 |
| mixed | VOSS | 1.308 | 1.314 | 0.988 | 94.3 | 94.7 |

Paired, simple / VOSS (P99) and VOSS / simple (exposure):

| hardware | P99 ratio new [CI] | P99 ratio old [CI] | exposure ratio new [CI] | exposure ratio old |
|---|---|---|---|---|
| homogeneous | 1.69 [1.34, 2.06] | 1.72 [1.32, 2.17] | 1.93 [1.84, 2.03] | 1.93 |
| mixed | 2.03 [1.80, 2.30] | 2.04 [1.82, 2.28] | 1.77 [1.65, 1.88] | 1.78 |

H11 (macro `HElevenPct`, relative difference of means): old 64% higher P99 for the simple baseline; new
(3.478 - 2.204) / 2.204 = 58%. By mean per-seed ratio (`RerunSimplePctHom`) 69% (old 72%). The simple baseline does not
match VOSS even on homogeneous hardware, as before; VOSS still holds about 1.9x the exposure.

## E17b (RQ15): VOSS vs reference clouds across load

| rate | system | P50 (s) | P99 (s) new | P99 old | met | USD per M new | USD per M old |
|---|---|---|---|---|---|---|---|
| 10 | VOSS | 0.424 | 1.312 | 1.325 | 0.986 | 19.6 | 19.6 |
| 10 | Lambda-like | 0.292 | 1.206 | 1.206 | 0.999 | 12.1 | 12.1 |
| 10 | Azure-like | 0.292 | 1.330 | 1.330 | 0.997 | 12.0 | 12.0 |
| 20 | VOSS | 0.424 | 1.275 | 1.267 | 0.988 | 9.8 | 9.8 |
| 20 | Lambda-like | 0.292 | 1.110 | 1.110 | 0.999 | 12.1 | 12.1 |
| 20 | Azure-like | 0.292 | 1.166 | 1.166 | 0.998 | 11.9 | 11.9 |
| 40 | VOSS | 0.437 | 1.474 | 1.505 | 0.985 | 4.9 | 4.9 |
| 40 | Lambda-like | 0.292 | 1.102 | 1.102 | 0.999 | 12.1 | 12.1 |
| 40 | Azure-like | 0.292 | 1.144 | 1.147 | 0.998 | 11.9 | 11.9 |

The reference clouds are not VOSS runs, so they are unchanged (small old/new differences are rerun noise only).
Paired difference VOSS minus reference, P99 (s) [95% CI]:

| rate | vs Lambda-like | vs Azure-like |
|---|---|---|
| 10 | +0.106 [+0.046, +0.170] | -0.018 [-0.115, +0.080] |
| 20 | +0.165 [+0.124, +0.201] | +0.109 [+0.067, +0.150] |
| 40 | +0.373 [+0.236, +0.522] | +0.331 [+0.184, +0.489] |

P50 difference is +0.13 s (10, 20 inv/s) and +0.14 s (40 inv/s) against both references, CIs excluding zero. Cost
falls with load and crosses below the references between 10 and 20 inv/s. Same qualitative picture as the old E17: VOSS
P99 is 10-35% above the Lambda-like cloud (old `CommP99Pct` is on the 20 inv/s cell), and the Azure-like tie at 10
inv/s holds.

## E24b: calibration sensitivity (alpha = 0.1 mixed adversary)

| bundle | system | P50 (s) | P99 new | P99 old | met | exposure |
|---|---|---|---|---|---|---|
| placeholder | VOSS | 0.428 | 1.356 | 1.323 | 0.985 | 46.8 |
| placeholder | simple | 0.505 | 3.668 | 3.886 | 0.966 | 53.0 |
| measured | VOSS | 0.241 | 0.998 | 1.166 | 0.980 | 36.1 |
| measured | simple | 0.266 | 4.239 | 4.585 | 0.956 | 52.6 |

Paired simple / VOSS P99: placeholder 2.76 [2.37, 3.20] (old 3.01 [2.49, 3.58]); measured 4.30 [3.90, 4.73] (old 4.17
[3.55, 4.70]). The conclusion does not flip between bundles. Differences from old are within seed noise, except that
the measured-bundle VOSS P99 is 14% lower (1.17 -> 1.00 s).

## E20ab

Not available at the time of writing: the release has no `runs-E20ab.tar.zst`. Everything is prepared: after
`python -m experiments.analysis.rerun E20ab <runs root>` writes `paper/tables/E20ab_runs.csv`, the generator emits
`RerunViabCells`, `RerunViabMet{Voss,Simple}`, `RerunViabP{Two,Three,Five}{Voss,Simple,VossOnly,BaseBetter}` and
`tab_rerun_viability.tex` (viable = success lower bound >= 0.99 and deadline-met lower bound >= 0.95, or mean sync
P99 <= 2/3/5 s, as `experiments.analysis.viability`). Old E20a for comparison: `ViabAPThreeVoss`, `ViabACells`,
`ViabAMetOnly` in `manuscript/generated/macros.tex`.
