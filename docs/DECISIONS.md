# Design Decisions

Current decisions are authoritative. History (ADR-001…029, proposals 0001/0002) is summarized at the end.
Format: **Decision**, why, rejected alternatives.

## Current decisions

**D-01 Custom Python discrete-event simulator.** FaaS physics is small; solver wall time must enter simulated time;
10⁵ workers need light state; there are no TEE-capable simulators. *Rejected:* SimGrid, SimPy.

**D-02 Substrate-agnostic design; profiles are data.**
- Primary substrate: **`appliance_tpm`**, a consumer PC with TPM 2.0 booting an owner-locked, measured VOSS appliance
  per donation session. Tenant functions run in Firecracker microVMs.
- Modeled: `cvm_snp`, `coco_pool`, `drtm_hv`, `none`.
- *Why:* the available hardware is consumer Intel. Memory Guard/TME are not TEEs (no isolation from the OS, no
  attestation). Server CVMs exist only on server CPUs.
- *Rejected:* Memory Guard/TME as a TEE; SGX (deprecated on client); vetted volunteers.

**D-03 Threat model.**
- Owners may be malicious; attestation reduces them to omission/timing faults.
- Out of scope: physical attacks needing equipment, appliance 0-days, side channels, traffic analysis, orchestrator
  failure.
- The orchestrator tier is trusted for availability and accounting only. (Doc 04.)

**D-04 No blockchain.** Attested receipts written by trusted routers already make work verifiable. A chain protects
against no adversary in the model. A transparency log is parked.

**D-05 Information boundary.** `policy` never imports `world`; policies see stale views only.

**D-06 Actor model.** Every cross-node interaction is a typed message via `net.send` with geography-derived delay.
Actors never call or import each other.

**D-07 Roles.**
- Orchestrator tier (provider): orchestrator, regional routers, verifier/registrar, operational DB.
- Scheduler: a role inside one attested worker per cluster.
- Workers: volunteers.
- Tenant KBS: tenant-run.

**D-08 Scheduler fault tolerance.** Soft-state succession; instance-bound epoch appointment by the orchestrator (CAS);
worker-side fencing; roll call; checkpoints in the DB; warm standbys; planned handover; self-fence lease. No consensus
among volunteers; **rollback-immune** by construction. *Rejected:* a Raft group of volunteers (brittle at high churn,
quorum RTT on every decision).

**D-09 Progress-based failure detection.** Evidence comes from trusted or attested observers (router dispatch
watchdog, scheduler result watchdog, decision-latency SLO, outcome model with change points). Heartbeats are hints.
Owner drain/preemption notices are hints that never excuse omissions.

**D-10 Two-timescale scheduling (core novelty).** The slow loop is a robust MILP planner for trust and warm state:
- f-robust coverage, linearized by duality;
- domain caps, exposure, memory/SSD knapsack, switching cost;
- greedy planner as baseline and fallback.

The fast loop is cost-matrix greedy/flow placement over planned candidates, plus a priced cold path, hedging and
retries. The per-window invocation ILP is a baseline only. Kill criterion in doc 03 §8.

**D-11 Measure locally, simulate globally.** Calibration bundles come from the real node (doc 10); literature-only
parameters are ranges with sensitivity sweeps; optional single-box emulation validation.

**D-12 Fast-loop objective.** The `slo_miss` scalarizer: expected SLO-violation cost + ε·E[T] + λ·exposure, over
moment-matched completion distributions.

**D-13 Exposure metric.** Assurance-weighted count of distinct key holders per tenant, with sensitivity classes and
assurance floors. Results are reported as Pareto fronts, never as a single weighted number.

**D-14 Three disjoint reliability signals:**
- **survival:** session ends;
- **omission:** mid-session drops, with change points;
- **reputation:** long-run commitment behavior, rewards only.

`f = ⌈α_assumed·N⌉` makes robustness independent of the adversary's strategy.

**D-15 Worker caches.**
- Three tiers (RAM / SSD / HDD), content-addressed and digest-verified, on a PCR-sealed partition.
- Plan-pinned entries plus GDSF value-density eviction; P2P within the cluster.
- Snapshots shared only with trust-warm workers of the same snapshot class, and counted as exposure.

