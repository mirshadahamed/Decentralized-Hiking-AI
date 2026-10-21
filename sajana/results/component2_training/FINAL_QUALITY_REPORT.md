# Component 2 final public-data quality check

Completed: 21 October 2026. **Current cycle complete; accuracy acceptance failed; development use only.**

The frozen 2,000-photo profile contains 1,499 TACO garbage photos and 501 WildScenes rock/log photos, including 336 validation and 286 final-test photos. Source split membership and file hashes were verified. Local trail-condition ground truth is absent. This report does not establish complete component coverage.

## Training and model selection

| Run | Completed epochs | Outcome |
| --- | ---: | --- |
| TACO garbage L1, YOLOv8n-seg | 100 | Original baseline retained |
| Compact rock/log O1, YOLOv8n | 34 | Early stopping after 15 epochs without improvement; best epoch 19 retained |
| Garbage detail refinement | 15 | Did not improve the validation selection score |
| Rock/log detail refinement | 45 | Did not improve the validation selection score |

Native validation AP50–95 for the retained garbage model was 0.3224 at 640 pixels versus 0.3124 for its refinement. Retained rock/log validation AP50–95 was 0.1411 at 416 pixels versus 0.1293 for its refinement at that size. Both candidates were also checked at the alternative resolution. These are validation localization measures, not photo accuracy. Details: [refinement completion](quality/refinement_completion.json), [model comparisons](quality/model_comparisons.json).

Checkpoint, resolution, export format and thresholds were [frozen](quality/frozen_selection.json) before final-test inference. Calibration used training photos only. No final-test optimization was performed.

## Frozen-model final test results

| Localization measure | Garbage masks | Rock boxes | Log boxes |
| --- | ---: | ---: | ---: |
| Positive photos | 185 | 30 | 73 |
| Labelled objects/regions | 497 | 48 | 278 |
| AP50 | 0.4356 | 0.0432 | 0.0483 |
| AP50–95 | 0.2900 | 0.0123 | 0.0117 |

Garbage object/mask precision and recall at the frozen localization confidence were approximately 0.546 and 0.450. Rock/log mean box AP50 was 0.0457. The framework's interpolated log precision at the high scalar localization threshold is 1.0 with **zero recall**; this must not be read as 100% correctness. The separate photo-presence interface uses the frozen per-class thresholds below.

| Photo-presence check | Garbage | Rock | Log |
| --- | ---: | ---: | ---: |
| Frozen confidence | 0.3984 | 0.39 | 0.03 |
| Positive photos detected | 182 / 185 | 5 / 30 | 71 / 73 |
| Positive photos missed | 3 | 25 | 2 |
| Negative photos falsely flagged | Not measurable: zero negatives | 0 / 71 | **20 / 28** |
| Negative photos correctly unflagged | Not measurable | 71 | 8 |

These counts test whether any detection of a class appeared in the photo; they do not require correct object localization. Garbage false alarms/general photo accuracy cannot be established because the holdout has no garbage-negative photos. Log false-positive rate was 71.4%. Rock positive-photo recall was 16.7%. Source rock/log-negative labels are task-specific, not evidence that the path is clear.

The predefined validation gate required per-class precision at least 0.8, recall at least 0.7 and at least 20 positive validation photos per class. Litter and log precision/recall failed; rock recall and coverage failed (only three rock validation photos). **No model is accepted for app accuracy.** Full machine-readable results are in [public_test_results.json](quality/public_test_results.json).

## Compression and functional checks

| Selected development model | Input | File size | Storage format |
| --- | ---: | ---: | --- |
| YOLOv8n-seg garbage | 640 | 3,643,497 bytes | INT8 weights; float32 inputs/outputs |
| YOLOv8n rock/log | 416 | 3,317,189 bytes | INT8 weights; float32 inputs/outputs |
| Combined | | **6,960,686 bytes** | About 7 MB |

The conversion pipeline preserved source checkpoints. Full validation compared compressed files against native models and checked each class, rejecting variants with AP degradation above 0.02 or recall degradation above 0.03. Static INT8 candidates collapsed to zero AP and were rejected. Selected dynamic INT8 weights retained the original validation quality closely; compression did not solve the underlying weak accuracy. See [export verification](quality/export_verification.json).

All **175 software tests passed**. The exact final manifest/assets processed a real validation photo, returning a garbage detection and normalized outline with `trail_condition=not_assessed` and `model_quality_accepted=false`. The stable [functional completion record](workflow_completion.json) records its input and manifest hashes.

The standalone LiteRT CPU check ran the same photo 40 times per model with finite, repeatable outputs and stable final memory samples. Mac warm median/p95 interpreter-call measurements were 65.5/84.8 ms for garbage and 22.0/25.8 ms for rock/log. Mac process peak RSS was about 181 MB, including Python, NumPy, decoding and interpreter overhead. These measurements exclude app UI/postprocessing and **do not establish Android latency, app PSS or a 4 GB phone memory guarantee**. See [desktop benchmark](litert_desktop_benchmark.json).

The [development bundle record](development_bundle.json) identifies the local ZIP, checksum and size. It contains both models, their portable manifest, quality report and handoff instructions. Photos, checkpoints and Python environments are excluded. Android compilation, emulator integration and physical-device testing are pending.

## Required next cycle

Review failures and improve representative labelled examples within the agreed image budget, including garbage-negative trail photos and stronger rock/log coverage. Collect reviewed local blockage/clear-trail, root and erosion labels; do not invent them from object absence. Use grouped local evaluation and a fresh independent final holdout for any further model selection, because this cycle's test results have now been examined.

The prepared [handoff](../../docs/COMPONENT2_DEVELOPMENT_HANDOFF.md) supports prototype photo capture/import and object overlays. Actual blocked/clear judgments and route recommendations remain unavailable until the missing supervision, evaluation, map and location inputs are supplied and tested.

## Supplemental trail-data cycle (21 October 2026)

A separate seven-class YOLOv8n trail-object model was trained from GOOSE semantic regions and MobimaSkidRoads annotations. This profile adds 560 trail photos and brings the combined active profile to 2,059 photos. The corrected, sequence-separated GOOSE extension test uses real camera photos, not colorized label images. The checkpoint reaches only 0.018 mAP50 and 0.009 mAP50–95 on that test; at confidence 0.25 it detects 3/46 obstacle-region, 2/43 rock, and 0/38 debris-positive photos. It fails quality acceptance and must remain development-only. Roots/erosion/passability labels remain unavailable, and the TACO litter model was not retrained. Details: [supplemental report](../component2_cycle2/SUPPLEMENTAL_TRAINING_REPORT.md) and machine-readable [trail training metrics](../component2_cycle2/trail_training.json).
