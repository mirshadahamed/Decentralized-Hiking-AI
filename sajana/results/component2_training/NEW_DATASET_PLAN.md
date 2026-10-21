# Component 2 new dataset plan

**Status:** proposal only; no training or split assignment has started. **Sources:** `DATASET_ACCURACY_AUDIT.md`, `dataset_accuracy_audit.json`, and `proposed_accuracy_recovery_plan.json` (21 October 2026). **Goal:** prepare a representative, leakage-resistant, maximum 2,000-photo cycle for litter and trail-obstacle development. The image budget is not evidence that the required data already exists.

## Current data disposition

The accompanying `new_dataset_manifest_template.csv` lists all 2,560 audited records with their present profile split, repository path, hashes, labels, grouping proxy, and proposed eligibility. Its `proposed_new_split` field is deliberately blank: the only proposed validation, calibration, and final-test assignments must come from new, unseen, grouped captures.

| Current records | Count | Proposed disposition |
| --- | ---: | --- |
| TACO litter, old train/validation | 1,314 | Training-only candidates after image/annotation quality checks. Old validation is demoted to train-only because it has already influenced model choices. |
| TACO litter, geometry-clean among old train/validation | 1,183 | Mechanically usable candidate labels; geometry checks do not prove annotation completeness. Preserve source coordinates and visually verify sample quality before training. |
| TACO litter, affected by suspect polygon geometry among old train/validation | 131 images, 175 annotation rows | Manual visual repair or exclusion before use. The 175 is the number of suspect polygon rows, not the number of images. |
| WildScenes rock/log, old train/validation | 400 | Training-only candidates, all requiring review. They are weak boxes derived from semantic regions, not verified physical instances or path-blockage labels. |
| GOOSE, old train/validation | 216 | Training-only candidates after class-mapping and visual review. Semantic-region boxes and windshield-view domain limit their fit to hiking obstacles. |
| MobimaSkidRoads, old train/validation | 293 | Training-only pool only. Route/session IDs are missing; keep all selected Mobima records in one group unless original provenance can recover meaningful groups. Review its near-duplicate candidates. |
| Previously reviewed final-test records: TACO 185, WildScenes 101, GOOSE 51 | **337** | **Quarantine from the entire new cycle:** no training, validation, calibration, final testing, threshold selection, or annotation queue. Keep only in this audit inventory with `quarantine_reviewed_final_test`. |

The audit found 209 suspect TACO polygon rows across 154 images overall: 175 rows in 131 non-test images, and 34 rows in 23 already-reviewed test images. Only the 131 non-test images enter the manual queue. The 23 test images remain quarantined. The other 1,183 non-test TACO images pass the numeric geometry checks, but still need normal image/label completeness checks before training.

The 242 perceptual-hash pairs are review candidates, not confirmed duplicate captures: 239 are Mobima pairs (81 historical train/validation, 152 train/train, 6 validation/validation) and 3 are TACO train/train pairs. Visually compare each pair and record decisions; do not automatically delete or treat hash similarity as proof of a duplicate. The old validation members in these pairs remain train-only in the proposed cycle.

The local-trail workspace currently has **zero photos and zero annotations**. It cannot supply trail corridors, corridor intersections, condition labels, or local hard negatives until real photos are collected and reviewed.

No currently audited image is eligible for the new validation, calibration, or fresh final-test sets. The compact and supplemental old validation photos have already influenced development; all old test photos are quarantined. WildScenes sequences also crossed its historical splits. GOOSE has sequence metadata but was used in prior development. Mobima has no usable route/session grouping metadata. A fresh group-held-out local capture is required for independent evaluation.

## Proposed 2,000-photo allocation

| New-cycle split | Unique photos | Allowed source and use |
| --- | ---: | --- |
| Train | 1,400 | Reviewed legacy training candidates and new local training captures. Select only after class coverage, annotation quality, and duplicate review. |
| Validation | 300 | Entirely new, previously unused route/session groups. Use for training decisions and development metrics. |
| Confidence calibration | 100 | Entirely new, previously unused groups, separate from train and validation. Use only to select confidence thresholds; never update weights. |
| Fresh final test | 200 | Entirely new, previously unused groups, frozen before training. Use once for final evaluation; never tune against it. |
| **Total** | **2,000** | Unique photos across the cycle. Old reviewed test images are outside this total and outside the cycle. |