**D-16 Operational DB.** Private to the orchestrator tier; never on the hot path; one writer per datum; routers write
receipts. The live queue, caches and keys are deliberately not stored.

**D-17 Identity = hash(TPM EK).** One identity per machine (Sybil-bounded). Reputation and credits bind to it.

**D-18 Tenant secrets.** Tenant-owned KBS releases keys wrapped to attested session keys, kept in appliance memory
only. Schedulers and the orchestrator never see them. Bundles are tenant-encrypted, so ciphertext can be cached and
forwarded freely.

**D-19 Small, diverse clusters.** Tens of workers (from E02), with failure-domain and assurance diversity, so robust
plans are feasible and the MILP stays small.

**D-20 Credits in reference work units** (throttling earns nothing), plus small credits for pinned cache donation
while responsive, and scheduler credits.

**D-21 Decision clock modes `measured | modeled | replay`;** a reproducibility contract with manifests, calibration
bundle hashes and `voss repro`.

**D-22 Parked:** workflows, GPU functions, padding, transparency log, real DRTM, multi-machine deployment.

## History (superseded or merged)

| Old | Became |
|---|---|
| ADR-001 SimGrid rejected; ADR-019 reproducibility; ADR-014 clock | D-01, D-21 |
| ADR-002, 020 | D-05, D-06 |
| ADR-005, 006 objective, hybrid placement | D-12, D-10 (the ILP moved to the slow loop) |
| ADR-007, 018, 027 ledger/chain | D-04 |
| ADR-008, 017, 022–024 control plane, Raft, succession | D-07, D-08 |
| ADR-009 reliability vs reputation | D-14 |
| ADR-010, 011 predictor, solver | Doc 03 §6, D-10 (HiGHS) |
| ADR-016, 026 crash-only / vetted honest | Replaced by D-03 (malicious owners + attestation) |
| ADR-021 small clusters | D-19 |
| ADR-025 worker crash tolerance | D-09 + doc 07 §4 |
| ADR-028 DB private | D-16 |
| ADR-029 worker readiness | Doc 08 §5 |
| Proposals 0001, 0002 | Accepted into docs 00–10 |

## Implementation decisions (coding phase)

**D-23 `ACCEPTED` is sent when the worker receives `DISPATCH`** (P2). Doc 00 §6 draws it after `INPUT`; with
multi-MB payloads on residential downlinks that makes the router's dispatch watchdog (`T_dispatch` = 1 s, doc 07 §2)
fire spuriously. The watchdog tests scheduler progress, so the worker acknowledges the dispatch itself; payload
arrival is accounted as `net_in` (input wait). *Rejected:* raising `T_dispatch` (slows real stall detection).

**D-24 Sessions already running at t = 0 skip their boot delays** (P2). Their establish ops keep the TPM quote and
verifier round trip but drop `delay`/`psp` steps, so a run does not start with every worker rebooting. Caches still
start empty; analyses may drop a warm-up window.

**D-25 Latency attribution with overlap** (P2). Trust and artifact fetch overlap the slot wait (doc 08 §5). The time
from `DISPATCH` receipt until slot, key and artifacts are all ready is split as trust first, then fetch (counted in
`startup`), and the remainder is `wait`; payload arrival after start-up is `net_in`. Components therefore always sum
exactly to end-to-end latency (doc 05 §7 invariant).

**D-26 Per-invocation execution noise is a precomputed matrix** (P2). Common random numbers (doc 01 §3) only need the
same draws for the same `(invocation, attempt)` in every system; a vectorized `noise_matrix` from one named stream
gives that without creating a generator per attempt (a measurable cost at 10⁵ invocations). Ladder delays use a
per-worker-session stream.

**D-27 Admission rejects only overload** (P3). Doc 03 §5.4 rejects a sync invocation when no candidate has
`pMiss < 1 − ε`. Without a warm plan, every cold function then has `pMiss ≈ 1` (deadline = k × warm latency), so it
would be rejected forever and its caches would never warm. Rejection (sync) or deferral (async) therefore also
requires overload: even the shortest slot wait exceeds the remaining budget. Cold-start misses are admitted.

