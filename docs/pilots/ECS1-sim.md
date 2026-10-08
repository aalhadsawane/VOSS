# E-CS1 (simulated side): start-up and trust establishment per substrate

Lifecycle engine on an isolated C0 host; values from the **placeholder** calibration bundle (literature/assumed until P9) and literature ranges at their midpoint; low/high in `ECS1-sim.csv`. Median seconds (p90 in parentheses).

| substrate | session establish | key release | function | L0 | L1 | L2 | L3 |
|---|---|---|---|---|---|---|---|
| appliance_tpm | 18.98 (22.94) | 0.052 | dynamic-html | 1.442 (1.480) | 0.342 (0.388) | 0.028 (0.036) | 0.002 (0.003) |
| appliance_tpm | 18.98 (22.94) | 0.052 | thumbnailer | 1.843 (1.893) | 0.495 (0.554) | 0.032 (0.041) | 0.002 (0.003) |
| appliance_tpm | 18.98 (22.94) | 0.052 | image-recognition | 7.899 (7.927) | 2.808 (2.858) | 0.086 (0.093) | 0.002 (0.003) |
| appliance_tpm | 18.98 (22.94) | 0.052 | video-processing | 3.090 (3.132) | 0.729 (0.764) | 0.053 (0.062) | 0.002 (0.003) |
| cvm_snp | 1.43 (1.81) | 0.052 | dynamic-html | 2.317 (2.599) | 1.206 (1.437) | 0.155 (0.156) | 0.002 (0.003) |
| cvm_snp | 1.43 (1.81) | 0.052 | thumbnailer | 2.677 (2.969) | 1.313 (1.560) | 0.305 (0.306) | 0.002 (0.003) |
| cvm_snp | 1.43 (1.81) | 0.052 | image-recognition | 8.748 (8.955) | 3.655 (3.814) | 2.505 (2.506) | 0.002 (0.003) |
| cvm_snp | 1.43 (1.81) | 0.052 | video-processing | 3.985 (4.235) | 1.613 (1.898) | 0.505 (0.506) | 0.002 (0.003) |
| coco_pool | 8.32 (10.73) | 0.052 | dynamic-html | 2.189 (2.563) | 1.190 (1.615) | — | 0.002 (0.003) |
| coco_pool | 8.32 (10.73) | 0.052 | thumbnailer | 2.578 (3.067) | 1.304 (1.664) | — | 0.002 (0.003) |
| coco_pool | 8.32 (10.73) | 0.052 | image-recognition | 8.627 (8.987) | 3.605 (4.158) | — | 0.002 (0.003) |
| coco_pool | 8.32 (10.73) | 0.052 | video-processing | 3.815 (4.124) | 1.559 (1.942) | — | 0.002 (0.003) |
| drtm_hv | 2.33 (3.32) | 0.052 | dynamic-html | 1.442 (1.481) | 0.346 (0.394) | 0.028 (0.035) | 0.002 (0.003) |
| drtm_hv | 2.33 (3.32) | 0.052 | thumbnailer | 1.848 (1.898) | 0.509 (0.551) | 0.033 (0.040) | 0.002 (0.003) |
| drtm_hv | 2.33 (3.32) | 0.052 | image-recognition | 7.899 (7.941) | 2.807 (2.845) | 0.085 (0.094) | 0.002 (0.003) |
| drtm_hv | 2.33 (3.32) | 0.052 | video-processing | 3.085 (3.129) | 0.721 (0.770) | 0.053 (0.066) | 0.002 (0.003) |
| none | 0.91 (1.26) | 0.000 | dynamic-html | 1.449 (1.501) | 0.347 (0.387) | 0.030 (0.040) | 0.002 (0.003) |
| none | 0.91 (1.26) | 0.000 | thumbnailer | 1.846 (1.890) | 0.511 (0.561) | 0.032 (0.041) | 0.002 (0.003) |
| none | 0.91 (1.26) | 0.000 | image-recognition | 7.892 (7.947) | 2.807 (2.853) | 0.084 (0.091) | 0.002 (0.003) |
| none | 0.91 (1.26) | 0.000 | video-processing | 3.085 (3.118) | 0.721 (0.766) | 0.055 (0.064) | 0.002 (0.003) |
