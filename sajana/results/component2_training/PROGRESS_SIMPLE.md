# Component 2 progress in simple terms

Updated: 21 October 2026. This is the committed completion snapshot for the current 2,000-photo training cycle.

**Training, compression and the final public-data tests have finished. The models run, but the accuracy checks failed. They are prepared for development experiments and cannot yet reliably tell a hiker whether a trail is blocked or clear.**

## What is finished

1. **Prepared 2,000 labelled photos**, including the photos kept separate for checking and final testing. Garbage has object outlines; rocks/logs have labelled region boxes. The two tasks use separate labels, so an unlabelled object from another dataset is not automatically taught as absent.
2. **Finished the YOLOv8 nano runs.** The garbage baseline completed 100 passes. The compact rock/log baseline completed 34 passes and stopped after 15 passes without improvement. Additional training completed 15 garbage passes and 45 rock/log passes, using the same image budget. The original models scored better on the model-selection measure, so they were retained. More passes did not solve the weak accuracy.
3. **Compared the models at 416 and 640 pixels**, using only checking photos to choose weights, sizes, confidence settings and compressed formats. Those choices were frozen before using the final test photos.
4. **Created smaller Android-format files.** Garbage uses 640 pixels and is 3.64 MB; rocks/logs use 416 pixels and are 3.32 MB. Together they are **6.96 MB**, about 7 MB. INT8 weight compression retained the checking scores closely; the fully quantized candidates that lost their predictions were rejected. Model file size is different from app RAM.
5. **Checked that inference functions.** All **175 automated software checks passed**. The final files processed an actual photo, producing a garbage box and outline. Each model also produced finite, repeatable outputs over 40 repeated runs on the Mac. These checks establish functioning code, not reliable real-world recognition or Android performance.
6. **Prepared the development handoff:** model files, versioned labels/settings/hashes, a photo-result interface, desktop reference command, final quality report and a ZIP containing the models. Training photos and Python environments are excluded from the ZIP and app assets.

## What data was used

| Task and source | Training | Checking | Final test | Total |
| --- | ---: | ---: | ---: | ---: |
| Garbage: TACO | 1,028 | 286 | 185 | 1,499 |
| Rocks/logs: WildScenes | 350 | 50 | 101 | 501 |
| Total | 1,378 | 336 | 286 | **2,000** |

Only training photos update model weights. Checking photos select model settings. Final tests measure the frozen choices; their results were not used to tune or train the models. The selected image/label payload is about 257 MB. Larger archives and earlier runs remain on the Mac; they are not included in this profile or the app.

MJU and other previously prepared datasets are not all merged into this model. Their tasks and historical runs remain separate. No real local blocked/clear-trail, erosion or exposed-root annotations have been supplied.

## What the final results actually say

These counts ask whether a photo produced any detection of that class. They do not establish that every object was correctly located.

| Photo check | Detected positive photos | Problem still present |
| --- | ---: | --- |
| Garbage | 182 of 185 | Three missed photos. All test photos contain garbage, so false alarms on garbage-free photos are **unknown**. This is not 98% general accuracy. |
| Rocks | 5 of 30 | **25 positive photos missed**; no false alarms on 71 rock-negative photos at the chosen setting. |
| Logs | 71 of 73 | **20 false alarms among 28 log-negative photos**; high detection of positives hides a serious false-alarm problem. |

Object localization is also weak: garbage mask AP50 is **43.6%** and average rock/log box AP50 is **4.6%**. AP measures detection/localization quality across confidence settings, not percentage of photos correctly classified. The predeclared per-class precision/recall checks failed. Only three checking photos contain rocks, which is inadequate coverage for a dependable choice.

The app contract therefore reports garbage and rock/log observations with `model_quality_accepted=false`. It keeps trail condition **not assessed**. A rock beside a path does not establish blockage, and no detections do not establish a clear path. Alternative-route advice needs reviewed obstruction evidence, location and an actual mapped alternative.

## What remains, in order

1. **Improve the data within the roughly 2,000-photo budget.** Review missed objects and false alarms; replace weak/redundant examples with representative hiking photos. Include reviewed garbage-free photos and enough varied rock/log examples. Preserve photo/session grouping when splitting.
2. **Collect the missing trail labels.** Reviewed local photos must distinguish actual blocked versus clear paths and provide the required root/erosion labels. Existing object labels cannot supply those decisions.
3. **Run a new training/evaluation cycle.** This cycle's final tests have now been examined. Any further model selection must use validation and a fresh independent final holdout; repeatedly tuning against the published test scores would overstate progress.
4. **Build the photo-screen prototype.** Use the prepared handoff for capture/import, orientation, overlays and uncertainty. Keep route judgments unavailable until the missing data/model/map requirements are met.
5. **Test on Android.** Android Studio/emulator compilation and a physical 4 GB phone benchmark are pending. Measure latency, peak app memory and repeated-photo behavior on the phone; Mac measurements do not establish those figures.

## Files and commit record

- [Final quality report](FINAL_QUALITY_REPORT.md): scores, limitations and completion evidence.
- [Development handoff](../../docs/COMPONENT2_DEVELOPMENT_HANDOFF.md): files, preprocessing, output meanings and the reference photo command.
- [Bundle record](development_bundle.json): local ZIP path, exact size and checksum. Model binaries are local/ignored; the manifest and reports are versioned.
- `b3b2a4ce`: verified 2,000-photo selection and preprocessing tools.
- `cc379f0b`: compact rock/log training launch.
- `33d546bf`: original run completion and simple progress snapshot.
- `9d4abb5e`: accuracy assessment and bounded additional training.
- `5aa114a5`: compressed export checks and photo inference contract.

The final reports, frozen model manifests and completed-run records form the next commit milestone. Use `git log --oneline -- sajana/results/component2_training/PROGRESS_SIMPLE.md` to see that commit. Images, checkpoints, environments and changing training logs remain ignored.