**D-28 Wall-clock columns are metadata** (P3). Columns ending in `_wall_s` (e.g. solver wall time) are logged but
excluded from the result hash, so `modeled` and `replay` runs hash identically across machines; `measured` runs
are reproduced through `replay` of their charged latencies (doc 01 §7).

**D-29 Decisions serialize on the scheduler host** (P3). A decision is computed on the view at its start and takes
effect after its charged latency; decisions queue behind each other (`busy_until`), so decision latency includes
queueing on a busy scheduler. Async/filler invocations wait in a window (`placer.window_s`) logged as `batch_wait`.

**D-30 The MILP is bounded by construction** (P4). With exposure fixed costs, robust top-f coverage and warm-state
benefits the full MILP took 20-35 s with large gaps on 200 workers. Three bounds keep it tractable, each a choice the
greedy planner already makes implicitly: a *planning pool* of at most `max_plan_workers` live workers (previous
holders first, then capacity × assurance; P5 clusters bound it further); *candidate* workers per tenant (previous
holders plus the best by the greedy score, 3× what robust coverage needs); and `fn_snaps` = warm units + 1 snapshot
copies per function. The solver gets a node limit and the greedy plan as a competing incumbent; the better objective
is kept (status `greedy_incumbent:*`), so the MILP is never worse than greedy (P4 exit test). An unchanged input
signature (workers, hot set, demand buckets) reuses the previous plan (status `reused`).

**D-31 The planner runs beside the fast loop** (P4). A plan is computed on the view at its start and applied after its
charged latency (decision clock kind `plan`), but it does not hold the scheduler's `busy_until`: the slow loop runs
on its own core, so placements are not delayed by a solve. Its actions are diffed against the workers' confirmed
state (heartbeat `pinned`, cache inventory), not against the previous plan.
**D-32 Clusters plan for their region's demand** (P5). With priced spillover (doc 03 §3) a cluster that receives no
traffic for a tenant never becomes trust-warm for it, so it keeps paying the trust-cold penalty and keeps receiving
no traffic: in the first multi-cluster pilot one cluster served 80% of the world and `nearest` routing beat `score`.
Routers therefore count every invocation against its *home* cluster (nearest by RTT, whatever it was routed to);
the orchestrator forwards these rates each period (`HOME_DEMAND`), and the arrival forecaster plans for
max(local, home) per tenant and function. In equilibrium local ≈ home, so nothing is double counted. *Rejected:*
routing exploration (wastes cold starts), dropping the trust-cold term (removes priced spillover).

