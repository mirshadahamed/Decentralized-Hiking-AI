# Component 2 progress in simple terms

Checked: 2026-10-21T13:04:58.824604+05:30. This is a committed snapshot; `HEALTH.md` shows live progress.

We have prepared the smaller dataset and finished training both public-data models: garbage and rock/log detection. The full photo-to-trail-advice feature is not ready yet.

## What is finished

1. We selected and checked **2,000 photos total**, including the photos saved for checking and final testing. Garbage photos have outlines around labelled garbage. Rock/log photos have boxes around labelled regions. Those are two separate learning tasks.
2. We created smaller image copies. The selected image/label payload is about **257 MB**, or roughly 260 MB with overhead. Image orientation, label counts, source split membership and file contents were checked. All current selected file hashes were rechecked for this snapshot.
3. The TACO-only garbage model completed **100 training passes**. We started from an existing pretrained YOLOv8 nano model and taught it the litter task. Its inference checkpoint is about **7 MB**.
4. We stopped the large obstacle run and retained its checkpoint. The smaller obstacle run started from official pretrained YOLOv8 nano weights and completed **34 passes**. It stopped automatically after 15 passes without better checking results and retained its best checkpoint from pass 19. Its inference file is about **6.5 MB**. Both selected model files together are about **13.5 MB**, before Android export; this is file storage, not app RAM.
5. There are **164 passing automated software checks** from the last implementation milestone, plus the current data-file verification. These checks help establish that the code and inputs work; they do not prove real-world prediction accuracy.
6. A basic alternative-route planning function exists and is tested with supplied map/obstruction inputs. It still needs real maps, location matching, reviewed blockage evidence and app integration.

## Where the 2,000 photos go

| Task | Learning photos | Checking photos | Reserved final test | Total |
| --- | ---: | ---: | ---: | ---: |
| Garbage | 1,028 | 286 | 185 | 1,499 |
| Rocks/logs | 350 | 50 | 101 | 501 |
| Total | 1,378 | 336 | 286 | 2,000 |

Learning photos update the model. Checking photos help choose a model and settings. Final test photos remain separate until those choices are fixed. They should not be used to teach or tune the model.

One **epoch** means one training pass through the learning photos. Completing half the planned epochs does not mean the model is 50% accurate.

The larger TACO+MJU garbage run finished before the budget was corrected. Its results are kept as history; it is excluded from the current 2,000-photo profile. Source archives and earlier datasets are still on disk, so the compact working set has not reclaimed their roughly 114 GiB of raw-data storage.

## What the results mean so far

Finished training does not mean reliable prediction. On the existing garbage validation check, the reported mask recall is about 45%: many labelled garbage objects are still missed at that reported operating point. This is a public-data development result, not a phone or local hiking result.

The completed compact rock/log model's checking results remain weak: its reported average recall is about 17%, with misses and false alarms. This figure is a checking-set metric, not general photo-classification accuracy. More passes alone may not solve that. Only three checking photos contain rocks, so rock-specific evidence is especially limited. Next, inspect failure examples and improve the selection or labels within the image budget if required.

A rock beside a path and a rock blocking a path need different decisions. Existing labels identify rock/log regions, not actual hiking blockage. An empty rock/log label file means no annotated rock/log target; it does not prove the path is clear.

## What happens next, in order

1. **Check prediction quality.** Review missed objects and false alarms on checking photos, including small garbage and rocks. Recheck the garbage model with the smaller image copies. Improve examples or labels if needed, staying within the 2,000-photo budget. Choose thresholds/settings using checking photos, then evaluate the fixed models on reserved test photos.
2. **Provide the missing trail labels.** Real local trail photos still need reviewed labels for blocked versus clear paths, exposed roots and erosion. These capabilities cannot be supplied by the current garbage/rock/log labels. Collection/review can run alongside public-model work.
3. **Prepare Android model files.** Export the selected models to the Android format and try INT8 quantization to reduce storage. Compare predictions after conversion, using a training-only calibration subset and separate checking photos.
4. **Measure on a physical 4 GB Android phone.** Check response time, memory and repeated-photo behavior. A small model file does not by itself prove low app memory. The emulator is useful for testing app behavior, but it does not establish physical-phone performance.
5. **Connect the component to the app.** The initial flow is take/import a photo, process it, and display garbage and rock/log detections with uncertainty. Blocked/clear decisions and route suggestions need their additional reviewed trail/map/location evidence before integration.
6. **Review storage cleanup.** Archive or remove the unnecessary large original downloads only after reviewing the verified compact set and the exact files to retain.

The Android app needs the selected model files and their labels/preprocessing information. Training photos and raw archives stay outside the app. Fewer photos reduce laptop storage and training time; model architecture, export precision and image processing determine model/app size and memory.

## Commit record

- `1923a715`: smaller inference snapshots and the 4 GB Android plan.
- `b3b2a4ce`: the verified 2,000-photo working set, budget, preprocessing/training tools and software checks.
- `cc379f0b`: verified launch of the smaller rock/log training run.
- This progress snapshot, both model completion records and the plain-language next steps are committed as the next milestone.

Code, configuration, selected-image membership, verification reports and progress milestones belong in commits. Large images, model weights, Python environments and changing per-batch logs stay ignored. Future work should keep the same milestone-based commit record; a new commit for every training batch is unnecessary.

See `progress_snapshot.json` for exact measurements and `HEALTH.md` for live progress. The mobile export, physical-phone test and full component acceptance remain incomplete.
