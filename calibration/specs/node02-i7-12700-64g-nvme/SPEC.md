# Hardware & Software Specification: `node02-i7-12700-64g-nvme`

## 1. Plain-Language Summary & Paper Table

**Host label:** `node02-i7-12700-64g-nvme` (chosen as a short neutral identifier reflecting the 12th-Gen Intel Core i7-12700 CPU and 64 GB DDR5 RAM configuration, distinguishing this bare-metal host from the 128 GB `c0-9132c8a291` configuration).

**Summary:** `node02-i7-12700-64g-nvme` is a bare-metal x86-64 desktop/workstation host built on an MSI PRO Z790-A WIFI (MS-7E07) motherboard (AMI UEFI BIOS `A.90`, dated `01/10/2024`, Secure Boot disabled) with a 12th-Gen Intel Core i7-12700 Alder Lake processor (12 physical cores / 20 threads: 8 Golden Cove P-cores with SMT up to 4.9 GHz and 4 Gracemont E-cores up to 3.6 GHz, 25 MiB L3 cache, microcode `0x3e`) and 64 GB of dual-channel DDR5-5200 DRAM (`2 × 32 GB` G.Skill DIMMs). It has an integrated Intel PTT firmware TPM 2.0 (`INTC` / `ADL`, revision 1.38, firmware `600.18.30.2264`, SHA-256 PCR bank active) and supports Intel Total Memory Encryption in silicon (CPUID leaf 7 ECX bit 13 set, disabled in BIOS with `MSR 0x982 = 0x1`). Its storage subsystem comprises eight physical drives across two hardware tiers: four 1 TB Samsung 980 PRO PCIe 4.0 NVMe SSDs (`nvme0n1` hosting the Ubuntu 22.04.5 LTS / Linux `5.15.0-198-generic` root filesystem on ext4/LVM, and `nvme1n1`–`nvme3n1` formatted with XFS) and four 2 TB HGST Ultrastar 7K2000 7200 RPM SATA HDDs (`sda`–`sdd`, formatted with XFS).

### Specification Table for the Paper

| Component | Specification (`node02-i7-12700-64g-nvme`) |
|---|---|
| **CPU** | 12th Gen Intel Core i7-12700 (Alder Lake-S, Golden Cove + Gracemont, microcode `0x3e`) |
| **Cores / Threads** | 12 cores / 20 threads (8 P-cores / 16 threads @ 0.8–4.9 GHz + 4 E-cores / 4 threads @ 0.8–3.6 GHz; 25 MiB L3) |
| **RAM** | 64 GB (62.67 GiB usable) DDR5-5200 MT/s dual-channel (`2 × 32 GB` G.Skill `F5-5200J3636D32G`, 2 of 4 slots) |
| **NVMe SSDs (×4)** | `nvme0n1`–`nvme3n1`: 4 × 1000.2 GB Samsung SSD 980 PRO 1TB (fw `5B2QGXA7`, PCIe NVMe, `nvme0n1` ext4/LVM, `nvme1..3n1` XFS) |
| **SATA HDDs (×4)** | `sda`–`sdd`: 4 × 2000.4 GB HGST `HUS722T2TALA604` (fw `RAGNWA09`, SATA 7200 RPM, XFS) |
| **TPM** | Firmware TPM 2.0: Intel PTT (`INTC` / `ADL`, rev 1.38, fw `600.18.30.2264`, active bank `sha256`, 24 PCRs) |
| **Firmware / Board** | MSI `PRO Z790-A WIFI (MS-7E07)`, AMI UEFI BIOS `A.90` (`01/10/2024`), UEFI boot, Secure Boot disabled |
| **OS / Kernel** | Ubuntu 22.04.5 LTS, Linux `5.15.0-198-generic` x86_64, Firecracker `v1.10.1` (`firecracker v1.10.1, kernel firecracker-ci/v1.10/x86_64/vmlinux-6.1.102`), QEMU `6.2.0` |

---

## 2. Virtualisation
- **Commands:** `systemd-detect-virt`, `ls -l /dev/kvm`, `cat /sys/module/kvm_intel/parameters/nested`
- **`systemd-detect-virt`:** `none` (bare metal)
- **`/dev/kvm`:** `crw-rw---- 1 root kvm 10, 232 Nov 12 16:23 /dev/kvm` (accessible: `True`)
- **Nested virtualisation:** `{"/sys/module/kvm_intel/parameters/nested": "Y"}`

## 3. CPU
- **Commands:** `lscpu`, `lscpu -e=CPU,NODE,SOCKET,CORE,CACHE,ONLINE,MAXMHZ,MINMHZ`, `cat /proc/cpuinfo`, `cat /sys/devices/system/cpu/smt/*`, `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`, `cat /sys/devices/system/cpu/intel_pstate/no_turbo`, `numactl --hardware`, `grep . /sys/devices/system/cpu/vulnerabilities/*`, `cpuid -1 -l 7 -r`, `rdmsr 0x982`, `dmesg | grep -iE 'tme|total memory encryption|dmar|iommu'`
- **Model:** `12th Gen Intel(R) Core(TM) i7-12700` (Family `6`, Model `151`, Stepping `2`)
- **Microarchitecture:** Intel Alder Lake-S (hybrid: 8 Golden Cove P-cores + 4 Gracemont E-cores)
- **Topology:** 1 socket, 12 physical cores, 20 hardware threads
  - **P-cores:** CPUs `0–15` (cores 0–7, 2 SMT threads/core, min 800 MHz, max 4800–4900 MHz)
  - **E-cores:** CPUs `16–19` (cores 8–11, 1 thread/core, min 800 MHz, max 3600 MHz)
