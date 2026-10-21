# Component 2: 2,000-photo working set

The user's total image budget is 2,000 across training, validation and test. The previous large training queue is superseded. Completed garbage checkpoints and the interrupted large obstacle checkpoint remain available as historical artifacts; no source data was deleted.

| Selected source/task | Train | Validation | Reserved test | Total |
| --- | ---: | ---: | ---: | ---: |
| TACO garbage segmentation | 1,028 | 286 | 185 | 1,499 |
| WildScenes rock/log detection | 350 | 50 | 101 | 501 |
| Total | 1,378 | 336 | 286 | 2,000 |

Reuse the completed TACO-only L1 model. The completed TACO+MJU L2 run used more photos and is excluded from this budgeted profile. Start compact rock/log training from official pretrained YOLOv8n weights, rather than resuming optimizer state from a run on a different dataset. Both tasks retain source split membership. Selection uses source labels and seed 42, never prediction scores. Rock/log strata include positive rocks, logs and background photos. The source validation split supplies only three rock photos, so rock-specific evidence remains limited. Local trail blockage, clear-trail, erosion and root annotations are still absent.

The working set contains JPEG copies with a maximum image edge of 640 pixels and quality 90. Uniform downsampling retains normalized polygon/box coordinates; there is no crop or rotation. All selected source bytes are checked against previous frozen source inventories, labels are counted, and converted image/label bytes are frozen. Smaller copies can affect small-litter accuracy, so old full-resolution validation scores are not treated as scores for these copies. Task labels stay separate because WildScenes photos have no reviewed litter labels.

The prepared image/label payload is about **257 MB** (decimal), compared with about **8.63 GB** for the same selected original image/label pairs. Filesystem allocation and manifest metadata add overhead. This is a working-copy size comparison, not reclaimed disk space. Larger source downloads remain on disk: the observed raw-data directory is about 114 GiB, and processed data before this working set about 13 GiB. Git ignore rules only prevent uploads; they do not reclaim disk space. Archive/delete obsolete sources only after reviewing the compact set, provenance requirements and the exact paths to remove.

Rebuild/verify from the repository root:

```bash
sajana/.venv-yolov8/bin/python -B -m sajana.src.prepare_compact_component2
sajana/.venv-yolov8/bin/python -B -m sajana.src.train_compact_component2 --smoke --device cpu
sajana/.venv-yolov8/bin/python -B -m sajana.src.train_compact_component2 --device mps
```

The smoke check uses eight selected training photos, with that same training subset as its validation input. The full runner requires the successful smoke check and verifies all frozen compact inputs. It uses the existing shared accelerator lock, 416-pixel inputs, batch 2, workers 0, no RAM image cache, no plots, best/last checkpoints only, up to 50 epochs with patience 15. Trainer YAML contains no test key. Test images are reserved; this runner does not tune or evaluate on them. New optimizer resumes require matching source/configuration/data hashes.

## Model size and Android memory

Dataset size affects laptop storage and training time. With the same architecture, 2,000 or 20,000 training photos produce the same number of model parameters. The Android app packages model files and class/preprocessing metadata; it does not package datasets, Python environments, raw archives or training checkpoints.

The completed TACO YOLOv8n-seg inference checkpoint is **7,021,108 bytes** (about 7 MB). Training has already stripped its optimizer state. A fresh inference-copy check found identical saved inference tensors; repackaging it again did not make it smaller. This `.pt` file is not yet an Android `.tflite` export or a measurement of app RAM.

Post-training INT8 quantization can reduce weight storage and sometimes runtime memory/latency. Google's general comparison is around four times smaller than FP32; the current PyTorch checkpoint already stores half-precision weights, so do not promise another fourfold reduction from its 7 MB size. Converter graph overhead, supported operators and the Android runtime determine the actual artifact size and memory. See [Google's quantization guidance](https://developers.google.com/edge/litert/conversion/tensorflow/quantization/post_training_quantization) and [Ultralytics LiteRT export](https://docs.ultralytics.com/integrations/litert/).

Keep YOLOv8 nano. The next deployment steps are a baseline LiteRT export, an INT8 candidate calibrated only on selected training photos, matched validation accuracy checks, then a physical 4 GB Android test. Use batch 1 for one captured photo, sampled bitmap decoding, reused buffers and serialized inference. Load separate task models sequentially if needed. Do not assume a 7 MB file uses only 7 MB RAM. Additional pruning or distillation requires its own training and accuracy evaluation; it is not needed just to begin Android compatibility work.

See [mobile memory plan](MOBILE_MODEL_SIZE_AND_MEMORY.md), [budget configuration](../configs/component2_compact_2000.json), and [compact readiness](../results/component2_training/compact_readiness.json).
