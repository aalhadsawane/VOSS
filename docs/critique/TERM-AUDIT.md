# VOSS manuscript: term audit

Scope: `manuscript/main.tex` (abstract), `manuscript/sections/*.tex` in `\input` order (intro, background, design, trust,
scheduling, network, faulttol, method, results, discussion, related, conclusion, appendix) and the TikZ labels of
`manuscript/diagrams/{arch,loops,broker,attest,failover}.tex`. Read-only audit; nothing else was edited.
Line numbers refer to the files as they stand now (many earlier-flagged terms such as "uncovered demand", "hot set",
"demand quantile", "unprovisioned path" are already gone from the text; remaining traces are listed).

Problem codes: **C** coined, **U** undefined at first use, **1x** used once or twice only, **I** inconsistent with another name,
**J** jargon a non-serverless reader will not know, **S** slogan (says nothing measurable), **SY** symbol not explained in
words, **AB** abbreviation not expanded.

## 1. Findings table

### 1.1 Abstract and main.tex

| # | file:line | term or phrase | problem | plain replacement / definition to add |
|---|---|---|---|---|
| 1 | main.tex:34 | "TPM-equipped laptop" | AB, J: TPM never expanded anywhere (background:27 only says "the security chip") | "a laptop with a Trusted Platform Module (TPM), a tamper-resistant chip that signs a fingerprint of the software that booted" |
| 2 | main.tex:23 | "isolated environment to start" | J: first mention before "sandbox"/"cold start" are introduced | "wait for the function's sandbox (a small isolated virtual machine) to start (a 'cold start')" |
| 3 | main.tex:26 | "prepared environment" | I: environment / sandbox / microVM / warm sandbox / "ready environments" / "warm state" | pick "sandbox" everywhere; define once |
| 4 | main.tex:29 | "Remote attestation, in which a machine proves ..." | fine, but "verifier" not defined here | keep; add "to a remote checker (the verifier)" |
| 5 | main.tex:31 | "Proving trust, handing a machine a customer's decryption key, and starting environments" | C: three steps unnamed; later called attestation / key release / provisioning / start-up | name them "attest, release key, start sandbox" and use only these |
| 6 | main.tex:33 | "A planner, run every 30 seconds ... ready environments, with spare capacity" | U: "planner" and "spare capacity" not defined; "ready environments" is a third name for warm sandbox | "a slow planning step ... decides which machines receive each tenant's key and keep warm sandboxes, and reserves extra for machines that disappear" |
| 7 | main.tex:34 | "A per-request step" | I: later "request placement", "fast loop", "placer", "per-request step", "placement" | use "request placement" only |
| 8 | main.tex:35 | "duplicates calls at risk" | C: "hedge" elsewhere; "calls" vs "requests" vs "invocations" | "sends a second copy of a request that is likely to be lost" |
| 9 | main.tex:36 | "judged failed when work it accepted does not come back, not when it stops sending heartbeats" | S/J: "heartbeat" undefined here; no number says how fast | add "(a heartbeat is a periodic 'I am alive' message)" |
| 10 | main.tex:37 | "without any agreement protocol" | J: consensus unexplained for non-distributed-systems readers | "without the machines voting on who is in charge (a consensus protocol)" |
| 11 | main.tex:38 | "publish/subscribe broker" | J: undefined in abstract | "a message relay to which parties post and from which they read by topic name" |
| 12 | main.tex:40 | "99th-percentile latency under 3 s" | U: "P99" appears only in method:40; 3 s target never justified | "the slowest 1% of requests take under 3 s"; state why 3 s |
| 13 | main.tex:40-41 | "churn-and-adversary settings", "strongest simple baseline" | U: neither defined in abstract; "simple baseline" defined only method:42 | "baseline that keeps sandboxes warm for 10 min and routes to the nearest region" |
| 14 | main.tex:41 | "parts that did not pay off" | S: no measure | "components that did not improve latency or success (list)" |
| 15 | main.tex:42 | "\ViabAPThreeVoss of \ViabACells settings" | SY: what a "setting" or "cell" is is not said | "of N simulated scenarios (each a churn x adversary-fraction pair)" |

### 1.2 Introduction (sections/intro.tex)

| # | file:line | term or phrase | problem | replacement / definition |
|---|---|---|---|---|
| 16 | intro:4 | "functions", "customer" | I: customer / tenant / developer; "tenant" defined only background:4 | define "tenant" here, then use only "tenant" |
| 17 | intro:6 | "isolated environment", "language runtime" | I,J: = sandbox; term "sandbox" defined later (background:6) | "sandbox (a lightweight virtual machine)" at first use |
| 18 | intro:7 | "cold start" | defined by example only | "the delay before a function's first run while its sandbox is created" |
| 19 | intro:8 | "keeping environments alive" | I: = "keep-alive" / "warm" later | "keeping idle sandboxes in memory (keep-alive)" |
| 20 | intro:15 | "churn" | ok (defined), but also "session ends", "leave", "departure", "drop out" | keep "churn"; define "session" here |
| 21 | intro:16 | "the secret keys it was given" | U: key-for-what not said | "the tenant's decryption key for its code and data" |
| 22 | intro:18 | "distrust" | C: coined noun | "untrusted owners" |
| 23 | intro:23 | "Earlier work solves parts of this" | S: no list of what | acceptable, but delete "this" ambiguity |
| 24 | intro:26 | "Confidential-computing designs" | J | "designs that run code inside hardware-protected memory (confidential computing)" |
| 25 | intro:29 | "gray failure" | defined here, but used again only related:46 | keep but gloss as "partial failure" in both |
| 26 | intro:32 | "Our starting point" | S | delete; say the claim directly |
| 27 | intro:33 | "locked operating-system image" | C: image / attested image / appliance / "the image" | "a read-only operating-system image with no login" |
| 28 | intro:33 | "a verifier" | U | "a checking service (the verifier) run by the provider" |
| 29 | intro:36 | "omission and timing failures" | J | one-line gloss: "answer never arrives / arrives too late" (given in background:67, 4 pages later) |
| 30 | intro:40 | "a session" | U: first use; "session" later also means session key / certificate / survival | "a session is the period between boot into our image and the next power-off" |
| 31 | intro:42 | "attested worker", "worker" | U: "worker" defined background:6 | define on first use |
| 32 | intro:42 | "thousands of times longer" | S-ish: ratio of what to what | "\CalAttested s versus a few ms to hand a request to a warm sandbox" |
| 33 | intro:45 | "a decision with a cost" | S | "a decision that spends time, memory and key exposure" |
| 34 | intro:48 | "planner" | U: what it plans | see #6 |
| 35 | intro:49 | "which functions they keep ready" | I: ready / warm / prepared / provisioned | "keep warm" |
| 36 | intro:49 | "spare capacity" | C | "extra reserved slots (a slot = one concurrent invocation) so that losing a few machines does not hurt" |
| 37 | intro:50 | "per-request step" | I | request placement |
| 38 | intro:51 | "a provider-run coordinator" | I: = "orchestrator" (design:37) | "the orchestrator, a provider service" |
| 39 | intro:52 | "Signed receipts record who did which work" | U | add "(Section 5.3)" |
| 40 | intro:59 | "capacity even if any f machines fail together" | SY, U: f unexplained; "fail together" wrong (the model removes the f largest contributors, not a correlated failure) | "enough warm capacity remains after the f largest key-holding contributors are removed" |
| 41 | intro:60 | "addresses change and cannot accept incoming connections" | J: NAT not named | "machines behind home routers (NAT)" |
| 42 | intro:63 | "hypotheses and decision rules fixed before the runs" | J | "pre-registered" is clearer to some; or one sentence |
| 43 | intro:66 | "Planning has the largest effect" | S: effect on what; also contradicted by discussion:4 ("two largest contributors") | "planning lowers P99 by X-Y%" (the number follows; delete the slogan) |
| 44 | intro:66 | "provisioning machines only when requests arrive" | I: "no planner", "provisioning on demand", "reactive" | "no planner (keys and sandboxes created when the request arrives)" |
| 45 | intro:66 | "judging machines by returned work" | I: returned work / progress-based detection / progress evidence / dispatch timer / result timer | choose "returned work" |
| 46 | intro:66 | "against \HbSuccAlpha\% with heartbeats" | U: "heartbeat-only baseline" not named | "against the baseline that trusts heartbeats" |
| 47 | intro:67 | "commercial-style datacenter reference" | C | "a model of a datacenter FaaS (Lambda-like) on the same workload" |

