# Calibration data contract (VOSS v2)

What the bare-metal session must deliver for each machine, why the simulator needs it, and how it is checked.
`tools/calibrate/check_bundle.py` (plan V1 step 8) enforces the "Check" column. Probe names in `code font` are the names the
harness logs; if the harness uses a different name, the harness is wrong, not this file (fix it in plan V1).

Every bundle entry the simulator reads (`measured/<name>` in `configs/substrates/*.yaml`, and the bundle keys read in
`voss/`) comes from a probe below; `check_bundle.simulator_entries` lists them and
`tests/unit/test_calibrate_ingest.py` fails if one has no probe or a newly ingested bundle does not hold it as
`measured` (guardrails 28, 29). Nothing is demanded that the simulator does not read, except the crypto and unseal
probes of §2 that the paper's machine table reports (D-102).

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
| `tpm2_unseal` | unseal of a key sealed under a PCR policy (one `tpm2_unseal` process; the cache-partition step of the image) | paper's machine table | 50 |
| `verify_quote` | verifier checks quote, certificate chain and event log; signs a session certificate | verifier time per session | 50 |
| `tls_handshake` | TLS 1.3 mutual handshake CPU time on this machine | every new connection to a worker | 1,000 |
| `key_request` | worker side of a key request over loopback TLS: new connection, 256-byte request, 256-byte reply (`keys` suite) | key fetch delay (with `key_unwrap`; ingest writes `key_release` = sum) | 200 |
| `key_unwrap` | one RSA-2048 private-key operation, unwrapping the function key (`openssl speed`) | key fetch delay | 1 run |
| `kbs_check` | the key service's work per request, timed on the server from request read to reply ready: session certificate parse, Ed25519 signature check, expiry, measurement and policy version, holder budget, RSA-2048 OAEP wrap of the function key (`keys` suite) | bundle `kbs_check_s`: the trust step of every key release | 200 |
| `decrypt_per_MB` | seconds per MB of AES-256-GCM decryption on 1 MB blocks (`openssl speed`, `keys` suite) | start-up from an encrypted bundle | 1 run |
| `hash_per_MB` | seconds per MB of single-core SHA-256 (`disk` suite) | bundle `verify_s_per_MB`: integrity check of fetched files | 20 |

## 3. Boot to an attested worker (reboots; approval needed)

At least 10 boots. The simulator reads two entries (`appliance_tpm.yaml`, session `establish`):

| Bundle entry | Probe | n ≥ |
|---|---|---|
| `reboot_to_kernel` | firmware + boot loader + kernel, power-on (or reboot command) to the kernel handing over to userspace | 10 |
| `appliance_userspace` | userspace start to the agent ready to request a quote | 10 |

The TPM quote and the verifier check after them are §2's `tpm2_quote` and `verify_quote`. Either boot mode gives both
entries: the real image (`appliance` suite, image mode) or the host-mode probe (D-60), which boots the machine's own
kernel with wall-clock stamps. In image mode the suite also records each step (`boot_firmware`, `boot_loader`,
`boot_quote`, `boot_verify`, `boot_first_tls`, `boot_total`) and, from inside the image, `image_mem` and
`image_cache_bytes`; they are kept in the raw logs and may be reported, but no bundle entry and no check demands them,
because the simulator reads none of them (D-102).

## 4. Sandboxes (per storage tier; cold and warm page cache)

| Probe | What | n ≥ |
|---|---|---|
| `fc_spawn`, `fc_configure`, `fc_boot`, `fc_init_done` | steps of booting a sandbox from kernel and root file system | 100 per configuration |
| `fc_pause`, `fc_snapshot_create` | steps of writing a snapshot | 50 |
| `fc_restore_spawn`, `fc_restore_load`, `fc_restore_first_response` | steps of restoring a snapshot until the first invocation is answered | 50 |
| `dispatch_warm` | handing an invocation to a warm sandbox until the handler starts: a new vsock connection through Firecracker's socket (`CONNECT`), the request, and the guest's `START` line written just before the handler is called (`fc_dispatch` suite; `vsock_rtt` gives the return message's share); bundle `dispatch` | 200 |
| `snapshot_touched_frac` | `read_bytes` of the Firecracker process over a cold restore (snapshot files evicted from the page cache), input build and first invocation at the reference input size, divided by the memory file's size; per function and tier (`fc_touched` suite) | 10 per function and tier |

Configurations: sandbox memory sizes used by the workload functions; each storage tier the machine has; page cache cold
(`drop_caches`) and warm.

## 5. Functions (every function in `tools/calibrate/guest/functions/`)

| Probe | What | Used for | n ≥ |
|---|---|---|---|
| `fn_init` | initialisation (imports, model load) | cold-start cost | 30 |
| `fn_exec[size]` | handler time only, at SeBS's test, small and large input classes and two larger sizes | run-time model, deadlines, mapping of trace functions (plan V1 step 1, V9.1) | 30 per size |
| `fn_input_gen[size]` | time to build the input, one guest alone (`fn_inputs` suite; reported, excluded from `fn_exec`) | sanity | 30 per size |
| `fn_rss` | resident memory of the running sandbox | memory admission | 10 |
| `snap_size` | snapshot file size | disk space, restore time | 3 |
| `fn_corun[n]` | handler time with `n` sandboxes of the same function running, `n` = 1, 2, …, physical cores, and thread count | co-run slowdown (plan V5.5) | 30 per level, per-guest samples kept |

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
| `snapshot_touched_frac` | all functions' samples on the bundle's tier; per function in `functions.yaml` |
| `tme_cpu_factor`, `tme_mem_factor` | `tme` suite, `--phase on` and `--phase off` on the same node: SeBS subset handler time at concurrency 1 on/off (geometric mean over function and size) and STREAM triad bandwidth off/on. Written only when both phases were measured; otherwise missing, and `check_bundle` reports it (never assumed). Each run records the firmware's TME state (`tme_state`) and refuses a phase that contradicts it. |

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
