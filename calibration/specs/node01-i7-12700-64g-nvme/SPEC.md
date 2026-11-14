# Hardware & Software Specification: `node01-i7-12700-64g-nvme`

> **Generation note (2026-11-14).** `node_run.sh spec` ran the locked harness (`HARNESS.lock` tree
> `6ceef631`); its `spec.sh` still hard-codes an MSI PRO Z790-A / 4×NVMe / 4×HDD summary. The structured
> `spec.yaml` was probed correctly, so the hard-coded summary, paper table, topology, TME/IOMMU and DIMM
> lines above were re-rendered from `spec.yaml` with the already-written fix `spec_md.py` (commit c444ff4),
> with the human's approval. No measurement or harness file was changed.

## 1. Plain-Language Summary & Paper Table

**Host label:** `node01-i7-12700-64g-nvme` (chosen as a short neutral identifier reflecting the 12th-Gen Intel Core i7-12700 CPU and 64 GB DDR5 RAM configuration, distinguishing this bare-metal host from the 128 GB `c0-9132c8a291` configuration).

**Summary:** `node01-i7-12700-64g-nvme` is a bare-metal x86-64 desktop/workstation host built on an ASUSTeK COMPUTER INC. PRIME Z790-P WIFI (Rev 1.xx) motherboard (American Megatrends Inc. UEFI BIOS `1645`, dated `03/15/2024`, Secure Boot disabled) with a 12th Gen Intel(R) Core(TM) i7-12700 processor (12 physical cores / 20 threads: 8 P-cores / 16 threads @ 4900.0 MHz + 4 E-cores / 4 threads @ 3600.0 MHz, 25 MiB (1 instance) L3 cache, microcode `0x3e`) and 64 GB of 2-channel DDR5-4800 DRAM (`2 × 32 GB G Skill Intl F5-5200J3636D32G`). It has an Intel PTT firmware TPM 2.0 (`INTC` / `ADL`, revision `1.38`, firmware `600.18.30.2307 (raw 0x2580012/0x1E0903)`, sha256 PCR bank active) and supports Intel Total Memory Encryption in silicon (CPUID leaf 7 ECX bit 13 set, disabled in BIOS with `MSR 0x982 = 1`). Its storage subsystem comprises 2 × 1000.2 GB Samsung SSD 980 PRO 1TB (NVMe SSD); the calibration scratch directory is on /dev/mapper/ubuntu--vg-ubuntu--lv (ext4, mount options `rw,relatime`).

### Specification Table for the Paper

| Component | Specification (`node01-i7-12700-64g-nvme`) |
|---|---|
| **CPU** | 12th Gen Intel(R) Core(TM) i7-12700 (Intel Alder Lake-S (Golden Cove P-cores + Gracemont E-cores), microcode `0x3e`) |
| **Cores / Threads** | 12 cores / 20 threads (8 P-cores / 16 threads @ 800.0-4900.0 MHz + 4 E-cores / 4 threads @ 800.0-3600.0 MHz; 25 MiB (1 instance) L3) |
| **RAM** | 64 GB (62.45 GiB usable) DDR5-4800 MT/s 2-channel (`2 × 32 GB G Skill Intl F5-5200J3636D32G`, 2 of 4 slots) |
| **NVMe SSD (×2)** | `nvme0-1n1`: 2 × 1000.2 GB Samsung SSD 980 PRO 1TB (fw `5B2QGXA7`, NVMe SSD) |
| **TPM** | Intel PTT firmware TPM 2.0: (`INTC` / `ADL`, rev `1.38`, fw `600.18.30.2307 (raw 0x2580012/0x1E0903)`, active bank `sha256`, 24 PCRs) |
| **Firmware / Board** | ASUSTeK COMPUTER INC. `PRIME Z790-P WIFI` (Rev 1.xx), American Megatrends Inc. UEFI BIOS `1645` (`03/15/2024`), Secure Boot disabled |
| **OS / Kernel** | Ubuntu 22.04.5 LTS, Linux `5.15.0-198-generic` x86_64, Firecracker `absent`, QEMU `6.2.0` |

