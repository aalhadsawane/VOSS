# E-CS1 (measured)

Calibration node `laptop-b9212a4528`; seconds; raw logs from `tools/calibrate` (doc 10 §3). Rows marked *not measured* keep literature values in the simulator (doc 10 §2).

| Path | Configuration | n | p50 | p90 | p99 |
|---|---|---|---|---|---|
| Firecracker spawn → API | — | 800 | 0.1818 | 0.7268 | 1.0253 |
| Firecracker boot → init (L1→L3) | mem_mb=1024, tier=hdd, cache=cold | 100 | 1.5086 | 1.7946 | 1.9900 |
| Firecracker boot → init (L1→L3) | mem_mb=1024, tier=hdd, cache=warm | 100 | 0.1751 | 0.1822 | 0.1965 |
| Firecracker boot → init (L1→L3) | mem_mb=128, tier=hdd, cache=cold | 100 | 1.5083 | 1.8065 | 2.2312 |
| Firecracker boot → init (L1→L3) | mem_mb=128, tier=hdd, cache=warm | 100 | 0.1509 | 0.1576 | 0.1763 |
| Firecracker boot → init (L1→L3) | mem_mb=256, tier=hdd, cache=cold | 100 | 1.4504 | 1.7556 | 2.2814 |
| Firecracker boot → init (L1→L3) | mem_mb=256, tier=hdd, cache=warm | 100 | 0.1542 | 0.1594 | 0.1739 |
| Firecracker boot → init (L1→L3) | mem_mb=512, tier=hdd, cache=cold | 100 | 1.4902 | 1.8016 | 1.9685 |
| Firecracker boot → init (L1→L3) | mem_mb=512, tier=hdd, cache=warm | 100 | 0.1612 | 0.1674 | 0.1818 |
| Firecracker snapshot create | mem_mb=128, tier=hdd | 1 | 2.7563 | 2.7563 | 2.7563 |
| Firecracker snapshot create | mem_mb=512, tier=hdd | 1 | 6.6802 | 6.6802 | 6.6802 |
| Firecracker restore, load API (L2→L3) | mem_mb=128, tier=hdd, cache=cold | 50 | 0.6413 | 1.0258 | 1.5557 |
| Firecracker restore, load API (L2→L3) | mem_mb=128, tier=hdd, cache=warm | 50 | 0.0066 | 0.0099 | 0.0128 |
| Firecracker restore, load API (L2→L3) | mem_mb=512, tier=hdd, cache=cold | 50 | 0.6267 | 0.9381 | 1.0369 |
| Firecracker restore, load API (L2→L3) | mem_mb=512, tier=hdd, cache=warm | 50 | 0.0068 | 0.0092 | 0.0118 |
| Firecracker restore → first response | mem_mb=128, tier=hdd, cache=cold | 50 | 1.5078 | 2.4577 | 3.4303 |
| Firecracker restore → first response | mem_mb=128, tier=hdd, cache=warm | 50 | 0.0119 | 0.0218 | 0.0243 |
| Firecracker restore → first response | mem_mb=512, tier=hdd, cache=cold | 50 | 1.1384 | 1.5243 | 1.9581 |
| Firecracker restore → first response | mem_mb=512, tier=hdd, cache=warm | 50 | 0.0122 | 0.0205 | 0.0231 |
| QEMU boot → init | machine=microvm | 1 | 1.7221 | 1.7221 | 1.7221 |
| Appliance reboot → kernel | — | 9 | 21.0451 | 22.0885 | 22.4050 |
| Appliance userspace → agent | — | 9 | 30.7440 | 31.3166 | 31.7832 |
| Appliance userspace → attested | — | 9 | 44.4240 | 44.9246 | 45.3840 |
| TPM quote | — | 400 | 0.5062 | 0.5178 | 0.9452 |
| Local attestation round trip | — | 100 | 0.5377 | 0.5455 | 0.5659 |
| TLS 1.3 handshake | — | 2000 | 0.0017 | 0.0026 | 0.0036 |
