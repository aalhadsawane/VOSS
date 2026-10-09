# Pilot results

Pilots are small runs that exercise each experiment end to end before the paper runs (P10). Every table here is
regenerated from run logs by the scripts named below; numbers come from the **placeholder calibration bundle**
(literature/assumed values) until P9 lands measured data.

| Pilot | Regenerate | Notes |
|---|---|---|
| [E03](E03.md) predictors × scalarizers | `python -m experiments.runner configs/experiments/E03.yaml --jobs 3` then `python -m experiments.analysis.e03 runs/E03` | 150 workers, 10 min, 8 inv/s, 5 seeds. Predictors are indistinguishable here because the simulated truth equals the profile prior and workers are only speed-scaled; BLR's worker offsets matter once throttling adversaries (P6) and measured SeBS profiles (P9) differ from the prior. Conformal calibration keeps 90% intervals at 0.88-0.89 coverage. Scalarizers differ by < CI width in benign regimes. |
| [E04](E04.md) planners | `python -m experiments.runner configs/experiments/E04.yaml --jobs 3` then `python -m experiments.analysis.p4 E04 runs/E04` | 200 workers, 15 min, 10 inv/s, two churn regimes, 7 paired systems × 5 seeds. MILP has the lowest sync P99 (1.48 s vs 1.75 s without planning, churn_med) and greedy sits between (1.57 s); keep-alive TTL alone gets 1.66 s at the lowest exposure (12.2). The MILP pays for it with ~30% more idle warm memory than greedy (100 GB vs 77 GB cluster-wide), the highest exposure (19.4 vs 17.2) and ~5 s per solve. Dropping robustness cuts exposure to 14.2 for +4% P99; dropping the exposure term changes nothing at weight 1 (E23 shows why). P2P volumes predate D-37 (slow peers were still used). |
| [E09](E09.md) cache policy | `… E09.yaml`, `… p4 E09 runs/E09` | 200 workers, 15 min, churn_high, tight SSD, greedy planner. GDSF vs LRU, P2P and the HDD tier are within CI of each other here: 15 min is too short for eviction pressure to build. Needs longer horizons and version churn (P8). |
| [E23](E23.md) exposure × robustness | `… E23.yaml`, `… p4 E23 runs/E23` | MILP, exposure weight × f. The robustness level is the main lever: exposure rises 13.6 → 20 → 24 for f = 0 → 0.1 → 0.2 while sync P99 falls ~6-10%, and solve time grows to ~12 s at f = 0.2. The exposure weight matters only at f = 0 (15.1 → 13.6); robust coverage constraints dominate otherwise. |
| [E-CS1 (simulated)](ECS1-sim.md) | `python -m experiments.ecs1 --n 200` | Lifecycle engine per substrate on an isolated C0 host. The appliance pays a reboot per donation session (~19 s), CVM classes pay 1-8 s per wCVM; warm (L3) starts are ms everywhere. Measured side arrives with P9. |

**Caveat (P3/P4 pilots).** E03, E04, E09, E23 and E02 build on `configs/smoke.yaml`, which pins the sync placer to
`least_loaded` (a P2 setting). Scalarizers therefore only affect async/filler placement and admission in E03, and
planners act through warm/trust state only. P5+ pilots use `configs/pilot.yaml` with VOSS's default placers; the
full experiments (P8) rerun these on it.