- **Caches:** L1d `512 KiB (12 instances)`, L1i `512 KiB (12 instances)`, L2 `12 MiB (9 instances)`, L3 `25 MiB (1 instance)`
- **Microcode:** `0x3e`
- **SMT / Governor / Turbo:** `smt/control=on`, `smt/active=1`, `governor=powersave`, `intel_pstate/no_turbo=0` (Turbo enabled)
- **VM & Crypto Flags:** `{"vmx": true, "svm": false, "ept": true, "vpid": true, "vnmi": true, "tpr_shadow": true, "flexpriority": true, "aes": true, "vaes": true, "pclmulqdq": true, "vpclmulqdq": true, "sha_ni": true, "rdrand": true, "rdseed": true, "avx": true, "avx2": true, "avx_vnni": true, "avx512f": false, "tme": true, "smep": true, "smap": true, "umip": true, "pku": true}`
- **TME / IOMMU:**
  - CPUID leaf 7 subleaf 0 ECX bit 13 (TME): `True`; `MSR 0x982` (`IA32_TME_ACTIVATE`): `1`; kernel dmesg: `x86/tme: not enabled by BIOS`
  - IOMMU: ACPI DMAR table present; kernel booted with `intel_iommu=off` (`DMAR: IOMMU disabled`, `DMAR-IR: Enabled IRQ remapping in x2apic mode`)
- **NUMA (`numactl --hardware`):**
```text
available: 1 nodes (0)
node 0 cpus: 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19
node 0 size: 63967 MB
node 0 free: 20960 MB
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
- **Total RAM:** `65502984` kB (`62.47` GiB usable; 64 GB physical)
- **DIMM Layout:** 2 × 32 GB DDR5-5200 MT/s (`G Skill Intl F5-5200J3636D32G`, Rank 2, 1.25 V) in `Controller0-DIMMA2` (serial `sha256:e9956da8ef`) and `Controller1-DIMMB2` (serial `sha256:329a507d96`); `DIMMA1` and `DIMMB1` empty
- **Swap:** `8388604` kB (`8.0` GiB)
- **Transparent Huge Pages (THP):** `enabled: always [madvise] never`, `defrag: always defer defer+madvise [madvise] never`

## 5. Storage Devices & Scratch Directories
- **Commands:** `lsblk -J -b -o NAME,TYPE,SIZE,ROTA,MODEL,TRAN,FSTYPE,MOUNTPOINT`, `smartctl -j -a /dev/<dev>`, `cat /sys/block/<dev>/queue/{rotational,logical_block_size,physical_block_size,nr_requests,scheduler}`, `findmnt -J -T <dir>`, `df -h`

### Physical Block Devices
| Device | Model | Firmware | Serial (SHA-256) | Capacity | Interface | ROTA | Sectors (L/P) | Queue (`nr_requests` / sched) | SMART Health & Wear |
|---|---|---|---|---|---|---|---|---|---|
| `/dev/sda` | HGST HUS722T2TALA604 | `RAGNWA09` | `sha256:41020ddf2d` | 2000.4 GB | SATA | 1 | 512/512 B | `64` / `[mq-deadline] none` | PASSED, 34°C, 22037h, realloc=0 |
| `/dev/sdb` | HGST HUS722T2TALA604 | `RAGNWA09` | `sha256:5473fc2638` | 2000.4 GB | SATA | 1 | 512/512 B | `64` / `[mq-deadline] none` | PASSED, 37°C, 22452h, realloc=0 |
| `/dev/sdc` | HGST HUS722T2TALA604 | `RAGNWA09` | `sha256:a2811a04b8` | 2000.4 GB | SATA | 1 | 512/512 B | `64` / `[mq-deadline] none` | PASSED, 36°C, 22414h, realloc=0 |
| `/dev/sdd` | HGST HUS722T2TALA604 | `RAGNWA09` | `sha256:709fc38039` | 2000.4 GB | SATA | 1 | 512/512 B | `64` / `[mq-deadline] none` | PASSED, 39°C, 22451h, realloc=0 |
| `/dev/nvme0n1` | Samsung SSD 980 PRO 1TB | `5B2QGXA7` | `sha256:d4f73c9424` | 1000.2 GB | NVME | 0 | 512/512 B | `1023` / `[none] mq-deadline` | PASSED, 44°C, 4328h, wear=11%, spare=100% |
| `/dev/nvme2n1` | Samsung SSD 980 PRO 1TB | `5B2QGXA7` | `sha256:86ac30a492` | 1000.2 GB | NVME | 0 | 512/512 B | `1023` / `[none] mq-deadline` | PASSED, 41°C, 386h, wear=0%, spare=100% |
| `/dev/nvme3n1` | Samsung SSD 980 PRO 1TB | `5B2QGXA7` | `sha256:4970fb4421` | 1000.2 GB | NVME | 0 | 512/512 B | `1023` / `[none] mq-deadline` | PASSED, 40°C, 373h, wear=3%, spare=100% |
| `/dev/nvme1n1` | Samsung SSD 980 PRO 1TB | `5B2QGXA7` | `sha256:e93c926bc3` | 1000.2 GB | NVME | 0 | 512/512 B | `1023` / `[none] mq-deadline` | PASSED, 41°C, 385h, wear=1%, spare=100% |

### Scratch Directories Used for Calibration
| Scratch Path | Mount Point | Backing Device | FS Type | Mount Options | Encryption | Free / Total |
|---|---|---|---|---|---|---|
| `/mnt/nvme1/voss-calib-node02` | `/mnt/nvme1` | `/dev/nvme1n1p1` | `xfs` | `rw,relatime,attr2,inode64,logbufs=8,logbsize=32k,noquota` | none (raw partition) | 815.0 GB (759.0 GiB) / 999.7 GB |
| `/mnt/hdd1/voss-calib-node02` | `/mnt/hdd1` | `/dev/sda1` | `xfs` | `rw,relatime,attr2,inode64,logbufs=8,logbsize=32k,noquota` | none (raw partition) | 1796.1 GB (1672.7 GiB) / 1999.4 GB |

## 6. Firmware & Motherboard
- **Commands:** `cat /sys/class/dmi/id/{bios_vendor,bios_version,bios_date,board_vendor,board_name,board_version}`, `mokutil --sb-state`, `efibootmgr -v`, `bootctl status`
- **Board:** `Micro-Star International Co., Ltd.` `PRO Z790-A WIFI (MS-7E07)` (version `2.0`)
- **BIOS:** `American Megatrends International, LLC.`, version `A.90`, date `01/10/2024`
- **Boot Mode:** `UEFI`
- **Secure Boot:** `SecureBoot disabled`
- **`efibootmgr -v`:**
```text
BootCurrent: 0003
Timeout: 0 seconds
BootOrder: 0003
Boot0003* ubuntu	HD(<redacted-partuuid>)/File(\EFI\ubuntu\shimx64.efi)
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
- **Revision / Firmware:** revision `1.38`, firmware `600.18.30.2264 (raw 0x2580012/0x1E08D8)`
- **Device Nodes:** `/dev/tpm0`, `/dev/tpmrm0` (`tpm_version_major=2`)
- **Active PCR Banks:** `sha256` (24 PCRs)

