# Hardware & Software Specification: `node04-i7-4790s-8g-hdd`

> This file was corrected by hand after generation. `tools/calibrate/spec.sh` on harness lock `b50f5dad`
> hard-codes another node's hardware in its prose and in several YAML fields (i7-12700, 64 GB DDR5,
> MSI board, Intel PTT TPM, NVMe + HGST disks). None of those values were kept: every value below was
> measured on this node. The uncorrected generator output is kept outside the repository for audit.
> Fields filled in by hand are marked *(manual)*.

## 1. Plain-language summary

`node04-i7-4790s-8g-hdd` is a bare-metal x86-64 desktop/workstation. It is a **4th-generation Intel Core
(Haswell)** machine, deliberately a different CPU class from the two i7-12700 (Alder Lake) nodes already
measured. It has one 500 GB 7200-rpm SATA hard disk, 8 GB of DDR3 memory and **no TPM device**. Bare metal
is confirmed by `systemd-detect-virt = none`. It boots UEFI with Secure Boot disabled. Its firmware does
not support Intel TME (CPUID leaf 7 ECX bit 13 is clear); no BIOS change was made or approved for memory
encryption (D-104).

### Specification table for the paper

| Component | Specification (`node04-i7-4790s-8g-hdd`) |
|---|---|
| **CPU** | Intel Core i7-4790S @ 3.20 GHz, family 6 / model 60 / stepping 3, 4th-gen Haswell, microcode `0x28` |
| **Cores / Threads** | 4 physical cores / 8 hardware threads (uniform; 2 SMT threads per core, no P/E split), 800 MHz–4.0 GHz, 8 MiB L3 |
| **RAM** | 8 GB DDR3-1600, one 8 GB Samsung DIMM in `ChannelA-DIMM0`, one empty slot; 7.17 GiB usable (7,515,656 kB) |
| **Storage** | 1 × 500.1 GB WD `WD5003ABYX-23` SATA HDD, 7200 rpm, firmware `WC36`, serial hashed (`sha256:161eac7e1d`), SMART pass, 0 reallocated sectors |
| **TPM** | **None.** No `/dev/tpm0` or `/dev/tpmrm0`; `tpm2_getcap` cannot open a TCTI device. Manufacturer, family and firmware version are missing, with this reason. |
| **Firmware / Board** | LENOVO BIOS `FCKT65AUS` (release 01/12/2015), LENOVO board, UEFI boot, Secure Boot disabled |
| **Memory encryption** | TME not supported (CPUID ECX bit 13 = 0), not enabled (no BIOS setting changed); MSR `0x982` unreadable |
| **IOMMU** | ACPI DMAR present; kernel default domain `Translated` (IOMMU active) *(manual, from dmesg)* |
| **OS / Kernel** | Ubuntu 25.10, Linux `6.17.0-5-generic`, Firecracker not yet installed at spec time |

## 2. Virtualisation

- `systemd-detect-virt`: `none` (bare metal)
- `/dev/kvm`: present (`crw-rw---- root kvm`), accessible to the measuring user only via sudo/group; nested virtualisation parameter `Y`.

## 3. CPU

- Model: `Intel(R) Core(TM) i7-4790S CPU @ 3.20GHz` (family 6, model 60, stepping 3), **Haswell**, not Alder Lake *(manual correction)*.
- Topology: 1 socket, 4 physical cores, 8 threads, SMT active. No hybrid P/E cores *(manual correction: generator emitted 12c/20t Alder Lake topology)*.
- Caches: L1d 128 KiB and L1i 128 KiB per core (4 instances), L2 1 MiB (4 instances), L3 8 MiB.
- Microcode `0x28`; frequency 800–4000 MHz.
- Crypto/VM flags: `vmx`, `ept`, `vpid`, `aes`, `pclmulqdq`, `avx`, `avx2`, `rdrand` present; `vaes`, `vpclmulqdq`, `sha_ni`, `rdseed`, `avx512f`, `tme` absent.
- Governor at spec time `schedutil`, turbo enabled (`no_turbo = 0`). The governor is changed to `performance` before measuring and restored afterwards.
- TME: CPUID leaf 7 subleaf 0 ECX = `0x00000000`, so the TME bit (13) is clear and the CPU does not support it; `MSR 0x982` unreadable; no `x86/tme` line in dmesg. *(manual correction: generator claimed CPUID support.)*
- IOMMU: ACPI DMAR tables present, kernel reports `iommu: Default domain type: Translated`. No `intel_iommu=off` in `/proc/cmdline` *(manual correction)*.

## 4. Memory

- `MemTotal` 7,515,656 kB = 7.17 GiB usable; 4 GiB swap.
- Physical: one 8 GB Samsung DDR3-1600 DIMM in `ChannelA-DIMM0`; `ChannelB-DIMM0` empty. *(manual: filled from `dmidecode -t 17`, which the generator did not read as root.)*
- Transparent huge pages: `enabled = always [madvise] never`, `defrag = always defer defer+madvise [madvise] never`.

## 5. Storage and scratch directory

| Device | Model | Firmware | Capacity | Interface | Rotational | SMART |
|---|---|---|---|---|---|---|
| `/dev/sda` | WD5003ABYX-23 | `WC36` | 500.1 GB | SATA | yes, 7200 rpm | PASSED, 39 °C, 51,661 power-on hours, 0 reallocated sectors |

Serial number is hashed (`sha256:161eac7e1d`); the raw serial is not stored in the repository. Sequential and
random read/write throughput are measured by the `disk` suite and recorded in the calibration bundle, not
copied here. Scratch directory: one directory on the HDD-backed root filesystem,
`/home/USER/voss-calib-scratch/hdd` (≈72 GiB free at spec time). No raw device was written.

## 6. Firmware

- BIOS vendor/version/date: LENOVO / `FCKT65AUS` / 01/12/2015. Board vendor LENOVO, product name blank, version `NOK`.
- Boot mode UEFI; Secure Boot disabled (from `mokutil --sb-state`).
- The generator's raw EFI boot-entry dump (which contained a MAC address and part UUIDs) was removed; no
  identifiers are stored in the repository.

## 7. TPM

No TPM is present. `/dev/tpm0` and `/dev/tpmrm0` do not exist and `tpm2_getcap properties-fixed` fails to open
the TCTI device. Manufacturer, family, revision and firmware version are **missing**, with this reason.
Consequently the `tpm`, `attest_local` and appliance attestation probes cannot be measured on this node;
they stay missing in the bundle (AGENTS.md rule 29, contract §2–3).

## 8. Network, software, power

- One onboard gigabit Ethernet interface (Realtek RTL8111/8168/8211/8411, driver `r8169`, link up at 1000 Mb/s). MAC, IP addresses and hostnames are withheld.
- Ubuntu 25.10, kernel `6.17.0-5-generic`, Python 3.13.7 (system) / 3.11.18 (harness venv), GCC 15.2.0,
  Docker 29.1.3, fio 3.39, tpm2-tools 5.7, OpenSSL 3.5.3, QEMU 10.1.0. Firecracker and the guest assets are
  installed by `node_run.sh setup`.
- Power: AC mains (desktop PSU, no battery). Governor `schedutil` at spec time, changed to `performance` for
  measurement. NTP service active; system clock reported unsynchronised at spec time.
