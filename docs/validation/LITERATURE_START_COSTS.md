# Published start-up and attestation costs (literature context)

**Purpose.** Published measurements of the steps a volunteer machine goes through before it runs a function: power-on
to booted OS, TPM 2.0 operations, remote-attestation round trips, and Firecracker microVM boot and snapshot restore.
These values are **context for related work and the range of a sensitivity axis only**. Reported results use the
measured calibration bundles (`node02`, `node04`; AGENTS.md rules 13, 28, 29). Nothing here enters
`configs/calibration/measured/`.

**Rules used to build this file.**

- A number appears only if it was read in the source itself (PDF text extracted with `pdftotext`, or the raw file of a
  repository at a pinned commit). Quotes are verbatim; `[...]` marks an omission, and nothing is rounded or converted.
- Where a source states a value in another unit (CPU cycles), it is given in that unit. No conversion to seconds is
  made here, because the conversion needs a clock frequency the source does not state for every row.
- Locations are printed page numbers of the version read, plus section, figure or table. For arXiv versions, the arXiv
  version is named and no proceedings page is given unless the proceedings PDF was also read.
- A source that could not be read, or that gives no number with named hardware, is marked **UNVERIFIED** and carries
  no number.
- Bibliographic data were checked against Crossref (`api.crossref.org/works/<doi>`) for every entry with a DOI, and
  against the title page of the PDF otherwise. `manuscript/refs.bib` was not edited; differences from it are listed in
  §6.

Read on 2026-11-21.

---

## 1. Firecracker microVM boot and snapshot restore (d)

