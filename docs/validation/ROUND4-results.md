# Round 4 results: E04b and E25 (pre-registered H12-H16)

Runs: GitHub workflow `paper-rerun` (run 41351691046, release `paper-runs-41351691046`), main at `123ce65`, E04b 380 runs and
E25 360 runs, all `ok`. Analysis: `python -m experiments.analysis.round4 E04b|E25 <csv>` (300 s warm-up, paired by seed) and
`experiments/analysis/round4_h16.py`; per-run metrics in `paper/tables/`. Pre-registration:
`docs/architecture/06-experiments.md` §8. Verdict rule as registered, except that Holm is applied to one-sided
bootstrap p-values of "mean ratio >= bound" (10,000 resamples) over the eight P99 comparisons of H12-H15 instead of widening
CIs (equivalent in effect; stated here so it is not a silent change).

## E04b: mean P99 of synchronous latency (s), 20 seeds (MILP 10); warm memory GB; exposure

| system | churn_med P99 | warm | exposure | churn_high P99 | warm | exposure |
|---|---|---|---|---|---|---|
| plan_none | 1.673 | 1.4 | 7.9 | 1.836 | 1.2 | 7.1 |
| keepalive_ttl (600 s) | 1.534 | 56.6 | 7.2 | 1.531 | 52.1 | 6.4 |
| keepalive_inf | 1.542 | 75.2 | 7.2 | 1.520 | 71.2 | 6.4 |
| hist_prewarm (Azure-style) | 1.569 | 38.9 | 7.2 | 1.669 | 35.9 | 6.5 |
| provisioned_keys | 1.243 | 67.2 | 18.4 | 1.268 | 62.6 | 13.1 |
| plan_greedy | **1.177** | 86.7 | 18.5 | **1.209** | 81.1 | 13.7 |
| plan_milp (10 seeds) | 1.167 | 130.3 | 19.2 | 1.232 | 119.6 | 13.9 |
| erlang_greedy | 1.231 | 97.9 | 14.6 | 1.236 | 88.1 | 11.7 |
| erlang_dpp | 1.208 | 103.7 | 17.7 | 1.223 | 92.6 | 12.7 |
| plan_greedy_oldwait (E04 placement) | 1.194 | 86.2 | 18.5 | 1.217 | 78.9 | 13.4 |

Success is 1.000 for every system (0.9999 at lowest). All systems are far inside a 3 s target; the differences are in
the tail between 1.2 and 1.7 s.

## Verdicts

