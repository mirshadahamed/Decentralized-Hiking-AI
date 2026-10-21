# Supplemental trail-data training report

Checked: 21 October 2026. **Training completed; trail-detector accuracy gate failed.**

## What was prepared

The new profile contains 560 trail photos: 293 annotated MobimaSkidRoads photos and 267 selected GOOSE photos. With the existing 1,499 TACO litter photos, the combined profile is 2,059 photos, about 3% above the earlier 2,000 target. Train, validation and test photo hashes and GOOSE recording sequences are disjoint. The final 51-photo test uses camera RGB inputs paired to native semantic masks; it excludes GOOSE colorized label images.

YOLOv8n trained seven object classes: tree, stump, stem, GOOSE obstacle region, Mobima non-passable obstacle, debris and rock. The model ran 16 epochs on CPU at 416 pixels with batch 2, no image cache and early stopping. The best `.pt` checkpoint is 6,465,002 bytes. This detector does not include garbage; the TACO litter model remains separate.

The Pakistan garbage dataset was not merged into the segmentation model: its labels are image-level garbage/not-garbage categories, not object outlines or boxes. The “not garbage” images require visual review before they can serve as clean negatives. GOOSE has only eight source-positive exposed-root photos and does not label erosion or route passability, so roots and erosion were not trained.

## Results

| Measure | Validation | Fresh GOOSE extension test |
| --- | ---: | ---: |
| Photos | 118 | 51 |
| Overall box precision / recall | 0.568 / 0.209 | 0.073 / 0.052 |
| mAP50 | 0.156 | **0.018** |
| mAP50–95 | 0.077 | **0.009** |

At the fixed 0.25 confidence photo check, the model detected 3 of 46 obstacle-region photos, 2 of 43 rock photos, and 0 of 38 debris photos. It detected 9 of 42 tree photos and falsely flagged 2 of 9 tree-negative photos. The non-passable-obstacle class has 32 training boxes and one validation box, with no positive test examples, so its accuracy is unknown.

**Do not use this checkpoint to decide whether a route is clear or recommend an alternative.** The final test generalization is very poor. The best checkpoint and full metrics are local/ignored; the committed source scripts and manifests record how to reproduce them. The Mac run also does not establish Android latency or memory use.

## Reproduction and source notes

- Preprocess: `sajana/.venv-yolov8/bin/python -m sajana.src.data.prepare_cycle2_trail`
- Train: `sajana/.venv-yolov8/bin/python -m sajana.src.train_cycle2_trail`
- Evaluate the selected checkpoint: `sajana/.venv-yolov8/bin/python -m sajana.src.evaluate_cycle2_trail`
- Machine-readable coverage, readiness, run and score records are in this directory.
- GOOSE classes and license: [official class definitions](https://goose-dataset.de/docs/class-definitions/), CC BY-SA 4.0.
- MobimaSkidRoads: [KIT publication and dataset record](https://publikationen.bibliothek.kit.edu/1000162515), DOI 10.35097/1750, CC BY-SA 4.0.
- Pakistan garbage source: [Zenodo record](https://zenodo.org/records/17025661), CC BY 4.0.
