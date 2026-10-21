"""Recorded training-only refinements; select improvements on validation only."""
from __future__ import annotations

import csv
import fcntl
import json
import os
import subprocess
from pathlib import Path

from .assess_compact_models import environment
from .prepare_compact_component2 import configuration, verify_compact
from .train_yolov8 import ROOT, now, sha256, write_json

CONFIG = ROOT / 'configs/component2_refinement.json'
PROJECT = ROOT / 'runs/component2_refinement'
REPORTS = ROOT / 'results/component2_training'


def run_experiment(key, spec, settings):
    import torch
    from ultralytics import YOLO
    from .yolov8_validation import CompleteSegmentationTrainer
    from .yolov8_detection_validation import CompleteDetectionTrainer
    cfg = configuration(); prepared = verify_compact(cfg); task = spec['task_key']
    job = cfg[task]; folder = PROJECT / key
    folder.mkdir(parents=True, exist_ok=True)
    status = folder / 'status.json'
    if status.exists():
        existing = json.loads(status.read_text())
        if existing['phase'] == 'completed':
            return existing
        raise ValueError('Existing refinement is incomplete; inspect it before recovery')
    initial = json.loads((ROOT / spec['initial_status']).read_text())
    if initial['phase'] != 'completed':
        raise ValueError('Warm-start baseline is incomplete')
    checkpoint = Path(initial['best_checkpoint'])
    training = dict(settings, epochs=spec['epochs'], patience=spec['patience'])
    state = {'experiment': key, 'task_key': task, 'pid': os.getpid(), 'phase': 'preparing',
             'configuration': training, 'initial_checkpoint': str(checkpoint),
             'initial_checkpoint_sha256': sha256(checkpoint), 'completed_epochs': 0,
             'test_split_loaded': False, 'total_unique_photos_in_profile': 2000,
             'quality_accepted_for_app': False}

    def record(**values):
        state.update(values, updated_at=now()); write_json(status, state)
        write_json(REPORTS / 'refinement_status.json', state)
        if state['phase'] in ('training', 'completed', 'failed'):
            (REPORTS / 'HEALTH.md').write_text(
                '# Component 2 accuracy improvement\n\nChecked: ' + state['updated_at'] + '\n\n'
                'Profile: **2,000 photos total**, including validation and reserved test.\n\n'
                f"Experiment: **{key}**. Phase: **{state['phase']}**. "
                f"Completed passes: **{state['completed_epochs']}/{spec['epochs']}**.\n\n"
                'The original garbage and rock/log runs completed. Their accuracy is insufficient for release. '
                'Current refinements use the same selected photos and validation-only selection. '
                'Final test photos remain reserved. Local blockage/clear-trail labels, mobile export checks '
                'and physical 4 GB Android measurements remain required.\n')

    yaml = ROOT / cfg['output'] / task / 'data.yaml'
    identity = {'configuration_sha256': sha256(CONFIG),
                'dataset_inventory_sha256': prepared['inventory_sha256'],
                'data_yaml_sha256': sha256(yaml), 'initial_checkpoint_sha256': sha256(checkpoint),
                'source_sha256': {p: sha256(ROOT / 'src' / p) for p in
                                  ('improve_compact_models.py', 'yolov8_validation.py',
                                   'yolov8_detection_validation.py', 'prepare_compact_component2.py')},
                'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()}
    write_json(folder / 'run_manifest.json', identity)
    model = YOLO(str(checkpoint), task=job['task'])
    if model.names != {int(k): v for k, v in job['names'].items()}:
        raise ValueError('Warm-start checkpoint classes changed')
    expected = prepared['tasks'][task]['splits']

    def loaders(trainer):
        for split, loader in [('train', trainer.train_loader), ('val', trainer.test_loader)]:
            labels = loader.dataset.labels
            if (len(labels) != expected[split]['images'] or
                    sum(len(r['cls']) for r in labels) != expected[split]['objects']):
                raise ValueError('Native loader lost selected image/label membership')
            if task == 'litter' and any(len(r['cls']) != len(r['segments']) for r in labels):
                raise ValueError('Native loader lost masks')
        record(phase='training', train_images=expected['train']['images'],
               validation_images=expected['val']['images'])

    def epoch(trainer):
        if trainer.validator.complete_nms_images != expected['val']['images']:
            raise ValueError('Validation did not process the complete split')
        if not torch.isfinite(trainer.loss.detach()).all().item():
            raise FloatingPointError('Nonfinite loss')
        with Path(trainer.csv).open() as stream:
            completed = sum(1 for _ in csv.DictReader(stream))
        record(phase='training', completed_epochs=completed, metrics=trainer.metrics,
               best_checkpoint=str(trainer.best), last_checkpoint=str(trainer.last))

    model.add_callback('on_pretrain_routine_end', loaders)
    model.add_callback('on_fit_epoch_end', epoch)
    record(phase='preparing')
    try:
        model.train(data=str(yaml), trainer=CompleteSegmentationTrainer if task == 'litter' else CompleteDetectionTrainer,
                    device='mps', project=str(folder), name='fit', save_dir=str(folder / 'fit'),
                    val=True, verbose=False, **training)
        record(phase='completed', finished_at=now())
        return state
    except BaseException as exc:
        record(phase='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
               error=type(exc).__name__ + ': ' + str(exc))
        raise


if __name__ == '__main__':
    environment()
    import torch
    torch.set_num_threads(2)
    PROJECT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(CONFIG.read_text())
    with (ROOT / 'runs/yolov8_litter/.training.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for key, spec in cfg['experiments'].items():
            run_experiment(key, spec, cfg['training'])
