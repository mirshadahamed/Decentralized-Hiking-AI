# Component 2: from verified datasets to the Android app

The immediate deliverable is a reproducible litter-segmentation training experiment. The YOLOv8n-seg L1 baseline is running; check [the live training status](../results/yolov8_training/status.json) and [training guide](YOLOV8_TRAINING_GUIDE.md). The full concurrent litter/trail-damage model follows after genuine damage annotations are available. This roadmap records the work order.

## Required photo behavior

The requested app flow is: capture a photo, locate garbage, assess the visible trail for an obstruction, and show the findings on that photo. Garbage and obstacles may occur together, so these are independent findings rather than exclusive image classes.

| Finding | Evidence needed | Current model support |
| --- | --- | --- |
| Garbage detected | Reviewed litter masks/boxes and validation-selected confidence threshold | L1 trains this task; final/local evaluation pending. |
| Visible trail obstruction | Reviewed trail corridor and objects that actually obstruct it, including rocks/logs/branches across the route | No trained obstruction model yet. WildScenes object masks can support a context experiment; presence alone does not establish obstruction. |
| No visible obstruction detected | Assessable trail corridor and evaluated obstruction model, trained with reviewed clear-trail examples as well as obstructions | Not established by the litter model. |
| Unable to assess | Trail outside the photo, poor visibility, uncertain inference, or a required model unavailable | Required result state; do not convert missing predictions/labels into clear-trail claims. |

The result should retain independent litter and obstacle states, model version, confidence and overlay coordinates. The current litter model must return obstacle assessment as unavailable. A litter-free result does not establish that the trail has no obstacles. Only the visible part of the photographed trail can be assessed.

Local collection must include clear trails, natural objects beside a clear route, true obstructions across the route, garbage with/without obstruction, and difficult lighting or obscured trails. Review corridor and obstruction labels together. Keep route/site/session groups separate across training, validation and final test. Start with the planned reviewed pilot, then expand based on class coverage and error analysis; a fixed image count cannot guarantee accuracy.

## 1. Finish the dataset and label alignment

Read the current counts and verification gates in [the dataset status](../results/component2_preprocessing/STATUS.md). Different exports can reuse the same images, so their counts must not be added as independent training examples.

| Source | Supported training target | Role and restriction |
| --- | --- | --- |
| Clean official TACO | Binary litter instance polygons | First segmentation baseline; keep its fixed validation/test sets. |
| MJU-Waste | Binary litter instance polygons | Auxiliary training comparison; use only its training split in the existing TACO+MJU export. |
| Available unofficial TACO | Verified available litter polygons | Optional later experiment after annotation-quality review; keep separate from the first baseline. |
| pLitterStreet | Plastic, pile, face-mask and trash-bin boxes | Separate detection experiment. Five ambiguous orientation cases and one cross-split exact duplicate currently block the canonical export. Boxes do not supply segmentation masks. |
| RUGD | Native terrain/object semantic masks | Separate context task; preserve IDs 1–24 and ignore void ID 0. Reuse terms remain unresolved in the source audit. |
| WildScenes | Native forest terrain/object semantic masks | Separate context task; preserve IDs 1–18 and ignore unlabelled ID 0. |
| WildScenes rock/log derivative | YOLO detection boxes from connected native rock/log regions | Separate context detector; preserves author splits and unknown litter/blockage labels. Not independent new photos. |
| ORFD | Binary vehicle freespace mask | Auxiliary path-context experiment; it is not a hiking-safety or trail-damage label. |
| Mawanella CSV | Geographic count observations | Mapping data; not image training annotations. |
| Local trail photos | Reviewed litter, erosion, roots, trail and selected obstruction annotations | Still missing; needed for local adaptation and final component evaluation. |

Alignment means correct image/label geometry, trustworthy class meanings, traceable source IDs, and suitable splits. It does not mean converting every dataset into one ordinary multiclass folder. For example, RUGD class 5 is `pole`, while WildScenes class 5 is `gravel`. An explicit reviewed mapping is needed before any shared semantic head. Dirt is not automatically erosion, and a log is not automatically a blocked trail.

Retain originals. Resolve pLitter orientation cases by inspecting annotation overlays and recording hash-bound decisions, or quarantine whole images in a documented derived export. Preserve held-out examples when removing training duplicates; do not silently alter the official release. Keep validation/test frame correlation visible in its data card.

## 2. Train and evaluate the first litter baseline

The first two experiments use identical TACO validation/test images so their results can be compared:

| Experiment | Training | Validation | Test |
| --- | --- | --- | --- |
| L1: TACO only | 1,028 images | 286 images | 185 images |
| L2: TACO + MJU auxiliary | 2,513 images | Same 286 TACO images | Same 185 TACO images |

Use [taco_litter.yaml](../configs/taco_litter.yaml) and [litter_taco_mju_aux.yaml](../configs/litter_taco_mju_aux.yaml), preferably their locally generated absolute `data.yaml` equivalents. These are data configs, not complete trainer implementations. The planning profiles in [component2_training_plan.json](../configs/component2_training_plan.json) identify the required readiness reports.

