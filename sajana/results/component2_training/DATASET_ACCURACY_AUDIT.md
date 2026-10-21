# Component 2 dataset accuracy and leakage audit

**Audit date:** 21 October 2026  
**Purpose:** Check whether the available, preprocessed data can support a trustworthy Component 2 model-recovery cycle.  
**Training started:** No.  **Dataset images/labels changed:** No.

## Finding

The current models are **not ready to make dependable photo or trail-safety judgments**. The existing reports already fail their accuracy gates, and this audit found data coverage, split-leakage, and annotation-quality limits that prevent the old scores from supporting a fresh claim of accuracy. Keep the app's development-only quality state and `trail_condition=not_assessed` unchanged. Do not train, tune thresholds, or report final accuracy against the already reviewed test photos.

The audit covered the exact 2,000-photo compact profile (1,499 TACO litter photos plus 501 WildScenes rock/log photos) and the separate 560-photo GOOSE/Mobima supplemental profile. These are separate task datasets, not one aligned 2,560-photo multi-class dataset. The compact files total about 256.5 MB; the supplemental images and labels add about 38.7 MB. The two packaged on-device models total about 7 MB, while local research checkpoints under `sajana/runs` total about 1.20 GB and should remain outside the app and Git.

## What was checked

The read-only audit script checks the two selected profiles for decodable images, label presence, class counts, normalized box/polygon geometry, annotation size, dimensions, SHA-256 duplicates, near-duplicate candidates, source-group split overlap, and the integrity of the compact inventory and supplemental manifest. It also reads existing dataset-readiness records for TACO, MJU Waste, WildScenes, GOOSE/Mobima, Pakistan Urban Waste, pLitter, ORFD and RUGD. See [the machine-readable audit](dataset_accuracy_audit.json) and [the audit script](../../src/audit_component2_accuracy.py) for file-level details and methods.

The compact inventory has 4,003 listed image/label files; every listed file exists and matches its recorded hash. The supplemental manifest's image hashes and annotation counts also match the current files. The exact-byte comparison found no duplicate image groups in the 2,560 selected records. It found 242 perceptual-hash near-duplicate candidates, including 81 train/validation pairs, all within Mobima. These are review candidates, not confirmed duplicates; the source manifest has no route/session ID with which to prove whether they are separate captures.

## Selected profile coverage

“No class annotation” below means only that the selected label file has no annotation for that class. It does not mean that a trail is clear or passable. In datasets with incomplete annotations, it may not even be a confirmed object-level negative.

| Profile / class | Train photos with label | Validation photos with label | Reviewed old test photos with label | Object/region labels | Main issue |
| --- | ---: | ---: | ---: | ---: | --- |
| TACO litter | 1,028 | 286 | 185 | 4,783 total | Every photo in all three splits is litter-positive; no negative-photo false-alarm rate can be measured. |
| WildScenes rock | 120 | **3** | 30 | 233 | Only three positive validation photos; the selected five source sequences cross splits. |
| WildScenes log | 233 | 33 | 73 | 1,277 | The old test has only 28 log-negative photos, and 20 were falsely flagged. |
| Supplemental tree | 384 | 114 | 42 | 12,564 | Strong class imbalance; 540 of 560 photos are source-positive. |
| Supplemental stump | 35 | 9 | 0 | 86 | No positive test photos. |
| Supplemental stem | 18 | 6 | 0 | 117 | No positive test photos. |
| Supplemental obstacle region | 106 | 42 | 46 | 1,086 | A region/object label is not a trail-blockage label. |
| Supplemental non-passable obstacle | 32 | **1** | 0 | 33 | No positive test photos; validation coverage is inadequate. |
| Supplemental debris | 106 | 30 | 38 | 681 | Test data is from a separate GOOSE extension domain. |
| Supplemental rock | 39 | 25 | 43 | 333 | GOOSE/Mobima definition and WildScenes rock-region labels are not automatically interchangeable. |

