# Local YOLOv8 litter segmentation

This run fine-tunes the official COCO-pretrained `yolov8n-seg.pt` checkpoint for one class, `0: litter`. It is the L1 TACO-only baseline. The configuration is [yolov8_litter_train.json](../configs/yolov8_litter_train.json); the runner is [train_yolov8.py](../src/train_yolov8.py).

The local target is an Apple M4 Mac with 16 GB memory. A separate `sajana/.venv-yolov8` environment preserves preprocessing dependencies. Its versions are pinned in [requirements_yolov8.txt](../requirements_yolov8.txt). The Ultralytics package version and YOLO architecture version are different: the `yolov8n-seg.pt` checkpoint selects YOLOv8 instance segmentation. See the [official YOLOv8 model table](https://docs.ultralytics.com/models/yolov8/) and [MPS training instructions](https://docs.ultralytics.com/modes/train/#apple-silicon-mps-training).

## Training protocol

- Training: 1,028 TACO images / 3,611 instances.
- Validation: 286 images / 675 instances, used for checkpoint selection and early stopping.
- Held-out test: 185 images / 497 instances. The trainer YAML deliberately excludes this split. Reading files for the data-integrity audit does not compute test model scores.
- Budget: up to 100 epochs, patience 20, 640-pixel input size, batch 4, seed 42, data workers 0, no RAM image cache and no mixed precision.
- Accelerator: CUDA if available, otherwise Apple MPS if available, otherwise CPU; the actual selected device is recorded.
- A one-epoch smoke pass uses eight training images. Its final framework validation also uses those training images, and its metrics are not generalization results. The full experiment starts again from the original pretrained checkpoint.
- Source verification, source/manifest/image/label hashes, exact package versions, effective arguments and checkpoint acquisition evidence are retained. Native YOLO loader image/object/segment counts must match the independent verifier before full training.
- Checkpoints are saved each epoch; additional snapshots are requested every five epochs. Training stops on nonfinite loss. A checkpoint is usable for resume only after at least one epoch has completed.

No terrain, damage or pLitter detection labels enter this experiment. The later L2 TACO+MJU comparison must retain the same TACO validation/test membership. Model accuracy must be measured after training; a successful start or finite loss is not an accuracy result.

## Start

Run from the repository root:

```bash
python3 -m venv sajana/.venv-yolov8
sajana/.venv-yolov8/bin/python -m pip install -r sajana/requirements_yolov8.txt
sajana/.venv-yolov8/bin/python -u -B -m sajana.src.train_yolov8
```

The runner fully verifies TACO by default. `--preflight-report` can reuse a full report generated within the previous hour, with current source-label and modification checks. `--epochs`, `--batch` and `--device` explicitly override the recorded configuration. A process lock prevents overlapping local training jobs. Every new invocation starts a separate experiment directory.

## Monitor and retain results

Open `sajana/results/yolov8_training/status.json` for live phase, PID, device, completed epochs, batch progress, losses, validation metrics and checkpoint paths. The public dataset status reads this record and keeps full trail-damage readiness separate.

For a read-only health check and an estimate based on the latest five complete epochs (including validation), run:

```bash
sajana/.venv-yolov8/bin/python -B -m sajana.src.check_yolov8_training --plot
```

This writes `results/yolov8_training/health_report.json`, `HEALTH.md` and a local `learning_curves.png`. Add `--watch` to refresh every minute until the trainer finishes, fails, or a health issue is found. The check reads existing logs and metadata; it performs no additional model inference or test evaluation. Its ETA extrapolates the full epoch budget; early stopping, Mac sleep and speed changes can alter the finish time. A healthy training loop does not establish app accuracy, obstacle detection or clear-trail recognition.

The current run's `console.log`, dataset hashes, environment lock, effective data YAML and `run_manifest.json` are under `sajana/runs/yolov8_litter/<run>/`. Actual training results are in its `fit/` subdirectory:

- `results.csv`: epoch losses and validation metrics, including box/mask AP.
- `weights/last.pt`: latest checkpoint.
- `weights/best.pt`: checkpoint selected using validation fitness.
- Plot images and framework training arguments when generated.

Raw initial weights, environments, label caches, run folders and model artifacts stay ignored by Git. Keep the computer powered and awake for local training; closing its lid or stopping the process can interrupt a run.

To resume an interrupted checkpoint with optimizer state, use the training environment's Ultralytics CLI and the actual `last.pt` path:

```bash
YOLO_CONFIG_DIR="$PWD/sajana/data/raw/ultralytics_settings" \
PYTORCH_ENABLE_MPS_FALLBACK=1 \
sajana/.venv-yolov8/bin/yolo segment train \
  model="/absolute/path/to/fit/weights/last.pt" resume=True device=mps workers=0
```

The direct CLI restores saved training arguments. Custom live-status callbacks belong to the Python runner and are not attached by that CLI command; monitor its `results.csv` and console output when resuming directly. Do not start a new baseline run to resume an existing one.

Trail erosion, roots, obstructions, passability, mobile export and the bot remain later tasks with their own data and evaluation gates.
