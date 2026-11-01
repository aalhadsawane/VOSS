# Planner v2: loss-model planning of keys and warm sandboxes (proposal, not implemented)

Status: proposal answering critique C-44 (the greedy planner is ad hoc). Nothing here is implemented or evaluated yet. The
current greedy planner and the exact MILP stay as baselines. Every claim marked *(lit.)* is a textbook result to be cited;
every claim marked *(ours)* needs a proof in the paper or an appendix.

## 1. What is wrong with the current greedy planner

The current planner (`voss/policy/plan/greedy.py`, manuscript §5.4) does two passes:

1. per tenant, add the machine with the best `survival × assurance ÷ (memory + exposure cost)` until "coverage with the
   `f` largest allocations removed" reaches a demand number;
2. add warm sandboxes and snapshots in decreasing "start-up seconds saved per MB", where the value of a sandbox is
   `rate × horizon × seconds saved`, the same for the first and the tenth sandbox of a function.

Both passes are reasonable but neither is derived from what we want to minimise. Pass 2 is the clearer defect: the value of
a warm sandbox does **not** stay constant as more are added. The first warm sandbox of a function serves most requests, the
tenth serves almost none. A planner that ignores this over-warms popular functions and under-warms the rest.

## 2. The model: provisioned capacity as a loss system

Fix one tenant `t` and the planning horizon `H` (60 s). Requests of `t` arrive at rate `λ_t` and occupy a slot for a mean
time `s_t`. The offered load is `a_t = λ_t s_t` (in slots).

A request that finds a free provisioned slot runs there. A request that finds every provisioned slot busy goes to a machine
without the key (the slow path) and pays an extra delay `Δ_t` (key release plus start-up). This is exactly an Erlang loss
system, M/G/c/c, where "lost" means "sent to the slow path".

**Fact 1 (insensitivity) *(lit.)*.** In M/G/c/c the probability that an arriving request finds all `c` slots busy is the
Erlang-B formula `B(c, a)`, and it depends on the service-time distribution only through its mean
(Erlang 1917; Sevastyanov 1957; textbook: Kleinrock, *Queueing Systems* vol. 1). So we need only the rate and mean
service time, which the scheduler already estimates.

**Fact 2 (recursion) *(lit.)*.** `B(0, a) = 1`, `B(c, a) = a B(c-1, a) / (c + a B(c-1, a))`. One step costs O(1).

**Fact 3 (convexity) *(lit.)*.** `B(c, a)` is decreasing and convex in the integer `c` (Messerli 1972, *Bell Syst. Tech.
J.*; Jagers and van Doorn 1986). Equivalently the carried load `a (1 - B(c, a))` is increasing and concave in `c`.

The expected slow-path delay per second for tenant `t` with `c` provisioned slots is

    D_t(c) = λ_t Δ_t B(c, a_t).

By Fact 3 the saving from the `k`-th slot, `g_t(k) = λ_t Δ_t [B(k-1, a_t) - B(k, a_t)]`, shrinks as `k` grows. This is the
diminishing return the current planner misses.

## 3. Stage A: which machines hold a tenant's key (robust submodular selection)

Machine `j` holding `t`'s key contributes `c_tj` slots, and it is still there at the end of the horizon with probability
`e_j = S_j(H) (1 - p_j)` (session survives, and it does not drop work). Let `X_j ~ Bernoulli(e_j)`, independent, and
`C_t(S) = Σ_{j∈S} X_j c_tj` the slots that survive.

Utility of a key-holder set `S`:

    U_t(S) = λ_t Δ_t E[ 1 - B(C_t(S), a_t) ]      (slow-path delay avoided per second)

**Claim A1 *(ours, short proof)*.** `U_t` is monotone and submodular in `S`.
*Proof sketch.* For fixed outcomes `x`, `C_t(S)` is a sum of non-negative integers over `S`, and `h(c) = 1 - B(c, a)` has
non-increasing increments (Fact 3). The marginal gain of adding `j` to `S` is `h(y + x_j c_tj) - h(y)` with `y = C_t(S)`,
which does not increase when `y` grows, i.e. when `S` grows. Expectation over `x` keeps both properties. ∎