**D-33 Cluster cards carry measured prices** (P5). `E[completion_c(f)]` in the routing score is execution (the same
in every cluster up to speed) plus the cluster's overhead; the trust-cold term is "expected key release + cold start"
(doc 03 §3). Fixed constants overpriced both (pilot: `score` lost to `nearest` by 18-30%), so each scheduler reports
EWMAs of what it measured: in-cluster decision + slot wait of **sync** attempts (async batching would bias it), the
trust + start-up actually paid by trust-cold attempts, the start-up of cold attempts, and the backlog per slot when
over-full (`svc × (load − 1)`). Config values are only priors for clusters without measurements. The overhead prior
is **optimistic** (0) and stale overhead decays to it: a pessimistic prior kept idle clusters idle. The health
penalty applies only above the unhealthy threshold θ (doc 03 §2). *Rejected:* the scheduler's mean service time
(reflects each cluster's function mix, not its quality).

**D-34 Hard per-worker migration budget** (P5 exit: bounded migrations). Dwell time and a cap per period bound
rebalancing moves but not structural ones (merge/split). The orchestrator also enforces `max_moves_per_h` (default
3) per worker over a sliding hour, across sessions: merges wait until every member is eligible, splits move only
eligible members (and only if at least `min_size` remain eligible). A property test drives the trigger policy
through random churn and summaries and checks the bound in every one-hour window.

**D-35 Moves are explicit and fenced by cluster** (P5). The orchestrator moves a worker with `ASSIGN(cluster)`; the
worker accepts `EPOCH_INSTALL` and `DISPATCH` only for its assigned cluster (an install that arrives before the
`ASSIGN` is held) and answers others with `STALE(cluster)`. The source scheduler gets the worker in `MEMBERSHIP.moved`
and drops it from its view without retrying its in-flight copies: they still report to the scheduler that
dispatched them. *Rejected:* treating a move as a loss (needless retries and duplicate execution).

**D-36 Spillover withdraws the invocation** (P5). On spillover (no `ACCEPTED` within `T_spill`) the router sends
`WITHDRAW` to the previous cluster's scheduler, which forgets the invocation and cancels any copies already
dispatched; an `ASSIGNED` that still arrives from a cluster the router spilled away from is cancelled. Otherwise
both clusters could run it and the router could pair an input with the wrong attempt.

**D-37 P2P sources must beat the registry** (P5, fixes P4). Residential uplinks are often slower than the registry, so
the nearest peer is not the fastest source (a 175 MB bundle at 6 Mbps up takes ~230 s). Source hints rank peers by
expected pull time (RTT + bytes / min(peer uplink / (1 + busy), target downlink)) and keep only peers faster than the
registry estimate; snapshots, which the registry does not serve, keep the fastest eligible peers.
**D-38 The harness runs remotely and the node side is stdlib-only** (P9). C0 is reached over SSH and is not the
agent's machine, so `tools/calibrate/remote.py` copies the harness, runs suites there and pulls raw logs back; the
node needs only Python ≥ 3.10 and the measured tools. Reboots are never automated beyond one per invocation:
`--boots N` waits for SSH between reboots instead of installing a reboot loop on the owner's machine.

**D-39 Local attestation without Keylime** (P9). `attest_local` measures the same cryptographic work as a
Keylime-style verifier (TPM quote, `tpm2_checkquote`, an Ed25519 certificate signature) with tpm2-tools; Keylime's
policy-engine overhead is not included and the `verify_s` entry says so in its `source`. *Rejected:* installing
Keylime agent + verifier on the owner's machine for one number.

**D-40 SeBS-equivalent kernels instead of SeBS code** (P9). SeBS benchmarks fetch inputs from cloud object storage;
inside an offline microVM the guest runs small kernels with the same libraries and computation per function
(Jinja2, Pillow, ffmpeg, zip, ResNet-50, igraph, squiggle) on generated inputs. Measured `init_s`, `work_ref_s`,
`size_exp` and interference therefore describe these kernels. Node.js variants and Kata are not covered yet.

**D-41 Measured hardware and function profiles live in the bundle** (P9, AGENTS.md rule 13). Besides
`distributions.yaml`, a measured bundle may carry `hardware.yaml` (fields of hardware classes, e.g. C0 disk speeds)
and `functions.yaml` (per-function profile fields); loaders overlay them on the literature YAMLs when a run's
`calibration` points at that bundle. The placeholder bundle has neither, so existing runs are unchanged.

**D-42 Stalls are judged on router evidence, with a grace period** (P6). A router reports `STALL` when dispatch
watchdogs fire for `stall_n` distinct invocations of one cluster within `stall_window_s` (rate-limited), and includes
how long since it last saw an `ACCEPTED` from that cluster. The orchestrator suspects the scheduler only if that idle
time exceeds `T_dispatch` (an over-full cluster still gets new dispatches accepted: a capacity problem for the
triggers, not a reason to replace its scheduler) and only after a grace period following an appointment (a new
scheduler without a view defers everything). *Rejected:* the scheduler's self-reported load (a black-holed scheduler
looks over-full because its own lost dispatches count as in flight).

**D-43 Retries skip admission** (P6). Admission (doc 03 §5.4, D-27) decides whether new load enters. A retry was
admitted already; past its deadline the overload test is trivially true and would turn a recovered fault into a
rejection. Retries are placed whenever a feasible candidate exists.

**D-44 Schedulers report their own lost dispatches** (P6). A copy without `ACCEPTED` after 2 × `T_dispatch` is failed
and retried elsewhere (scheduler-side dispatch watchdog). The keepalive reports how many distinct workers had such
losses recently; at `stall_n` the orchestrator suspects the scheduler (`unaccepted`). The attested scheduler code
cannot stop its host from dropping messages, but it can notice and say so. Routers otherwise route around a
black-holed cluster (its summary shows no free slots) and its stalls become rare: detection fell from 33 s to ~2-8 s.

