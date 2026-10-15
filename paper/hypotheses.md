# Hypothesis scorecard

Paired by seed on the same scenarios; Δ = test − baseline with its 95% bootstrap CI; relative to the baseline mean. Verdict rules: `experiments/analysis/scorecard.py`.

| H | Claim | Experiment | Cell | Comparison | Metric | n | Δ [95% CI] | Δ rel | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| H1 | MILP planner cuts sync P99 vs no planning | E04 | regime=churn_med | plan_milp vs plan_none | p99_sync | 10 | -1.52 [-2.94, -0.38] | -54.6% | supported |
| H1 | MILP planner cuts sync P99 vs no planning | E04 | regime=churn_high | plan_milp vs plan_none | p99_sync | 10 | -2.1 [-3.37, -0.91] | -60.2% | supported |
| H1 | ... and vs keep-alive TTL | E04 | regime=churn_med | plan_milp vs keepalive_ttl | p99_sync | 10 | -0.515 [-1.02, -0.147] | -28.9% | supported |
| H1 | ... and vs keep-alive TTL | E04 | regime=churn_high | plan_milp vs keepalive_ttl | p99_sync | 10 | -1.91 [-3.86, -0.359] | -57.9% | supported |
| H1 | donor memory held warm: MILP vs keep-alive TTL (cost side) | E04 | regime=churn_med | plan_milp vs keepalive_ttl | warm_mb | 10 | +7.07e+04 [+5.71e+04, +8.14e+04] | +112.3% | info |
| H2 | f-robust plans keep success where non-robust collapse (α=0.2 mixed) | E08 | adversary={alpha: 0.2, regime: adversary_mixed} | f0 vs voss | success | 10 | -0.00114 [-0.00314, +0.000384] | -0.1% | inconclusive |
| H3 | Pareto front has a knee; moderate exposure loses little latency | E23 |  | knee vs best-latency front point | p99_sync | 10 | +0.00578 | +0.5% | supported |
| H4 | progress detection beats heartbeat-only on success under α=0.2 | E08 | adversary={alpha: 0.2, regime: adversary_mixed} | heartbeat_only vs voss | success | 10 | -0.0316 [-0.0428, -0.0211] | -3.2% | supported |
| H5 | appliance warm start ≈ Firecracker without attestation (L3) | E-CS1 (sim) |  | ratio - 1 (mid-range) | p50 s | 1 | -0.0204 | -2.0% | supported |
| H5 | appliance snapshot start ≈ Firecracker without attestation (L2) | E-CS1 (sim) |  | ratio - 1 (mid-range) | p50 s | 1 | +0.0252 | +2.5% | supported |
| H5 | CVM classes are 10-100x slower than the appliance to establish trust | E-CS1 (sim) |  | ratio - 1 (mid-range) | p50 s | 1 | -0.927 | -92.7% | refuted |
| H6 | GDSF + P2P + HDD tier beat LRU without P2P/HDD (sync P99) | E09 |  | lru_no_p2p_no_hdd vs gdsf_p2p_hdd | p99_sync | 10 | +0.0427 [-0.0376, +0.169] | +3.1% | inconclusive |
| H6 | ... GDSF vs LRU alone | E09 |  | lru vs gdsf_p2p_hdd | p99_sync | 10 | +0.0252 [-0.00165, +0.0581] | +1.8% | inconclusive |
| H7 | geo clusters reduce sync P99 vs one global scheduler (EU) | E05 | regions=[eu] | dynamic vs none_global | p99_sync | 10 | +0.176 [+0.115, +0.231] | +16.5% | refuted |
| H7 | ... EU+NA | E05 | regions=[eu, na] | dynamic vs none_global | p99_sync | 10 | +0.189 [+0.0588, +0.377] | +16.6% | refuted |
| H7 | ... world | E05 | regions=[] | dynamic vs none_global | p99_sync | 10 | +0.0568 [+0.0142, +0.106] | +4.7% | refuted |
| H8 | planner MILP beats greedy by ≥5% sync P99 (high churn) | E04 | regime=churn_high | plan_milp vs plan_greedy | p99_sync | 10 | -0.0354 [-0.082, +0.00662] | -2.5% | inconclusive |
| H9 | distribution-aware (quantile) beats expectation-only on P99 at high churn | E03 | regime=churn_high, name=blr | quantile vs expected | p99_sync | 10 | -0.0389 [-0.0733, -0.0107] | -2.8% | weak |
| H10 | accounting is off the critical path: settlement period 10 s vs 300 s | E13 | faults=[] | s300_b1 vs s10_b1 | p99_sync | 10 | +0.0207 [-0.0026, +0.0586] | +1.5% | supported |
| H10 | ... receipt batch 0.2 s vs 5 s | E13 | faults=[] | s60_b5 vs s60_b02 | p99_sync | 10 | -0.0135 [-0.0446, +0.0135] | -1.0% | supported |
| H11 | simple baseline matches VOSS when homogeneous, stable and benign | E10 | hw_mix={C1: 1.0} | simple vs voss | p99_sync | 10 | +1.5 [+0.594, +2.65] | +62.8% | refuted |
| H-FT1 | progress detection vs heartbeat-only: success with a black-holed scheduler | E15 | faults=sched_blackhole | progress vs heartbeat_only | success | 10 | +0.0314 [+0.0266, +0.0363] | +3.2% | supported |
| H-FT3 | risk-proportional hedging (θ=.3, 5%) cuts sync P99 under α=0.1 | E16 | adversary={alpha: 0.1, regime: adversary_mixed} | rp_t03_b005 vs hedge_off | p99_sync | 10 | -0.217 [-0.528, +0.0221] | -13.3% | inconclusive |
| H-FT3 | ... at what extra-attempt cost | E16 | adversary={alpha: 0.1, regime: adversary_mixed} | rp_t03_b005 vs hedge_off | waste | 10 | +0.013 [+0.00941, +0.0171] | +253.1% | info |
| RQ15 | VOSS vs Lambda-like reference, sync P99 at 20 inv/s | E17 | rate=20 | voss vs ref_lambda_like | p99_sync | 10 | +0.158 [+0.121, +0.201] | +14.2% | info |
| E12 | reputation tie-break (beta-decay) improves sync P99 vs no reputation | E12 |  | beta_decay vs none | p99_sync | 10 | -0.0323 [-0.0581, -0.0107] | -2.4% | weak |
| E12 | ... and success rate | E12 |  | beta_decay vs none | success | 10 | -8.76e-05 [-0.000247, +2.67e-05] | -0.0% | inconclusive |
