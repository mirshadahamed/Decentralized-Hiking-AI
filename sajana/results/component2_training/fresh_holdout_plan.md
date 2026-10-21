# Fresh Component 2 holdout plan

No current record is assigned to a new holdout. This plan preserves the proposed 300 validation, 100 calibration, and 200 fresh final-test quotas while keeping all previously reviewed test images outside the new cycle.

## Holdout source and capture

Capture new, full-resolution local trail photos that have never been used in a model run, prompt/demo review, threshold check, or annotation-selection decision. The selected test set must contain 200 unique photos; validation 300; calibration 100. Holdout photos count toward the 2,000-photo cycle and are separate from its 1,400 training photos. The old reviewed 337 test photos remain quarantined outside the cycle.

Use multiple independent routes and trips per split. As a minimum planning rule, gather at least five independent route/session groups for each holdout split and spread class-positive examples across groups; ten or more groups per split is preferred. A single route, hike, video, or burst stays in one split. If route/site groups cannot provide the needed class coverage, add groups and replace train candidates rather than shrinking a holdout or splitting a route.

Each photo needs immutable ID, image hash, source, site, route, trip/session, sequence and frame IDs where available, timestamp where known, camera/viewpoint, weather, lighting, environment, original dimensions/orientation, and label version. Unknown values stay blank. For a dataset with no reliable route/session metadata, keep its whole source pool in train only; this applies to current Mobima records.

## Grouping and leakage checks

Before split assignment, build connected components from shared source, route, site when appropriate, session/trip, video sequence, burst, exact image hash, and visually confirmed near-duplicate relationships. If two photos connect through any of these keys, their component cannot cross splits. Review all 242 audit near-duplicate candidates (239 Mobima and 3 TACO) before selecting current train candidates. Similarity candidates stay linked until a human confirms separate captures; confirmed duplicates are reduced to one representative or excluded according to the recorded decision.

Use the group assignment as the split unit, then select photos inside each split to meet its quota and coverage. Avoid choosing many consecutive or nearly identical frames from one route. Verify counts by unique image hash and by class-positive photo after annotation review. Check that no group key, exact hash, or confirmed near-duplicate group appears in more than one split. Store the frozen group-to-split mapping with the manifest before model work begins.

## Split use and freeze

- **Train (1,400):** train weights only. This may include reviewed legacy train candidates and new local training examples. Historical validation records can be used only as train candidates after quality checks.
- **Validation (300):** monitor fitting and compare model variants. Do not use it to choose deployment confidence thresholds.
- **Calibration (100):** select confidence thresholds and any post-processing parameters only. No gradient updates or model-variant selection.
- **Fresh final test (200):** freeze labels and groups before training. Evaluate once after all model and threshold choices are locked. Do not inspect per-image predictions to revise this cycle's model; any later iteration requires a new untouched test.

For each split, report unique photos, route/session groups, source and condition distribution, class-complete positives/negatives, annotation coverage, and excluded uncertain labels. Report per-class TP/FP/FN/TN, precision, recall, specificity, false-positive rate, mask/box AP, and confidence intervals. An unmet count or group-diversity target makes the affected class or result inconclusive; it does not authorize treating unknown annotations as negatives.

## Required holdout mix

Validation must contain at least 20 confirmed positive photos for each modeled class, including litter, rock, log/fallen branch, debris, exposed roots, and erosion, plus reviewed hard-negative litter photos. The 100-photo calibration set needs confirmed positives and negatives per thresholded class. The final test targets at least 30 positive and 30 class-complete negative photos per modeled object class; use the 200 photos across classes and conditions with intentional overlap of multi-label scenes. Also cover corridor intersection and each observed condition (`clear`, `partly_obstructed`, `substantially_obstructed`, `uncertain`) where that output is being evaluated. If these requirements cannot fit, collect more fresh groups and revise the budget before training.

The current manifest template records the old 2,560 records for disposition, but leaves all `proposed_new_split` values blank. Append newly collected holdout records only after the capture and group audit. Never copy an old reviewed test photo into this holdout, including under a renamed file.
