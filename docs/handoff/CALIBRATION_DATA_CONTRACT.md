# Calibration data contract (VOSS v2)

What the bare-metal session must deliver for each machine, why the simulator needs it, and how it is checked.
`tools/calibrate/check_bundle.py` (plan V1 step 8) enforces the "Check" column. Probe names in `code font` are the names the
harness logs; if the harness uses a different name, the harness is wrong, not this file (fix it in plan V1).

Rules for every value:
- tagged `measured`, with `n`, median, 5th and 95th percentile, and the raw samples kept in the raw archive;
- measured on this machine; never copied from another machine or from literature;
- missing stays missing: no estimates, no defaults.

A bundle that fails this contract is not used for any reported result (plan guardrail G14).

---

## 1. Machine specification (`calibration/specs/<host_label>/spec.yaml`)

| Field | Used for | Check |
|---|---|---|
| CPU model, family, generation | paper's machine table | present |
| Physical cores, hardware threads, core kinds (performance/efficiency) | concurrency limit = physical cores (plan V5.5) | integers; cores ≤ threads |
| Memory (MiB) | memory available to sandboxes | present |
| Each disk: type (HDD, SATA SSD, NVMe), capacity, sequential and random read/write throughput (`fio`) | bundle and snapshot load times | one entry per tier measured |
| TPM: manufacturer, family (discrete or firmware), firmware version | paper's table; explains quote time | present |
| Firmware: UEFI or legacy, vendor, version; Secure Boot state | paper's table | present |
| Memory encryption: supported (CPUID), enabled (firmware) | owner class M or not (plan §2 trust) | boolean each |
| Kernel version, Firecracker version, CPU governor, turbo state | reproducibility | present |
| `systemd-detect-virt` | must be bare metal | equals `none` |

## 2. Attestation and keys (no reboot)

| Probe | What | Used for | n ≥ |
|---|---|---|---|
| `tpm2_quote` | TPM quote over the PCR set the image uses | cost of attesting a session; re-attestation | 200 |
| `tpm2_unseal` | unseal of the cache-partition key under the PCR policy | boot step | 50 |
| `verify_quote` | verifier checks quote, certificate chain and event log; signs a session certificate | verifier time per session | 50 |
| `tls_handshake` | TLS 1.3 mutual handshake CPU time on this machine | every new connection to a worker | 1,000 |
| `key_request` | worker side of a key request over loopback TLS: new connection, 256-byte request, 256-byte reply (`keys` suite) | key fetch delay (with `key_unwrap`; ingest writes `key_release` = sum) | 200 |
| `key_unwrap` | one RSA-2048 private-key operation, unwrapping the function key (`openssl speed`) | key fetch delay | 1 run |
| `decrypt_per_MB` | seconds per MB of AES-256-GCM decryption on 1 MB blocks (`openssl speed`, `keys` suite) | start-up from an encrypted bundle | 1 run |
| `hash_per_MB` | SHA-256 throughput | integrity check of fetched files | 20 |

## 3. Boot of the real image (reboots; approval needed)

Per boot, one timestamp per step. At least 10 boots.

| Step | Probe |
|---|---|
| Firmware (power-on self-test to loader) | `boot_firmware` |
| Boot loader | `boot_loader` |
| Kernel start to initial RAM disk done | `boot_kernel` |
| dm-verity root set up | `boot_verity` |
| Cache partition unsealed and mounted | `boot_unseal` |
| System services up to agent start | `boot_services` |
| Agent start to quote requested | `boot_agent` |
| TPM quote | `boot_quote` |
| Verifier round trip (local verifier; network excluded) | `boot_verify` |
| Session certificate installed, first mutual-TLS connection | `boot_first_tls` |
| **Total power-on to attested worker** | `boot_total` (must equal the sum of the steps within 2%) |

