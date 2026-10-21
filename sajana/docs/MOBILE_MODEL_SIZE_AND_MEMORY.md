# Component 2 on a 4 GB Android phone

The target is a physical Android phone with about 4 GB total RAM. Android Studio's emulator is the first app-behavior test environment. A physical phone is needed to accept latency, peak RAM, acceleration, heat and battery behavior; emulator timings are not phone benchmarks. The app initially processes one captured photo at a time.

The existing model is already the nano YOLOv8 instance-segmentation model. Keep its current recorded experiment running. The proposed `yolo11n-seg.pt` selects a different architecture and would require a separate experiment. Fewer epochs and a smaller batch do not reduce the model's parameter count. A reduced input size may miss small litter, so compare validation results before selecting it.

## What the suggested settings change

| Setting | Mac training effect | Android effect |
| --- | --- | --- |
| `imgsz=416` instead of 640 | Less image-dependent computation and memory | Less computation and activation/mask memory when also used for export/inference; parameter count stays the same |
| `batch=2` instead of 4 | Less batch-dependent training memory | No automatic change; the app will use batch 1 |
| `epochs=50`, `patience=15` | Lower training budget or earlier stopping | Same architecture and parameter count |
| `workers=0`, `cache=False` | Avoid worker duplication and an image RAM cache | Training-only controls |
| `amp=False` | Matches the current MPS run's precision setting | Does not choose mobile inference precision |
| `plots=False` | Fewer saved images and plotting overhead | No change to deployed weights |
| `save_period=-1` in a future run | Avoid extra periodic checkpoints; retain best/last | No change to the selected mobile model |
| Remove optimizer from a separate inference copy | Smaller distribution artifact | Avoid packaging training state; runtime RAM still needs measurement |
| INT8 mobile export | Separate post-training conversion | Can reduce weights/activation storage; verify operator support, accuracy and real-device memory |

416 × 416 has 42.25% of the pixels of 640 × 640. This is **57.75% fewer input pixels**, not a promise of 57.75% less total RAM. A batch of two 416-pixel images contains 21.125% of the input elements of four 640-pixel images; weights, optimizer, augmentation and runtime workspaces do not scale identically. At app batch 1, just the normalized RGB FP32 input is about 1.98 MiB at 416 versus 4.69 MiB at 640. These figures exclude all activations, masks, decoded photos, the model and the app.

The [deployment plan](../configs/mobile_deployment_plan.json) records 640/416 input candidates and FP32/INT8 precision candidates. Its 10 MiB model, 256 MiB incremental vision peak PSS, and 2-second warm p95 photo targets are provisional design budgets, **not measured results or release guarantees**. Compare them with small-litter accuracy on the same validation set. Reducing inference resolution can be tested on existing weights before deciding whether another training run is worthwhile.

## Smaller intermediate checkpoint now

Run from the repository root:

```bash
sajana/.venv-yolov8/bin/python -B -m sajana.src.prepare_mobile_yolov8
```

This snapshots the current `best.pt` into a new ignored `sajana/runs/mobile_litter_preview/<timestamp>/` folder, strips optimizer/training state from the copy, and checks that all saved inference tensors are identical. It runs on CPU, reads no dataset images, installs no dependencies, deletes its temporary source copy, and writes a hash/size report. It never writes the original checkpoints. A source save during copying triggers a retry.

The resulting `litter_inference_preview.pt` is an **intermediate development snapshot**, not the Android runtime file and not a resumable training checkpoint. Use the original `last.pt` and project recovery runner to resume training. Do not run the suggested `runs/segment/train/weights/last.pt` path: the suggested custom name actually creates `runs/segment/m3_memory_optimized/weights/last.pt`. For our active run, follow the recorded `run_directory` and [recovery guide](YOLOV8_TRAINING_GUIDE.md).

Training checkpoints, datasets, cached images, recovery archives and Python environments remain on the Mac. Only one selected `.tflite` artifact plus its class/preprocessing metadata belongs in the app. Keep required checkpoint-selection candidates until validation comparison finishes; ignoring a file in Git does not free disk space.

## Android export and calibration

The pinned Ultralytics **8.4.183** source supports `format="litert"`, producing `.tflite`. Its `quantize=8` option performs static INT8 calibration. It does **not** support a separate `half=True` LiteRT export; FP16 execution is chosen through a supported GPU delegate at runtime. See the official [LiteRT export documentation](https://docs.ultralytics.com/integrations/litert/) and [export argument reference](https://docs.ultralytics.com/modes/export/).

Do conversion in a separate environment after selecting a checkpoint; the active training environment currently lacks the export dependencies. No conversion packages were installed into it. Use the pinned exporter and compatible conversion packages recorded in a new environment lock. The following is the intended conversion API, **not an export already performed**:

```python
from ultralytics import YOLO

model = YOLO("/path/to/selected_inference_copy.pt")
baseline = model.export(format="litert", imgsz=416, batch=1, device="cpu")
quantized = model.export(
    format="litert", imgsz=416, batch=1, device="cpu",
    quantize=8, data="/path/to/train_only_calibration.yaml", split="train",
)
```

Create the calibration YAML from a frozen, representative **training-only** subset, with its dataset root and both `train` and required `val` keys referring to that same calibration subset. Omit `test` and do not point calibration at our held-out validation images. The pinned exporter can default calibration to `val`, so explicitly select `split="train"` as well. Select representative training scenes rather than a convenient fixed first few images. Freeze calibration hashes. INT8 changes weights/activations and needs its own validation; the tensor-identity check on the intermediate `.pt` does not validate quantization.

Evaluate the 640/416 native models and exports using identical validation images, matched letterboxing, confidence/NMS settings and the complete validator. Record per-size/precision mask AP, recall, missed small litter and false alarms. Threshold/size/precision selection uses validation only; perform the reserved test evaluation after final selection. Inspect exported tensor metadata rather than assuming output order, layout, coordinate scaling or quantization from an older example. Phone inference must follow that exact contract.

## App memory and acceptance

Decode a sampled bitmap with the correct photo orientation, letterbox once, and reuse one interpreter and input/output buffers. Keep original photos as files instead of retaining several full-resolution bitmaps. Reconstruct selected masks at model resolution and scale the overlay geometry to the displayed photo. Serialize camera/inference requests and release temporary arrays after use. A 4 GB phone cannot give this app all its RAM; Android, other apps and graphics also need memory.

Use the emulator for photo capture/import, orientation, overlays, cancellation, repeat-photo flows and unavailable-model behavior. Its nominal RAM setting does not emulate a phone's CPU/GPU or prove the model fits the physical device.

On the physical phone, record the exact device/OS/runtime/delegate and model hash, cold start, warm median/p95 latency, app baseline and peak PSS, model/APK size, repeated-photo memory growth, and behavior on difficult photos. Recheck detection/mask parity and accuracy after export. Model file size is only one part of APK storage and runtime memory. Garbage-only weights still cannot label a trail clear or identify actual blockage; those component data/model gates remain unchanged.
