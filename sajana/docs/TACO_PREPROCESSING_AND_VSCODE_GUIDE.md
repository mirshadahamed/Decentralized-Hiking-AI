# Ground-Level Vision for Concurrent Litter Detection & Trail Damage Segmentation

This workspace prepares the TACO data already supplied for the component's litter baseline. The other component datasets can be added when uploaded. Current training labels use **`0 = litter`**; original TACO category IDs remain available for a later taxonomy mapping.

## Prepared data

| Dataset | Images referenced | Litter instances | Role |
|---|---:|---:|---|
| Original official baseline | 1,500 | 4,784 | Preserved source baseline under `taco_litter_seg` |
| Cleaned official dataset | 1,499 | 4,783 | Primary dataset under `taco_litter_seg_clean`; existing image files reused |
| Validated unofficial extension | 3,808 | 8,134 | Separate optional train-only annotation pool under `taco_unofficial_litter_seg`; image files not supplied |

The cleaned official split contains:

| Split | Images | Instances |
|---|---:|---:|
| Train | 1,028 | 3,611 |
| Validation | 286 | 675 |
| Test | 185 | 497 |

One exact duplicate was removed from the cleaned official training split: image ID `1173` (`batch_7/000000.JPG`). Image ID `1305` (`batch_8/000005.jpg`) has identical image bytes and the more complete two-object annotation, so that record is retained. No images were moved between splits. The original source JSON and original baseline files remain present.

The unofficial source contains 3,831 image references and 8,334 annotations. Strict validation identifies 32 invalid annotations across 23 images, including empty polygons and coordinates outside image bounds. Those **whole images**, containing 200 annotations in total, are excluded from the validated extension. Removing only the invalid objects would leave partially annotated images and teach false background. Every exclusion is recorded for later review; no polygons are invented or severely out-of-bounds regions silently clamped.

The unofficial labels are preprocessed, but the corresponding photographs are absent. This is a separate pool with no validation/test split, and it is not merged with the official benchmark. Its source URLs are retained for future acquisition.

## Run preprocessing in VS Code

Open the repository root `Decentralized-Hiking-AI` in VS Code. Select **Terminal → Run Task → TACO: Preprocess supplied data**.

This task:

1. Reads the supplied official and unofficial annotation files.
2. Checks official image coverage and removes exact within-split duplicates in a derived dataset.
3. Quarantines entire unofficial images with invalid polygons.
4. Converts retained polygons into normalized YOLO segmentation labels, preserving original IDs and category metadata.
5. Reuses local official images, verifies the cleaned official dataset, and audits unofficial labels.
6. Writes the status, dataset register, conversion reports and exclusion records.

The task uses local files and performs no downloads. The original official baseline must already contain its images, as it does in the current workspace. To restore missing baseline images, use **TACO: Download, preprocess and verify**, or **TACO: Import, preprocess and verify** for a local image folder.

Other tasks:

- **TACO: Regenerate labels** — reruns supplied-data preparation, including verification.
- **TACO: Verify complete dataset** — full audit of the cleaned official dataset.
- **TACO: Audit uploaded labels** — source/label audit of the cleaned official dataset without image decoding.
- **TACO: Audit unofficial labels** — validates the separate unofficial annotation pool.
- **TACO: Preview polygon overlays** — creates cleaned official source/overlay comparisons.
- **TACO: Run preprocessing tests** — regression checks for conversion, filtering, source coverage and image alignment.
- **TACO: Regenerate original baseline labels** — reproduces the original 1,500-image benchmark, including its original duplicate; this does not replace the cleaned dataset.

For debugging, install VS Code's Python and Python Debugger extensions. Select `sajana/.venv/bin/python` on macOS/Linux or `sajana/.venv/Scripts/python.exe` on Windows, then choose **TACO: Debug preprocessing** under Run and Debug.

## Terminal commands

Run these commands from the repository root. The environment and lightweight dependencies already exist locally; the setup commands are included for another checkout.

```bash
python3 -m venv sajana/.venv
sajana/.venv/bin/python -m pip install -r sajana/requirements_preprocess.txt

# Process the supplied sources and existing images; no new image downloads.
sajana/.venv/bin/python -B -m sajana.src.data.prepare_supplied_taco

# Full cleaned official verification.
sajana/.venv/bin/python -B -m sajana.src.data.verify_taco_ready \
  --dataset sajana/data/processed/taco_litter_seg_clean \
  --annotations sajana/data/interim/taco/annotations_official_cleaned.json \
  --report sajana/results/taco_preprocessing/official_clean_readiness.json

# Create source/polygon comparisons.
sajana/.venv/bin/python -B -m sajana.src.data.contact_sheet \
  --dataset sajana/data/processed/taco_litter_seg_clean \
  --output-dir sajana/results/taco_preprocessing/clean
```

On Windows use `python` to create the environment and replace `sajana/.venv/bin/python` with `sajana/.venv/Scripts/python.exe`.

To audit only the supplied unofficial annotations:

```bash
python3 -B -m sajana.src.data.verify_taco_ready \
  --dataset sajana/data/processed/taco_unofficial_litter_seg \
  --annotations sajana/data/interim/taco/annotations_unofficial_validated.json \
  --split-policy train_only --labels-only \
  --report sajana/results/taco_preprocessing/unofficial_labels_audit.json
```

## Evidence and provenance

