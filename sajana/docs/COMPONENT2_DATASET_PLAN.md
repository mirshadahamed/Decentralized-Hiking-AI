# Component 2 dataset plan and annotation data card

This plan covers ground-level litter, trail degradation, route obstructions and path context. It prepares genuine source data for later modelling. It does not create missing photographs, damage masks or passability ground truth. The user confirmed on 2026-10-20 that no annotated local trail data is available yet. Model training is a later stage.

The working scope comes from the Component 2 master document, pages 4–11: litter; erosion/washout; exposed roots; fallen trees/major branches; rock/boulder/rockfall; landslide/rubble/debris; and traversable trail context. The obstruction expansion is identified there as a proposal requiring scope confirmation. Preserve these working annotation keys while recording any later scope decision as a new taxonomy version. Current litter exports remain one class, `0: litter`.

## Preparation order and acceptance evidence

| Order | Work | Acceptance evidence |
| --- | --- | --- |
| 1 | Inventory raw sources, record source/version/licence and intended task; keep original annotations read-only. | Source hashes, source IDs and download/acquisition inventories; no source instructions executed as commands. |
| 2 | Complete the official TACO and MJU litter preparations and verify the existing combination. | Images decode; exact label correspondence; duplicate audit; only MJU train joins TACO train; original TACO holdouts remain fixed. |
| 3 | Recover the optional unofficial TACO photo pool only where source URLs and source labels verify. | Every retained label has the correct photo; failures remain explicitly excluded/pending; duplication against TACO holdouts checked before any merge. |
| 4 | Resume ORFD acquisition and verify the available RGB/mask release without resplitting video frames. | RGB/mask correspondence, lossless binary masks, CRC/hashes and preserved source splits; distinguish downloaded mirror coverage from published coverage. |
| 5 | Add relevant public support only after a source and label audit. | pLitterStreet stays detection data when annotations are boxes. WildScenes/RUGD can support natural-scene appearance. Map only verified source classes; inspect a representative sample before committing to full acquisition. |
| 6 | Collect and annotate local trail scenes using the templates below. | Real images, per-class coverage states, reviewed polygons, site/route/session metadata, uncertainty queue and annotation agreement records. |
| 7 | Assign grouped local holdouts, audit data leakage and freeze a version. | Site/route/session and near-duplicate groups do not cross splits; local test remains untouched; per-class counts and missing-label report published. |
| 8 | Export the task datasets and approve model input. | Litter baseline and auxiliary path data can be independently ready. A concurrent export requires joint complete labels or an implemented missing-label-aware loss/data loader. |

Read current acquisition/count results from `results/taco_preprocessing/supplied_preprocessing_status.json`, `results/training_readiness_recheck.json` and each dataset's own readiness report. This plan deliberately does not embed live download counts that could become stale.

## Source-to-task mapping

| Source | Labels that can be used | Labels that remain unknown | Intended role |
| --- | --- | --- | --- |
| Official TACO | Litter instance polygons; retain `original_category_id` and original category catalog. | Damage, roots, obstruction and trail/path labels. | Main litter baseline and its fixed public holdouts. |
| Unofficial TACO pool | Validated litter polygons when matching photos can be acquired. | Other component classes; photo correspondence until verified. | Optional train-only pool after cross-source duplicate review. |
| MJU-Waste | Source `Rubbish` instances mapped to binary litter; reviewed empty labels are litter negatives only. | Hiking context, damage, route obstruction and trail/path labels. | Auxiliary litter training. Adjacent source frames make its validation/test unsuitable as independent trail evaluation. |
| ORFD | Source blue channel greater than 200 maps to auxiliary vehicle freespace class 1; other source pixels map to class 0. Preserve the original colored masks. | Hiking safety, actual damage, litter and the reason that a pixel is non-freespace. | Separate binary semantic freespace task; never map non-freespace to damage. |
| pLitter supplied Mawanella CSV | Longitude, latitude, plastic count and bin count observations. | Image-level object boxes/masks and all damage/path labels. | Mapping/output-data validation only. Repeated observations are not automatically unique physical litter items. |
| Actual pLitterStreet release, if acquired | Only the source category IDs/names and annotation types present in its released JSON; box annotations support detection. | Segmentation shape where only a box exists; hiking damage/path classes. | Supplementary detection/domain study; polygon reannotation needed for a segmentation subset. |
| WildScenes/RUGD, if acquired | Audited semantic classes such as dirt/mud, vegetation, log and rock where present in the actual source catalog. Retain every source ID/name in the mapping record. | Erosion from dirt, exposed roots from vegetation, fallen-tree obstruction from a generic log, or blockage from rock. | Separate natural-scene/context supervision. These classes are visual context, not verified damage or blockage. |
| RELLIS-3D, if acquired | Verified source terrain/obstacle classes only. | Trail erosion, landslide cause, hiking passability and any unsupported target class. | Optional terrain/context experiment after suitability and licence audit. |
| RoadObstacle21/LostAndFound, if acquired | Source obstacle/freespace benchmark labels, subject to released benchmark terms. | Local hiking damage and final tropical trail evaluation. | Separate benchmark; do not automatically add benchmark test scenes to training. |
| Local hiking imagery | Only classes and attributes actually reviewed on each image. | Every unreviewed class or uncertain/occluded region. | Joint supervision, domain adaptation and final grouped local evaluation. |

