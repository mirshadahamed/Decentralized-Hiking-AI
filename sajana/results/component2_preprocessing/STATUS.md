# Component 2 dataset preparation status

Checked: 2026-10-21T00:12:23.959781+05:30

| Source | Prepared pairs | State | Source release complete |
| --- | ---: | --- | --- |
| taco | 1,499 | verified_prepared | True |
| mju | 2,475 | verified_prepared | True |
| taco_mju | 2,984 | verified_prepared | True |
| unofficial_taco | 3,762 | verified_auxiliary_pool | False |
| plitter | 15,100 | not_ready | False |
| orfd | 11,830 | verified_prepared | True |
| rugd | 7,436 | verified_prepared | True |
| wildscenes | 8,467 | verified_prepared | True |
| wildscenes_objects | 8,467 | verified_prepared | True |

Local jointly annotated trail dataset: **missing**. The annotation workspace and instructions are prepared in `sajana/data/local_trails/`.

The full concurrent component cannot be certified until real local damage/path/passability annotations and independent local holdouts exist.

Binary litter baseline data ready: **True**. YOLOv8 training status: **training**; see `sajana/results/yolov8_training/status.json`.
