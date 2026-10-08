# Pilot results

Pilots are small runs that exercise each experiment end to end before the paper runs (P10). Every table here is
regenerated from run logs by the scripts named below; numbers come from the **placeholder calibration bundle**
(literature/assumed values) until P9 lands measured data.

| Pilot | Regenerate | Notes |
|---|---|---|
| [E03](E03.md) predictors × scalarizers | `python -m experiments.runner configs/experiments/E03.yaml --jobs 3` then `python -m experiments.analysis.e03 runs/E03` | 150 workers, 10 min, 8 inv/s, 5 seeds. Predictors are indistinguishable here because the simulated truth equals the profile prior and workers are only speed-scaled; BLR's worker offsets matter once throttling adversaries (P6) and measured SeBS profiles (P9) differ from the prior. Conformal calibration keeps 90% intervals at 0.88-0.89 coverage. Scalarizers differ by < CI width in benign regimes. |
| [E-CS1 (simulated)](ECS1-sim.md) | `python -m experiments.ecs1 --n 200` | Lifecycle engine per substrate on an isolated C0 host. The appliance pays a reboot per donation session (~19 s), CVM classes pay 1-8 s per wCVM; warm (L3) starts are ms everywhere. Measured side arrives with P9. |
