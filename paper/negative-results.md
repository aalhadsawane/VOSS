# Negative and inconclusive results

## Scorecard

| H | Claim | Experiment | Cell | Comparison | Δ rel | Verdict |
|---|---|---|---|---|---|---|
| H5 | CVM classes are 10-100x slower than the appliance to establish trust | E-CS1 (sim) |  | ratio - 1 (mid-range) (p50 s) | -92.7% | refuted |

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
