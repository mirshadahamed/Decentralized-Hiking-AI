# ORFD RGB path preprocessing

ORFD supplies auxiliary vehicle freespace labels for the trail component. Keep it separate from TACO/MJU litter instance masks. Non-freespace does not mean trail damage, and vehicle freespace does not establish hiking safety.

## Source and coverage

The [official repository](https://github.com/chaytonmin/Off-Road-Freespace-Detection) links a [Drive mirror shared with author permission](https://github.com/chaytonmin/Off-Road-Freespace-Detection/issues/6#issuecomment-1347324143). Its archive contains 11,830 RGB/mask pairs, compared with 12,198 images reported in the publication. This preparation records the available mirror subset, with 368 unavailable published frames, rather than claiming full published coverage. The mirror contributor reports extraction problems in that issue. Files successfully acquired here must pass ZIP CRC, full image decoding and source correspondence checks.

| Preserved mirror split | Available pairs | Published count | Missing |
| --- | ---: | ---: | ---: |
| Train | 8,392 | 8,398 | 6 |
| Validation | 1,245 | 1,245 | 0 |
| Test | 2,193 | 2,555 | 362 |

Published split counts are from [Table 1 of the ORFD paper](https://arxiv.org/html/2206.09907).

The mirror flattens original sequence directories. Do not claim verified sequence independence from its filenames. Preserve its train/validation/test membership; do not randomly resplit adjacent video frames. Hold out local trails separately for component evaluation.

The supplied Downloads pack remains untouched. Its audit and code informed the review; they are not the dataset and were not executed as instructions. The project implementation uses Pillow and standard Python rather than the legacy training environment.

## Acquisition and conversion

`download_orfd_rgb` reads the ZIP central directory using HTTP byte ranges and downloads only RGB/mask members in resumable chunks, approximately 16.55 GB. Depth, point clouds and scripts are not extracted. Range responses must match the requested offsets and lengths. ZIP member CRCs are checked during extraction. Source RGBs and colored masks remain in `data/raw/orfd/ORFD/`.

The raw archive cache is a sparse ZIP with only selected byte ranges present. It is not a complete archive of all ORFD modalities. Keep its `drive_completed_ranges.json` alongside it for resume. The source inventory records selected files, sizes and original CRCs.

The converter preserves native geometry and maps masks according to the [official loader](https://github.com/chaytonmin/Off-Road-Freespace-Detection/blob/main/data/ORFD_dataset.py): source RGB blue channel greater than 200 is class 1. Other pixels become class 0. Prepared PNG masks contain **class IDs 0 and 1**, not display intensities 0 and 255. They may appear nearly black in ordinary image viewers; inspect the colored overlay sheets instead. Use nearest-neighbor interpolation for mask resizing in training.

Prepared layout:

```text
data/processed/orfd_path_seg/
  images/{train,val,test}/*.png
  masks/{train,val,test}/*.png
  manifests/{train,val,test}.csv
  conversion_report.json
  readiness.json
```

Each manifest stores original image/mask paths, dimensions, positive pixel counts and SHA256 hashes. Verification checks source coverage, full decoding, image geometry/orientation, exact source-to-output mask conversion, hashes, manifest membership, unexpected files and identical RGB pixels across splits. Sequence overlap is checked when sequence names exist. Reports explicitly flag absent sequence metadata and incomplete published coverage. No model training is performed.

## Run in VS Code

Create `sajana/.venv` using the existing environment task if needed. Install `sajana/requirements_orfd.txt`, then run **ORFD: Download and preprocess** from **Tasks: Run Task**. Individual download, conversion and verification tasks are also provided. Commands from the repository root:

```bash
sajana/.venv/bin/python -m pip install -r sajana/requirements_orfd.txt
sajana/.venv/bin/python -B -m sajana.src.data.download_orfd_rgb
sajana/.venv/bin/python -B -m sajana.src.data.preprocess_orfd_rgb
```

Read `results/orfd_preprocessing/local_readiness.json` and review `{train,val,test}_overlays.jpg` in the same folder. The shared `results/taco_preprocessing/supplied_preprocessing_status.json` includes ORFD readiness separately from litter readiness. A successful download alone does not certify training readiness. Large raw data, generated semantic PNGs and overlay images remain local under ignore rules.

## Current partial recovery

Google Drive stopped the transfer with **Quota exceeded** after 7.48 GB (229 of 507 range chunks). The full dataset is not ready. Saved download state is retained for a later resume; the torrent fallback had no connected peers.

The completed chunks contained **5,999 complete, CRC-validated pairs**: **3,806 training** and **2,193 testing**, with **no validation images**. These are prepared separately under `data/processed/orfd_path_seg_partial/`, preserving source split membership. Use `configs/orfd_path_partial.yaml` for its paths and class mapping. Only the training portion is an auxiliary training pool. Its `training_ready` remains false because the benchmark is incomplete; `training_pool_ready` can become true after all available pairs pass verification. This subset has not been used to train a model.

To recover and preprocess completed chunks again:

```bash
sajana/.venv/bin/python -B -m sajana.src.data.extract_orfd_partial
sajana/.venv/bin/python -B -m sajana.src.data.preprocess_orfd_rgb \
  --raw-root sajana/data/raw/orfd/partial/ORFD \
  --out sajana/data/processed/orfd_path_seg_partial --allow-incomplete
```

The partial folder's `readiness.json` and `results/orfd_preprocessing/partial/` describe the recovered data. Retry **ORFD: Download and preprocess** when Drive permits downloads again; it resumes saved ranges and writes the complete mirror preparation to the separate primary folder. The full mirror still lacks the 368 published frames noted above even after its transfer completes.
