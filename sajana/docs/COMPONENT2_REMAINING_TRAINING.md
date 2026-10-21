# Remaining YOLOv8 training

**Superseded on 21 October 2026:** the user requests 2,000 photos total including holdouts. Use the [compact profile](COMPACT_DATA_AND_MODEL.md) and `sajana.src.train_compact_component2`. L1/L2 have completed; the large O1 queue below was stopped and remains documented as historical evidence. Do not restart this large queue for the compact profile.

The user authorized the remaining relevant public-data training with small storage and memory use. The [queue configuration](../configs/component2_training_queue.json) keeps YOLOv8 nano architectures and schedules full jobs sequentially after the current L1 TACO run successfully finishes and releases its kernel lock.

| Job | Model | Training | Validation | Reserved public test | Scope |
| --- | --- | ---: | ---: | ---: | --- |
| L1, already running | YOLOv8n-seg | 1,028 TACO | 286 TACO | 185 TACO | Existing 640-pixel baseline; its frozen protocol remains fixed |
| L2, next | YOLOv8n-seg | 2,513 TACO+MJU | Same 286 TACO | Same 185 TACO | Compact litter candidate |
| O1, after L2 | YOLOv8n | 6,051 WildScenes | 283 WildScenes | 2,133 WildScenes | Rock/log semantic-region context |

New full jobs use **416-pixel input, batch 2, up to 50 epochs, patience 15, workers 0, cache disabled, AMP disabled, plots disabled and save_period -1**. Best/last checkpoints remain available. No extra periodic snapshots are created. Full runs have independent pretrained initialization, task heads, manifests, environment locks and source hashes. Eight-image training-only CPU smoke checks precede them; smoke weights are not the full model's initialization.

L2 changes resolution and epoch budget as well as auxiliary data. Its comparison with L1 is practical model selection, not a controlled measurement of the MJU-only effect. Full litter heads contain only `litter`. O1 has `rock_region` and `log_region`; unreviewed litter/corridor labels never become negatives in a joint multiclass dataset.

## Start, monitor and recover

From the repository root, with the pinned training environment:

```bash
# Verify current source/derived labels, full file membership, image hashes,
# geometry/pixel duplicates where needed; freeze every input and obtain weights.
sajana/.venv-yolov8/bin/python -u -B -m sajana.src.run_component2_training_queue --prepare

# These small CPU runs use eight training photos, never the held-out splits.
sajana/.venv-yolov8/bin/python -u -B -m sajana.src.train_component2_yolov8 --job L2 --smoke --device cpu
sajana/.venv-yolov8/bin/python -u -B -m sajana.src.train_component2_yolov8 --job O1 --smoke --device cpu

# Watches L1, then runs L2 and O1 sequentially, then selects/evaluates public models.
sajana/.venv-yolov8/bin/python -u -B -m sajana.src.run_component2_training_queue
```

The launched supervisor and its `caffeinate` helper are recorded in `results/component2_training/launch.json`. They keep the Mac awake for the queue; restarting or closing the computer can interrupt local execution. The supervisor reports actual queued/running/completed phases and never counts queue registration as completed training.

Open **`results/component2_training/HEALTH.md`** or `queue_status.json` for the live queue. L1's existing `results/yolov8_training/HEALTH.md` continues to describe L1. Per-job statuses/checkpoints are under ignored `runs/component2_training/jobs/<job>/`. Preparation certificates and the launch verification record are versioned; logs, changing live reports, image data and weights remain local.

A second supervisor is rejected by a queue lock. Full training and final evaluation share L1's accelerator lock, preventing overlapping GPU jobs. A restarted supervisor adopts an existing child when it is still alive; otherwise a job with a valid last checkpoint resumes with optimizer/EMA/early-stopping state. It rechecks every frozen input and rejects changed source/configuration/membership. An interrupted L1 requires its existing recovery procedure before dependent jobs proceed. A failure before the first saved epoch requires inspection of that fit directory rather than silently starting another experiment.

`--refresh-prepared` rehashes all existing frozen inputs and refreshes tooling hashes after source changes; it refuses changed job/data configuration. A full `--prepare` is required if job membership/settings changed. Do not edit frozen runtime modules during a job and expect a reproducible resume.

## Selection and public evaluation

The [predeclared selection policy](../configs/component2_model_selection.json) compares current L1/L2 best checkpoints and preserved L1 checkpoints whose old validation could time out. Each litter candidate is completely evaluated at 640 and 416 on the same 286-image validation set, with matched letterboxing/NMS. O1 receives complete validation on its 283-image author split.

The highest mask mAP50–95 is the litter reference. Prefer the best 416 candidate only when it stays within 0.02 absolute mask mAP and 0.03 recall of that reference. Otherwise retain the stronger candidate and record that memory optimization did not meet the validation rule. These are predeclared selection tolerances, not a guarantee of application accuracy. Freeze a confidence threshold from the validation F1 curve before public test evaluation. Standard AP summarizes a confidence sweep; separate summaries report precision/recall at the frozen validation threshold.

After selection is frozen, evaluate the chosen litter model on the 185 reserved TACO images and the rock/log model on its 2,133 reserved author-test images. Test files are omitted from trainer YAMLs and never influence optimizer steps, threshold choice or model ranking. The evaluator records a test-start marker; an interrupted holdout evaluation requires inspection before any repeat. Results go to `model_selection.json` and `public_evaluation.json`. Public-data training/evaluation can complete while the full component remains incomplete.

The box source retains all 14,185 connected-region boxes, including tiny components, and author splits. Only three validation images contain rocks, so rock metrics have weak support. Connected regions are not physical instance counts, and an object beside a trail does not establish blockage.

## Remaining component gates

Reviewed local erosion, roots, actual obstruction, trail corridor and clear-trail examples are still absent. These jobs cannot supply those missing labels. Independent local evaluation and the 4 GB Android export/latency/memory acceptance remain required. ORFD vehicle freespace, RUGD terrain semantics and native WildScenes terrain are context sources, not interchangeable YOLO instance/obstruction ground truth. The unresolved pLitter export and optional unofficial pool are excluded.

The queue's final success phase is **public_jobs_completed_local_data_missing**, with `full_component_ready=false`. It does not manufacture labels, certify a clear route from no detections, or declare Android release readiness. See the [mobile deployment guide](MOBILE_MODEL_SIZE_AND_MEMORY.md) for storage and phone memory work after model selection.
