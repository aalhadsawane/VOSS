# E04 wait-model check (WP6, D-77)

Cells: `configs/experiments/E04.yaml` systems `keepalive_ttl` and `plan_greedy`, `scenario.regime=churn_high`, seeds 2 and 8, built with
`experiments.runner.points()` plus overrides: (a) none, (b) `voss.cost.wait_model=per_worker`, (c) (b) + `voss.worker.sync_priority=true`.
Metrics after a 60 s warm-up: sync = `slo_class == 0`, `outcome == ok`. "wait" is the logged slot-queue time of sync requests; `met` = SLO met share.
Run on a machine whose NumPy canary differs from the published one (D-70 warning), yet the (a) cells reproduce the published P99 exactly.

| system | seed | variant | P99 sync (s) | mean wait sync (s) | P99 of wait (s) | success | met | warm RAM (GB) | exposure |
|---|---|---|---|---|---|---|---|---|---|
| keepalive_ttl | 2 | a default | 5.27 | 0.165 | 4.43 | 0.9999 | 0.944 | 72.6 | 9.45 |
| keepalive_ttl | 2 | b per_worker | 3.07 | 0.055 | 2.21 | 0.9994 | 0.961 | 80.9 | 9.27 |
| keepalive_ttl | 2 | c + sync priority | 1.71 | 0.015 | 0.44 | 0.9979 | 0.977 | 76.7 | 9.50 |
| keepalive_ttl | 8 | a default | 4.89 | 0.167 | 3.57 | 1.0000 | 0.922 | 96.0 | 9.16 |
| keepalive_ttl | 8 | b per_worker | 6.10 | 0.182 | 4.83 | 1.0000 | 0.931 | 89.8 | 10.50 |
| keepalive_ttl | 8 | c + sync priority | 2.94 | 0.114 | 2.34 | 1.0000 | 0.933 | 89.5 | 10.06 |
| plan_greedy | 2 | a default | 1.50 | 0.004 | 0.00 | 0.9993 | 0.980 | 124.2 | 18.50 |
| plan_greedy | 2 | b per_worker | 1.41 | 0.000 | 0.00 | 0.9999 | 0.984 | 125.5 | 18.85 |
| plan_greedy | 2 | c + sync priority | 1.34 | 0.001 | 0.00 | 0.9993 | 0.988 | 125.1 | 18.87 |
| plan_greedy | 8 | a default | 1.49 | 0.007 | 0.00 | 1.0000 | 0.967 | 116.0 | 18.47 |
| plan_greedy | 8 | b per_worker | 1.44 | 0.003 | 0.00 | 1.0000 | 0.967 | 109.7 | 18.05 |
| plan_greedy | 8 | c + sync priority | 1.38 | 0.005 | 0.11 | 1.0000 | 0.966 | 118.8 | 19.02 |

Reading: two seeds per system, one run each; differences of a few tenths of a second are within what a changed trajectory produces. The per-worker estimate alone is
not enough (seed 8 gets worse; not investigated). Sync priority removes most of the keep-alive queueing. Keep-alive stays above greedy
(1.7 / 2.9 s vs 1.3 / 1.4 s) and holds about half the warm RAM and half the exposure, consistent with the key-holder capacity explanation of `E04-tail.md`.
Script: not committed (scratchpad `wp6_run.py`).