Also from inside the booted image:
| Probe | What | Used for |
|---|---|---|
| `image_mem` | resident memory of the idle image (MiB) | memory available to sandboxes = total − this |
| `image_cache_bytes` | size of the cache partition | disk space for bundles and snapshots |

Check: every step present or explicitly listed as merged with a neighbour; `boot_total` consistent.

## 4. Sandboxes (per storage tier; cold and warm page cache)

| Probe | What | n ≥ |
|---|---|---|
| `fc_spawn`, `fc_configure`, `fc_boot`, `fc_init_done` | steps of booting a sandbox from kernel and root file system | 100 per configuration |
| `fc_pause`, `fc_snapshot_create` | steps of writing a snapshot | 50 |
| `fc_restore_spawn`, `fc_restore_load`, `fc_restore_first_response` | steps of restoring a snapshot until the first invocation is answered | 50 |
| `dispatch_warm` | handing an invocation to a warm sandbox until the handler starts (measured, not a model value) | 200 |

Configurations: sandbox memory sizes used by the workload functions; each storage tier the machine has; page cache cold
(`drop_caches`) and warm.

## 5. Functions (every function in `tools/calibrate/guest/functions/`)

| Probe | What | Used for | n ≥ |
|---|---|---|---|
| `fn_init` | initialisation (imports, model load) | cold-start cost | 30 |
| `fn_exec[size]` | handler time only, at SeBS's test, small and large input classes and two larger sizes | run-time model, deadlines, mapping of trace functions (plan V1 step 1, V9.1) | 30 per size |
| `fn_input_gen[size]` | time to build the input (reported, excluded from `fn_exec`) | sanity | 30 |
| `fn_rss` | resident memory of the running sandbox | memory admission | 10 |
| `snap_size` | snapshot file size | disk space, restore time | 3 |
| `fn_corun[n]` | handler time with `n` sandboxes of the same function running, `n` = 1, 2, …, physical cores, and thread count | co-run slowdown (plan V5.5) | 30 per level, per-guest samples kept |
| `fn_corun_mixed` | one short function alongside `physical cores − 1` sandboxes of the longest function | slowdown under a mixed load | 30 |

Checks:
- all functions present on every machine;
- every input size of the suite present; handler times together span under 1 ms to over 10 s, or the gap is reported;
- `fn_exec` within 10x of the published SeBS execution time where one exists, or an explanation in the report;
- `fn_corun[1]` equals `fn_exec` at the reference size within 5%;
- slowdown is non-decreasing in `n` within noise, or explained.

## 6. Derived by ingest (not measured directly; `tools/calibrate/ingest.py`)

| Bundle entry | From |
|---|---|
| per-function `work_ref_s`, `size_exp` | fit of `fn_exec` against input size (log-log); fit residuals reported |
| per-function `interference[n]` | median `fn_corun[n]` / median `fn_corun[1]` |
| relative machine speed | geometric mean of `fn_exec` ratios to the reference machine (the reference machine is named in the bundle) |
| start-up level times | sums of the step probes of §4 for each path (boot, restore, warm) per tier and cache state |

## 7. Emulation run (Part E of the handoff; only on the largest machine, after `v2-freeze`)

| Output | Content |
|---|---|
| `runs-emu/<host_label>/<system>/rep<i>/` | recorder tables in the simulator's schema (invocations, attempts, events), manifest with scenario hash and code commit |
| `docs/validation/emulation-<host_label>.md` | side-by-side with the simulator: deadlines met, key holders, start-up level mix, latency distribution; spread over 3 repetitions; disagreements |

## 8. What is deliberately not measured on bare metal

| Item | Where it comes from instead |
|---|---|
| Wide-area and home-network delay and bandwidth | public measurement datasets (plan V9.3) |
| Session lengths, arrivals | public traces (plan V9.1, V9.2) |
| Scheduler decision time | timed on a server-class GitHub runner (plan V10) |
| Confidential-VM costs | out of scope in v2 |
