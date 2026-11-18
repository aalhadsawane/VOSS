| node | CPU | cores/threads | memory GiB | disks (class: model) | TPM | memory encryption |
|---|---|---|---|---|---|---|
| node01-i7-12700-64g-nvme | 12th Gen Intel(R) Core(TM) i7-12700 | 12/20 | 62.5 | nvme:Samsung SSD 980 PRO 1TB | firmware INTC | false |
| node02-i7-12700-64g-nvme | 12th Gen Intel(R) Core(TM) i7-12700 | 12/20 | 62.5 | hdd:HGST HUS722T2TALA604; nvme:Samsung SSD 980 PRO 1TB | firmware INTC | false |

Coverage:
- cpu vendor: intel
- storage class: hdd, nvme
- disk models: hdd:HGST HUS722T2TALA604, nvme:Samsung SSD 980 PRO 1TB
- tpm kind: firmware
- memory encryption: false
- core count: 12
- memory (GiB): 62.5

Pairs to look at:
- node01-i7-12700-64g-nvme / node02-i7-12700-64g-nvme: similar (same CPU model, same core/thread count, memory within 25%, same TPM kind, different disk models)

Gaps against NODE_PLAN.md §2:
- 2 node(s): at least 3 distinct nodes are needed
- disk class missing on every node: sata (wanted)
- one TPM kind only (firmware and discrete both wanted)
- core counts within 2x of each other