---

## 2. Virtualisation
- **Commands:** `systemd-detect-virt`, `ls -l /dev/kvm`, `cat /sys/module/kvm_intel/parameters/nested`
- **`systemd-detect-virt`:** `none` (bare metal)
- **`/dev/kvm`:** `crw-rw----+ 1 root kvm 10, 232 Nov 12 21:08 /dev/kvm` (accessible: `True`)
- **Nested virtualisation:** `{"/sys/module/kvm_intel/parameters/nested": "Y"}`

## 3. CPU
- **Commands:** `lscpu`, `lscpu -e=CPU,NODE,SOCKET,CORE,CACHE,ONLINE,MAXMHZ,MINMHZ`, `cat /proc/cpuinfo`, `cat /sys/devices/system/cpu/smt/*`, `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`, `cat /sys/devices/system/cpu/intel_pstate/no_turbo`, `numactl --hardware`, `grep . /sys/devices/system/cpu/vulnerabilities/*`, `cpuid -1 -l 7 -r`, `rdmsr 0x982`, `dmesg | grep -iE 'tme|total memory encryption|dmar|iommu'`
- **Model:** `12th Gen Intel(R) Core(TM) i7-12700` (Family `6`, Model `151`, Stepping `2`)
- **Microarchitecture:** Intel Alder Lake-S (hybrid: 8 Golden Cove P-cores + 4 Gracemont E-cores)
- **Topology:** 1 socket, 12 physical cores, 20 hardware threads
  - **P-cores:** CPUs `0-15` (8 cores, 2 SMT threads/core, min 800.0 MHz, max 4900.0 MHz)
  - **E-cores:** CPUs `16-19` (4 cores, 1 thread/core, min 800.0 MHz, max 3600.0 MHz)
- **Caches:** L1d `512 KiB (12 instances)`, L1i `512 KiB (12 instances)`, L2 `12 MiB (9 instances)`, L3 `25 MiB (1 instance)`
- **Microcode:** `0x3e`
- **SMT / Governor / Turbo:** `smt/control=on`, `smt/active=1`, `governor=powersave`, `intel_pstate/no_turbo=0` (Turbo enabled)
- **VM & Crypto Flags:** `{"vmx": true, "svm": false, "ept": true, "vpid": true, "vnmi": true, "tpr_shadow": true, "flexpriority": true, "aes": true, "vaes": true, "pclmulqdq": true, "vpclmulqdq": true, "sha_ni": true, "rdrand": true, "rdseed": true, "avx": true, "avx2": true, "avx_vnni": true, "avx512f": false, "tme": true, "smep": true, "smap": true, "umip": true, "pku": true}`
- **TME / IOMMU:**
  - CPUID leaf 7 subleaf 0 ECX bit 13 (TME): `True` (the `tme` CPU flag is set); `IA32_TME_ACTIVATE` (`MSR 0x982`): `1` (lock bit set, enable bit clear: disabled in BIOS)
  - IOMMU: ACPI `DMAR` table present; kernel cmdline does not set `intel_iommu=off`; boot-time `dmesg` lines rotated out after 21 days of uptime, so per-boot DMAR messages are not available in this spec
- **NUMA (`numactl --hardware`):**
```text
available: 1 nodes (0)
node 0 cpus: 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19
node 0 size: 63946 MB
node 0 free: 31108 MB
node distances:
node   0 
  0:  10
```
- **Vulnerability Mitigations (`/sys/devices/system/cpu/vulnerabilities/*`):**
```yaml
gather_data_sampling: Not affected
indirect_target_selection: Not affected
itlb_multihit: Not affected
l1tf: Not affected
mds: Not affected
meltdown: Not affected
mmio_stale_data: Not affected
reg_file_data_sampling: 'Mitigation: Clear Register File'
retbleed: Not affected
spec_rstack_overflow: Not affected
spec_store_bypass: 'Mitigation: Speculative Store Bypass disabled via prctl and seccomp'
spectre_v1: 'Mitigation: usercopy/swapgs barriers and __user pointer sanitization'
spectre_v2: 'Mitigation: Enhanced / Automatic IBRS; IBPB: conditional; PBRSB-eIBRS:
  SW sequence; BHI: BHI_DIS_S'
srbds: Not affected
tsa: Not affected
tsx_async_abort: Not affected
vmscape: 'Mitigation: IBPB before exit to userspace'
```

