"""Train only the budgeted rock/log subset; reuse completed TACO-only litter weights."""
from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
import platform
import subprocess
from pathlib import Path

from .component2_training_data import data_yaml, label_count
from .prepare_compact_component2 import CONFIG, REPORTS, configuration, verify_compact
from .train_yolov8 import ROOT, now, sha256, write_json

PROJECT = ROOT / 'runs/component2_compact_2000'


def record_health(state):
    write_json(REPORTS / 'queue_status.json', {
        'pid': state['pid'], 'phase': 'compact_' + state['phase'], 'updated_at': state['updated_at'],
        'dataset_image_limit_including_holdouts': 2000, 'full_component_ready': False,
        'L1': {'phase': 'completed', 'completed_epochs': 100, 'role': 'Selected TACO-only litter baseline'},
        'jobs': {'O1_compact': state},
        'superseded_large_queue': 'results/component2_training/dataset_budget_change.json'})
    (REPORTS / 'HEALTH.md').write_text(
        '# Component 2 compact YOLOv8 training\n\nChecked: ' + state['updated_at'] + '\n\n'
        '**Budget: 2,000 photos total, including training, validation and test.**\n\n'
        '| Task | Train | Validation | Test | Status |\n| --- | ---: | ---: | ---: | --- |\n'
        '| TACO garbage | 1,028 | 286 | 185 | Completed L1 baseline retained |\n'
        '| Rock/log context | 350 | 50 | 101 | ' + state['phase'] + '; ' +
        str(state.get('completed_epochs', 0)) + '/50 epochs |\n\n'
        'Large L2 completed earlier and is historical, outside this budgeted profile. '
        'Large O1 was stopped at the user\'s request; its checkpoint is preserved. '
        'The compact O1 run starts from official pretrained YOLOv8n weights.\n\n'
        'Models use separate task labels. A rock/log detection does not establish a blocked trail. '
        'Only three rock validation images are available. Local blocked/clear trail, erosion and root '
        'annotations and physical 4 GB Android acceptance are still missing.\n\n'
        'Input: 416; batch: 2; workers: 0; no RAM image cache, plots or periodic checkpoints. '
        'Reserved test images are absent from trainer YAML and are not evaluated here.\n\n'
        'Raw source datasets remain on disk; the compact set does not delete them.\n' +
        ('\nIssue: ' + state['error'] + '\n' if state.get('error') else ''))


