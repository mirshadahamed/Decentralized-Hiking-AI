# Training progress and dataset coverage

This is a historical snapshot of the larger training plan. For the current 2,000-photo profile, see [simple progress](PROGRESS_SIMPLE.md) and live `HEALTH.md`.

Snapshot: 2026-10-21T09:16:13.558465+05:30

L1 has completed 92/100 epochs; epoch 93 is running. Queue: waiting_for_L1.
The current learned task is one-class litter segmentation. Full component ready: **False**.

| Full run | Training images / annotations | Validation / test images | State |
| --- | ---: | ---: | --- |
| L1, YOLOv8n-seg TACO | 1,028 / 3,611 litter instances | 286 / 185 | 92 saved epochs |
| L2, compact YOLOv8n-seg TACO+MJU | 2,513 / 5,138 litter instances | Same 286 / 185 TACO | Queued; only training-only smoke check completed |
| O1, compact YOLOv8n rock/log context | 6,051 / 9,502 derived region boxes | 283 / 2,133 WildScenes | Queued; only training-only smoke check completed |

L2 adds 1,485 MJU training photos to the same 1,028 TACO training photos. Do not add the derived union to its sources as independent images. WildScenes native semantic and derived object exports reuse the same photos.

Latest completed validation: mask precision 75.3%, recall 47.4%, mAP50 51.8%, mAP50–95 31.3%.
Highest complete-validation mask mAP50–95 so far: 32.1% at epoch 85.
These precision/recall values are framework maximum-F1 summaries; deployed confidence has not been selected. AP is not classification accuracy. The best checkpoint can differ from the latest epoch.

From epoch 50 to 91, training segmentation loss declined (1.952 to 1.626), while validation segmentation loss rose (2.247 to 2.347). Mask mAP50–95 changed only from 0.304 to 0.305, with a higher intermediate peak. This suggests a plateau and possible overfitting/diminishing returns, not a confirmed cause. More epochs alone do not establish local trail accuracy.

| Source | Preparation state | Actual use |
| --- | --- | --- |
| taco | verified_prepared | Currently learning litter from its training split |
| mju | verified_prepared | Prepared auxiliary train split; full L2 training queued |
| taco_mju | verified_prepared | Derived union; L2 queued, not an additional independent source |
| unofficial_taco | verified_auxiliary_pool | Optional pool excluded pending annotation-quality review |
| plitter | not_ready | Excluded: five orientation/alignment cases and one cross-split duplicate remain unresolved |
| orfd | verified_prepared | Prepared vehicle-freespace context; excluded from these YOLO task heads |
| rugd | verified_prepared | Prepared terrain context; excluded from these YOLO task heads |
| wildscenes | verified_prepared | Native terrain-semantic task not trained; same photos underpin queued O1 |
| wildscenes_objects | verified_prepared | O1 rock/log region detector queued; no full training yet |

The Mawanella geographic CSV contains observations for mapping, not image supervision. RUGD/ORFD/native WildScenes use terrain/vehicle-freespace semantic labels; they are not automatically compatible garbage or hiking-obstruction labels.

Local trail images found: **0**. Reviewed class-coverage rows: **0**. Reviewed erosion, roots, actual blockage, corridor, clear-trail and independent local holdout data remain absent.
Rock/log presence does not establish a blocked trail; only three author-validation images contain rocks. No garbage detection cannot establish a clear trail.

Next: finish L1; run compact L2 and O1 sequentially; compare complete validation results and select resolution/checkpoint/threshold; perform the reserved public evaluation; obtain and review local ground truth; then validate Android export, accuracy, latency and memory on the 4 GB phone.

This is a versioned snapshot. Live progress is in `HEALTH.md` and `queue_status.json` in this folder. Model selection/public test results were not present at this check.