## 4. Memory
- **Commands:** `cat /proc/meminfo`, `dmidecode -t 17`, `cat /sys/kernel/mm/transparent_hugepage/enabled`, `cat /sys/kernel/mm/transparent_hugepage/defrag`
- **Total RAM:** `65481584` kB (`62.45` GiB usable; 64 GB physical)
- **DIMM Layout:** 32 GB DDR5-4800 MT/s (G Skill Intl F5-5200J3636D32G, 2) in `Controller0-DIMM1` (serial `sha256:399f7ee6f4`); 32 GB DDR5-4800 MT/s (G Skill Intl F5-5200J3636D32G, 2) in `Controller1-DIMM1` (serial `sha256:e50bd3db14`); `Controller0-DIMM0`, `Controller1-DIMM0` empty
- **Swap:** `8388604` kB (`8.0` GiB)
- **Transparent Huge Pages (THP):** `enabled: always [madvise] never`, `defrag: always defer defer+madvise [madvise] never`

## 5. Storage Devices & Scratch Directories
- **Commands:** `lsblk -J -b -o NAME,TYPE,SIZE,ROTA,MODEL,TRAN,FSTYPE,MOUNTPOINT`, `smartctl -j -a /dev/<dev>`, `cat /sys/block/<dev>/queue/{rotational,logical_block_size,physical_block_size,nr_requests,scheduler}`, `findmnt -J -T <dir>`, `df -h`

### Physical Block Devices
| Device | Model | Firmware | Serial (SHA-256) | Capacity | Interface | ROTA | Sectors (L/P) | Queue (`nr_requests` / sched) | SMART Health & Wear |
|---|---|---|---|---|---|---|---|---|---|
| `/dev/nvme0n1` | Samsung SSD 980 PRO 1TB | `5B2QGXA7` | `sha256:afe5029168` | 1000.2 GB | NVME | 0 | 512/512 B | `1023` / `[none] mq-deadline` | PASSED, 46°C, 5540h, wear=13%, spare=100% |
| `/dev/nvme1n1` | Samsung SSD 980 PRO 1TB | `5B2QGXA7` | `sha256:bb3adc8e22` | 1000.2 GB | NVME | 0 | 512/512 B | `1023` / `[none] mq-deadline` | PASSED, 44°C, 3819h, wear=5%, spare=100% |

### Scratch Directories Used for Calibration
| Scratch Path | Mount Point | Backing Device | FS Type | Mount Options | Encryption | Free / Total |
|---|---|---|---|---|---|---|
| `/home/USER/voss-calib-work/scratch/nvme0` | `/` | `/dev/mapper/ubuntu--vg-ubuntu--lv` | `ext4` | `rw,relatime` | none (LVM2 on raw partition) | 799.3 GB (744.4 GiB) / 1965.2 GB |