Start with compatible published pretrained weights and fine-tune for litter segmentation. Pretraining provides learned visual features; fine-tuning adapts those features to this task. Training a new model from random weights is a separate experiment, not a prerequisite. See the [PyTorch transfer-learning tutorial](https://docs.pytorch.org/tutorials/beginner/transfer_learning_tutorial.html).

L1 now uses COCO-pretrained YOLOv8n-seg on Apple MPS, with its actual versions and configuration frozen in the run manifest. Continue in this order:

The user has now authorized the remaining compact public-data jobs. See the [executable queue and completion gates](COMPONENT2_REMAINING_TRAINING.md). Its 416-pixel L2 candidate changes resolution/budget from L1 and is therefore a practical model comparison rather than the original data-only ablation described above.

1. Refresh the full source verifiers and freeze dataset/manifest hashes, taxonomy and split membership.
2. Run a small training-set-only check to confirm that images, masks, losses and predictions align.
3. Train L1 with recorded seed, initial-weight hash, input resolution, normalization, batch size, optimizer, learning rate, schedule, augmentation, epoch limit and checkpoint-selection rule.
4. Select checkpoints and thresholds using validation only. Report mask AP/recall and relevant per-class errors; inspect missed small litter and false positives on natural objects. Do not use training loss alone as evidence of accuracy.
5. Train L2 with the same evaluation protocol. Use validation to compare experiments and select the final approach, then evaluate on the held-out test without further tuning.

Record dataset version, code commit, environment, configuration, learning curves, best checkpoint, validation/test metrics, inference overlays and failure cases for each run. The smoke-check and main-run acceptance rules must be recorded before running. No run is currently claimed complete.

## 3. Prepare the full trail-damage component

RUGD/WildScenes/ORFD can support separate context experiments or compatible encoder adaptation. Their class IDs, tasks and partially annotated scenes cannot be merged directly with litter data as if all missing classes were negative. Any encoder transfer must use compatible architectures; final heads must use the reviewed target taxonomy.

Collect a reviewed local pilot before expanding collection. The existing 50–100-image pilot and 1,000–2,000-image overall figures are planning targets from the component plan, not guaranteed sample requirements or completed data. Inspect class balance and annotation disagreement before deciding whether more collection is needed. Public images with genuinely suitable permissions and labels can also supplement the damage task; no matching erosion/root source has been verified in the current collection.

`data/local_trails/class_coverage.csv` is a review ledger, not the model's training labels. Its header-only state is intentional. A missing row means a class is unreviewed. Record one real image/class review per row, reference its actual annotation export, and distinguish reviewed absence from missing labels.

Group local splits by route/site/session and duplicate groups before augmentation. Keep a local test set that has not been used for model selection. The final concurrent export needs either exhaustive joint annotations or an implemented and tested loss/data loader that handles unknown classes/regions. The current templates do not implement that trainer. Annotate passability separately; do not invent it from ORFD freespace or object presence.

## 4. Export and validate inference

After task and local evaluation pass, select the phone runtime and export a compatible model. Check exported predictions against the training model using fixed images, then benchmark accuracy, latency and memory on an actual Android device. Recheck accuracy after quantization or other optimization. Preserve the exact input preprocessing and output class mapping with the model artifact.

The target is now a physical Android phone with about 4 GB RAM, using the Android Studio emulator first for app behavior. The [mobile size and memory guide](MOBILE_MODEL_SIZE_AND_MEMORY.md) and [deployment plan](../configs/mobile_deployment_plan.json) record a smaller inference-copy tool, 640/416 resolution and INT8 comparisons, and unmeasured device budgets. The ongoing YOLOv8 training protocol remains fixed; mobile optimization is evaluated separately.

The inference interface should return structured predictions: model/version, classes, confidence and mask/box geometry. Any severity/passability output needs its own reviewed labels and evaluation. Keep image coordinates consistent through resizing and orientation handling.

The [obstacle context export and route-advisory prototype](OBSTACLES_AND_ROUTE_ADVISORY.md) prepare the next stage. Marked-trail alternatives use reviewed, located blockage observations and a supplied permitted trail graph. Visible bypass suggestions remain pending corridor/surface/clearance review. The planner does not infer either feature from litter alone.

## 5. Add the bot and app

The project is already Flutter-based. Android Studio can be the IDE and Android build/debug environment; the component does not need a second app implementation simply to use that IDE. Follow the [official Flutter Android setup](https://docs.flutter.dev/platform-integration/android/setup).

Place the app feature in the repository's Component 2 boundary. Decide whether inference runs on-device or through a backend after the phone benchmark. Connect image capture/upload, preprocessing, inference, overlays and result handling first. Define what the requested bot should do, then connect it to verified model outputs. A conversational response does not validate a vision prediction.

The present priority is dataset readiness and a clearly specified first training experiment. Bot development and Android integration follow measured model behavior.