The compact obstacle split contains 350 train, 50 validation, and 101 old test photos. It has 70, 15, and 20 fully empty label files in those splits. Per-class no-annotation counts are: rock 230/47/71 and log 117/17/28. Those counts describe the source labels only, not clean hiking-path negatives. TACO has 0 negative photos in train, validation, or test.

The supplemental profile contains 391 train, 118 validation, and 51 old test photos. Its train and validation records include both Mobima and GOOSE; all 51 test photos are GOOSE. The test has no positive stump, stem, or non-passable-obstacle photos. Eight source frames with exposed-root labels were excluded from the trained taxonomy; erosion and route-condition labels are absent. The supplemental detector does not include garbage.

## Annotation and image-quality findings

The 4,783 TACO polygon rows include 4,574 rows passing geometric checks and 209 requiring visual review: 197 self-intersections and 12 repeated consecutive vertices. This parser removes a repeated closing vertex before checking; it does not rewrite labels. Among the 4,574 usable polygons, 2,799 are small, 1,265 medium, and 510 large by polygon pixel area; 1,251 have a bounding-box side under 10 pixels and 236 touch an image edge. Small objects are especially vulnerable to missed detections after resizing. Keep the original coordinates until an annotator confirms any proposed correction.

All 1,510 selected WildScenes box rows and all supplemental box rows pass the numeric geometry checks. Numeric validity does not verify that each box accurately surrounds a physical obstacle. WildScenes boxes were derived from semantic regions and should be treated as weak object localization labels. Mobima's exported labels and GOOSE's semantic-region boxes also have different source meanings; harmonize and visually review the mapping before joint training.

## Leakage and independence

- **TACO compact selection:** its 15 `batch_N` groups are separated by split (10 train, 3 validation, 2 old test). The old test has already been reviewed and is now excluded from every new training, tuning, threshold-calibration, and acceptance step.
- **WildScenes:** all five selected sequences (`K-01`, `K-03`, `V-01`, `V-02`, `V-03`) occur in multiple compact splits. In the full 8,467-frame source manifests, all five sequences cross train and test, and `K-01` is the only validation sequence. Source split names therefore do not provide independent route/session evaluation for this selection.
- **MJU Waste:** all nine date groups cross train, validation, and test. The preprocessing record finds 2,093 adjacent frame pairs under 10 seconds, including 1,116 pairs crossing a split. Its source validation/test must not be used as independent component evaluation. The 8 train negatives are the only MJU negative photos; validation and test have none.
- **GOOSE:** the supplemental profile keeps its 228 represented sequence groups disjoint across train/validation/test. The source's original `val` partition (384 frames from eight groups) is absent from the supplemental profile and is a possible public object-evaluation candidate only after confirming that no existing run or manual review used it. It has sparse target positives, including one exposed-root-positive frame, and cannot substitute for local trail evaluation.
- **Mobima:** source route/session IDs are unavailable. There are 234 train and 59 validation photos, but independence cannot be verified. The 81 cross-split perceptual-hash candidates all come from this source and require manual inspection.
- **Pakistan Urban Waste:** its verified archive has 3,675 photos rather than the description's 3,693; 1,024 photos occur in cross-split similarity clusters. The labels are image-level garbage categories, not segmentation masks or exhaustive object boxes. It is not ready to supply litter masks or verified clean-path negatives.
- **pLitter:** the local readiness record reports four missing train images, one missing validation image, and an identical decoded image across train/validation. It is a street-litter detection dataset, not a trail-condition dataset, and is not currently ready for an independent evaluation.
- **ORFD and RUGD:** both can provide auxiliary visual context only. ORFD's mirror is short by 368 images versus the published count and lacks original sequence identifiers; its vehicle free-space labels are not hiking safety labels. RUGD's official release counts differ from the paper table by 40 images, and dataset reuse terms remain unverified.