## 6. Firmware & Motherboard
- **Commands:** `cat /sys/class/dmi/id/{bios_vendor,bios_version,bios_date,board_vendor,board_name,board_version}`, `mokutil --sb-state`, `efibootmgr -v`, `bootctl status`
- **Board:** `ASUSTeK COMPUTER INC.` `PRIME Z790-P WIFI` (version `Rev 1.xx`)
- **BIOS:** `American Megatrends Inc.`, version `1645`, date `03/15/2024`
- **Boot Mode:** `UEFI`
- **Secure Boot:** `SecureBoot disabled`
- **`efibootmgr -v`:**
```text
BootCurrent: 0000
Timeout: 1 seconds
BootOrder: 0000
Boot0000* ubuntu	HD(<redacted-partuuid>)/File(\EFI\ubuntu\shimx64.efi)
```
- **`bootctl status`:**
```text
systemd-boot not installed in ESP.
System:
     Firmware: n/a (n/a)
  Secure Boot: disabled
   Setup Mode: user
 TPM2 Support: yes
 Boot into FW: supported

Current Boot Loader:
      Product: n/a
     Features: ✗ Boot counting
               ✗ Menu timeout control
               ✗ One-shot menu timeout control
               ✗ Default entry control
               ✗ One-shot entry control
               ✗ Support for XBOOTLDR partition
               ✗ Support for passing random seed to OS
               ✗ Boot loader sets ESP information
          ESP: n/a
         File: └─n/a

Random Seed:
 Passed to OS: no
 System Token: not set
       Exists: no
```

## 7. TPM
- **Commands:** `tpm2_getcap properties-fixed`, `tpm2_pcrread`, `cat /sys/class/tpm/tpm0/tpm_version_major`
- **Type:** Firmware TPM 2.0 (Intel Platform Trust Technology / PTT)
- **Manufacturer / Vendor String:** `INTC` / `ADL`
- **Revision / Firmware:** revision `1.38`, firmware `600.18.30.2307 (raw 0x2580012/0x1E0903)`
- **Device Nodes:** `/dev/tpm0`, `/dev/tpmrm0` (`tpm_version_major=2`)
- **Active PCR Banks:** `sha256` (24 PCRs)

## 8. Network, Software, Power & Time Sync
- **Commands:** `lspci`, `cat /sys/class/net/<if>/*`, `uname -a`, `cat /proc/cmdline`, `timedatectl status`, tool `--version` flags

### Network Interfaces
| Interface | Model | Driver | State | Speed (Mb/s) | MAC (SHA-256) |
|---|---|---|---|---|---|
| `eno1` | Realtek Semiconductor Co., Ltd. RTL8125 2.5GbE Controller (rev 05) | `r8169` | `up` | `2500` | `sha256:59f2ab78aa` |
| `wlp0s20f3` | Intel Corporation Device 7a70 (rev 11) | `iwlwifi` | `down` | `down` | `sha256:cabd7aa27e` |

### Software Versions
```yaml
distro: Ubuntu 22.04.5 LTS
kernel: 5.15.0-198-generic
kernel_version: '#208-Ubuntu SMP Fri Sep 4 10:22:38 UTC 2026'
kernel_cmdline: BOOT_IMAGE=/vmlinuz-5.15.0-198-generic root=/dev/mapper/ubuntu--vg-ubuntu--lv
  ro nomodeset
python_system: Python 3.10.12
python_venv: Python 3.11.16
gcc: gcc (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0
firecracker: absent
firecracker_guest_assets: ''
qemu: QEMU emulator version 6.2.0 (Debian 1:6.2+dfsg-2ubuntu6.31)
docker: Docker version 28.4.0, build d8eb465
fio: fio-3.28
tpm2_tools: tool="tpm2_quote" version="5.2" tctis="libtss2-tctildr" tcti-default=tcti-device
openssl: 'OpenSSL 3.0.2 15 Mar 2022 (Library: OpenSSL 3.0.2 15 Mar 2022)'
```

### Power & Time Sync
- **Power:** `AC mains (desktop PSU; no battery in /sys/class/power_supply)`, governor `powersave`
- **`timedatectl status`:**
```text
Local time: Sat 2026-11-14 16:02:51 IST
           Universal time: Sat 2026-11-14 10:32:51 UTC
                 RTC time: Sat 2026-11-14 10:32:51
                Time zone: Asia/Kolkata (IST, +0530)
System clock synchronized: yes
              NTP service: active
          RTC in local TZ: no
```
