| node | CPU | cores/threads | memory GiB | disks (class: model) | TPM | memory encryption |
|---|---|---|---|---|---|---|
| node01-i7-12700-64g-nvme | 12th Gen Intel(R) Core(TM) i7-12700 | 12/20 | 62.5 | nvme:Samsung SSD 980 PRO 1TB | firmware INTC | false |

Coverage:
- cpu vendor: intel
- storage class: nvme
- disk models: nvme:Samsung SSD 980 PRO 1TB
- tpm kind: firmware
- memory encryption: false
- core count: 12
- memory (GiB): 62.5

Pairs to look at:
- none

Gaps against NODE_PLAN.md §2:
- 1 node(s): at least 3 distinct nodes are needed
- fewer than 2 disk classes (HDD, SATA SSD, NVMe)
- one TPM kind only (firmware and discrete both wanted)
- core counts within 2x of each other