| File | Meaning |
|---|---|
| `results/taco_preprocessing/supplied_preprocessing_status.json` | Combined preparation status; distinguishes processed annotations from actual image readiness |
| `results/taco_preprocessing/official_clean_readiness.json` | Current full audit for the primary cleaned official dataset |
| `results/taco_preprocessing/unofficial_labels_audit.json` | Annotation-only audit; does not certify missing unofficial images |
| `results/taco_preprocessing/official_exclusions.json` | Exact duplicate evidence, retained/excluded IDs and annotation counts |
| `results/taco_preprocessing/unofficial_quarantine.json` | Every excluded image, invalid record, source index and reason |
| `results/taco_preprocessing/supplied_dataset_register.csv` | Dataset roles, source hashes and actual coverage |
| `data/interim/taco/annotations_official_cleaned.json` | Derived official source with duplicate excluded |
| `data/interim/taco/annotations_unofficial_validated.json` | Derived unofficial source with invalid images excluded |
| `data/processed/<dataset>/conversion_report.json` | Normalization, class mapping, clipping, multipart handling and source SHA256 |
| `data/processed/<dataset>/data.yaml` | Generated absolute paths for this checkout; regenerate after moving the project |

The original binary annotation files are never rewritten. Derived records retain their original image and annotation IDs plus raw source indices. Duplicate annotation IDs `309` and `4040` in the official JSON identify different source records; those records are retained. Undefined scene ID `7` is kept as `unknown_7` rather than assigned an invented scene meaning.

Official images are reused through hardlinks when supported, with copy fallback, to avoid a second full image download. Treat both prepared image directories as read-only; perform augmentation during training.

`training_ready: true` applies to a dataset after full source, label, split, image decoding, geometry, orientation and exact-pixel leakage checks. Label-only verification always reports `training_ready: false`. A complete auxiliary pool can report `training_pool_ready: true` after its images are verified, but it still has no independent evaluation split. Current unofficial images have not been supplied.

The original pack's `dataset_stats.json` and distribution CSVs describe the original baseline. Their 1,500-image/4,784-instance counts are not the cleaned dataset counts. Use the new conversion and readiness reports for the primary cleaned dataset.

## Polygon and image quality

The converter retains one row per instance, joins multipart contours with doubled bridge endpoints, normalizes coordinates and records small boundary clipping. Unsupported masks or larger coordinate errors are rejected. Saved photos retain their source geometry; training performs input resizing.

The downloaded official baseline already has normalized EXIF metadata. Eight source images had invalid EXIF value `0`, which was stripped while preserving annotation-compatible pixels. A reviewed 180-degree correction for `batch_14/000058.jpg` is recorded in `configs/taco_orientation_overrides.json` and bound to the exact source SHA256. The image downloader rejects other ambiguous orientations for review. `orientation_review.jpg` and `exif_zero_review.jpg` preserve the earlier diagnostic comparisons.

Inspect overlays, particularly small litter, multipart objects and corrected images. Automated checks detect structural errors and exact duplicates; they do not prove every source annotation is semantically correct or that different batches represent independent locations.

## Training the current litter baseline

The preprocessing environment is separate from model-training dependencies:

```bash
sajana/.venv/bin/python -m pip install -r sajana/requirements_taco.txt
sajana/.venv/bin/yolo segment train \
  data=sajana/data/processed/taco_litter_seg_clean/data.yaml \
  model=yolov8n-seg.pt epochs=30 imgsz=640 \
  name=taco_litter_pp1 project=sajana/runs
```

Run training after full verification passes and overlays are reviewed. Model weights may download on first use. `configs/taco_litter.yaml` points to the cleaned official dataset; the generated `data.yaml` supplies absolute paths. No model training is performed by preprocessing.

The unofficial extension's generated YAML describes a train-only pool. It is not a standalone evaluation dataset. Review its photographs and provenance before deciding whether to add it to future training.

## Adding the other component data later

This prepared data supports litter detection and instance masks. Trail damage, obstruction, traversable-path masks and passability ground truth require the other datasets and local annotations. Keep new sources separate until class mapping and source-aware splits are defined. Scene labels such as vegetation or dirt are background context, not damage labels. Missing damage annotations mean unknown, not healthy ground.

Retain original categories for the planned final taxonomy; do not reinterpret unlabeled litter as a mixed waste pile. For local trail data, retain route/site/session metadata, keep neighboring frames together, and reserve local held-out data for final evaluation of the concurrent component.

## MJU auxiliary data

MJU has now been imported with all 2,475 matching RGB images and 2,532 litter instances. The combined dataset adds MJU train to TACO clean train while retaining TACO-only validation/test: 2,513 / 286 / 185 images. Use `data/processed/litter_taco_mju_aux/data.yaml` or the **MJU: Preprocess and add data** VS Code task. See [the MJU preprocessing guide](MJU_WASTE_PREPROCESSING_GUIDE.md) for conversion decisions, split limitations, reports and commands. The original TACO-only configuration remains available for comparison.

## ORFD path data

ORFD is prepared separately for binary freespace segmentation, with PNG class-ID masks rather than litter polygons. See [the ORFD preprocessing guide](ORFD_PREPROCESSING_GUIDE.md), the **ORFD: Download and preprocess** task and `configs/orfd_path.yaml`. Its readiness is recorded under `orfd` in the shared status file; it is not merged into the TACO/MJU litter dataset.
