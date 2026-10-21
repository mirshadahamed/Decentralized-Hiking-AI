# Component 2 model handoff

This component has a bounded working set of **2,000 unique photos including holdouts**. Training, model comparison, compressed export validation and reserved testing are complete. **Accuracy acceptance failed; the files are for development experiments.** Local trail blockage/clear-path, erosion and exposed-root labels are still missing. See the [final quality report](../results/component2_training/FINAL_QUALITY_REPORT.md) and the bundled `public_test_results.json` for the measured failures.

## Files and commands

The quality workflow has prepared these local assets:

- `assets/models/component2_litter.tflite`: garbage segmentation.
- `assets/models/component2_obstacle.tflite`: rock/log context detection.
- `assets/models/component2_manifest.json`: portable asset names, hashes, labels, input sizes and validation-selected confidence thresholds.
- `sajana/configs/component2_development_models.json`: the same frozen model choices with local paths for desktop checks.
- `sajana/results/component2_training/quality/public_test_results.json`: final public holdout results, including separate object-localization and photo-presence checks.

The root Flutter project already declares `assets/models/` as an asset directory. The two generated model binaries stay ignored by Git. The manifest and source code are versioned. The prepared ZIP contains the model files, hashes, interface description and quality report; it does not contain training photos or Python environments.

Find the ZIP path and checksum in `sajana/results/component2_training/development_bundle.json`. Its `FINAL_QUALITY_REPORT.md` explains the results in plain language; `public_test_results.json` contains the exact scores. When transferring the bundle to another checkout, copy its two `.tflite` files and `component2_manifest.json` into `assets/models/`; keep the names in the manifest. The two models total 6,960,686 bytes (about 7 MB). They use INT8 weights with float32 graph inputs/outputs. Keep `quality_accepted_for_app=false` visible in the prototype.

On reserved photo-presence checks, garbage was detected in 182/185 garbage-positive photos, but there were no garbage-negative photos to establish false alarms. Rocks were detected in only 5/30 positive photos. Logs were detected in 71/73 positive photos but falsely flagged 20/28 negative photos. These are not acceptable results for dependable trail judgments.

Run a real photo through the reference implementation from the repository root:

```bash
sajana/.venv-export/bin/python -B -m sajana.src.predict_component2_photo \
  --image /path/to/photo.jpg \
  --output /private/tmp/component2_photo_result.json
```

This Python command is a desktop reference and integration check. On Android, load the `.tflite` files with a compatible LiteRT/Flutter interpreter; Python and PyTorch are not app dependencies. Android compilation, emulator interaction and a physical 4 GB phone benchmark are separate acceptance steps.

## Input and output contract

1. Apply the photo's EXIF orientation. Decode a sampled bitmap rather than keeping several full-resolution copies.
2. Read each model's input size from the manifest. Preserve aspect ratio, resize using bilinear interpolation, then pad to the square input with RGB `(114,114,114)`. The padding uses the same `round(pad-0.1)`/`round(pad+0.1)` convention as the reference. Reuse buffers and process one photo at a time.
3. Feed RGB `float32` values divided by 255 into NHWC `[1,height,width,3]`. INT8-weight models can still have float32 graph inputs and outputs; inspect tensor metadata rather than assuming an integer input.
4. For YOLOv8 dense output `[1,4+classes+mask_coefficients,anchors]`, the first four channels are **xywh normalized to the padded input**. Class probabilities follow; there is no separate objectness channel. Segmentation has 32 mask coefficients. Detection has none.
5. Apply the manifest's per-class confidence thresholds and class-aware NMS at IoU 0.7, maximum 300 detections. Undo square padding and resizing to display boxes in the correctly oriented photo. The Python reference uses the pinned Ultralytics postprocessing for this step.
6. Garbage also supplies NHWC mask prototypes `[1,height/4,width/4,32]`. Reconstruct each selected mask from its coefficients, crop to its box, remove padding, and map it to the displayed photo. Check output tensor shapes to identify detection versus prototype outputs; tensor order is not assumed.

The native photo command emits normalized box and mask-polygon coordinates, image dimensions, model-manifest hash and image hash. Class IDs belong to each task: litter model class 0 is `litter`; obstacle class 0 is `rock_region`, class 1 is `log_region`.

## Result meanings

The photo-result contract contains:

- `garbage_observation`: `detected` or `not_detected`.
- `rock_log_observation`: `detected` or `not_detected`.
- `detections`: model task, label, confidence, normalized box, and optional garbage-mask polygon.
- `trail_condition`: `not_assessed`.
- `route_advisory`: `requires_map_and_reviewed_obstruction`.
- `model_quality_accepted`: the recorded quality gate, never inferred merely from successful inference.

The app can display object observations and overlays during development. A detection is not a reviewed blockage judgment. No detections do not establish a clear trail. The existing route planner requires an actual map, located/reviewed obstruction inputs and valid mapped alternatives; photo observations alone do not create a detour.

Object AP/precision/recall and photo-presence scores answer different questions and are reported separately. The TACO holdout contains garbage-positive photos only, so it cannot establish a garbage-negative photo false-alarm rate. Rock validation has only three positive images. These limits must remain visible in the development quality report.

## Reproduction and acceptance

Training and export environments are separate. The source training environment remains pinned to Ultralytics 8.4.183 and Torch 2.8.0. `requirements_mobile_export.lock.txt` records the tested Python 3.11 export/runtime environment.

The pinned direct LiteRT Torch exporter documents Linux support. The tested Mac fallback explicitly exports ONNX opset 17, simplifies the graph, normalizes output coordinates and converts through onnx2tf 1.26.3 and TensorFlow 2.19. Conversion dummy inputs and static calibration use selected training photos only. The converter's automatic COCO dummy-image download is replaced with a selected training sample. The trained source checkpoint is preserved.

FP32, FP16 where generated, dynamic INT8-weight and static INT8 candidates are checked on complete validation splits. A smaller file is rejected if any class loses more than 0.02 AP or 0.03 recall relative to the native candidate. Static INT8 candidates that collapsed predictions were rejected; a successful file conversion is not an accuracy check. The final checkpoint, resolution, format and thresholds are frozen before reserved-test inference.

Before accepting the component, review missed objects and false alarms, add reviewed local trail supervision/evaluation, validate camera orientation/overlay behavior, and measure cold start, repeated-photo latency, peak app PSS, heat and battery on the physical target phone. Mac CPU measurements do not substitute for those phone measurements.

Primary references: [LiteRT Torch platform requirements](https://github.com/google-ai-edge/litert-torch#requirements-and-dependencies), [versioned onnx2tf converter](https://github.com/PINTO0309/onnx2tf/tree/1.26.3), [LiteRT runtime](https://ai.google.dev/edge/litert).