Cost of `S`: the exposure it creates, `Σ_{j∈S} σ_t (1 - a_j)`, plus the memory of the slots reserved. This is modular.

So Stage A maximises *submodular minus modular*:

    max_S  U_t(S) - Σ_{j∈S} κ_tj ,   κ_tj = σ_t (1 - a_j) + ρ_mem m_t c_tj.

**Algorithm A (distorted greedy, Harshaw, Feldman, Ward, Karbasi, ICML 2019) *(lit.)*.** With a limit of `k` key holders
per tenant, run `k` rounds; in round `i` add the machine maximising `(1 - 1/k)^{k-i-1} ΔU - κ`, and only if positive. It
returns `S` with `U(S) - κ(S) ≥ (1 - 1/e) U(OPT) - κ(OPT)`. This is the strongest known guarantee for this objective
class, and it is a greedy algorithm.

**Robustness to `f` worst-case losses.** Replace "remove the `f` largest allocations" (only a bound for a modular
objective) by robust submodular maximisation `max_S min_{|R| ≤ f} U(S \ R)`. The two-stage algorithm of Orlin, Schulz and
Udwani (IPCO 2016, *Math. Prog.* 2018) first takes the `f` elements with the largest single values as a sacrificial
buffer and then runs greedy on the rest; it has a constant-factor guarantee (about 0.387) when `f` is small relative to
`k` *(lit.)*. Bogunovic, Mitrović, Scarlett and Cevher (ICML 2017, PRO) extend it to larger `f` *(lit.)*. This keeps the
idea of the current planner (protect against the `f` biggest losses) and gives it a theorem.

Computing `E[1 - B(C, a)]`: `C` is a sum of independent weighted Bernoullis, so its distribution is computed exactly by a
convolution over the at most 40 machines (support at most total slots), O(|S| · slots) per evaluation, and incrementally
when one machine is added. Lazy evaluation (Minoux 1978) avoids recomputing gains that cannot win *(lit.)*.

## 4. Stage B: how many warm sandboxes of each function (marginal allocation)

Among machines that hold the tenant's key, function `f` has load `a_f = λ_f s_f`. With `w` idle warm sandboxes kept, a
request finds none free with probability `B(w, a_f)` (Fact 1), and then pays the boot or restore time `τ_f` instead of a
few milliseconds. Expected start-up seconds saved per second:

    V_f(w) = λ_f τ_f [1 - B(w, a_f)]

Each warm sandbox costs memory `m_f`. With a memory budget `M`:

    max_w Σ_f V_f(w_f)   s.t.  Σ_f m_f w_f ≤ M,  w_f ∈ {0, 1, 2, ...}

The objective is separable and concave in each `w_f` (Fact 3).

**Algorithm B (marginal allocation, Gross 1956; Fox 1966; Ibaraki and Katoh 1988) *(lit.)*.** Keep a heap keyed by the
next gain per MB, `λ_f τ_f [B(w_f, a_f) - B(w_f+1, a_f)] / m_f`; pop the best, add one sandbox, push the function's next
gain (one Erlang-B step). When all `m_f` are equal this greedy is exactly optimal; with unequal sizes it is optimal for
the continuous relaxation and loses at most one item's value on integers. Cost: O(W log F) for W sandboxes over F
functions. This is the classic water-filling argument, and it replaces the current constant-value pass with a derived one.

**Snapshots on disk.** A request that misses a warm sandbox (probability `B(w_f, a_f)`) restores a snapshot if one is on
the chosen machine, saving `τ_f^boot - τ_f^restore`. So a snapshot's value is
`λ_f B(w_f, a_f) (τ_f^boot - τ_f^restore)`: it is worth most when few sandboxes are warm. Put warm sandboxes and
snapshot pins in one heap; their gains interact only through `B(w_f, a_f)`, so after each pop only that function's two
entries change.

**Churn.** A warm sandbox on machine `j` survives the horizon with probability `S_j(H)`. Use the expected number of
surviving sandboxes, or, exactly, the distribution of survivors as in Stage A. The robust buffer of Stage A already covers
correlated losses of whole machines.