Generic dirt is not erosion. A rock or log is not automatically a blocked route. Existing boxes must not be converted to rectangular masks and described as real segmentation ground truth. Model-generated proposals require human correction/review before they become ground truth.

The supplied Downloads packs were inspected as reference data. TACO and MJU packs contain source JSON/labels without photos; the ORFD pack contains loader/code/configuration but no image/mask pairs. The pLitter pack contains the mapping CSV and reference illustrations, without actual pLitterStreet photos or COCO training JSON. `TACO-master/data/annotations.json` retains the original category catalog. No named RUGD, WildScenes, RELLIS or damage pack was found in the targeted Downloads inventory on 2026-10-20.

## Working local annotation keys

These keys reserve annotation concepts; they are not a claim that examples exist. Numeric export IDs for the concurrent model remain unassigned until the label audit and scope review are complete. Keep the existing binary litter model's ID 0 unchanged.

| Key | Annotation rule | Do not label as a positive |
| --- | --- | --- |
| `litter` | One visible artificial waste item per instance; use a separate instance for a mixed pile when individual pieces cannot be distinguished. Optional reviewed `litter_subtype`: `rigid_plastic`, `soft_plastic_paper`, `metal_glass`, `mixed_waste_pile`, `other`, `unknown`. | Leaves, flowers, ordinary branches or unidentified ambiguous objects. Never infer a missing subtype from binary MJU labels. |
| `erosion_washout` | Polygon around visible lost/displaced trail surface, rills/gullies or washout. Describe visible evidence in notes. | Ordinary soil, harmless surface texture, mud or a change of color alone. |
| `exposed_roots` | Region covering a visible exposed root network on/at the trail. Annotate presence separately from severity. | Generic vegetation or an assumed root hidden under soil. Harmless visible roots are not automatically severe hazards. |
| `fallen_tree_major_branch` | Visible fallen trunk/large branch instance. Record its relation to the trail separately. | Upright trees or small twigs. Object presence alone does not establish obstruction. |
| `rock_boulder_rockfall` | Distinguishable substantial rock/boulder or visible rockfall region; preserve an instance/region distinction in attributes. | Ordinary small gravel. Do not infer that a rock has recently fallen from appearance alone. |
| `landslide_rubble_debris` | Visible debris/rubble region, with `origin` recorded as `unknown` unless evidence establishes landslide/another cause. | Every muddy/rocky surface; do not guess a landslide cause. |
| `traversable_trail` | Visible usable trail/access-route surface under a written viewpoint-specific rule. Mark ambiguous/occluded regions for review. | All vehicle freespace, all soil, or hidden trail pixels imagined behind an object. |

Passability is a separate reviewed image/route-level attribute: `clear`, `partly_restricted`, `substantially_blocked`, or `uncertain`. Annotators must record the visible basis and usable alternatives; a single photograph may be insufficient. An unreviewed image has no severity label. Do not calculate final passability truth automatically from ORFD masks.