def train(device='mps', smoke=False):
    cfg = configuration(); report = verify_compact(cfg); job = cfg['obstacle']
    dataset = ROOT / cfg['output'] / 'obstacle'
    folder = PROJECT / ('smoke' if smoke else 'O1')
    folder.mkdir(parents=True, exist_ok=True)
    status_path = folder / 'status.json'
    prior = json.loads(status_path.read_text()) if status_path.exists() else {}
    if prior.get('phase') == 'completed':
        return prior
    state = dict(prior, job='O1_compact', task='detect', model=job['model'], names=job['names'],
                 pid=os.getpid(), device=device, test_split_used_for_training=False,
                 full_component_ready=False, total_profile_images=2000)
    state.pop('error', None)

    def record(**values):
        state.update(values, updated_at=now()); write_json(status_path, state)
        if not smoke:
            record_health(state)

    record(phase='preparing')
    try:
        for key, value in {
            'PYTORCH_ENABLE_MPS_FALLBACK': '1', 'PYTORCH_MPS_HIGH_WATERMARK_RATIO': '1.0',
            'PYTORCH_MPS_LOW_WATERMARK_RATIO': '0.9', 'YOLO_AUTOINSTALL': 'false', 'YOLO_OFFLINE': 'true',
            'YOLO_CONFIG_DIR': str(ROOT / 'data/raw/ultralytics_settings'),
            'MPLCONFIGDIR': str(ROOT / 'data/raw/matplotlib')}.items():
            os.environ.setdefault(key, value)
        import torch
        import ultralytics
        from ultralytics import YOLO, settings
        from .yolov8_detection_validation import CompleteDetectionTrainer
        if ultralytics.__version__ != '8.4.183':
            raise ValueError('Use the pinned Ultralytics 8.4.183 environment')
        torch.set_num_threads(1 if device == 'cpu' else 2)
        for key in ('sync', 'hub', 'wandb', 'mlflow', 'comet', 'clearml', 'neptune', 'raytune', 'tensorboard', 'dvc'):
            if key in settings:
                settings.update({key: False})
        weights = ROOT / job['initial_weights']
        evidence = json.loads((ROOT / job['weights_evidence']).read_text())
        if evidence['sha256'] != sha256(weights):
            raise ValueError('Official pretrained checkpoint changed')
        expected = report['tasks']['obstacle']['splits']
        yaml = dataset / 'data.yaml'
        if smoke:
            candidates = sorted((dataset / 'images/train').glob('*.jpg'))
            chosen = []
            for class_id in ('0', '1', None):
                for path in candidates:
                    text = (dataset / 'labels/train' / path.with_suffix('.txt').name).read_text()
                    classes = {line.split()[0] for line in text.splitlines() if line.strip()}
                    if (class_id in classes if class_id is not None else not classes) and path not in chosen:
                        chosen.append(path); break
            for path in candidates:
                if len(chosen) == 8:
                    break
                if path not in chosen:
                    chosen.append(path)
            objects = 0
            for path in chosen:
                label = dataset / 'labels/train' / path.with_suffix('.txt').name
                objects += label_count(label, 'detect', job['names'])
                for kind, source in (('images', path), ('labels', label)):
                    out = folder / 'data' / kind / 'train' / source.name
                    out.parent.mkdir(parents=True, exist_ok=True)
                    if not out.exists():
                        os.link(source, out)
            yaml = data_yaml(folder / 'data.yaml', folder / 'data', job['names'], val='images/train')
            expected = {split: {'images': len(chosen), 'objects': objects} for split in ('train', 'val')}
        elif json.loads((PROJECT / 'smoke/status.json').read_text()).get('phase') != 'completed':
            raise ValueError('Successful training-only smoke check required')

        sources = ['train_compact_component2.py', 'prepare_compact_component2.py',
                   'yolov8_detection_validation.py', 'yolov8_validation.py',
                   'component2_training_data.py', 'train_yolov8.py']
        identity = {'config_sha256': sha256(CONFIG), 'compact_inventory_sha256': report['inventory_sha256'],
                    'data_yaml_sha256': sha256(yaml), 'initial_weights_sha256': sha256(weights),
                    'source_sha256': {name: sha256(ROOT / 'src' / name) for name in sources}}
        fit = folder / 'fit'; last = fit / 'weights/last.pt'; manifest = folder / 'run_manifest.json'
        resume = not smoke and last.is_file()
        if resume:
            if json.loads(manifest.read_text())['identity'] != identity:
                raise ValueError('Frozen compact run changed; refusing optimizer resume')
            checkpoint = torch.load(last, map_location='cpu', weights_only=False)
            if checkpoint.get('optimizer') is None or checkpoint.get('ema') is None:
                raise ValueError('Checkpoint is not resumable')
            del checkpoint
        elif fit.exists():
            raise ValueError('Existing run output has no resumable checkpoint')
        else:
            write_json(manifest, {'created_at': now(), 'identity': identity,
                                 'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                                 'versions': {'python': platform.python_version(), 'torch': torch.__version__,
                                              'ultralytics': ultralytics.__version__},
                                 'selection': 'best complete validation fitness; no test tuning',
                                 'test_split_loaded': False, 'smoke_training_only': smoke})
        model = YOLO(str(last if resume else weights), task='detect')
        record(batches_seen=prior.get('batches_seen', 0), planned_epochs=1 if smoke else cfg['training']['epochs'])

        def prepared(trainer):
            for split, loader in [('train', trainer.train_loader), ('val', trainer.test_loader)]:
                labels = loader.dataset.labels
                if (len(labels) != expected[split]['images'] or
                        sum(len(row['cls']) for row in labels) != expected[split]['objects']):
                    raise ValueError('Native loader dropped selected images/labels: ' + split)
                record(**{split + '_loader_images': len(labels),
                          split + '_loader_objects': sum(len(row['cls']) for row in labels)})

        def batch(trainer):
            if not torch.isfinite(trainer.loss.detach()).all().item():
                raise FloatingPointError('Nonfinite training loss')
            state['batches_seen'] += 1
            if state['batches_seen'] == 1 or state['batches_seen'] % 10 == 0:
                record(phase='training', current_epoch=int(trainer.epoch) + 1,
                       latest_loss=float(trainer.loss.detach().cpu().item()))

        def epoch(trainer):
            if getattr(trainer.validator, 'complete_nms_images', 0) != expected['val']['images']:
                raise ValueError('Incomplete compact validation')
            with Path(trainer.csv).open() as stream:
                completed = sum(1 for _ in csv.DictReader(stream))
            record(completed_epochs=completed, metrics=trainer.metrics,
                   best_checkpoint=str(trainer.best), last_checkpoint=str(trainer.last))

        model.add_callback('on_pretrain_routine_end', prepared)
        model.add_callback('on_train_batch_end', batch)
        model.add_callback('on_fit_epoch_end', epoch)
        training = dict(cfg['training'])
        if smoke:
            training.update(epochs=1, patience=0)
        if resume:
            model.train(resume=True, trainer=CompleteDetectionTrainer, device=device, workers=0,
                        cache=False, plots=False, save_period=-1, save_dir=str(fit), val=True)
        else:
            model.train(data=str(yaml), trainer=CompleteDetectionTrainer, device=device,
                        project=str(folder), name='fit', save_dir=str(fit),
                        save=not smoke, val=True, verbose=False, **training)
        record(phase='completed', finished_at=now())
        return state
    except BaseException as exc:
        record(phase='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
               error=type(exc).__name__ + ': ' + str(exc))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', default='mps')
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    PROJECT.mkdir(parents=True, exist_ok=True)
    lock_path = PROJECT / '.smoke.lock' if args.smoke and args.device == 'cpu' else ROOT / 'runs/yolov8_litter/.training.lock'
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        train(args.device, args.smoke)