## 5. A second variant: exposure as a budget, with prices (drift-plus-penalty)

Tenants find "exposure weight σ = 1" hard to set. A budget is easier to state: "on average, no more than `E_t^max` of
trust-weighted key holders". Treat it as a long-run constraint and enforce it with a virtual queue updated once per
planning round `k` (Neely, *Stochastic Network Optimization with Application to Communication and Queueing Systems*,
2010) *(lit.)*:

    Q_t(k+1) = max( Q_t(k) + E_t(k) - E_t^max, 0 )

Each round, run Algorithms A and B with exposure price `Q_t(k)` in place of `σ_t`, and the utility scaled by a parameter
`V`. The drift-plus-penalty theorem gives a time-average utility within O(1/V) of the best policy that meets the budget,
with time-average exposure at most `E_t^max` and queue size O(V) *(lit.)*. This matches the planner's timescale exactly:
the queue changes only once per round. The mobile edge computing literature on two-timescale placement uses this
machinery heavily (see related work), so a reviewer from that field will recognise it.

## 6. What the planner needs, and what is new about it

Inputs per round (all already estimated by the scheduler): per tenant and function, arrival rate and mean service time;
per machine, probability of surviving the horizon, probability of dropping work, trust score, slots and memory; per
tenant, sensitivity (or exposure budget) and how many machine losses to tolerate. Output: the same plan as today (key
holders, warm counts, snapshot pins, reserved slots), so the placer and workers do not change.

What is new, compared with the two-timescale edge-computing papers: the resource being placed is *trust* (keys) whose
cost is exposure and whose value is the slow path it avoids; machines vanish with probabilities we estimate; and the
robustness is against adversarial worst-case losses, not only random ones.

## 7. Evaluation plan

- Register `erlang_greedy` (A + B) and `erlang_dpp` (A + B + virtual queues) as planners; keep `greedy` and `milp`.
- Unit tests: Erlang-B recursion against closed form for small `c`; convexity of `B` numerically; submodularity of `U_t`
  on random instances; marginal allocation equals brute force on small instances.
- Rerun E04 (planners), E19 (ablation), E20 (feasibility maps) and E23 (trade-off front); E24 if time allows. Pre-state:
  H-new1, `erlang_greedy` lowers synchronous P99 against `greedy` by at least 5% at medium and high churn at no more
  warm memory; H-new2, `erlang_dpp` keeps time-average exposure under the budget with P99 within 5% of `erlang_greedy`.
- Charge the measured solve time to the simulated clock (C-16), so the comparison with the MILP is fair.

## References to add (verify each before citing)

- A. K. Erlang (1917); B. A. Sevastyanov (1957): Erlang-B and its insensitivity; L. Kleinrock, *Queueing Systems*, Vol. 1 (1975).
- E. J. Messerli, "Proof of a convexity property of the Erlang B formula", *Bell System Technical Journal* 51(4), 1972.
- O. Gross (1956), marginal analysis; B. Fox, "Discrete optimization via marginal analysis", *Management Science* 13(3), 1966; T. Ibaraki and N. Katoh, *Resource Allocation Problems*, MIT Press, 1988.
- C. Harshaw, M. Feldman, J. Ward, A. Karbasi, "Submodular maximization beyond non-negativity", ICML 2019.
- J. B. Orlin, A. S. Schulz, R. Udwani, "Robust monotone submodular function maximization", IPCO 2016 / *Math. Programming* 2018.
- I. Bogunovic, S. Mitrović, J. Scarlett, V. Cevher, "Robust submodular maximization: a non-uniform partitioning approach", ICML 2017.
- M. Minoux, "Accelerated greedy algorithms for maximizing submodular set functions", 1978.
- M. J. Neely, *Stochastic Network Optimization with Application to Communication and Queueing Systems*, Morgan & Claypool, 2010.
- G. L. Nemhauser, L. A. Wolsey, M. L. Fisher, "An analysis of approximations for maximizing submodular set functions", *Math. Programming* 14, 1978.
