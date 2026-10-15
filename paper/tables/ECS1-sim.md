# E-CS1 (simulated side): start-up and trust establishment per substrate

Lifecycle engine on an isolated C0 host; values from the **placeholder** calibration bundle (literature/assumed until P9) and literature ranges at their midpoint; low/high in `ECS1-sim.csv`. Median seconds (p90 in parentheses).

| substrate | session establish | key release | function | L0 | L1 | L2 | L3 |
|---|---|---|---|---|---|---|---|
| appliance_tpm | 19.24 (23.81) | 0.052 | dynamic-html | 1.446 (1.484) | 0.346 (0.393) | 0.029 (0.038) | 0.002 (0.003) |
| appliance_tpm | 19.24 (23.81) | 0.052 | thumbnailer | 1.848 (1.890) | 0.502 (0.548) | 0.032 (0.041) | 0.002 (0.003) |
| appliance_tpm | 19.24 (23.81) | 0.052 | image-recognition | 7.901 (7.943) | 2.807 (2.854) | 0.085 (0.095) | 0.002 (0.003) |
| appliance_tpm | 19.24 (23.81) | 0.052 | video-processing | 3.086 (3.133) | 0.726 (0.772) | 0.053 (0.062) | 0.002 (0.003) |
| cvm_snp | 1.41 (1.79) | 0.052 | dynamic-html | 2.310 (2.598) | 1.187 (1.436) | 0.155 (0.156) | 0.002 (0.003) |
| cvm_snp | 1.41 (1.79) | 0.052 | thumbnailer | 2.695 (3.005) | 1.367 (1.696) | 0.305 (0.306) | 0.002 (0.003) |
| cvm_snp | 1.41 (1.79) | 0.052 | image-recognition | 8.736 (9.021) | 3.656 (3.928) | 2.505 (2.506) | 0.002 (0.003) |
| cvm_snp | 1.41 (1.79) | 0.052 | video-processing | 3.924 (4.197) | 1.564 (1.808) | 0.505 (0.506) | 0.002 (0.003) |
| coco_pool | 8.11 (10.55) | 0.052 | dynamic-html | 2.254 (2.655) | 1.137 (1.483) | — | 0.002 (0.003) |
| coco_pool | 8.11 (10.55) | 0.052 | thumbnailer | 2.692 (3.131) | 1.291 (1.791) | — | 0.002 (0.003) |
| coco_pool | 8.11 (10.55) | 0.052 | image-recognition | 8.696 (9.161) | 3.590 (3.991) | — | 0.002 (0.003) |
| coco_pool | 8.11 (10.55) | 0.052 | video-processing | 3.882 (4.388) | 1.509 (1.824) | — | 0.002 (0.003) |
| drtm_hv | 2.31 (3.14) | 0.052 | dynamic-html | 1.443 (1.493) | 0.340 (0.383) | 0.028 (0.036) | 0.002 (0.003) |
| drtm_hv | 2.31 (3.14) | 0.052 | thumbnailer | 1.845 (1.886) | 0.500 (0.547) | 0.032 (0.042) | 0.002 (0.003) |
| drtm_hv | 2.31 (3.14) | 0.052 | image-recognition | 7.900 (7.937) | 2.804 (2.854) | 0.085 (0.093) | 0.002 (0.003) |
| drtm_hv | 2.31 (3.14) | 0.052 | video-processing | 3.088 (3.133) | 0.718 (0.761) | 0.055 (0.064) | 0.002 (0.003) |
| none | 1.06 (1.57) | 0.000 | dynamic-html | 1.450 (1.495) | 0.344 (0.383) | 0.028 (0.039) | 0.002 (0.003) |
| none | 1.06 (1.57) | 0.000 | thumbnailer | 1.846 (1.893) | 0.499 (0.543) | 0.031 (0.041) | 0.002 (0.003) |
| none | 1.06 (1.57) | 0.000 | image-recognition | 7.900 (7.948) | 2.811 (2.855) | 0.085 (0.094) | 0.002 (0.003) |
| none | 1.06 (1.57) | 0.000 | video-processing | 3.087 (3.131) | 0.718 (0.775) | 0.054 (0.064) | 0.002 (0.003) |