**D-45 Probe replies come from the attested agent** (P6). The result watchdog fires at `slack × q90` of the predicted
execution; the scheduler probes and the agent answers `running`, `done` (with the time it sent the result) or
`unknown`. `done` long ago without an outcome is direct evidence of omission on the host's network; an omitting
owner drops the probe reply along with the result, so no reply also fails the copy. A fenced (zombie) scheduler draws
no conclusions from its own unanswered probes.

**D-46 What a successor inherits** (P6). Checkpoints carry the last plan and a frozen copy of the learned models
(predictor, survival, omission, forecaster), epoch-fenced at the orchestrator. On appointment with a predecessor,
workers answer `EPOCH_INSTALL(roll_call)` with their running attempts (adopted with fresh watchdogs, their outcomes
re-pointed to the successor) and their retained outcomes (replayed into the predictor). One warm standby per cluster
receives heartbeats and is promoted first, keeping its view. Leases ride on keepalive replies; a scheduler without a
fresh lease stops dispatching.

**D-47 The decision-latency SLO is absolute** (P6, doc 07 §6). `T_decide_max` = 200 ms on the p90 of placement
latency (queueing on the scheduler included) over consecutive keepalive periods with decisions. With modeled
placement costs of 1-2 ms, only a severe slowdown (≥ 100×) breaches it; E15 injects 400×.

**D-48 Receipt statuses** (P7, doc 09 §3). The router writes one `receipts` row per attempt: `ok` (the verified result
that finished the invocation), `duplicate` (a verified result of an already finished invocation: a hedge loser that
completed) and `no_result` (every other attempt, written when the invocation reaches its terminal outcome; for a
timeout that is the router's give-up). Duplicates are credited like `ok`: the scheduler asked for the work and the
receipt proves it was done. Signature checks are charged as router CPU (`verify`) on the asynchronous batch path.

**D-49 Settlement is its own actor reading the DB journal** (P7, doc 09 §4). The `credits` batch job runs in the
orchestrator tier as a separate actor: every `settle_s` it reads, by cursor, the receipts, scheduler-role records and
cache accruals appended since its last read, pays after the charged CPU time (`settle`), and returns verified on-time
and late reference work to the orchestrator for reputation. Scheduler time is credited from each role record until the
cluster's next record (a crashed holder keeps accruing until its successor's appointment, a few seconds).

**D-50 The share cap guards the reputation bonus, not credits** (P7, doc 09 §2 guards). Capping paid credits would
confiscate verified work: in the first pilot the cap clipped over half of all work credit, because trust-warm sets
concentrate work on few workers by design. Instead, an identity holding more than `share_cap` of the last settlement's
verified work gets no tie-break bonus (when the cap is feasible, i.e. at least `1/share_cap` identities earned).

**D-51 Reputation inputs and weights** (P7, doc 09 §1-2). Disjoint from survival and omission: a session shorter than
its declared tier's commitment (`dedicated` 24 h, `nightly` 4 h; `idle` declares none) is a breach (β 3 / 1, half with
a graceful notice), any other session end is honored (α 1); verified on-time work adds α 0.1 per reference unit, late
work β 0.05 per unit (the delivered-vs-declared shortfall the simulator can observe); omission change points add β 2
and suspicions β 1 (the long-run omission summary). Abrupt ends are seen at certificate expiry or at the identity's
next join. `survival_informed` also counts every abrupt end (the double-counting variant). All weights `assumed`.

**D-52 How reputation breaks ties** (P7, doc 09 §1). Greedy multiplies a worker's selection score by
`1 + tie_break × score`; the MILP scales the trust-exposure and churn costs by `1 − tie_break × score`. Plan objective
terms are reported without it. Newcomers in probation get the exploration floor `ε` as score. Reputation never enters
`pFail`; the `reputation_in_cost` ablation belongs to the P8 ablation switches.

