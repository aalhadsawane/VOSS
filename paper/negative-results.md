# Negative and inconclusive results

## Scorecard

| H | Claim | Experiment | Cell | Comparison | Δ rel | Verdict |
|---|---|---|---|---|---|---|
| H2 | f-robust plans keep success where non-robust collapse (α=0.2 mixed) | E08 | adversary={alpha: 0.2, regime: adversary_mixed} | f0 vs voss (success) | -0.1% [-0.3, +0.0] | inconclusive |
| H5 | CVM classes are 10-100x slower than the appliance to establish trust | E-CS1 (sim) |  | ratio - 1 (mid-range) (p50 s) | -92.7% | refuted |
| H6 | GDSF + P2P + HDD tier beat LRU without P2P/HDD (sync P99) | E09 |  | lru_no_p2p_no_hdd vs gdsf_p2p_hdd (p99_sync) | +2.8% [-2.9, +11.9] | inconclusive |
| H6 | ... GDSF vs LRU alone | E09 |  | lru vs gdsf_p2p_hdd (p99_sync) | +1.6% [-0.2, +4.0] | inconclusive |
| H7 | geo clusters reduce sync P99 vs one global scheduler (EU) | E05 | regions=[eu] | dynamic vs none_global (p99_sync) | +17.3% [+12.5, +22.0] | refuted |
| H7 | ... EU+NA | E05 | regions=[eu, na] | dynamic vs none_global (p99_sync) | +16.6% [+5.2, +33.1] | refuted |
| H7 | ... world | E05 | regions=[] | dynamic vs none_global (p99_sync) | +4.5% [+0.9, +8.7] | refuted |
| H8 | planner MILP beats greedy by ≥5% sync P99 (high churn) | E04 | regime=churn_high | plan_milp vs plan_greedy (p99_sync) | -2.5% [-5.8, +0.5] | inconclusive |
| H9 | distribution-aware (quantile) beats expectation-only on P99 at high churn | E03 | regime=churn_high, name=blr | quantile vs expected (p99_sync) | -2.8% [-5.3, -0.8] | weak |
| H11 | simple baseline matches VOSS when homogeneous, stable and benign | E10 | hw_mix={C1: 1.0} | simple vs voss (p99_sync) | +63.7% [+25.0, +112.8] | refuted |
| H-FT3 | risk-proportional hedging (θ=.3, 5%) cuts sync P99 under α=0.1 | E16 | adversary={alpha: 0.1, regime: adversary_mixed} | rp_t03_b005 vs hedge_off (p99_sync) | -13.3% [-32.5, +1.4] | inconclusive |
| E12 | reputation tie-break (beta-decay) improves sync P99 vs no reputation | E12 |  | beta_decay vs none (p99_sync) | -2.4% [-4.4, -0.8] | weak |
| E12 | ... and success rate | E12 |  | beta_decay vs none (success) | -0.0% [-0.0, +0.0] | inconclusive |

## Viability maps: cells where VOSS is not the winner (deadline-met target 0.95)

- E20b [substrate_mix={coco_pool: 1.0}, rate=10]: none (VOSS met 0.957, P99 3.60 s)
- E20b [substrate_mix={coco_pool: 1.0}, rate=20]: baseline_better (VOSS met 0.948, P99 4.57 s)
- E20b [substrate_mix={coco_pool: 1.0}, rate=40]: baseline_better (VOSS met 0.944, P99 4.00 s)
- E20b [substrate_mix={cvm_snp: 1.0}, rate=20]: baseline_better (VOSS met 0.959, P99 2.51 s)
- E20b [substrate_mix={cvm_snp: 1.0}, rate=40]: baseline_better (VOSS met 0.957, P99 2.90 s)
- E20c [workers=100, rate=10]: none (VOSS met 0.939, P99 1.43 s)
- E20c [workers=100, rate=20]: none (VOSS met 0.939, P99 2.55 s)
- E20c [workers=100, rate=40]: none (VOSS met 0.877, P99 5.01 s)
- E20c [workers=100, rate=5]: none (VOSS met 0.934, P99 1.32 s)
