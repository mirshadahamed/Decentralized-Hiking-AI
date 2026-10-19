# MJU waste data added to the litter component

The supplied `.txt` files are YOLO segmentation labels: each row starts with class `0`, followed by normalized polygon coordinates. They need matching RGB photos; labels alone cannot train a model.

The Downloads pack contained no photos. Its three COCO JSON files were copied unchanged into `data/interim/mju_waste/`, labels were regenerated from those sources, and the RGB archive was downloaded from the [official MJU repository](https://github.com/realwecan/mju-waste). The Downloads pack remains untouched. Archive extraction selects only `JPEGImages` photos, because `SegmentationClass` masks reuse the same filenames.

| MJU source split | Images | Litter instances | Empty negative labels |
| --- | ---: | ---: | ---: |
| Train | 1,485 | 1,527 | 8 |
| Validation | 248 | 261 | 0 |
| Test | 742 | 744 | 0 |
| Total | 2,475 | 2,532 | 8 |

All images have matching labels and passed decoding, source geometry, orientation, label correspondence and exact-pixel cross-split duplicate checks. Sample polygon overlays were visually reviewed. The source's flat polygons are normalized directly by image dimensions; inconsistent bounding boxes do not rescale polygons. Two annotations have small negative boundary coordinates (maximum overshoot 1.07 pixels); these were clipped under an explicit 2-pixel tolerance and recorded in `conversion_report.json`. Source hashes, IDs and split membership remain in reports/manifests.

## Combined training data

`data/processed/litter_taco_mju_aux/` uses TACO clean train plus MJU train. Validation and test contain only the existing TACO clean holdouts. MJU validation/test remain available separately for inspection.

| Combined split | Images | Litter instances |
| --- | ---: | ---: |
| Train | 2,513 | 5,138 |
| Validation | 286 | 675 |
| Test | 185 | 497 |

Filename timestamps identify 1,116 neighboring pairs within 10 seconds across MJU source splits. Therefore MJU's original validation/test should not support claims of independent trail performance. Its indoor scenes are auxiliary examples; compare TACO-only training with combined training using the same TACO holdouts, then evaluate on a separate local trail dataset. These labels support litter masks; they do not supply trail damage labels.

Use `data/processed/litter_taco_mju_aux/data.yaml` for model training: it contains absolute paths. `configs/litter_taco_mju_aux.yaml` documents the same layout. Keep `configs/taco_litter.yaml` for the TACO-only comparison. Model training has not been run.

## VS Code and commands

Open the repository root. Run **Tasks: Run Task → MJU: Preprocess and add data** to regenerate labels, import already downloaded photos, verify, render overlays and rebuild the combination. The data is already prepared, so running it again is optional. For a fresh environment, create `sajana/.venv` using the existing environment task and run **MJU: Install preprocessing dependencies**. **MJU: Download RGB archive** downloads/extracts photos when absent; a valid local archive is reused.

Equivalent commands from the repository root:

```bash
sajana/.venv/bin/python -m pip install -r sajana/requirements_mju.txt
sajana/.venv/bin/python -B -m sajana.src.data.preprocess_mju_waste
sajana/.venv/bin/python -B -m sajana.src.data.download_mju_waste
sajana/.venv/bin/python -B -m sajana.src.data.prepare_mju_images
sajana/.venv/bin/python -B -m sajana.src.data.verify_mju_ready
sajana/.venv/bin/python -B -m sajana.src.data.build_litter_aux_combined
```

Inspect `results/mju_preprocessing/local_readiness.json`, `results/mju_preprocessing/{train,val,test}_overlays.jpg`, and the combined dataset's `readiness.json`. The shared `results/taco_preprocessing/supplied_preprocessing_status.json` includes MJU and combined readiness. The optional unofficial TACO pool still lacks photos; that does not block this combination.

Prepared photos use hardlinks where possible, with copy fallback. Treat raw and prepared photos as read-only and augment during training. Combined labels are independent copies. Large photos/archive/overlays are kept locally under existing ignore rules.