**D-53 Reference clouds are a world transform plus a profile** (P8, doc 02 §9). `system: reference_cloud` keeps the
VOSS scenario's workload (same arrivals, so comparisons are paired) and replaces the world: `hosts_per_region`
always-on provider hosts (class `DC`) at each router metro, one session covering the run, no adversaries, no control
faults. The reference's own choices live in `configs/references/<name>.yaml` as config overrides (keep-alive TTL,
no planning, nearest routing, `warm_first`, no hedging); its ladder is a substrate profile with published cold-start
figures, provider assurance 1 and no key release. Cost per million invocations uses list prices with the
provider's billing granularity on startup + execution time.

**D-54 Substrate `none` still registers a session** (P8). Workers without attestation need a platform session id
to join, so `none` sends a registration RPC (no quote, assurance 0). Tenants with an assurance floor cannot be
served on such hosts; their invocations wait until give-up (rejecting them up front is parked).

**D-55 Ablation semantics** (P8, doc 06 §4). Switches live in `configs/ablations.yaml`. Where doc 06 names a
mechanism without a knob: prediction → `instant` (last observed runtime per function, a point estimate, no speed or
load model); lifecycle/cache awareness → placement sees one startup estimate (the candidates' mean) for every
worker; heterogeneity → predictions ignore worker speed (scheduler side; the world stays heterogeneous);
`reputation_in_cost` → `p_omit' = 1 − (1 − p)(0.5 + 0.5·score)`.

**D-56 Scalability mode is configuration** (P8, doc 01 §9). `configs/scalability.yaml`: 10 s heartbeats with
staleness bounds scaled to match, greedy planner and placers, 2 min horizon, load 0.01 inv/s per worker. 10⁵ workers
take ~14 min and ~9 GB, so E18 runs one point at a time.

**D-57 Completeness allows for results still uploading** (P8, fixes P7). Large outputs over slow residential uplinks
can still be in transit when a run ends (one took 27 s in a 30k-worker run). The receipt invariant now excuses
results the network has neither delivered nor dropped at the end (`MsgStats.in_flight`), and routers flush receipt
batches once more after the drain window.

**D-58 Figures carry their provenance** (P8, doc 01 §8). A figure is a registered function of an experiment's runs;
its PDF metadata holds a digest of the runs' result hashes (no creation date, so output is deterministic) and a JSON
sidecar lists every run with config, scenario and result hashes. Sweeps record failed points in `index.csv` instead of
aborting.

**D-59 Owners keep powering off during the drain window** (P8, fixes P2). The session driver replayed drains and ends
only before the horizon, so a host whose session ended during the drain kept executing; the attested-execution
invariant caught it in a 30k-worker run. Ends and drains now replay through `horizon + drain_s` (starts still stop at
the horizon). Pilot reports of P5-P7 predate this fix; only invocations in flight at the horizon are affected.

**D-60 Host-mode appliance measurement on a stand-in machine** (P9, doc 10 §3.1, rule 14). The designed appliance is
a UKI with a dm-verity root built by `mkosi`; that image is untested and needs boot-entry changes. For the throwaway
laptop the owner approved reboots, so `appliance` gained a host mode: a minimal one-shot systemd target on the
machine's own kernel runs the same TPM attestation round (EK, AK, quote, check) and logs wall-clock stamps, because
GRUB gives systemd no firmware or loader times. Reboot time is `btime - prev_end` (last journal line of the previous
boot) plus the kernel time, ±1 s; records carry `method: wallclock`. Safety: the restore service puts the original
default target back before anything else in the measured boot; the driver loop stops on a STOP file, N completed
boots, N+3 armed boots, or two unfinished boots in a row; install refuses a LUKS root and saves the original target.
The loop lives in `appliance/host/` and `laptop/voss-calib.sh appliance`, never in the harness module. The image mode
stays for the i7 node.

**D-61 Fixes from the first stand-in laptop run** (P9, doc 10 §3). Real hardware exposed six harness bugs that no stub
could: Firecracker API sockets deeper than the 107-byte `AF_UNIX` limit (rep 10 of `fc_snapshot`); the `graph-mst`
guest counting `spanning_tree(return_tree=False)`, which is a list; `tpm2_quote -q` needing hex qualifying data (every
measured boot lost its attestation timing, and two unfinished boots stopped the loop); a machine that used to run
Windows keeping its hardware clock in local time (a +5.5 h step corrupted wall-clock boot timings, so the install
switches the RTC to UTC for the run and restores it, and `collect` rejects samples outside 0..600 s); `MemTotal`
changing by a few kB between boots, which split one machine into three fingerprints (memory is now rounded to
0.1 GB); and QEMU boot failures aborting the suite (now recorded with the console tail). A failed TPM step no longer
discards a boot's timings. The pack also carries plain-text `debug/*.log` files (scrubbed). Records of the failed
suites stay in the first-round data; round two (`voss-calib-auto.sh redo`) reruns only those suites and the reboot test.

**D-62 The stand-in laptop's bundle is labelled as the laptop** (P9, doc 10 §1, rule 13). The only measured machine is
an i3-7020U laptop with one spinning disk, not the i7 node C0. Its bundle lives at
`configs/calibration/measured/laptop-<hash>/`; the hash is over CPU, board, BIOS and memory rounded to 0.1 GB (D-61).
`ingest --tier hdd` maps that machine's only tier onto the mapping's `ssd` role, so `fc_boot`, `fc_restore` and
`fc_snapshot_create` are HDD numbers; `appliance_*` come from the host-mode probe (D-60) and bound a purpose-built
image from above. Entries without data keep their `literature`/`assumed` tags. Measurements of a failed `sebs` run
are kept (each function is written when finished); other failed suites are ignored. The scenario config still names
the placeholder bundle by default (`configs/base.yaml`); experiments choose the measured one with
`--set calibration=configs/calibration/measured/laptop-<hash>`. The usernames in raw paths were replaced by the host
label before committing.

**D-63 Paper protocol and scope** (P10, doc 06 §6). `make paper` runs every frozen spec in `configs/experiments/`
with seeds 1-10 and writes tables, figures and the scorecard under `paper/` from run logs only; finished runs are
reused, so a rerun is idempotent. Deviations, each visible in the specs: (1) E03, E04, E09, E23 move from the P2
smoke base (`least_loaded` placer, one cluster) to `pilot.yaml`, so planners act with VOSS's own placers and geo
clusters; (2) E20 (viability map) is three 2-D panels, not the full five-way product (churn × α, substrate × load,
N × load; 3 systems in panel A: VOSS, the best simple baseline, and the same baseline with no attestation), at 300
workers and 10 min so that the unattested system (3.5× the events) stays tractable; viable means the lower 95%
bootstrap bound of success ≥ 0.99 and of deadline-met ≥ 0.95; (3) E12 keeps four reputation rules at tie-break 0.2
(the pilot was null at 0.02 and 0.2) and E04 keeps four planners (the MILP-term ablations are E19's and E23's); (4) E18's 30k and 100k points keep 3 seeds (6-20 wall minutes and up to 9 GB per
run); E02 (planning pool × T_plan) stays a pilot outside `make paper`: its measured decision clock needs the machine
to itself and ~7 minutes a run, and it only informs the cluster-size target of D-19; (5) E23 gets 10% omitting adversaries so that
robustness is an outcome, per-sensitivity-class latency, and exposure weights {0.1, 10} (the middle value was
indistinguishable in the pilot; MILP runs cost 2-4 minutes each); (6) E24 repeats the key comparison under the placeholder
and the laptop-measured bundle (D-62). Hypothesis verdicts are mechanical (`experiments/analysis/scorecard.py`):
supported only when the paired CI excludes 0 by the stated margin; refuted and inconclusive rows are collected in
`paper/negative-results.md`.