| Key | Quantity | Exact quote | Hardware / setup (as stated in the source) | Location |
|---|---|---|---|---|
| `agache2020firecracker` | microVM boot, headline | "boots to application code in less than 125ms, and allows creation of up to 150 MicroVMs per second per host." | Production claim; setup not stated at this point in the text | p. 420, §1 |
| `agache2020firecracker` | Evaluation machine | "Our evaluation is performed on an EC2 m5d.metal instance, with two Intel Xeon Platinum 8175M processors (for a total of 48 cores with hyper-threading disabled), 384GB of RAM, and four 840GB local NVMe disks. The base OS was Ubuntu 18.04.2 with kernel 4.15.0-1044-aws." | — | p. 427, §5 |
| `agache2020firecracker` | Definition of boot time | "The boot time is measured as the time between when VMM process is forked and the guest kernel forks its init process." Guest: "Linux 4.14.94 kernel [...] directly loaded by the VMM", "a single vCPU and 256MB of memory", no networking. | m5d.metal as above; 500 serial boots (Fig. 5) | p. 427, §5.1 |
| `agache2020firecracker` | Parallel boot, 50 concurrent, p99 | "pre-configured Fire-cracker out-performing Cloud Hypervisor both in average boot times as well as a tighter distribution with a 99th percentile of 146ms vs 158ms." | 1000 microVMs, 50 launching concurrently (Fig. 6) | p. 428, §5.1 |
| `agache2020firecracker` | 100 concurrent, p99 | "starting 100 MicroVMs concurrently and see a similar trend, albeit with a slightly wider distribution with the 99th percentile for pre-configure Firecracker going up to 153ms." | m5d.metal as above | p. 428, §5.1 |
| `agache2020firecracker` | Effect of guest kernel | "Decompressing the kernel during boot adds around 40ms." "the kernel which ships with Ubuntu 18.04 takes an additional 900ms to start!" "Adding a statically configured network interface adds around 20ms to the boot times for Firecracker and Cloud Hypervisor". Disabling serial console logging: "saving up to 70ms of boot time". | m5d.metal as above | p. 428, §5.1 |
| `firecracker2025spec` | VMM start, wall clock | "The Firecracker virtual machine manager starts (up to API socket availability) within `8 CPU ms` [...] The wall-clock time has a large standard deviation, spanning `6 ms to 60 ms`, with typical durations around `12 ms`." | "On an M5D.metal instance (with hyperthreading disabled) and an M6G.metal instance" | `SPECIFICATION.md`, item 1 |
| `firecracker2025spec` | Guest boot, CI bound | "It takes `<= 125 ms` to go from receiving the Firecracker InstanceStart API call to the start of the Linux guest user-space `/sbin/init` process. The boot time is measured using a VM with the serial console disabled and a minimal kernel and root file system." | microVM "with `1 CPUs and 128 MiB of RAM`", same hosts | `SPECIFICATION.md`, item 4 (Overhead) |
| `ustiugov2021reap` | Snapshot restore, VMM + connection | "We observe that the first two universal components, namely Load VMM and Connection restoration, take 156-317 ms." | "2×24-core Intel Xeon E5-2680 v3, 256GB RAM, Intel 200GB SATA3 SSD, running Ubuntu 18.04 Linux with kernel 4.15", CPU frequency fixed at 2.5 GHz (§6.1); page cache flushed before each cold invocation (§4.1); FunctionBench functions | arXiv v3, §4.2, Fig. 2 |
| `ustiugov2021reap` | Vanilla snapshot, helloworld | "Vanilla snapshots: This is the baseline configuration, which restores the VMM and the emulation layer in 50ms, then spends 182ms processing the function invocation (Fig. 7) that takes just 1ms for for a warm instance (Fig. 2)." | Same platform, SATA SSD | arXiv v3, §6.2, Fig. 7 |
| `ustiugov2021reap` | Concurrent restores (REAP) | "REAP's cold invocation latency stays relatively low, increasing from 70ms to 185ms when the number of concurrent function arrivals goes from 1 to 8." | Same platform; helloworld | arXiv v3, §6.5, Fig. 9 |
| `ao2022faasnap` | Snapshot restore, qualitative | "A Firecracker snapshot can be restored in a few milliseconds" (no number given) | Not stated at this point | p. 732, §2.4 |
| `ao2022faasnap` | Lazy restore, hello-world | "a simple hello-world function takes more than 200 ms to execute using Firecracker snapshots, compared to a warm VM which finishes within 4 ms." | Refers to its §3 measurements: "AWS EC2 c5d.metal instance with an Ubuntu Linux kernel version of 5.4.0. The disk is an NVMe SSD with measured maximum throughput of 1589 MB/s and 285,000 IOPS. The guest VM is configured with 2 GB of memory and 1 VCPU." (§3.1, p. 733) | p. 732, §2.4 |
| `ao2022faasnap` | Evaluation machine (§6) | "AWS c5d.metal instance with a 96 vCPU Intel Xeon Platinum 8275CL CPU running at 3.00 GHz, 192 GB of memory [...] Each guest VM has 2GB of memory and 2 vCPUs" | NVMe SSD, 1589 MB/s, 285,000 IOPS | p. 739, §6.1 |

All Firecracker numbers above are on datacenter servers with NVMe or SATA SSDs. None is on a desktop, a laptop or an
HDD. The guest kernel is the minimal Firecracker configuration unless the row says otherwise.

---

## 2. TPM 2.0 operations (b)