Before any overlap experiment, specify whether the reference is *visible usable surface* or a *route corridor*. Subtracting an obstruction from a usable-surface mask can produce zero overlap even when it blocks the trail. If a separate corridor annotation is needed, review and version it separately; never fill hidden route pixels automatically and call them observed ground truth.

## Unknown, absent and positive labels

Use one `class_coverage.csv` row per reviewed image/class pair:

- `unreviewed`: no class-specific review; absence of a polygon provides no negative evidence.
- `positive_partial`: at least one positive annotation exists, but remaining instances/regions were not exhaustively reviewed.
- `positive_complete`: all visible instances/regions of that class have been reviewed and annotated; positive count must be greater than zero.
- `negative_reviewed`: the class was explicitly reviewed and is absent; positive count is zero.
- `uncertain`: ambiguity remains, with notes and an optional review-region annotation. Exclude from supervised loss until adjudicated or handled by an explicit ignore mask.

Missing coverage rows mean `unreviewed`. A label file with no rows means a true full-scene negative **only when every exported target class has `negative_reviewed` coverage**. The eight MJU empty litter labels are not negatives for unreviewed trail damage classes.

Standard multi-class YOLO does not infer these coverage states from ordinary `.txt` files. Do not merge class-incomplete TACO/MJU/ORFD images into an ordinary concurrent export: unannotated real classes would become background. Use staged task-specific training, completely review the selected joint subset, or implement and test class/region ignore handling before export. No such missing-label-aware trainer is supplied by these templates.

## Local annotation workspace

`data/local_trails/` contains header-only CSV templates and empty tracked directories. There are no fabricated sample records. Copy real photos into `images/`, source annotation exports into `annotations/`, and disagreement/uncertainty work into `review/`.

1. Assign immutable `image_id`; record the original filename and SHA256 in `image_manifest.csv`. Keep the full-resolution original. Use repository-relative paths; record oriented dimensions so mask alignment is reproducible.
2. Record stable `site_id`, `route_id`, `session_id`, `sequence_id` and `near_duplicate_group_id`. Put all images from the same walk/video/burst or duplicate group together. Record actual timestamps where known; leave unknown values blank rather than inventing them.
3. Annotate polygons with the keys above in an annotation tool and retain its original export. COCO polygons or a documented pixel-mask export are suitable; do not produce final YOLO labels before the class mapping/coverage rules are settled. Native image geometry and class IDs must stay traceable.
4. Record per-class coverage and review states. A second reviewer adjudicates uncertain, rare and difficult scenes. Retain separate original annotator exports for agreement measurement; record IoU/Dice and class agreement before adjudication.
5. Use `passability_review.csv` only for reviewed judgments, with evidence and reviewer identity. Store no invented GPS values or personal identifiers. GPS can be omitted where unavailable.
6. Keep `split` as `unassigned` during collection. Prefer holding out entire sites/routes where enough sites exist. Otherwise hold out complete sessions/sequences and report that the test shares a site. Never randomly split neighboring frames. Near-duplicate groups and connected session/sequence groups must stay within one split.
7. Lock the test assignment before tuning or augmentation. Augment training data only, preserve geometry for labels, and keep test photographs/annotations unchanged.

The master document proposes a 50–100 image collection pilot and approximately 1,000–2,000 local images overall. These are collection targets, not existing counts. Balance genuine positives, hard negatives and difficult conditions; review per-class coverage before increasing volume.

## Readiness gates and present limitation

Public litter preprocessing can finish independently of local data. A complete downloadable ORFD mirror can support an auxiliary path baseline while still missing publication frames and hiking-specific validity. Optional acquisition failures must remain visible, without holding an otherwise verified litter baseline hostage.

The full concurrent component remains unready until genuine erosion/root and selected obstruction/path annotations exist, local grouped holdouts are available, annotation coverage is validated, and a compatible model input/export has been built. No amount of reformatting the existing binary litter and vehicle-freespace labels can satisfy those missing ground truths.

Machine-readable working keys, coverage states, source mappings and readiness gates are in `configs/component2_dataset_plan.json`. This planning file is not a model training configuration or a readiness certificate. Acquisition reports remain the source of truth for current file counts.