**D-64 `static_regions` re-creates a region's cluster after it dissolved** (P10, fixes P5). The orchestrator cached the
cluster id of each region, but a cluster whose last member leaves is dissolved; the next worker joining that region was
homed to the dead id and the run crashed with a `KeyError` (E06, seed 7, 1 of 60 runs). The cache entry is now
validated against the live clusters. Runs that did not reach that state are unchanged (same result hashes); the failed
run was rerun after the fix.

**D-65 The manuscript is generated from result tables** (P11, doc 06 §6). Every number and table in `manuscript/` is
written by `experiments/paper_tex` from `paper/tables/*` (committed per-seed and per-cell CSVs) and the measured bundle;
prose uses LaTeX macros (no digits in names) for each number. `expect()` assertions in the generator raise when a result
stops supporting a sentence of the draft (for example H7 refuted, baseline never viable at a 3 s P99 target), and
`tests/unit/test_manuscript.py` fails when `manuscript/generated/` is stale. Consequences: the draft cannot silently
drift from the data, but each change to a frozen result forces a deliberate edit of the text. Decided alongside: the
journal class is `IEEEtran` in journal mode because the target venue is only "IEEE Transactions"; the viability maps
use the default criterion (success ≥ 0.99, deadline-met ≥ 0.95) in the figure and report absolute P99 targets in a
table, since the two criteria disagree for the simple baseline on confidential-VM substrates; the bibliography is
unverified (written from memory) and is flagged in `manuscript/README.md` and `docs/ROADMAP.md`. The raw `runs/` of the
P10 sweep were lost with the ephemeral worktree that held them; the per-seed CSVs in `paper/tables/` (which the manuscript
reads) remain, so `make paper-analyze` needs a rerun of `make paper` to redraw from logs.