### 1.3 Background (sections/background.tex)

| # | file:line | term or phrase | problem | replacement / definition |
|---|---|---|---|---|
| 48 | bg:4 | "Terms." paragraph | good, but defines 7 terms and omits slot, session, level, plan, hedge, epoch, exposure | add those that the paper keeps |
| 49 | bg:4-9 | tenant / invocation / provider / volunteer / owner / worker / sandbox | I: volunteer = owner = donor (faulttol:72, method:21, results:33) = machine = host = node (arch, results) = worker | one noun for the person (owner) and one for the machine (worker) |
| 50 | bg:6 | "microVM" | J | "a minimal virtual machine (e.g. Firecracker)" |
| 51 | bg:7 | "warm" | J: central, defined here, but "warm" also = "warm cache" (bg:29, fig. cost) with a different meaning | "warm sandbox" vs "files in the page cache" |
| 52 | bg:8 | "snapshot" | J: the memory image of a started sandbox; ok | keep |
| 53 | bg:12 | "waiting for a free slot" | U: "slot" first used undefined (defined by usage bg:91, never defined) | "a slot is room for one invocation to run at a time on a worker" |
| 54 | bg:13 | "making the machine able to run this tenant's code" | S/C: euphemism for attest + key release | name the two steps |
| 55 | bg:17-21 | "L0..L3" and "level" | C: "level", "start-up level", "state", "lifecycle", "lifecycle-aware placement" (results:47, discussion:4), "warm sandbox", "cache tier" | call them "start levels L0-L3"; drop "lifecycle" |
| 56 | bg:18 | "L0 nothing on the machine ... checked" | ok but L0-L3 reused as per-function while key held is per-tenant (design:79) | say "key" is a separate flag |
| 57 | bg:22 | "choosing which functions to keep at which level on which machines is already a scheduling problem" | S | fine as problem statement; add what is optimised (memory vs start time) |
| 58 | bg:27 | "TPM, the security chip" | AB (see #1) | expand |
| 59 | bg:30 | "attested worker" | U until #31 fixed; "attestation" defined only at bg:54 | forward reference or move rats paragraph before |
| 60 | bg:31 | "upper bounds" | S | "slower than a tuned deployment would be" |
| 61 | bg:44 | "Mbit/s", "medians" | ok | |
| 62 | bg:46-50 | "planner prepares machines", "per-request step charges each candidate" | I: "charges", "candidate" undefined here; "planner" and "per-request step" | "request placement estimates, for each candidate machine, the time to fetch what is missing" |
| 63 | bg:49 | "registry" | U until design:40 | "the provider's store of encrypted code" |
| 64 | bg:54 | "IETF attestation architecture (RFC 9334)" | J,AB: IETF, RATS | drop the name of the RFC family or expand |
| 65 | bg:55 | "registers of its TPM" | J: PCR | "measurement registers (PCRs)" or drop |
| 66 | bg:56 | "quote" | defined; fine | |
| 67 | bg:57 | "verifier", "certificate chain back to the chip's manufacturer" | J | "the manufacturer's certificate proves the signing key belongs to a genuine TPM" |
| 68 | bg:58 | "key service" | U: first use without owner; (design:43 says tenant's) | "a service run by the tenant" |
| 69 | bg:60 | "the evidence goes stale" | C | "a quote proves the state only at that instant, so it must be repeated" |
| 70 | bg:64 | "session" | defined here, 3rd page | move to intro |
| 71 | bg:65 | "heavy-tailed" | J | "most sessions are short, a few are very long" |
| 72 | bg:66 | "with notice from the owner" | C: "notice" / "announced departure" / "request to leave" (trust:47) | "owner notice" once |
| 73 | bg:66 | "sometimes for a whole city at once" | I: "correlated shocks" (method:15), "failure domain" (loops fig) | "correlated departures (e.g. a city-wide outage)" |
| 74 | bg:67-68 | crash / omission / timing | ok; but "crash" is also called "stop" and "churn produces crashes" | keep |
| 75 | bg:70 | "adaptive ... phi-accrual detector" | J, SY: phi | gloss "a detector that adapts its timeout to heartbeat jitter" |
| 76 | bg:74 | "service class (synchronous ...; asynchronous; or low-priority background)" | J: "synchronous" not defined | "synchronous = the client waits for the answer" (gloss exists, inline) |
| 77 | bg:75 | "deadline" | I: deadline / target / SLO / "latency target" (G2) | "deadline" per request, "P99 target" per run; say both |
| 78 | bg:76 | "idempotent" | defined, fine | |
| 79 | bg:79-89 | long comparison of vendor retry semantics | 1x: heavy detail for one design assumption | shorten to two sentences |
| 80 | bg:91 | "slots for concurrent invocations" | see #53 | |
| 81 | bg:92 | "attest and give which tenant's key" | I: key release / provision / give | "release the key" |
| 82 | bg:94 | "G1-G4" | 1x: goals are never referred to again by label | cite them in results or drop labels |
| 83 | bg:96 | "bypassed within seconds" | S: no number | state the metric (detection time, Table faults) |
| 84 | bg:98 | "claim credit" (G4) | U: credit defined faulttol:72 | forward reference |
| 85 | bg:95 | "within the target" | U: which target (3 s? 5x warm run time?) | |

### 1.4 System design (sections/design.tex)

| # | file:line | term or phrase | problem | replacement / definition |
|---|---|---|---|---|
| 86 | design:7 | "warm sandboxes are prepared ahead of demand" | I,S: "demand" = request rate | "ahead of the requests that will need them" |
| 87 | design:8 | "as seen by the router or the scheduler" | S slogan form of "returned work" | restate with the metric |
| 88 | design:11 | "compromised provider learns little" | S/C | "learns only ciphertext and request metadata" |
| 89 | design:30 | "Provider services are assumed reliable" | I: contradicts "failure of provider's own services" (threat model) only by exclusion; make explicit | ok |
| 90 | design:32 | "router" | U: router in network sense? | "request router (a provider front end)" |
| 91 | design:34 | "resends the request or sends it to another cluster" / "spill" | C: "spill" (failover fig "spill sync"), "spilling" (faulttol:61) | "forwards to another cluster" |
| 92 | design:37 | "orchestrator" | 1x-ish coined; first appears intro:51 as "coordinator" | define: "the provider service that groups workers into clusters and appoints schedulers" |
| 93 | design:38 | "certificate authority" | AB (CA used in fig. comment? no) fine; but "session certificate" undefined until trust:52 | forward ref |
| 94 | design:40 | "broker ... between a cluster's machines" | J | #11 |
| 95 | design:46 | "attested image", "locked, measured operating system" | I: image / appliance (arch, loops fig) | "attested image" only; relabel figure |
| 96 | design:49 | "scheduled or dedicated session rather than background use" | C: introduces tiers (nightly, idle-hours, dedicated) that appear only method:15 | define tiers or delete |
| 97 | design:55 | "organise scheduling" | | |
| 98 | design:57 | "One global scheduler ... plans and places" | I: "places" = request placement; "plan" | "plans and assigns" |
| 99 | design:61 | "Geographic clusters" | I: geographic clusters / clustered architecture / geo-clustering / dynamic clusters / static regions / "scheduling domain" | "clusters"; one name; "geo-clustering" only as result label |
| 100 | design:62 | "planning problem stays small" | S | "at most about 30 workers per planner call" |
| 101 | design:72 | "hedge" | defined parenthetically here; intro/abstract use "duplicate" | choose "hedge (send a second copy)" at first use, abstract included |
| 102 | design:72 | "at whatever level it has reached" | C | "at whichever of L0-L3 the function is currently at on that worker" |
| 103 | design:72 | "Each part of the latency is logged separately" | S | "latency is split into five logged components (wait, key, start-up, network, run)" |
| 104 | design:75 | "Sessions" subsection label `sec:lifecycle` | I: label "lifecycle" vs text "session" | rename label |
| 105 | design:80 | "reads these two facts ... from a data file for each trust technology" | I,C: file / substrate profile (code) / trust technology; label `sec:substrates` | "trust technology" in text; rename label |
| 106 | design:84 | "typed messages", "mutual TLS" | J,AB: TLS | "TLS, in which both ends present certificates" (given) |
| 107 | design:87 | "State lives where it is created" | S | "queues and caches on workers; unassigned requests at routers; estimates in the scheduler" (given after) keep the list, drop the slogan |

### 1.5 Trust (sections/trust.tex)

| # | file:line | term or phrase | problem | replacement |
|---|---|---|---|---|
| 108 | trust:4 | "attestation turns a hostile owner into an unreliable one" | S | "after attestation, the worst an owner can do is stop or delay a worker" |
| 109 | trust:5 | "limit how many machines hold each key" | C: "limit exposure" / "key exposure" / "exposure term" / "exposure weight" | define once |
| 110 | trust:10 | "our measured image" | J: "measured" = hashed during boot | "an image whose boot is hashed (measured) into the TPM" |
| 111 | trust:14 | "cold-boot attack" | J | "reading RAM after power-off" |
| 112 | trust:26 | table: "fake a TPM", "replay" | J | |
| 113 | trust:26 | "a disk key sealed to the measurement" | J,C | "a disk key that the TPM releases only to the expected image" |
| 114 | trust:33 | "Property 1" | 1x label; used in faulttol:4, method:17 | keep, but number is odd with no Property 2 → "Claim" |
| 115 | trust:38 | "running every task on several machines is no longer needed" | | ok |
| 116 | trust:41 | "proofs that let a client verify a computation" | J | "zero-knowledge / verifiable computation" |
| 117 | trust:41 | "Confidential virtual machines" | J,AB | "VMs with encrypted memory (AMD SEV-SNP, Intel TDX)"; these acronyms appear in method:25 unexpanded |
| 118 | trust:50 | "session key pair", "session certificate" | I: session key / session public key / session certificate; "session" now three meanings | fine; define "session" once earlier |
| 119 | trust:52 | "trust score" | I: = "assurance" (attest fig, loops fig), "a_j", "reliability times trust score" (scheduling:134), "trust level" | use "trust score" and relabel figures |
| 120 | trust:56 | "Trust is perishable" | S, C | "A certificate lasts at most one session, so trust must be re-earned after every reboot" |
| 121 | trust:57 | "identity costs hardware ... Sybil" | J: Sybil | "one person cannot fake many workers without many TPMs" |
| 122 | trust:56-58 | "endorsement key" | J (EK in attest fig, undefined) | "the TPM's factory-installed identity key (EK)" |
| 123 | trust:72 | "provisioned" | I: "provisioned for the tenant" (trust) vs "provisions q_t slots" (scheduling:89) vs "provisioned machines" (loops fig) vs "provisioning on demand" (intro) | reserve "holds the key"; drop "provisioned" |
| 124 | trust:76 | "policy" / "tenant's policy" | U: "accept image versions at or above"; policy also names code-level scheduling "policy" (method:10) | "tenant rule" for key service; "decision rule" for scheduler |
| 125 | trust:84-85 | "key exposure" E_t | C: central coined metric | "key-holder count, weighted by distrust" |
| 126 | trust:87 | $E_t$, $a_j$, sum over j | SY: j/t not named in words | "E_t is the tenant's exposure; j runs over workers holding t's key; a_j is j's trust score" |
| 127 | trust:87 | E also = expectation (scheduling:72) and experiment ids E01-E24 | I | rename to X_t or "exposure(t)" |
| 128 | trust:90 | "trust score a_j ... 0.8 ... 0.95" | numbers unsourced | tag "assumed, literature seed"; say who sets them |
| 129 | trust:91 | "known-good list" | C | "list of firmware versions we consider safe" |
| 130 | trust:92 | "Exposure ... not a probability of compromise" | S-risk: reader will treat as risk | add "units are 'distrust-weighted machines'" |
| 131 | trust:102 | "99th-percentile latency changes by \AblExposureP s" | U: P99 before definition (method:40) | define P99 in intro |
| 132 | trust:108 | "trust technology" | C: = "substrate" (code/labels), "trust mechanism", "platform" | keep "trust technology"; define: "a way a machine proves trust: TPM image, SEV-SNP VM, ..." |
| 133 | trust:108 | "five trust technologies" | list at 110-113 has "measured hypervisor" and "no attestation" which are not technologies | "four technologies and a no-attestation control" |

### 1.6 Scheduling (sections/scheduling.tex)

| # | file:line | term or phrase | problem | replacement |
|---|---|---|---|---|
| 134 | sched:4 | "made trust a resource with a price" | S, C | "showed that attesting a machine costs time and key exposure" |
| 135 | sched:7 | "Why two loops" / "two loops" / "two parts" / "slow loop / fast loop" (loops fig) / "two-timescale" | I: loop / part / step | "planner (every 30 s)" and "request placement (per request)"; drop "loop" |
| 136 | sched:9-14 | "horizons" (table label), "refresh period" | C | "how fast the input changes / how long the decision lasts" |
| 137 | sched:10 | "busy slots" | U (see #53) | |
| 138 | sched:36 | "from a forecast, ahead of time" | S | ok; keep |
| 139 | sched:38 | "demand is still covered" | C: "covered demand" (from earlier "uncovered demand") undefined | "the tenant's expected simultaneous requests still fit in the reserved slots" |
| 140 | sched:43 | "share one view of the cluster" | C: "view" (method:10 "immutable views") | "a shared snapshot of reported state" |
| 141 | sched:44 | "earlier if demand or membership changes sharply" | C: "membership" | "when request rate or the set of live workers changes sharply" |
| 142 | sched:46 | "reserved for each tenant" slots | C | |
| 143 | sched:46 | "Request placement" vs section label `sec:placer`, "placement" (placement subsection also in network `sec:placement` = where the scheduler runs) | I: "placement" has two meanings: assigning a request to a worker, and hosting the scheduler on a volunteer (network:62, table `tab:placement`) | rename the network one "Where the scheduler runs" |
| 144 | sched:47 | "plan actions" | C | "preparation commands (fetch key, warm sandbox)" |
| 145 | sched:47-48 | "design choice, not a measured optimum" | OK, honest | |
| 146 | sched:61 | "five times the function's run time on a warm sandbox, plus 50 ms" | U: why; deadline vs 3 s target | give rationale or tag assumed |
| 147 | sched:62 | "misses" | C: noun; "deadline missed", "miss rate", "P^miss" | "misses its deadline" (first), then "miss" |
| 148 | sched:65-68 | Eq. J: $J_{ij}$, $w_i$, $P^{miss}_{ij}$, $\varepsilon$, $\lambda$, $x_{ij}$, $\mathbb{E}[T_{ij}]$ | SY: only described afterwards; "J" is not named in words; $w_i$ (request weight) never explained beyond "=1 for synchronous" | "J is the cost of putting request i on worker j: weighted chance of missing + 0.05 per expected second + key exposure" |
| 149 | sched:68 | $\lambda$ in Eq. J (exposure weight) vs $\lambda_t$ (Poisson rate, sched:87) vs "lambda" in `Lambda-like` | I: symbol clash | rename exposure weight $\mu$ |
| 150 | sched:74 | "the tenant's sensitivity" | U: never defined (low / medium / high appear only in results:86) | "tenant-chosen weight on key exposure (low/medium/high)" |
| 151 | sched:75-77 | "one second counts as much as a 5-point rise" | S-ish but numeric; weights unsourced | tag "assumed" |
| 152 | sched:81 | "minimises cost while keeping enough capacity ready" | S/I | "minimises memory + exposure + key-release churn subject to a coverage constraint" |
| 153 | sched:87 | "slots", "provisioned slot", "Poisson", "$q_t$, $s_t$, $\lambda_t$" | SY, J: Poisson | "random arrivals at constant average rate"; define q_t as "the number of slots to reserve" |
| 154 | sched:89 | "the 95th percentile of that distribution" | J: coined as "demand quantile" earlier; now "95th percentile"; no reason for 95% | "the smallest number of slots that is enough 95% of the time" |
| 155 | sched:91 | "finds none goes to a worker without the key" | C: formerly "unprovisioned path" | "slow path (key release + start-up)" |
| 156 | sched:94 | "tolerates the loss of any f machines", $c_{tj}$, $e_j$, $u_t$ | SY: $e_j$ explained; $u_t$ "shortfall" ok; "f" never says what its default means for a 30-worker cluster (3) | add numeric example |
| 157 | sched:98 | Eq. robust | S-ish: wording "after removing the f workers that contribute most" is fine; label "robust" | rename "worst-case coverage constraint" |
| 158 | sched:98-105 | "robust", "robustness", "robust planner" (loops fig), "robust-coverage constraint" (results:71), "protection against losing f machines" (results:47), "f=0" | I: five names | "worst-case coverage ($f$)" and use it throughout |
| 159 | sched:103 | "so no model of an adversary is needed" | S | |
| 160 | sched:104 | "Bertsimas and Sim ... linear constraints ... integer-program solver" | J | one-line gloss |
| 161 | sched:105 | "f is a tenth of the cluster" | I: Fig. loops "any f machines" | |
| 162 | sched:107-110 | "key releases compared with the previous plan" | C: churn of plan | "number of keys newly sent" |
| 163 | sched:109 | "caps ... one city or one internet provider" | I: elsewhere "failure domain" (loops fig), "correlated shocks" | "diversity cap: no more than X% of a tenant's slots in one city or one ISP" (state X; none given) |
| 164 | sched:114-122 | "Reported / Learned / Forecasts / Fixed" numbers | C: four-way taxonomy used once | keep as a table or delete; used only to say "no future knowledge" |
| 165 | sched:119 | "declared speed" | C | "speed reported by the owner" (a hint, not evidence, per threat model) |
| 166 | sched:120 | "the code forbids the scheduling policies from importing the simulated world" | J,S: software-engineering mechanism | "policies receive only snapshots of reported state, never the simulator's hidden state" |
| 167 | sched:126 | "at most 40 workers", "20 tenants and 50 functions" | numbers unexplained | tag as caps |
| 168 | sched:130 | "mixed-integer program" | J,AB (MILP macro) | "exact planner = integer-programming solver (HiGHS)" |
| 169 | sched:130 | "exact planner" / "greedy planner" / "MILP" (macros) / "exact solver" (results, intro) | I | "exact planner"; "solver" only for HiGHS |
| 170 | sched:132-135 | "ratio of reliability times trust score to memory and exposure cost" | C,I: "reliability" (= $e_j$? = reliability score?) | name which quantity |
| 171 | sched:137 | "In a pilot" | 1x, unreported | cite table |
| 172 | sched:141 | "beyond a tolerance" | S | give threshold |
| 173 | sched:142-143 | "Actions are safe to repeat" | J: idempotent (used for functions elsewhere) | "idempotent" consistent |
| 174 | sched:147 | `\label{sec:placer}`, discussion:12 "cost-based placer" | 1x: "placer" survives | "request placement" |
| 175 | sched:149 | "12 candidates" | numeric, why | tag |
| 176 | sched:149 | "candidates" | U: first use here though loops fig and bg:48 use it | define |
| 177 | sched:156 | "shifted log-normal" | J | "a long-tailed distribution fitted to the sum" |
| 178 | sched:157 | "minimum-cost matching" | J | "optimal one-to-one assignment" |
| 179 | sched:160 | "overloaded", "rejected", "deferred" | C: admission control unnamed | "admission control" |
| 180 | sched:163-165 | "duplicates", "hedge", "slower copy is cancelled" | I with design:72 "hedge" and abstract "duplicates"; "10% of placements" budget | "hedge" |
| 181 | sched:171 | "Four estimators" | C: "estimator" (= predictor); and the named list: Session survival / Dropped work / Run time / Request rate vs. loops fig "survival, omission rate, assurance, failure domains, forecast demand" | match names to figure |
| 182 | sched:173 | "$S_j(\tau)$" | SY | "chance session lasts another tau seconds" (given) |
| 183 | sched:174 | "Weibull", "maximum likelihood", "censored", "Kaplan-Meier", "hazard", "shape/scale" | J | one-sentence gloss each or move to appendix |
| 184 | sched:181 | "prior (shape 0.7, scale 2 h)" | assumed number; untagged | tag |
| 185 | sched:184 | "Dropped work ... $p_j$", "Beta distribution" | I: "omission rate" (fig), "dropped-work", "loss rate" (sched:189), "black hole" | "drop probability" |
| 186 | sched:188 | "CUSUM change detector" | AB,J | "CUSUM (cumulative-sum test for a jump in a rate)" |
| 187 | sched:191-199 | "Run time ... Bayesian ... forgetting factor ... conformal calibration ... Gaussian processes ... BART" | J: five techniques in 9 lines, each used once | trim to what is used; conformal glossed |
| 188 | sched:191 | "function $f$" | SY clash: $f$ is also the failure count | rename |
| 189 | sched:201 | "Request rate ... two exponentially weighted averages ... take the larger" | J | "moving averages with 1-min and 15-min memory; take the larger" |
| 190 | sched:204 | "Holt-Winters" | J, 1x | drop |
| 191 | sched:207 | "copied to the provider every 30 s" | C: "checkpoint" in failover fig | one name |
| 192 | sched:210-212 | "hysteresis" | J, 1x | "only after a sustained change" |
| 193 | sched:212 | "round-trip time" | AB: RTT never used, fine | |
| 194 | sched:212 | "clusters of about 30 (10-60)" | I: "tens of machines" (design:61, arch fig), "20 to 35 attested hosts" (results:90) | one number |
| 195 | sched:214-217 | router "scores each cluster ... explicit price" | S ending | delete last sentence or give measured outcome |

### 1.7 Network (sections/network.tex)

| # | file:line | term or phrase | problem | replacement |
|---|---|---|---|---|
| 196 | net:11 | "network address translation" | J,AB (NAT) | ok as given; add the acronym used later (broker fig no) |
| 197 | net:17 | "HTTP and gRPC" | J,AB | "ordinary web-style request-response (HTTP, gRPC)" |
| 198 | net:19 | "Hole punching" | J, 1x | drop or gloss |
| 199 | net:26 | "topics" | J (pub/sub) | "named mailboxes" |
| 200 | net:39 | "MQTT", "at-least-once delivery" | J,AB | "MQTT (a lightweight publish/subscribe protocol)" |
| 201 | net:41 | "epoch" | U: first use here (defined faulttol:32) | forward reference or define in design |
| 202 | net:44 | "Replacing a scheduler becomes simple." | S | "A replacement subscribes to the same topic; no address changes" |
| 203 | net:48 | "The broker cannot forge messages." | S-ish | "cannot create or alter messages without detection" |
| 204 | net:51 | "sequence number" | J | |
| 205 | net:57 | "Costs." "extra hop", "0.46 KB/s per worker in a scalability pilot" | U: "pilot" unreported | cite table |
| 206 | net:62-64 | "Why the scheduler is on a volunteer machine at all" | I: `sec:placement` | see #143 |
| 207 | net:66-68 | "0.9 processor cores", "450 cores" | numeric, "planning times we measured" | which measurement |
| 208 | net:70 | "scheduling domain" | C, I: = cluster | "cluster" |
| 209 | net:74 | "E05" | U: experiment id, first use | "(experiment E05, Section 6.4)" or drop ids |
| 210 | net:93-94 | "behind a relay (15%) ... stands in for the broker hop" | C: "relay" vs "broker" | "relayed share" definition |
| 211 | net:97 | "the comparison is therefore tilted towards the clustered design" | I with results:92 "favours clusters" but results show clusters lose: clarify the direction | |

### 1.8 Fault tolerance (sections/faulttol.tex)

| # | file:line | term or phrase | problem | replacement |
|---|---|---|---|---|
| 212 | ft:4 | "By Property 1, the same mechanisms must handle crashes, churn and malicious owners" | S | |
| 213 | ft:7 | "Judging machines by returned work" | I: returned work / progress-based detection / progress evidence / "dispatch timer" / "result timer" / "progress watchdogs" (arch fig) | one: "returned-work detection" |
| 214 | ft:8 | "heartbeat" | defined here; intro:28 earlier; abstract earlier | define at abstract |
| 215 | ft:10 | "black hole" | C, J: used 4x (ft, results:59, failover fig "black-holes") | "silent drop (the worker accepts work and never returns it)" |
| 216 | ft:11-13 | "as observed by a party that cannot be faked", "their observations are honest" | S | "observed by a router (provider hardware) or by attested code" |
| 217 | ft:15 | "dispatch timer", "result timer" | C | "request-acknowledgement timeout (1 s)", "result timeout" |
| 218 | ft:17 | "predicted 90th-percentile completion time times 1.2, and at least 3 s" | numbers, tag | |
| 219 | ft:18 | "stalled", "STALL(cluster, 7)" fig | C | "reported unresponsive" |
| 220 | ft:20 | "treats more than 200 ms as a failure" | U: of what; "place requests" | |
| 221 | ft:22 | "a working heartbeat never clears a suspicion" | S-ish | state rule |
| 222 | ft:27 | "consensus protocol" | J | gloss |
| 223 | ft:29 | "referee" | C, 1x | "the orchestrator decides who is scheduler" |
| 224 | ft:32 | "epoch", "atomic compare-and-swap" ("CAS" in failover fig) | J,AB | "epoch = counter of scheduler appointments for a cluster; the orchestrator increments it atomically so only one successor wins" |
| 225 | ft:33 | "much like a lease [Chubby]" | J | "lease = permission that expires unless renewed" |
| 226 | ft:35 | "shut out" | S | "rejected" |
| 227 | ft:36 | "one lease period (5 s)" | | state in table with other timeouts (1 s, 3 s, 5 s, 60 s, 200 ms) |
| 228 | ft:41-45 | "Rebuilding the state", "roll call" (fig), "pins" (fig), "checkpoint" (fig), "outcomes" | C | glossary |
| 229 | ft:47 | "ranked list of candidates" | C | |
| 230 | ft:50 | "a clean handover" | C | |
| 231 | ft:60 | "retry storms" | C, 1x | "retries overloading the cluster" |
| 232 | ft:65 | "Receipts and credit" | I: credit vs reputation vs reliability score vs "trust score" | single set: credit (payment), reliability score (history), trust score (hardware) |
| 233 | ft:68 | "benchmark units" | C | "units of work defined by a fixed benchmark function" |
| 234 | ft:72 | "credit" | I (see 232); used before at bg:98 | |
| 235 | ft:73 | "reliability score" | C, 1x-ish (also scheduling:134 "reliability", results:94-96, discussion:10) | define as "long-term fraction of declared commitments kept" |
| 236 | ft:76 | "signed append-only log" | J | "tamper-evident log" |

### 1.9 Method (sections/method.tex)

| # | file:line | term or phrase | problem | replacement |
|---|---|---|---|---|
| 237 | method:4 | "calibrate" | J | "set its time constants from measurements on one real laptop" |
| 238 | method:7 | "discrete-event simulator" | J | |
| 239 | method:9 | "content-hashed traces" | J | "fixed random traces, hashed so two systems face the same world" |
| 240 | method:10 | "Policies see only immutable views" | J (and software-engineering) | |
| 241 | method:12 | "**Nothing is free.**" | S | "All message, disk, CPU, quote and decision times are charged as simulated delay" (second sentence already says this) |
| 242 | method:12 | "last-mile", "jitter", "log-normal" | J | |
| 243 | method:13 | "placeholders from the literature, not measurements" | OK but "placeholder" (also "placeholder bundle", `\CalRebootPh`) vs "assumed" vs "literature seed" | three words for one status: use "assumed" |
| 244 | method:15 | "three tiers (nightly, idle-hours, dedicated)" | U: not defined | define |
| 245 | method:15 | "correlated shocks" | C | "correlated departures" |
| 246 | method:16 | "SeBS", "skewed popularity", "day-and-night arrivals" | AB,J | |
| 247 | method:17 | "$\alpha$" | SY: defined as fraction; fine; "adversaries" vs "owners who drop work" vs "malicious owners" | |
| 248 | method:21 | "calibration bundle" | C, 1x-ish (method, results:111 "bundles") | "a file of measured timings" |
| 249 | method:22 | "harness reboots it", "microbenchmarks" | J | |
| 250 | method:28 | "E01" ids; "single-box emulation", "donor slices" | C | "emulation on one machine with real microVMs" |
| 251 | method:29 | "graded 'partly' close" | C (the `\ok`/`\partly` macros) | state the cut-offs |
| 252 | method:29 | "P99 of about 530 requests is the five slowest" | OK; P99 defined at method:40 only | move definition to intro |
| 253 | method:34 | "frozen specification", "cell", "seed" | C | "cell = one parameter setting; seed = one random world" |
| 254 | method:34 | "paired by seed" | J | |
| 255 | method:35 | "bootstrap interval" | J | |
| 256 | method:37 | "supported / weak / inconclusive / refuted" | C but defined | keep |
| 257 | method:38 | "also fails if a result stops supporting the sentence it backs" | S-ish | |
| 258 | method:40 | "feasible" | C: defined here only; "viable" label `sec:res-viab`, "meets target", "works" | keep "feasible"; state both thresholds up front (0.99 success and 95% deadlines or P99 target) |
| 259 | method:40 | "P99" | AB: defined only here, used since abstract (99th-percentile) and in trust, bg, intro | define at first use |
| 260 | method:40 | "extra attempts per successful request" | C | "wasted copies" (results:80 "wasted") |
| 261 | method:42 | "baselines": "no planner", "keep-alive timer", "heartbeat-only", "$f=0$", "simple baseline", "Lambda-like", "Azure-like" | U: first defined here but used in abstract/intro | gloss in intro |
| 262 | method:42 | "least-loaded placement" | J | |
| 263 | method:47 | "bit-reproducible", "canary hash" | J | |
| 264 | method:48 | "AVX-512", "SSE4", "NumPy" | AB,J | move to appendix |
| 265 | method:49 | "2,366 of 2,366 hashes" | 1x | |

### 1.10 Results, discussion, related, conclusion, appendix

| # | file:line | term or phrase | problem | replacement |
|---|---|---|---|---|
| 266 | results:6 | "H5", "H-FT1", "H1", "H2", "H3", "H4", "H6", "H7", "H8", "H10", "H11", "H-FT3" | C: hypothesis ids defined only in appendix table | include a one-clause hypothesis or drop ids |
| 267 | results:8 | "\SimApplSession", "Appl", "confidential-container pool", "Coco" | AB,J | |
| 268 | results:9 | "10 to 100 times slower ... refuted" | OK | |
| 269 | results:14 | "feasibility map", "cell" | C | "table of scenarios coloured by which system meets the target" |
| 270 | results:14 | "(success at least 0.99 and 95% of deadlines met)" | duplicates method:40 with a different condition (method says either P99 or deadlines) | one rule |
| 271 | results:19-20 | "panel A/B/C" | C | |
| 272 | results:24 | "only feasible system", "\ViabBMetOnly" | | |
| 273 | results:27 | "wrong choice" | S | |
| 274 | results:28 | "needs a minimum population" | S | state the number (few hundred) |
| 275 | results:32 | "synchronous P99", "single-loop alternatives" | I,C: "single-loop" | "reactive rules" |
| 276 | results:33 | "donor memory", "warm memory" | I: donor / owner | |
| 277 | results:36 | "Met", "Warm" in table caption | C | spell out |
| 278 | results:42 | "\MilpGreedy... below our 5% threshold" | 5% threshold unexplained in this section | |
| 279 | results:43 | "simulated clock charges both about 0.1 s" | J | |
| 280 | results:45 | "single-loop rule", "pre-warming" | C | |
| 281 | results:47 | "Making request placement ignore start-up levels" | I with discussion:4 "lifecycle-aware placement" | one name |
| 282 | results:47 | "removing planning", "removing hedging", "removing the protection against losing f machines" | I | |
| 283 | results:48 | "key exposure ... units" | U: units | |
| 284 | results:48 | "Geo-clustering" | I (see #99) | |
| 285 | results:57 | "progress-based detection" | I (see #213) | |
| 286 | results:59 | "a 60 s timeout" | U: not in the ft section (heartbeat timeout 60 s never stated there) | |
| 287 | results:60 | "failover", "slowed but live scheduler", "evidence must build up" | C | |
| 288 | results:69 | "otherwise identical machinery" | S | |
| 289 | results:70 | "attested owners who drop work behave like churn" | S: no measure | "success within X points of the churn-only run" |
| 290 | results:71 | "Detection and re-dispatch carry success; robust planning buys tail latency." | S | give numbers |
| 291 | results:80 | "Always sending a duplicate", "wastes" | I (hedge) | |
| 292 | results:80 | "cheap insurance" | S | |
| 293 | results:84-86 | "Robustness f", "exposure weight", "knee", "operating point" | J: Pareto vocabulary (`sec:res-pareto`, "trade-off front", "Pareto") | "the point beyond which more f buys little" |
| 294 | results:86 | "sensitivity" | U (see #150) | |
| 295 | results:88 | "earn their complexity" (also discussion:12) | S | "improve a measured outcome" |
| 296 | results:90 | "static regions, static k-means, dynamic clusters", "plans over at most 40 hosts" | J,U: k-means | gloss |
| 297 | results:94 | "nearest-region routing", "least-loaded routing", "flash crowds" | J | |
| 298 | results:95 | "cost-aware caching with peer fetch and a disk tier ... plain LRU" | U,AB: LRU unexpanded; cost-aware caching never introduced in design | "least-recently-used (LRU) eviction" |
| 299 | results:95 | "start about 98% of invocations from a warm sandbox" | | |
| 300 | results:96 | "settlement" | C: receipts settled | "payment" |
| 301 | results:96 | "Gini" | J | "inequality index (0 equal, 1 one worker has all)" |
| 302 | results:96 | "RepPNinetyninePct" "reliability score" | I | |
| 303 | results:100 | "homogeneous, stable, benign pool" | C | |
| 304 | results:101 | "trade-off front of the previous section" | J | |
| 305 | results:103 | "list prices", "fixed tier", "control plane" | J: control plane | "the provider's always-on servers" |
| 306 | results:106 | "cheaper mode (coarse heartbeats...)" | U | |
| 307 | results:107 | "decision path", "decision P99" | C | "time the scheduler takes to decide" |
| 308 | results:116 | "as informative as the supported ones" | S | |
| 309 | discussion:4 | "lifecycle-aware placement" | I | |
| 310 | discussion:9 | "coverage guarantee" | C: = worst-case coverage constraint | |
| 311 | discussion:12 | "cost-based placer", "epoch-fenced failover", "greedy robust planner" | C,I: "placer" survives; "fenced" J | "request placement with hedging", "failover using epochs" |
| 312 | discussion:14 | "**Exposure is the price of latency.**" | S | "To lower P99 by X% the plan gives keys to Y% more machines" |
| 313 | discussion:15 | "trust technology and minimum population matter more than tuning" | S, unsupported by a sweep | |
| 314 | discussion:17 | "exposure would stop being a proxy for risk" | S | |
| 315 | discussion:19 | "scheduling domains" | I (#208) | |
| 316 | discussion:22-28 | "Erlang loss system", "marginal analysis", "diminishing returns", "approximation guarantees", "better-founded planner" | J,1x: designed but unevaluated | one paragraph in Future work |
| 317 | discussion:30 | "look-ahead warming", "speculation", "workflows" | 1x | |
| 318 | discussion:37 | "adaptive adversary", "fixed menu of strategies" | C | |
| 319 | discussion:45 | "relayed share" | C (#210) | |
| 320 | related:4 | "gray failures", "verifiable records of work" | I (receipts) | |
| 321 | related:17-19 | "Sparrow", "Falcon", "Borg", "ALPS" | J: named systems not described to a non-serverless reader (1x each) | one clause each (Sparrow already) |
| 322 | related:24-31 | "Lyapunov drift-plus-penalty", "Gibbs sampling", "approximation guarantee" | J, 1x | drop or gloss |
| 323 | related:33 | "Harvested ... evictions" | J: "harvest" | "spare datacenter capacity" |
| 324 | related:35 | "Trusted execution environments", "SGX" | J,AB | |
| 325 | related:41-43 | "Byzantine agreement", "trusted component (counter, log)" | J | |
| 326 | related:52 | "budgeted robust optimisation" | I (#158) | |
| 327 | conclusion:6-8 | "given a tenant's key and kept warm", "plans this state" | C: "state" = keys + warm sandboxes + snapshots | name them |
| 328 | conclusion:13 | "settings where simple baselines do not" | | |
| 329 | conclusion:16 | "loss-model planner" | C, U: only defined in discussion:22 as "Erlang loss" | |
| 330 | appendix:3 | "NumPy pin", "AVX-512" | J | |
| 331 | appendix:23-28 | commands `make paper-verify`, `voss repro` | 1x | |
| 332 | appendix:33 | "A dash marks cost-side information" | C | |

### 1.11 Figures (TikZ labels)

| # | file:line | term or phrase | problem | replacement |
|---|---|---|---|---|
| 333 | arch:6-11 | legend "provider / attested code / tenant / untrusted" | ok | |
| 334 | arch:15-16 | "Provider control plane", "availability and accounting, no tenant keys" | J: control plane; "accounting" 1x | "Provider services" |
| 335 | arch:18 | "pending copies", "progress watchdogs" | C,I: pending copies = held requests; watchdogs = dispatch/result timers | "held requests, timeouts" |
| 336 | arch:19 | "one topic set per cluster" | C | |
| 337 | arch:20 | "clusters, epochs, database" | U: epoch | |
| 338 | arch:23 | "tens of machines" | I (#194) | |
| 339 | arch:25 | "Worker (attested appliance)" | I,C: "appliance" (arch, loops) vs "image" | "attested image" |
| 340 | arch:25 | "agent and TPM quote ... sealed, encrypted cache" | J: sealed | |
| 341 | arch:27 | "Worker with scheduler role ... rebuildable state, epoch e" | SY: e vs $e_j$ (survival) | |
| 342 | arch:32 | "Key service: secrets to attested hosts only" | I: host; macro "KBS" in the source name | |
| 343 | arch:33 | comment "hot path" | internal | (comment only) |
| 344 | arch:42 | "Other clusters have the same structure" | ok | |
| 345 | loops:6-9 | "Slow loop / Fast loop" | I: figure uses loop, text uses planner / request placement | relabel |
| 346 | loops:11 | "Estimates: survival, omission rate, assurance, failure domains, forecast demand" | I,C: 4 undefined names; text: session survival, dropped work, trust score, (no estimator for failure domains), request rate | use text names |
| 347 | loops:12 | "Robust planner ... any f machines fail" | I (#158) | |
| 348 | loops:13 | "Plan: who holds which key, which snapshots, how many warm sandboxes" | ok | |
| 349 | loops:14 | "Actions: prepare, pin, warm, release" | C: pin, prepare | "fetch, keep snapshot, warm, release key" |
| 350 | loops:17 | "provisioned machines, plus other attested ones" | I (#123) | "machines holding the key" |
| 351 | loops:18 | "Cost of each candidate: wait, trust, start-up, network, execution, failure risk, exposure" | I: text has five delays; "trust" ambiguous | align with sched:153 |
| 352 | loops:19 | "lowest risk-weighted cost" | C | "lowest J" |
| 353 | loops:22 | "confirmed state" | C | |
| 354 | loops:27 | "heartbeats" feeding estimates | I: contradicts "heartbeats never clear suspicion" if shown feeding the planner | label "load reports" |
| 355 | broker:6-27 | "Provider-hosted broker", "topic", "subscribe/publish" | J (#199) | |
| 356 | broker:26 | "pair of topics" | I: text says scheduler topic + per-worker + cluster-wide | |
| 357 | attest:4-12 | "PCRs", "EK chain", "event log", "replay event log against reference values" | AB,J | |
| 358 | attest:12 | "SESSION_CERT(id, key, assurance, expiry)" | I: assurance vs trust score | trust score |
| 359 | attest:10,13 | "ATTEST", "KEY_REQUEST" message names | C | |
| 360 | attest:18 | "$T_{\text{reattest}}$" | SY: value not given | |
| 361 | failover:3-9 | "Sched. epoch 7", "Orch. + DB", "Succes-sor", "ENQUEUE", "black-holes" | AB,C | |
| 362 | failover:10 | "$T_{\text{dispatch}}$", "spill sync" | SY,C | 1 s; "forward synchronous requests" |
| 363 | failover:12 | "CAS epoch 7 to 8; token binds successor's cert" | AB,J | |
| 364 | failover:13 | "APPOINT(8, checkpoint)" | C | |
| 365 | failover:15-16 | "EPOCH_INSTALL, ROLL_CALL, work, pins, keys, outcomes" | C | |
| 366 | failover:18-20 | "dedupe by id", "STALE" | J | |

## 2. Same concept, several spellings

| Concept | All spellings found | Proposed single name |
|---|---|---|
| Isolated function environment | environment, isolated environment, prepared environment, ready environment, sandbox, microVM, warm sandbox, warm state, Firecracker host | **sandbox** (warm sandbox when idle and ready) |
| Machine | machine, host, node, worker, volunteer machine, donor, donor slice, appliance, cluster member | **worker** (owner's machine running our image); **owner** for the person |
| Person | owner, volunteer, donor, adversary | **owner**; "adversarial owner" only in the threat model |
| Customer | customer, tenant, developer, client (client = the caller) | **tenant**; **client** for the caller |
| Scheduler's per-request part | per-request step, request placement, placement, placer, fast loop, assign, dispatch | **request placement** |
| Scheduler's slow part | planner, plan, slow loop, planning, first loop, robust planner | **planner** |
| Two parts | two loops, two parts, two-timescale, two-part scheduler | **planner + request placement** |
| Cluster | cluster, geographic cluster, clustered architecture, geo-clustering, scheduling domain, static regions, dynamic clusters | **cluster**; "geo-clustering" only as the name of the compared design |
| Trust checking | attestation, proving trust, establishing trust, trust step, making the machine able to run tenant code | **attestation** |
| Key delivery | key release, giving the key, provisioning, provisioned, key request | **key release**; "holds the key" for state |
| Trust score | trust score, assurance, $a_j$, trust level, reliability (in greedy ratio) | **trust score** |
| Key-leak metric | key exposure, exposure, exposure term, exposure weight, sensitivity | **key exposure**; tenant weight called **sensitivity** defined once |
| Worst-case coverage | robust, robustness, robust planner, robust-coverage constraint, protection against losing f machines, $f=0$, "fail together" | **worst-case coverage (f)** |
| Failure detection | returned work, progress-based detection, progress evidence, progress watchdogs, dispatch timer, result timer, judging machines by returned work | **returned-work detection** |
| Silent drop | black hole, black-hole, drops work, omission, discards, dropped work, omission rate, loss rate | **drop work** (verb), **drop probability** (number); "omission" only in the failure taxonomy |
| Second copy | duplicate, hedge, hedging, second copy, duplicates at risk | **hedge** (defined once) |
| Reward/history | credit, reputation (earlier drafts), reliability score, reliability | **credit** (payment) and **reliability score** (history) defined separately; no "reputation" |
| Latency percentile | 99th-percentile latency, P99, tail latency, synchronous P99, decision P99 | **P99**, defined in the introduction |
| Target | deadline, target, latency target, P99 target, SLO-like | **deadline** (per request); **P99 target** (per run) |
| Request | request, call, invocation, event | **request** for the arriving item, **invocation** for the execution |
| Trust mechanism | trust technology, substrate (labels/code), trust mechanism, platform | **trust technology** |
| No planner | no planner, provisioning on demand, reactive, single-loop, keep-alive timer | **reactive baseline**, with the two variants named |
| Saved state at scheduler | estimators' numbers, checkpoint, copy of the estimators, rebuildable state | **estimator checkpoint** |
| Timing symbols | $T_{dispatch}$, $T_{reattest}$, lease period, 1 s, 5 s | one parameter table |
| Experimental names | E01..E24, H1..H11, H-FT1/3, panel A/B/C, "cell", "setting", "scenario" | one convention, defined once |

## 3. Symbols not explained in words (or clashing)

| Symbol | where | problem |
|---|---|---|
| $f$ | scheduling:98-105, intro:59, loops fig | also "function $f$" at scheduling:191 |
| $\lambda$ | Eq. J (sched:68) vs $\lambda_t$ (sched:87) | two meanings |
| $E_t$, $\mathbb{E}[T_{ij}]$, E01-E24 | trust:87, sched:72, method | three meanings of E |
| $e_j$ vs $e$ (epoch, arch fig) vs $\varepsilon$ | sched:95, arch:27, sched:68 | three similar symbols |
| $a_j$, $x_{ij}$, $w_i$, $q_t$, $s_t$, $c_{tj}$, $u_t$, $S_j(\tau)$, $p_j$ | trust:87, sched | each defined once in a clause but not collected; no notation table |
| $J_{ij}$ | sched:68 | never called "the cost of placing"; read as a number |
| $\alpha$ | method:17 | fraction of adversarial owners; macros call it "Alpha" |
| $\varphi$ | bg:70 | not explained |
| $\tau$, $T_{reattest}$, $T_{dispatch}$ | sched:173, attest, failover figs | values/definitions not given in the text |
| "k" in k-means, "x" in $10^5$ | results | fine |

## 4. Abbreviations to expand at first use

TPM (main.tex:34), P99 (use from abstract), TLS (design:84), NAT (net:11 only partly), HTTP/gRPC (net:17), MQTT (net:39), CA (design:38 gives "certificate authority", no acronym; fine), PCR/EK/CAS/DB (attest and failover figs), IETF/RATS (bg:54), CUSUM (sched:188), LRU (results:95), MILP (macro names, results), HiGHS (sched:130), SeBS (method:16), SEV-SNP and TDX (method:25), CVM / "Coco" (results:8), SGX (related:36), BOINC (intro cites), AVX-512/SSE4/NumPy/glibc/NVMe (method:48-28, appendix), KBS (arch source name only), FaaS (not used; good), SLO, TTL, RTT (not used in the manuscript: do not introduce), GB/MB/KB/USD (fine), "Gini", "Weibull", "Beta", "Kaplan-Meier", "Holt-Winters", "BART", "Erlang", "Lyapunov", "Gibbs" (all one-use technical names).

## 5. Terms used once or twice only (candidates to delete or gloss in place)

perishable (trust:56), hysteresis (sched:212), retry storm (ft:61), referee (ft:29), hole punching (net:19), Holt-Winters (sched:204), Kaplan-Meier (sched:179), Gaussian processes and BART (sched:197), conformal calibration (sched:197), Lyapunov drift-plus-penalty (related:31), Gibbs sampling (related:27), Erlang loss system (discussion:24), look-ahead warming (discussion:30), flash crowds (results:94), settlement (results:96), tiers nightly/idle-hours/dedicated (method:15), "known-good list" (trust:91), scheduling domain (net:70, table, discussion), placer (sched label, discussion:12), Sybil (trust:58), cold-boot attack (trust:14), canary hash (method:48), shifted log-normal (sched:155), minimum-cost matching (sched:157), "gray failure" (2 uses, fine if glossed), G1-G4 labels (bg only), Property 1 (3 uses, ok), "sensitivity" (sched:74, results:86), "reported/learned/forecast/fixed" taxonomy (sched:114-119), "benchmark units" (ft:68), "assurance" (two figure labels), "failure domains" (loops fig only), "pins" (two figure labels), "ROLL_CALL" (failover fig).

## 6. Slogans and statements that do not say what is measured

| file:line | sentence | what should be said |
|---|---|---|
| intro:32 | "Our starting point is that proving which software a machine runs changes what a hostile owner can do." | Argument of Property 1; delete the slogan |
| intro:66 | "Planning has the largest effect" | planning reduces P99 by X% and ablation ranks it 1st or 2nd |
| trust:4 | "attestation turns a hostile owner into an unreliable one" | list of the owner capabilities that remain (stop, delay) |
| trust:56 | "Trust is perishable" | certificate lifetime in seconds/hours |
| sched:4 | "trust as a resource with a price" | price = attestation time + key exposure |
| sched:81 | "minimises cost while keeping enough capacity ready" | cost = memory + exposure + key releases |
| sched:214-217 | "Sending a request to another cluster is therefore a decision with an explicit price." | measured effect |
| network:44 | "Replacing a scheduler becomes simple." | number of messages / seconds |
| method:12 | "Nothing is free." | list of what is charged (already follows) |
| results:70 | "behave like churn once machines are judged by returned work" | success within N points of churn-only |
| results:71 | "Detection and re-dispatch carry success; robust planning buys tail latency." | Success and P99 deltas |
| results:80 | "cheap insurance" | waste percentage and P99 interval (follows) |
| results:88, discussion:12 | "earn their complexity" | improves P99/success by at least the pre-set margin |
| results:116 | "as informative as the supported ones" | |
| discussion:14 | "Exposure is the price of latency." | P99 saved per unit of exposure added |
| discussion:15 | "trust technology and a minimum population matter more than tuning" | no sweep supports "more than tuning" |
| discussion:17 | "exposure would stop being a proxy for risk" | |
| design:87 | "State lives where it is created." | |
| design:8 / intro:51 | "judged by whether the work it accepted comes back" | time to detection, success under alpha |
| background:96 | "bypassed within seconds" | detection time from Table faults |
| abstract | "keeps 99th-percentile latency under 3 s in N of M settings" | the 3 s is not derived; two different feasibility rules (3 s or 5x warm + 50 ms) |

## 7. Proposed outputs

### (a) The only terms the paper should define (each one line)

1. **Tenant**: a customer who deploys functions and holds their own decryption key.
2. **Owner / worker**: the person who donates a machine / the machine while it runs our attested image.
3. **Sandbox (warm)**: a small isolated virtual machine running one function; warm means already started and idle.
4. **Start level L0-L3**: how much of a function is already on a worker (nothing, files on disk, snapshot, warm sandbox).
5. **Slot**: capacity for one running invocation on a worker.
6. **Session**: the period from booting our image to the next reboot or power-off; all keys and warm sandboxes die with it.
7. **Churn**: owners switching machines off at any time.
8. **Attestation**: the machine proves to a verifier which software it booted; the verifier then issues a session certificate.
9. **Key release**: the tenant's key service sends the tenant's key to an attested worker, which holds it in memory only.
10. **Trust score** $a_j$: a number in [0,1] for how well a worker's hardware protects keys.
11. **Key exposure**: sum over key-holding workers of (1 - trust score); a distrust-weighted count of machines that hold the key.
12. **Planner**: every 30 s decides which workers receive which keys, snapshots and warm sandboxes, using forecasts.
13. **Request placement**: chooses a worker per request by the lowest cost $J$ (miss risk + expected time + exposure).
14. **Worst-case coverage ($f$)**: reserved capacity still covers forecast demand after the $f$ largest key-holding contributors are removed.
15. **Hedge**: a second copy of an idempotent request sent to a different city/ISP when miss risk is high.
16. **Returned-work detection**: a worker or scheduler is suspected when work it accepted does not come back in time; heartbeats never clear this.
17. **Drop work**: a worker accepts a request and never returns a result (omission); **delay** is the timing failure.
18. **Epoch**: a per-cluster counter, incremented atomically by the orchestrator, that identifies the one valid scheduler.
19. **Orchestrator / router / verifier / broker / key service**: the five named services (one clause each).
20. **Credit** (payment for benchmarked work) and **reliability score** (history of kept commitments): defined separately or dropped.
21. **P99** (slowest 1% of synchronous requests), **feasible** (success >= 0.99 and deadlines met >= 95%, or P99 below target), **idempotent**.

### (b) Terms to drop entirely

- Replaced by the single name above: appliance, environment (except as plain word), ready/prepared/provisioned (as a state), placer, per-request step, fast loop / slow loop / two loops, assurance, failure domain(s), omission rate (as an estimator name), progress watchdog(s), progress evidence, pending copies, black hole / black-hole, spill / spilling, substrate (text and labels), lifecycle (and "lifecycle-aware"), scheduling domain, geo-clustering (except as design name), robust planner / robust-coverage constraint, single-loop, cost-based placer, epoch-fenced failover.
- Slogans: "Nothing is free", "Trust is perishable", "Our starting point", "Replacing a scheduler becomes simple", "Exposure is the price of latency", "earn their complexity", "cheap insurance", "attestation turns a hostile owner into an unreliable one", "a decision with an explicit price", "State lives where it is created".
- One-use jargon that does not carry an argument: hysteresis, referee, retry storm, hole punching, Holt-Winters, Kaplan-Meier, Gaussian process/BART, Gibbs sampling, Lyapunov drift-plus-penalty, Erlang loss (move to one sentence in future work), look-ahead warming, flash crowds, canary hash, settlement, the Reported/Learned/Forecast/Fixed taxonomy, G1-G4 labels, tiers (nightly/idle-hours/dedicated) unless defined, "reputation" (already removed; keep removed), hypothesis ids in running text (keep in appendix table only), experiment ids E01-E24 (use section pointers).
- Symbol clashes to rename: exposure weight $\lambda$ -> $\mu$; function $f$ -> $\phi$ or word "function"; exposure $E_t$ -> $X_t$.

## 8. Count

366 numbered findings in section 1 (tables 1.1-1.11), plus 24 rows in section 2 (synonym groups), 10 in section 3 (symbols), the abbreviation list in section 4 and the one-use list in section 5 (about 30 terms) and 21 slogan rows in section 6.