## Existing model errors

These are historical measurements from test sets that have now been reviewed. They explain why the models need a new cycle; they are not valid final acceptance scores for a future version.

| Model/class | Historical test result | What it means |
| --- | --- | --- |
| YOLOv8n-seg litter | Mask AP50 0.4356; AP50–95 0.2900; object/mask precision about 0.546 and recall about 0.450 | 182/185 positive photos had a detection and 3 were missed, but every test photo had litter, so photo-level false alarms cannot be measured. High photo-presence recall does not mean accurate masks. |
| YOLOv8n rock | Box AP50 0.0432; AP50–95 0.0123 | Only 5/30 positive photos detected; 25 missed (photo-presence recall 16.7%). The 0/71 source-label-negative flags are not proof of path safety. |
| YOLOv8n log | Box AP50 0.0483; AP50–95 0.0117 | 71/73 positive photos detected, 2 missed; 20/28 source-label-negative photos falsely flagged (71.4% false-positive rate, 28.6% specificity). |
| Supplemental seven-class detector | Extension test mAP50 0.0183 and mAP50–95 0.00877; overall precision/recall 0.073/0.052 | At confidence 0.25 it detected only 3/46 obstacle-region, 2/43 rock, and 0/38 debris-positive photos. It failed badly on this extension domain. |

The prior validation gate was per-class precision at least 0.80, recall at least 0.70, and at least 20 positive validation photos/class. Litter and log missed the precision/recall gate; rock missed recall and had only three validation positives. The supplemental model also failed its held-out extension evaluation. No model is accuracy-accepted for app use.

## Other available data and whether it fits

| Dataset | Current repository record | Component 2 use |
| --- | --- | --- |
| TACO official-clean | 1,499 selected photos; source split preserved; two repeated source annotation IDs are recorded as warnings | Best current litter-mask base. It still needs verified clean and hard-negative trail photos. |
| TACO unofficial auxiliary | 3,762 train-only photos and 8,053 labels; 39 missing/invalid photos and 7 within-pool exact duplicates excluded; annotation review is outstanding | Candidate training-only data after label, duplicate, provenance, and taxonomy review. It has no held-out split and cannot be called an evaluation set. |
| MJU Waste | 2,475 selected photos across source splits; 1,527/261/744 object instances | Optional litter training data only after history and label review. Keep its validation/test away from component evaluation because of temporal leakage and no negative photos. |
| WildScenes 2D | 8,467 selected semantic-region frames, including 3,311 train, 179 validation, and 1,004 test background frames in the source readiness record | Candidate weak supervision for rock/log context. `obstruction_training_ready=false`; no path-blockage ground truth. Rebuild by sequence or obtain new routes. |
| GOOSE/Mobima | 560-image supplemental experiment | Historical development data only for now. GOOSE sequence groups are separated, but the source taxonomy failed on test; Mobima capture groups are unknown. |
| Pakistan Urban Waste | 3,675 verified archive photos, with 1,024 cross-split similarity-cluster photos | Possible image-classification pretraining after visual verification; cannot provide object masks or trail obstacles. |
| pLitter | 15,105 split records, 15,100 verified images, 5 missing images and a cross-split decoded duplicate | Repair and group-audit before considering as auxiliary street-litter training; not trail passability truth. |
| ORFD | 11,830 available vs 12,198 published images | Optional vehicle-scene visual context only; do not treat freespace as hiking-route labels. |
| RUGD | 7,436 official release pairs (4,779/733/1,924); paper table reports 7,456 (4,759/733/1,964) | Optional terrain context only; resolve reuse terms before use and do not map terrain classes to passability. |

## Proposed recovery split and experiments