The 2,223 non-test legacy records are only an upper-bound candidate pool, not 2,223 accepted training examples. If 1,400 training photos came only from that pool, at least 823 would be left out; new local training photos should replace weak, redundant, or irrelevant candidates within the 1,400-photo quota. Holdout quotas must not be reduced to make room for training. If the reviewed training candidates cannot meet the requested classes within 1,400, collect more useful local training photos and replace lower-value candidates. Keep the total at 2,000.

Every image must have exactly one split. Group on source plus site/route/trip/session/sequence, and connect all members that share a route, capture session, video burst, exact duplicate, or visually confirmed near-duplicate. Keep each connected group in one split. Use dataset source as the group where source records lack finer trustworthy provenance; therefore the current Mobima pool stays train-only. TACO batch IDs are only a source grouping proxy, not known route IDs. Do not use random frame-level splitting.

## Data required for the two training tasks

Keep litter segmentation and natural-obstacle detection as separate task exports unless every training photo has complete annotations for every exported class. Missing annotations remain `unreviewed`; they must never become background examples by default.

For litter, the selected TACO photos provide positive masks only. Add explicitly reviewed litter-negative photos, including clean trails and hard negatives with leaves, rocks, roots, shadows, mud, puddles, and vegetation. A hard-negative photo can carry several reviewed confusion tags and can also be a positive for a separate obstacle task. It is a negative for litter only when the full visible scene has been checked for litter. Include difficult light, wet surfaces, varied trail materials, distances, viewpoints, and partial occlusion.

For obstacles, visually verify object boxes or polygons and record object identity separately from whether it intersects the trail corridor. Improve positive examples of rock, log/fallen branch, debris, exposed roots, and erosion/washout. WildScenes region boxes and GOOSE/Mobima labels can be retained only where an annotator confirms the intended object mapping; neither source establishes trail obstruction. The current supplemental taxonomy has no erosion/passability supervision and too little validation coverage for several classes.

## Local-trail annotation protocol

Record a full-resolution original and immutable image ID. For each photo, collect source/license or consent reference, SHA-256, dimensions/orientation, capture time when available, site, route, trip/session, sequence/frame, environment, weather, lighting, viewpoint, and near-duplicate group. Leave unknown fields blank. Store masks/polygons and object boxes against the oriented original image.

Annotate these independently:

1. **Objects:** `litter`, `rock`, `log_fallen_branch`, `debris`, `exposed_roots`, and `erosion`. Mark each visible instance/region, and record completeness per class as `unreviewed`, `positive_partial`, `positive_complete`, `negative_reviewed`, or `uncertain`. `negative_reviewed` is allowed only after a deliberate full-scene review for that class.
2. **Trail corridor:** polygon the visible corridor and mark occluded or ambiguous parts as unknown. Do not fill in hidden trail surface.
3. **Object/corridor relation:** for each relevant object, record `intersects`, `does_not_intersect`, or `uncertain`, with the corridor and object annotation references. An object outside the corridor is not a blocking example.
4. **Observed trail condition:** one reviewed image-level value from `clear`, `partly_obstructed`, `substantially_obstructed`, or `uncertain`. Record visible evidence and reviewer. A photo may not show enough context to decide; use `uncertain`. Object presence or an empty label file does not imply `clear`, and no photo alone establishes `safe`, `unsafe`, or a route recommendation.

Before collection starts, update the legacy `passability_review.csv` schema: it currently uses `partly_restricted` and `substantially_blocked`, which do not match the requested new values. Do not mix the old and new enums in a single export. Define an illustrated annotation guide and adjudicate disagreements before freezing labels.

## Coverage gates before any training

The exact targets are in `class_coverage_target.csv`. At minimum, each modeled obstacle class must have **20 manually confirmed positive validation photos** before training begins; the target file uses 20 as a floor and recommends 30 where the 300-photo validation budget allows. Count distinct photos, not boxes. Build class-complete reviewed negatives as well; an absent class label is not a negative unless reviewed.

The coverage rows are per-class checks, not additive photo quotas. One distinct photo may count for multiple classes only when each label is actually present or class-completely reviewed; condition states are mutually exclusive. Never count a single photo more than once for the same class.

For the final test, target at least 30 confirmed positives and 30 confirmed negatives per object class, and report the actual counts and confidence intervals. The 200-photo budget may not support all class-specific targets plus four route-condition states. If any class misses coverage, mark that class inconclusive and collect more data before making a claim; do not silently lower the gate or merge unrelated classes. Calibration needs both positive and negative examples for every thresholded class.

Training remains blocked until the 1,400/300/100/200 grouped manifest has been populated and reviewed, old-test exclusions are verified, labels and class mappings are approved, group and near-duplicate leakage checks pass, and the class coverage gates are met. This document and its templates do not start training.
