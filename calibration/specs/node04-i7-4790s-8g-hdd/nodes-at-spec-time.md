| node | CPU | cores/threads | memory GiB | disks (class: model) | TPM | memory encryption |
|---|---|---|---|---|---|---|
| node01-i7-12700-64g-nvme | 12th Gen Intel(R) Core(TM) i7-12700 | 12/20 | 62.5 | nvme:Samsung SSD 980 PRO 1TB | firmware INTC | false |
| node02-i7-12700-64g-nvme | 12th Gen Intel(R) Core(TM) i7-12700 | 12/20 | 62.5 | hdd:HGST HUS722T2TALA604; nvme:Samsung SSD 980 PRO 1TB | firmware INTC | false |
| node04-i7-4790s-8g-hdd | Intel(R) Core(TM) i7-4790S CPU @ 3.20GHz | 4/8 | 7.2 | hdd:WD5003ABYX-23 | none  | false |

Coverage:
- cpu vendor: intel
- storage class: hdd, nvme
- disk models: hdd:HGST HUS722T2TALA604, hdd:WD5003ABYX-23, nvme:Samsung SSD 980 PRO 1TB
- tpm kind: firmware, none
- memory encryption: false
- core count: 4, 12
- memory (GiB): 7.2, 62.5

Pairs to look at:
- node01-i7-12700-64g-nvme / node02-i7-12700-64g-nvme: similar (same CPU model, same core/thread count, memory within 25%, same TPM kind, different disk models)

Gaps against NODE_PLAN.md §2:
- disk class missing on every node: sata (wanted)