The assignment is **not yet created** because new, unseen, grouped validation and test photos are not available for all required classes. A planning quota that keeps the next profile at 2,000 photos is 1,400 train, 300 validation, 100 threshold-calibration, and 200 fresh final-test photos. These are photo quotas, not fabricated manifests. Validation, calibration, and especially final test should be new, group-separated photos that no existing run has used. Reserve test groups before training. If class coverage cannot fit those quotas, shrink the training pool rather than weaken the holdout.

Current compact plus supplemental train/validation contains 2,223 candidate development records (1,714 compact plus 509 supplemental). Selecting 1,400 from them would exclude at least 823 records from the next 2,000-photo profile; select after class balance, source taxonomy, quality, and the 81 Mobima near-duplicate candidates are reviewed. Quarantine the 337 already reviewed old-test photos (185 TACO, 101 WildScenes, 51 GOOSE) from the new cycle. Add 600 new held-out photos for the proposed validation/calibration/test quotas; keep the old tests outside the new profile. The 823 count is a planning floor, not a promise that all remaining records are valid or useful.

The experiment matrix is in [the proposed plan](proposed_accuracy_recovery_plan.json). In order:

1. Repair/visually review the 209 suspicious TACO polygons; manually verify real litter-negative and hard-negative trail images. Use the TACO task as segmentation and keep image-level-only datasets out of mask training.
2. Rebuild the rock/log split by complete sequence/route group, remove visually confirmed near-duplicates across splits, and review boxes against the actual obstacle rather than only semantic regions.
3. Add locally photographed and manually labelled rock, log, branch, debris, exposed-root, erosion, mud/water, and clear-trail examples. Annotate object presence separately from corridor intersection and trail condition. No object absence may be converted into `clear` or `safe`.
4. Compare YOLOv8n and YOLOv8s within each appropriate task, with the current 640 litter and 416 obstacle inputs as baselines; test alternative sizes/quantization only after the data split and baseline are frozen. Record model checksum, seed, source-group split, per-class PR/AP, false-positive and false-negative counts, storage, latency, and memory for every run.
5. Choose confidence thresholds using only the calibration set, then run exactly one final evaluation on the untouched new test groups. Report per-class mask/box AP, precision/recall, FP per negative photo, and confidence intervals. Do not merge scores across unrelated sources into one headline number.

Keep the existing gates of precision ≥0.80, recall ≥0.70, and ≥20 positive validation photos/class as minimum development gates, then add verified negative-photo coverage and false-positive limits. The suggested new minimum for a final test is 30 confirmed positive and 30 confirmed negative photos per class, with 100 each preferred for more stable estimates. The report must show counts and confidence intervals. Passing object detection gates still does not permit safety or route claims: `trail_condition` stays `not_assessed` until a separate route-condition model is labeled and independently validated.

## What is missing before trustworthy training

There are currently zero local trail photos and zero local annotations. The `class_coverage.csv` and image manifest are templates, not ground truth. Collect local examples across multiple independent hikes/routes and weather/light conditions. Include both positive and carefully reviewed negative examples for litter and each obstacle class. For route-condition work, annotate the trail corridor and whether each object intersects it; separately label observed condition such as clear, partly obstructed, substantially obstructed, erosion/washout, exposed roots, or uncertain. Record capture group/route/date so frames from one sequence stay together. Preserve uncertainty rather than forcing a class.

The user has confirmed no annotated local trail dataset exists. This is the main blocker to claiming that a phone photo can reliably say whether a hiking trail has an obstacle or can recommend an alternative route. No preprocessing step can manufacture those labels from the current files.

## Outputs and next gate

- [Machine-readable audit](dataset_accuracy_audit.json): counts, geometry findings, hashes, near-duplicate candidates, split leakage, source readiness, and artifact sizes.
- [Proposed recovery plan](proposed_accuracy_recovery_plan.json): split quotas, old-test quarantine, experiment matrix, gates, and missing supervision.
- Training and app code were not changed by this audit. The next authorized step should be collecting/reviewing suitable labeled photos and preparing a new grouped manifest; model training should follow only after that manifest is reviewed.
