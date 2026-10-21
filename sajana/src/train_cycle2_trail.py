"""Train and independently test the cycle-two compact YOLOv8 trail detector."""
from __future__ import annotations

import collections
import csv
import hashlib
import json
import os
import platform
import time
from pathlib import Path

from .train_yolov8 import ROOT, now, sha256, write_json

DATA = ROOT / 'data/processed/component2_cycle2_trail_v4'
WEIGHTS = ROOT / 'data/raw/pretrained/yolov8n.pt'
RUN = ROOT / 'runs/component2_cycle2/trail_yolov8n'
RESULT = ROOT / 'results/component2_cycle2/trail_training.json'
NAMES = ['tree', 'stump', 'stem', 'obstacle_region', 'non_passable_obstacle', 'debris', 'rock']


def check_dataset():
    if not DATA.joinpath('manifest.csv').is_file() or not WEIGHTS.is_file():
        raise FileNotFoundError('Cycle-two manifest or reviewed YOLOv8n weights are missing')
    rows = list(csv.DictReader((DATA / 'manifest.csv').open(newline='')))
    expected = {'train': 391, 'val': 118, 'test': 51}
    if dict(collections.Counter(r['split'] for r in rows)) != expected:
        raise ValueError('Dataset split counts differ from the reviewed profile')
    hashes = {s: set() for s in expected}
    sequences = {s: set() for s in expected}
    for row in rows:
        split = row['split']
        image, label = DATA / row['image'], DATA / row['label']
        if not image.is_file() or not label.is_file() or sha256(image) != row['sha256']:
            raise ValueError('Image/label/hash integrity failed: ' + row['image'])
        hashes[split].add(row['sha256'])
        if row['source'] == 'GOOSE':
            member = row['source_member']
            parts = Path(member).parts
            seq = parts[3] if 'gooseEx_2d_val' in member else parts[2]
            sequences[split].add(seq)
        for line in label.read_text().splitlines():
            values = line.split()
            if len(values) != 5 or not 0 <= int(values[0]) < len(NAMES):
                raise ValueError('Invalid YOLO annotation line: ' + str(label))
            numbers = list(map(float, values[1:]))
            if not all(0 <= x <= 1 for x in numbers) or numbers[2] <= 0 or numbers[3] <= 0:
                raise ValueError('Out-of-range YOLO box: ' + str(label))
    for left, right in [('train','val'), ('train','test'), ('val','test')]:
        if hashes[left] & hashes[right] or sequences[left] & sequences[right]:
            raise ValueError(f'Split leakage found between {left} and {right}')
    return rows, sequences


def main(epochs=30):
    rows, sequences = check_dataset()
    if RUN.exists():
        raise FileExistsError(f'Refusing to overwrite training run: {RUN}')
    RUN.mkdir(parents=True)
    test_data = RUN / 'test.yaml'
    test_data.write_text('path: ' + json.dumps(str(DATA.resolve())) +
                         '\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n' +
                         ''.join(f'  {i}: {name}\n' for i, name in enumerate(NAMES)))
    status = {'created_at': now(), 'state': 'preflight_passed', 'model': 'YOLOv8n',
              'weights_sha256': sha256(WEIGHTS), 'data_path': str(DATA),
              'data_manifest_sha256': sha256(DATA / 'manifest.csv'),
              'photo_count': len(rows), 'photos_by_split': dict(collections.Counter(r['split'] for r in rows)),
              'goose_sequences_by_split': {k: sorted(v) for k, v in sequences.items()},
              'test_split_used_during_training': False, 'device': 'cpu',
              'mps_available': False, 'epochs_requested': epochs, 'imgsz': 416,
              'batch': 2, 'workers': 0, 'cache': False, 'amp': False}
    write_json(RUN / 'status.json', status)
    write_json(ROOT / 'results/component2_cycle2/trail_training_status.json', status)
    os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'data/raw/ultralytics_settings'))
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'data/raw/matplotlib'))
    os.environ.setdefault('MPLBACKEND', 'Agg')
    os.environ.setdefault('YOLO_OFFLINE', 'true')
    os.environ.setdefault('YOLO_AUTOINSTALL', 'false')
    import torch
    from ultralytics import YOLO, settings
    for key in ('sync','hub','wandb','mlflow','comet','clearml','neptune','raytune','tensorboard','dvc'):
        if key in settings:
            settings.update({key: False})
    status.update(state='training', started_at=now(), torch_version=torch.__version__)
    write_json(RUN / 'status.json', status)
    model = YOLO(str(WEIGHTS))
    start = time.time()
    train_results = model.train(data=str(DATA / 'data.yaml'), epochs=epochs, imgsz=416,
        batch=2, device='cpu', workers=0, cache=False, amp=False, patience=7,
        plots=False, project=str(RUN), name='fit', exist_ok=False, save_period=-1,
        seed=42, deterministic=True, pretrained=True, verbose=True)
    status.update(state='training_complete', elapsed_seconds=round(time.time()-start, 2),
                  best_checkpoint=str(RUN/'fit/weights/best.pt'), last_checkpoint=str(RUN/'fit/weights/last.pt'),
                  best_checkpoint_sha256=sha256(RUN/'fit/weights/best.pt'))
    write_json(RUN / 'status.json', status)

    best = YOLO(str(RUN/'fit/weights/best.pt'))
    # Validation selects/characterizes the checkpoint; test is run only once after
    # selection and is never used to tune the training parameters.
    val = best.val(data=str(DATA/'data.yaml'), split='val', imgsz=416, batch=2,
                   device='cpu', workers=0, plots=False, verbose=False)
    test = best.val(data=str(test_data), split='test', imgsz=416, batch=2,
                    device='cpu', workers=0, plots=False, verbose=False)

    def metric_record(metrics):
        boxes = metrics.box
        return {'precision': float(boxes.mp), 'recall': float(boxes.mr),
                'mAP50': float(boxes.map50), 'mAP50_95': float(boxes.map),
                'per_class_mAP50_95': [float(x) for x in boxes.maps],
                'class_indices': [int(x) for x in getattr(boxes, 'ap_class_index', [])]}

    results = {'completed_at': now(), 'model': 'YOLOv8n', 'task': 'trail-object-detection',
        'dataset_manifest_sha256': status['data_manifest_sha256'],
        'weights_sha256': status['weights_sha256'], 'checkpoint': str(RUN/'fit/weights/best.pt'),
        'checkpoint_sha256': sha256(RUN/'fit/weights/best.pt'),
        'checkpoint_bytes': (RUN/'fit/weights/best.pt').stat().st_size,
        'photos_by_split': status['photos_by_split'], 'class_names': NAMES,
        'goose_sequences_by_split': status['goose_sequences_by_split'],
        'validation': metric_record(val), 'test': metric_record(test),
        'test_used_for_tuning': False, 'mps_available': torch.backends.mps.is_available(),
        'full_component_ready': False,
        'limitations': ['No garbage classes are in this detector; retain the existing litter model separately.',
          'GOOSE obstacle_region is a semantic object class, not route-passability ground truth.',
          'non_passable_obstacle has 32 training boxes and one validation box; no independent test examples.',
          'Exposed roots have only eight source-positive frames and are excluded; erosion is not annotated.',
          'The held-out test uses the GOOSE extension domain; local trail and Android evaluation are absent.']}
    write_json(RESULT, results)
    status.update(state='complete', completed_at=now(), results=str(RESULT),
                  test_split_used_for_training=False, full_component_ready=False)
    write_json(RUN/'status.json', status)
    write_json(ROOT/'results/component2_cycle2/trail_training_status.json', status)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