| H | comparison | mean ratio [95% CI], seeds with ratio < 1 | bound | verdict |
|---|---|---|---|---|
| H12 med | plan_greedy / keepalive_ttl (best single loop) | 0.793 [0.734, 0.848], 19/20 | <= 0.95 | **supported** (Holm) |
| H12 high | plan_greedy / keepalive_inf (best single loop) | 0.822 [0.759, 0.874], 20/20 | <= 0.95 | **supported** (Holm) |
| H13 med | erlang_greedy / plan_greedy, P99 | 1.049 [1.021, 1.080], 4/20 | <= 1.05 | not supported (CI crosses the bound) |
| H13 high | same | 1.025 [1.001, 1.050], 6/20 | <= 1.10 | P99 part supported |
| H13 memory | erlang_greedy / plan_greedy warm memory | 1.131 (med), 1.092 (high) | <= 1.05 | **fails** (uses more warm memory) |
| H13 exposure | same, exposure | 0.802 (med), 0.860 (high) | <= 1.05 | holds (lower exposure) |
| H13 overall | conjunction of P99, memory, exposure | | | **not supported: greedy stays the default** |
| H14b med/high | erlang_dpp / erlang_greedy | 0.982 [0.974, 0.989]; 0.989 [0.976, 1.002] | <= 1.05 | supported |
| H14a | exposure within budget | erlang_dpp exposure 17.7 (med) and 12.7 (high) vs erlang_greedy 14.6 and 11.7 | budget 1.5/tenant +10% | **not met**: the virtual queue did not reduce exposure (it is higher than erlang_greedy's). Total-exposure proxy only; per-tenant exposure was not computed. |
| H15 med | plan_greedy / provisioned_keys | 0.949 [0.927, 0.970], 18/20 | <= 0.95 | weak (point estimate at the bound, Holm not passed) |
| H15 high | same | 0.957 [0.932, 0.981], 16/20 | <= 0.95 | weak (CI excludes 1 but not the 5% bound) |

Reading: planning beats the strongest single loops by about 18-21% in P99 at 2.5x their exposure. Holding the same number
of keys ahead on the most reliable workers (`provisioned_keys`, same exposure as greedy) captures most of it (-19% against
the single loops); planning adds about 5% on top, with the CI excluding zero but not the 5% bound. The Azure-style
histogram policy uses 31-33% less warm memory than the fixed timer at 2-9% higher P99. The corrected placement
(per-worker wait, sync priority) lowers every system's tail; `plan_greedy` with the old placement is within 2%.

## E25: session length (H16), 10 seeds, 6 systems

Advantage `A = 1 - P99(plan_greedy) / P99(best single loop)` (best of keepalive_inf, hist_prewarm per cell), mean session
length multiple M against churn_med, Weibull shape k of idle and dedicated tiers; `B = P99(plan_greedy_blind) / P99(plan_greedy) - 1`.

| k | M | A [95% CI] | B [95% CI] |
|---|---|---|---|
| 0.6 | 0.25 | 0.204 [0.108, 0.322] | -0.007 [-0.025, 0.009] |
| 0.6 | 1 | 0.180 [0.098, 0.270] | -0.007 [-0.026, 0.011] |
| 0.6 | 4 | 0.162 [0.135, 0.192] | -0.008 [-0.041, 0.029] |
| 1.0 | 0.25 | 0.190 [0.095, 0.300] | 0.005 [-0.017, 0.032] |
| 1.0 | 1 | 0.247 [0.146, 0.359] | 0.028 [0.007, 0.050] |
| 1.0 | 4 | 0.150 [0.109, 0.195] | -0.022 [-0.043, -0.002] |

- **H16a (inverted U): weak.** At shape 1.0 the point estimates order as predicted (A(1) > A(0.25), A(1) > A(4)) but only A(1) - A(4) = 0.097 [0.008, 0.202] excludes 0. At shape 0.6 A falls slightly with session length, CIs include 0.
- **H16b (survival information matters): not supported.** B is within about +-3% of zero in every cell and has the wrong sign at shape 0.6 and at (1.0, 4); the only positive cell with a CI excluding 0 is (1.0, 1), the only negative one is (1.0, 4). The planner's gain over single loops is not explained by choosing longer-lived holders.
- Across all six cells the planner beats the best single loop by 15-25%. Session length changes the size of the gap only mildly.

## Key-release amortisation (E04b, from `events.parquet`)

Synchronous requests served per `key_release` event (one per worker session and tenant, logged by the tenant key broker), after
the 300 s warm-up, pooled over seeds: keepalive_ttl 1349 (med) / 1524 (high), keepalive_inf 1184 / 1510, provisioned_keys 69 / 86,
plan_greedy 30 / 36. Planning releases far more keys per request than the keepalive loops, not fewer: its keys are released
repeatedly on a rotating set of holders, while a keepalive worker keeps one key for the life of its session. The per-run columns
`sync_served`, `key_releases`, `sync_per_release` (post-warm-up) and `sync_per_release_all` (whole run) are in
`paper/tables/E04b_runs.csv`; `python -m experiments.analysis.round4 amort <csv> <runs dir with events.parquet>` adds them.

## What this says for the paper

1. The planner's advantage over strong single loops survives a fair baseline and the corrected placement: 18-21% lower P99.
2. The mechanism is holding keys (and the capacity that comes with them) on enough reliable workers ahead of demand, not
   avoiding key-release latency (E04-tail: trust-cold starts are 0.1-0.4% everywhere) and not survival-aware choice of
   holders (H16b). `provisioned_keys` is the honest decomposition: about four fifths of the gain is holding keys early, about
   one fifth is what planning adds.
3. State that lasts a session is why holding keys early works (one release serves every later request of the session),
   but the data do not show that session length or survival information modulates the advantage strongly.
4. Planner v2 (`erlang_greedy`) trades latency for exposure: -14 to -20% exposure for +2.5 to +5% P99 and +9 to +13% warm
   memory. It is not adopted as the default; it is reported as an option on the exposure-latency front. `erlang_dpp` did not
   deliver its budget (H14a).
5. Limits: absolute differences are 0.3 to 0.5 s of P99 with all systems under 3 s; 6 tenants, 12 functions, 200 workers;
   20 and 10 seeds; E25's best-single-loop choice per cell is made on the test seeds.
