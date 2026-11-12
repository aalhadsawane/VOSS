# 00 · Overview (v2)

This overview describes v2 (`docs/REVISION_PLAN.md` §2, decisions D-81 to D-93). The other documents in this folder
still contain v1 material, marked by a status note at their top.

## 1. Problem

Run serverless functions whose synchronous invocations must finish within seconds on volunteer machines: machines that
owners lend for sessions of minutes to hours, that leave without notice, and whose owners the provider does not trust.

## 2. Premise

A worker boots a measured image and proves it by remote attestation (TPM quote checked by the provider's verifier)
before it receives any function key. Owner classes (D-84):

| Class | Owner can | Guarantee |
|---|---|---|
| S, software-only | boot other software, drop or delay messages, switch off | integrity and confidentiality; only omission and timing faults |
| P, physical access, no memory encryption | additionally read memory | no confidentiality; integrity bounded by sampled audit |
| M, memory-encrypted hardware | as S | as S, up to side channels |

## 3. Parties and components

| Component | Runs on | Role |
|---|---|---|
| Router | provider, several sites | public entry; forwards each invocation to the scheduler; streams input to the chosen worker without reading it; verifies signed receipts |
| Scheduler | provider, one node | provisioning and request placement; failure handling |
| Orchestrator | provider | membership: appoints the scheduler once, tracks which workers are attested and live |
| Verifier | provider | checks TPM quotes; issues session certificates |
| Registry | provider | stores function bundles and root file systems as ciphertext |
| Key service | tenant | releases a function's data key only to attested workers, within the tenant's holder budget |
| Worker | volunteer machine | runs invocations in Firecracker microVMs; holds keys only in memory |

## 4. Scheduling (D-86)

- **Provisioning** (periodic): per function, which workers hold its key, how many warm sandboxes each keeps, and how much
  concurrency each reserves, so that the demand quantile is covered after losing any `f` holders, within the holder
  budget `K` and memory.
- **Request placement** (per invocation): among holders, the worker with the lowest probability of missing the deadline.
- **Failure handling:** timeout at the predicted q95 completion of each attempt; immediate backup attempt on another
  holder for idempotent functions; per-worker drop estimate with ejection; sampled audit for forged results.

## 5. Invocation path

client → router (nearest site) → scheduler (metadata only) → router → worker (input) → router (result, receipt) → client.

## 6. Evaluation

Deterministic simulator with the real policy code, driven by public traces, calibrated on several real machines
(`docs/handoff/`), checked against a multi-worker emulation. Primary metric: share of synchronous invocations answered
correctly within their deadline (D-88). Experiments run on GitHub Actions (D-90).