| Key | Quantity | Exact quote / value | Hardware / setup (as stated) | Location |
|---|---|---|---|---|
| `narayanan2023evtpm` | Discrete TPM (Nuvoton NPCT75x): `TPM2_Quote`, `CreatePrimary`, `PCR_Read`, `PCR_Extend` | "on a machine that has an on-board physical TPM 2.0 device (Nuvoton NPCT75x). On an average, TPM2_QUOTE and CREATEPRIMARY is 25,000 times slower compared to our emulated SVSM-vTPM at 262,143 µs and 192,918 µs respectively whereas PCRREAD is 9,000 times slower (30,026 µs), and PCREXTEND is 3,900 times slower (9,359 µs)." | Host machine of the Nuvoton run **not stated**. Commands issued "from the guest user space using the tpm2-tools package"; 3000 iterations, three runs, average. Quote: "three PCRs (16-18) from two different banks (sha1 and sha256)". CreatePrimary: "an ECC keypair with the default curve (ecc256)". PCR read: all PCRs of sha1, sha256, sha384 banks. Extend: one sha256 PCR. | ACSAC '23, p. 740, §6.1 (same text in arXiv v2, §6.1) |
| `moghimi2020tpmfail` | Intel PTT, ECDSA P-256 sign | "We can calculate the average execution time for ECDSA on Intel fTPM as 4.7 × 10^8 cycles/3.6 GHz = 130ms." | Dell XPS 8920, Core i7-7700 ("base frequency of 3.60 GHz"), Intel PTT, Dell BIOS 1.0.4 | p. 2061, §3.2 |
| `moghimi2020tpmfail` | ECDSA and RSA-2048 signing, average CPU cycles per signature, 8 platforms | Table 2, "ECDSA (Cycle)" / "RSA (Cycle)": NUC 8i7HNK, Core i7-8705G, Intel PTT: 4.1e8 / 7.0e8. NUC 7i3BNK, Core i3-7100U, Intel PTT: 3.2e8 / 5.4e8. Asus GL502VM, Core i7-6700HQ, Intel PTT: 3.5e8 / 5.9e8. Asus K501UW, Core i7 6500U, Intel PTT: 3.4e8 / 5.8e8. Dell XPS 8920, Core i7-7700, Intel PTT: 4.7e8 / 8.0e8. Dell Precision 5510, Core i5-6440HQ, Nuvoton "rls NPCT": 4.9e8 / 1.8e9. Lenovo T580, Core i7-8650U, STMicro ST33TPHF2ESPI: 8.7e7 / 9.2e8. NUC 7i7DNKE, Core i7-8650U, Infineon SLB 9670: 1.4e8 / 5.1e8. | Cycles of the host CPU, which runs at a different frequency on each row; not converted here. These are signing commands (`TPM2_Sign`), not `TPM2_Quote`. | p. 2062, Table 2 |
| `moghimi2020tpmfail` | Intel PTT sign, remote round trip | "the TPM takes around 200 milliseconds to generate a signature" | Server on "Core i7-8705G machine" (NUC 8i7HNK, Intel PTT) answering signing requests over UDP; client measures round trip | p. 2067, §5.3.1 |
| `moghimi2020tpmfail` | `tpm2_quote` on Intel PTT | Only a ratio: "using the tpm2_quote command [...] The timing observations suggest that EC-Schnorr executes about 1.4 times faster than ECDSA". No absolute quote time is given. | Intel PTT | p. 2062, §3.3 |
| `schear2016keylime` | Quote create / check on a physical TPM, vTPM, deep quote | Table 2, "Average TPM Operation Latency (ms)": Create Quote: TPM 725, vTPM 68.5, Deep quote 1390. Check Quote: TPM 4.64, vTPM 4.64, Deep quote 5.33. | "The Xen host had one Xeon E5-2640 CPU with 6 cores at 2.5Ghz, 10Gbit NIC, 64 GB RAM, a WinBond TPM"; physical-TPM values measured "on the same system with a standard (non-Xen) kernel". TPM specification version (1.2 or 2.0) **not stated** in the evaluation; IBM client library. RSA-2048 AIK (Table 1). | §5.1, Table 2 (MIT LL author copy) |
| `raj2016ftpm` | fTPM vs discrete TPM 2.0, command latency | "creating RSA keys is a lengthy command taking several seconds on all platforms." "On average, the slowest fTPM is anywhere between 2.4X (for decryption) and 15.12X (for seal) faster than the fastest dTPM." Per-command values are shown only as bar charts (Figs. 7, 9-15) without numeric labels. | Four ARM TrustZone mobile fTPMs (Cortex-A7/A9/A57, Table 1) and three discrete TPM 2.0 chips; **all devices anonymised**. These are not Intel PTT or AMD fTPM. Ten runs per command. | p. 851-852, §10.2-10.3 |
| `raj2015ftpmtr` | Discrete TPM 2.0, `Create` RSA-2048, per run | Bar labels, seconds, iterations 1-10: dTPM1 (Fig. 37): 26.7, 7.0, 10.7, 25.3, 15.7, 10.7, 19.3, 6.5, 19.3, 12.5. dTPM2 (Fig. 42): 3.7, 7.7, 9.8, 25.3, 5.9, 31.4, 14.2, 5.9, 20.6, 17.0. dTPM3 (Fig. 47): 0.3, 0.3, 0.3, 2.9, 6.9, 2.2, 6.5, 5.8, 9.7, 9.7. | Three anonymised discrete TPM 2.0 chips, as above. Labels read from the rendered page image, not from extracted text. | Appendix, Figs. 37, 42, 47 |