**D-66 The greedy planner is the method; the MILP is the reference solver** (P11, doc 03 §8). The pre-set kill criterion
was: if the planner MILP improves sync P99 by < 5% over the greedy planner in all regimes, greedy becomes the method. E04
(10 seeds) gives −2.1% (medium churn) and −2.5% (high churn), intervals including zero (H8 inconclusive), at 5.5 s against
10 ms per cluster solve. Every experiment except E04 and E23 already runs the greedy planner (`pilot.yaml`,
`scalability.yaml`); the manuscript says so and presents the robust formulation as the model, the MILP as a reference
solver and the heuristic as the practical one. The robustness constraint itself stays: it is what the heuristic enforces.

**D-67 The paper sweeps are rerun and archived on GitHub Actions** (P11, doc 01 §8). A container-local `make paper` needs
about 9 hours (E18 alone 80 minutes) and the sandbox that held the first sweep was recycled (its raw `runs/` was lost; only
the per-seed tables and, from sweep logs, the result hashes survived: `paper/run-hashes.csv`). The `paper-rerun` workflow
(manual trigger) runs one job per experiment, checks each run's result hash against `paper/run-hashes.csv`, re-draws the
experiment's table and diffs it against `paper/tables` (only wall-clock columns may differ), and uploads the raw logs as
`tar.zst` release assets (Actions artifacts are quota-limited on private repositories). Raw logs stay out of git (GBs).
Known limits: the E18 10^5-worker points need about 9 GB of memory (set repository variable `LARGE_RUNNER`); the one E06
run redone after D-64 has no recorded hash, so it is checked by table identity only until its hash is added from the
rerun's `run-hashes-rerun.csv`.

**D-68 Platform-independent linear algebra: no BLAS or LAPACK in the simulator** (P11, doc 01 §8). The `paper-rerun`
workflow (D-67) reproduced the recorded result hash of only 9 of 21 experiments (1,196 of 2,366 runs) on GitHub's AMD
runners; in the other 12 experiments no run matched. Forcing OpenBLAS kernels on the original machine
(`OPENBLAS_CORETYPE=Haswell|Nehalem`, numpy SIMD features and thread count unchanged or switched off separately) changed
the hashes, so the dependence is the BLAS kernel, i.e. the CPU: the Bayesian-regression predictor (`np.linalg.inv`, `@`,
`einsum`) and two planner dot products round differently per kernel, a last-bit difference flips a near-tie in placement,
and the discrete-event trajectory diverges (per-run P99 differs by up to 40%, the 10-seed statistics are what the paper
reports). `voss/core/detmath.py` replaces those calls by exactly rounded elementwise arithmetic in a fixed order
(3x3 cofactor inverse, `math.fsum` dot products, scalar `math.log`); with it the hashes are identical across all tested
kernel and SIMD settings. Consequence: results generated before this change are not reproducible bit for bit on other
CPUs and are replaced by a full rerun under the new arithmetic (new `paper/run-hashes.csv`, tables, figures, manuscript
numbers). `tools/diag/numeric_repro.sh` and the `numeric-diagnostic` workflow check the property on any machine.