## 8. Network, Software, Power & Time Sync
- **Commands:** `lspci`, `cat /sys/class/net/<if>/*`, `uname -a`, `cat /proc/cmdline`, `timedatectl status`, tool `--version` flags

### Network Interfaces
| Interface | Model | Driver | State | Speed (Mb/s) | MAC (SHA-256) |
|---|---|---|---|---|---|
| `enp7s0` | Intel Corporation Ethernet Controller I225-V (rev 03) | `igc` | `up` | `2500` | `sha256:e93398c11f` |
| `wlo1` | Intel Corporation Device 7a70 (rev 11) | `iwlwifi` | `down` | `down` | `sha256:ee540c2a43` |

### Software Versions
```yaml
distro: Ubuntu 22.04.5 LTS
kernel: 5.15.0-203-generic
kernel_version: '#213-Ubuntu SMP Fri Oct 23 13:21:06 UTC 2026'
kernel_cmdline: BOOT_IMAGE=/vmlinuz-5.15.0-203-generic root=/dev/mapper/ubuntu--vg-ubuntu--lv
  ro quiet splash nomodeset intel_iommu=off
python_system: Python 3.10.12
python_venv: Python 3.11.18
gcc: gcc (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0
firecracker: Firecracker v1.10.1
firecracker_guest_assets: firecracker v1.10.1, kernel firecracker-ci/v1.10/x86_64/vmlinux-6.1.102
qemu: QEMU emulator version 6.2.0 (Debian 1:6.2+dfsg-2ubuntu6.31)
docker: Docker version 29.3.0, build 5927d80
fio: fio-3.36
tpm2_tools: tool="tpm2_quote" version="5.2" tctis="libtss2-tctildr" tcti-default=tcti-device
openssl: 'OpenSSL 3.0.2 15 Mar 2022 (Library: OpenSSL 3.0.2 15 Mar 2022)'
```

### Power & Time Sync
- **Power:** `AC mains (desktop PSU; no battery in /sys/class/power_supply)`, governor `powersave`
- **`timedatectl status`:**
```text
Local time: Sat 2026-11-14 16:06:12 IST
           Universal time: Sat 2026-11-14 10:36:12 UTC
                 RTC time: Sat 2026-11-14 10:36:12
                Time zone: Asia/Kolkata (IST, +0530)
System clock synchronized: yes
              NTP service: active
          RTC in local TZ: no
```