Notes on §2.

1. **262,143 µs is 2^18 − 1.** The Nuvoton quote average equals 2^18 − 1 exactly. This may be a timer or
   formatting artefact. Quote it as printed, and do not use it as a sensitivity value without this caveat.
2. **TPM-FAIL measures signing, not quoting.** A quote is a signature over PCR values, so the signing cost is the
   dominant part of a quote on the same TPM, but the paper does not report `TPM2_Quote` times.
3. **No published per-command times were found for AMD fTPM.** The faulTPM paper (`jacob2023faultpm`) attacks the
   AMD fTPM but was not searched for latency figures. **UNVERIFIED; no number.**
4. **No per-command times for Intel PTT `TPM2_Quote`, `TPM2_Load` or `TPM2_Create` (ECC) were found** in a
   peer-reviewed source. The calibration bundles measure `tpm2_quote` on Intel PTT directly
   (`node02-i7-12700-64g-nvme.md`).

---

## 3. Remote-attestation round trip (c)

| Key | Quantity | Exact quote | Hardware / setup (as stated) | Location |
|---|---|---|---|---|
| `schear2016keylime` | Bootstrap (quote retrieval + key share delivery) | "We find the bootstrapping latency for bare metal and virtual machines to be approximately 793ms and 1555ms respectively." | Cloud verifier on bare metal / OpenStack m1.large / m1.small / Raspberry Pi 2; 100 vTPM-equipped VMs; "Each operation includes a full REST interaction along with the relevant TPM and cryptographic operations." | §5.2, Figs. 6-7 |
| `schear2016keylime` | Integrity-violation detection | "for a virtual machine with a vTPM, keylime can detect integrity violations in as little as 110ms. The detection latency for a system with a physical TPM (781ms for our Xen host) is limited by the speed of the physical TPM at generating quotes." | Xen host as in §2 (WinBond TPM) | §5.2 |
| `schear2016keylime` | Verifier throughput vs RTT | Table 3, quotes verified per second at added network latency: "4ms (native)" 937; 25ms 613; 50ms 398; 75 ms 282; 100 ms 208; 150 ms 141. | "On-Premises bare metal CV verifying 250 Cloud Nodes using 50 CV processes." (Table 3 caption); column header "Network RTT (ms)" | §5, Table 3 |
| `schear2016keylime` | General claim (not a measurement) | "taking 500 or more milliseconds to generate a quote" | Authors' characterisation of "typical TPMs" | §3.2 |

---

## 4. Power-on to booted OS (a)

(Filled in the next commit.)

---

## 5. BibTeX

```bibtex
@inproceedings{agache2020firecracker,
  author    = {Alexandru Agache and Marc Brooker and Andreea Florescu and Alexandra Iordache and Anthony Liguori and Rolf Neugebauer and Phil Piwonka and Diana-Maria Popa},
  title     = {Firecracker: Lightweight Virtualization for Serverless Applications},
  booktitle = {17th USENIX Symposium on Networked Systems Design and Implementation (NSDI 20)},
  pages     = {419--434},
  year      = {2020},
  publisher = {USENIX Association},
  url       = {https://www.usenix.org/conference/nsdi20/presentation/agache},
}

@misc{firecracker2025spec,
  author       = {{The Firecracker Authors}},
  title        = {Firecracker Specification ({SPECIFICATION.md})},
  howpublished = {GitHub repository firecracker-microvm/firecracker, commit 58cf1b2cdca407f2323d1b0b25ebb95dfe5b4bcb},
  url          = {https://github.com/firecracker-microvm/firecracker/blob/58cf1b2cdca407f2323d1b0b25ebb95dfe5b4bcb/SPECIFICATION.md},
  note         = {Accessed 2026-11-21},
}

@inproceedings{ustiugov2021reap,
  author    = {Dmitrii Ustiugov and Plamen Petrov and Marios Kogias and Edouard Bugnion and Boris Grot},
  title     = {Benchmarking, Analysis, and Optimization of Serverless Function Snapshots},
  booktitle = {Proceedings of the 26th ACM International Conference on Architectural Support for Programming Languages and Operating Systems (ASPLOS '21)},
  pages     = {559--572},
  year      = {2021},
  doi       = {10.1145/3445814.3446714},
  note      = {Read as arXiv:2101.09355v3},
}

@inproceedings{ao2022faasnap,
  author    = {Lixiang Ao and George Porter and Geoffrey M. Voelker},
  title     = {{FaaSnap}: {FaaS} Made Fast Using Snapshot-based {VMs}},
  booktitle = {Proceedings of the Seventeenth European Conference on Computer Systems (EuroSys '22)},
  pages     = {730--746},
  year      = {2022},
  doi       = {10.1145/3492321.3524270},
}

@inproceedings{narayanan2023evtpm,
  author    = {Vikram Narayanan and Claudio Carvalho and Angelo Ruocco and Gheorghe Alm{\'a}si and James Bottomley and Mengmei Ye and Tobin Feldman-Fitzthum and Daniele Buono and Hubertus Franke and Anton Burtsev},
  title     = {Remote Attestation of Confidential {VMs} Using Ephemeral {vTPMs}},
  booktitle = {Proceedings of the 39th Annual Computer Security Applications Conference (ACSAC '23)},
  pages     = {732--743},
  year      = {2023},
  doi       = {10.1145/3627106.3627112},
  note      = {Preprint: arXiv:2303.16463, titled ``Remote attestation of SEV-SNP confidential VMs using e-vTPMs''},
}

@inproceedings{moghimi2020tpmfail,
  author    = {Daniel Moghimi and Berk Sunar and Thomas Eisenbarth and Nadia Heninger},
  title     = {{TPM-FAIL}: {TPM} meets Timing and Lattice Attacks},
  booktitle = {29th USENIX Security Symposium (USENIX Security 20)},
  pages     = {2057--2073},
  year      = {2020},
  publisher = {USENIX Association},
  url       = {https://www.usenix.org/conference/usenixsecurity20/presentation/moghimi-tpm},
}

@inproceedings{schear2016keylime,
  author    = {Nabil Schear and Patrick T. Cable and Thomas M. Moyer and Bryan Richard and Robert Rudd},
  title     = {Bootstrapping and Maintaining Trust in the Cloud},
  booktitle = {Proceedings of the 32nd Annual Conference on Computer Security Applications (ACSAC '16)},
  pages     = {65--77},
  year      = {2016},
  doi       = {10.1145/2991079.2991104},
}

@inproceedings{raj2016ftpm,
  author    = {Himanshu Raj and Stefan Saroiu and Alec Wolman and Ronald Aigner and Jeremiah Cox and Paul England and Chris Fenner and Kinshuman Kinshumann and Jork Loeser and Dennis Mattoon and Magnus Nystrom and David Robinson and Rob Spiger and Stefan Thom and David Wooten},
  title     = {{fTPM}: A Software-Only Implementation of a {TPM} Chip},
  booktitle = {25th USENIX Security Symposium (USENIX Security 16)},
  pages     = {841--856},
  year      = {2016},
  publisher = {USENIX Association},
  url       = {https://www.usenix.org/conference/usenixsecurity16/technical-sessions/presentation/raj},
}

@techreport{raj2015ftpmtr,
  author      = {Himanshu Raj and Stefan Saroiu and Alec Wolman and Ronald Aigner and Jeremiah Cox and Paul England and Chris Fenner and Kinshuman Kinshumann and Jork Loeser and Dennis Mattoon and Magnus Nystrom and David Robinson and Rob Spiger and Stefan Thom and David Wooten},
  title       = {{fTPM}: A Firmware-based {TPM} 2.0 Implementation},
  institution = {Microsoft Research},
  number      = {MSR-TR-2015-84},
  year        = {2015},
  month       = nov,
  url         = {https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/msr-tr-2015-84.pdf},
}
```

---

## 6. Differences from `manuscript/refs.bib`

(Filled in the next commit.)
