"""Verified, reproducible YOLOv8 litter segmentation on the local Mac.

Run from the repository root using sajana/.venv-yolov8/bin/python.
Training-only smoke data precedes the real TACO baseline. Test is never loaded.
"""
from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'configs/yolov8_litter_train.json'
RESULTS = ROOT / 'results/yolov8_training'
STATUS = RESULTS / 'status.json'
PROJECT = ROOT / 'runs/yolov8_litter'


def now():
    return datetime.now(ZoneInfo('Asia/Colombo')).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def finite_json(value):
    if isinstance(value, dict):
        return {str(k): finite_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_json(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, 'item'):
        return finite_json(value.item())
    return str(value)


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(finite_json(value), indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def require_full_report(report, dataset, annotations):
    if not (report.get('passed') and report.get('training_ready') and
            report.get('mode') == 'full' and report.get('image_checks_performed')):
        raise ValueError('A successful full image/source-label audit is required before training')
    if Path(report.get('dataset', '')).resolve() != Path(dataset).resolve():
        raise ValueError('Readiness report belongs to a different dataset')
    if Path(report.get('annotations', '')).resolve() != Path(annotations).resolve():
        raise ValueError('Readiness report belongs to different source annotations')
    for split in ('train', 'val', 'test'):
        row = report.get('splits', {}).get(split, {})
        if not row.get('images') or row.get('verified_images') != row['images']:
            raise ValueError(f'{split}: full image verification is incomplete')


def write_data_yaml(path, dataset, train='images/train', val='images/val'):
    """Intentionally omits the held-out test split from trainer configuration."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('path: ' + json.dumps(str(Path(dataset).resolve())) + '\n' +
                    'train: ' + json.dumps(train) + '\nval: ' + json.dumps(val) +
                    '\nnames:\n  0: litter\n')
    return path


def make_smoke_data(dataset, out, count=8):
    dataset, out = Path(dataset), Path(out)
    with (dataset / 'manifests/train.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    count = min(count, len(rows))
    if count < 2:
        raise ValueError('At least two verified training images are required for the smoke check')
    chosen = [rows[round(i * (len(rows) - 1) / (count - 1))] for i in range(count)]
    for row in chosen:
        name = row['flat_file_name']
        if Path(name).name != name or name in ('', '.', '..'):
            raise ValueError('Unsafe training filename')
        for kind, filename in [('images', name), ('labels', Path(name).with_suffix('.txt').name)]:
            source = dataset / kind / 'train' / filename
            target = out / kind / 'train' / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
    config = write_data_yaml(out / 'data.yaml', out, val='images/train')
    return config, chosen


def verify_and_freeze(dataset, annotations, run_dir, preflight=None):
    from .data.verify_taco_ready import verify
    if preflight:
        preflight = Path(preflight)
        if time.time() - preflight.stat().st_mtime > 3600:
            raise ValueError('Provided preflight report is over one hour old; rerun the full verifier')
        report = json.loads(preflight.read_text())
        require_full_report(report, dataset, annotations)
        # Recheck current labels/source, while a very recent full audit certifies pixels.
        current = verify(dataset, labels_only=True, annotations=annotations)
        if not current['passed']:
            raise ValueError('Source/labels changed after full preflight verification')
        newer = [p for folder in ('images', 'labels', 'manifests') for p in (dataset / folder).rglob('*')
                 if p.is_file() and p.suffix != '.cache' and p.stat().st_mtime_ns > preflight.stat().st_mtime_ns]
        if annotations.stat().st_mtime_ns > preflight.stat().st_mtime_ns or newer:
            raise ValueError('Dataset files changed after the provided full preflight audit')
    else:
        report = verify(dataset, annotations=annotations)
        require_full_report(report, dataset, annotations)
    write_json(run_dir / 'preflight.json', report)
    inventory = {}
    for split in ('train', 'val', 'test'):
        inventory[split] = {}
        for kind in ('images', 'labels'):
            for path in sorted((dataset / kind / split).iterdir()):
                if path.is_file() and path.suffix != '.cache':
                    inventory[split][path.relative_to(dataset).as_posix()] = sha256(path)
    write_json(run_dir / 'dataset_hashes.json', inventory)
    return report


def obtain_weights(config):
    import requests
    name, url = config['model'], config['weights_url']
    if Path(name).name != name or not name.startswith('yolov8') or not name.endswith('-seg.pt'):
        raise ValueError('This runner requires a YOLOv8 instance-segmentation checkpoint')
    if not url.startswith('https://github.com/ultralytics/assets/releases/download/') or not url.endswith('/' + name):
        raise ValueError('Initial weights must come from the official Ultralytics assets release')
    target = ROOT / 'data/raw/pretrained' / name
    previous = RESULTS / 'pretrained_weights.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not previous.exists() or json.loads(previous.read_text()).get('sha256') != sha256(target):
            raise ValueError('Existing pretrained checkpoint has no matching acquisition evidence')
    else:
        temporary = target.with_suffix('.part')
        for attempt in range(3):
            try:
                with requests.get(url, stream=True, timeout=(30, 120)) as response:
                    response.raise_for_status()
                    with temporary.open('wb') as stream:
                        for chunk in response.iter_content(1024 * 1024):
                            stream.write(chunk)
                            if stream.tell() > 100 * 1024 * 1024:
                                raise ValueError('Checkpoint exceeds the reviewed download size limit')
                if temporary.stat().st_size < 1024 * 1024:
                    raise ValueError('Unexpectedly small pretrained checkpoint')
                temporary.replace(target)
                break
            except (OSError, ValueError, requests.RequestException):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    write_json(previous, {'source_url': url, 'model': name, 'bytes': target.stat().st_size,
                         'sha256': sha256(target), 'path': str(target), 'checked_at': now()})
    return target


def update_public_plan(state):
    plan_path = ROOT / 'configs/component2_training_plan.json'
    plan = json.loads(plan_path.read_text())
    plan.update(trainer_implemented=True, training_started=state['training_started'],
                compute_selection='Local Mac, selected device: ' + state.get('device', 'pending'),
                runtime_status='sajana/results/yolov8_training/status.json')
    for experiment in plan['first_experiments']:
        if experiment['experiment_id'] == 'L1':
            experiment.update(model_and_library_versions=state.get('versions'), device=state.get('device'),
                              training_run_config='sajana/configs/yolov8_litter_train.json')
    write_json(plan_path, plan)
    from .data.audit_component2_datasets import save
    save()


def run(args):
    config = json.loads(args.config.read_text())
    for key in ('epochs', 'batch', 'device'):
        if getattr(args, key) is not None:
            config[key] = getattr(args, key)
    if min(config['epochs'], config['batch'], config['imgsz']) < 1:
        raise ValueError('Epochs, batch size and image size must be positive')
    run_name = 'L1_' + Path(config['model']).stem.replace('-', '_') + '_' + datetime.now(ZoneInfo('Asia/Colombo')).strftime('%Y%m%d_%H%M%S')
    run_dir = PROJECT / run_name
    run_dir.mkdir(parents=True, exist_ok=False)
    if os.environ.get('C2_TRAIN_LOG'):
        console = Path(os.environ['C2_TRAIN_LOG']).resolve()
        if console.is_relative_to(ROOT) and console.is_file():
            os.link(console, run_dir / 'console.log')
    state = {'experiment': 'L1', 'phase': 'preparing', 'training_started': False, 'full_run_started': False,
             'started_at': now(), 'pid': os.getpid(), 'run_directory': str(run_dir),
             'model': config['model'], 'target_classes': {'0': 'litter'}, 'planned_epochs': config['epochs'],
             'batch': config['batch'], 'imgsz': config['imgsz'], 'test_split_used_for_training': False,
             'full_trail_damage_model': False, 'completed_epochs': 0, 'main_batches_seen': 0}

    def record(**values):
        state.update(values, updated_at=now())
        write_json(STATUS, state)
        write_json(run_dir / 'status.json', state)

    record()
    try:
        dataset, annotations = ROOT / config['dataset'], ROOT / config['annotations']
        record(phase='verifying_data')
        report = verify_and_freeze(dataset, annotations, run_dir, args.preflight_report)
        weights = obtain_weights(config)
        os.environ.setdefault('PYTORCH_ENABLE_MPS_FALLBACK', '1')
        os.environ.setdefault('PYTORCH_MPS_HIGH_WATERMARK_RATIO', '1.0')
        os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'data/raw/ultralytics_settings'))
        os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'data/raw/matplotlib'))
        os.environ.setdefault('MPLBACKEND', 'Agg')
        os.environ.setdefault('YOLO_OFFLINE', 'true')
        os.environ.setdefault('YOLO_AUTOINSTALL', 'false')
        import torch
        import ultralytics
        from ultralytics import YOLO, settings
        for key in ('sync', 'hub', 'wandb', 'mlflow', 'comet', 'clearml', 'neptune', 'raytune', 'tensorboard', 'dvc'):
            if key in settings:
                settings.update({key: False})
        device = config['device']
        if device == 'auto':
            device = '0' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        versions = {'python': platform.python_version(), 'torch': torch.__version__, 'ultralytics': ultralytics.__version__}
        record(device=str(device), versions=versions, dataset_counts=report['splits'])
        data_yaml = write_data_yaml(run_dir / 'data.yaml', dataset)
        frozen = {'configuration': config, 'effective_device': device, 'versions': versions,
                  'initial_weights_sha256': sha256(weights), 'annotations_sha256': sha256(annotations),
                  'data_yaml_sha256': sha256(data_yaml), 'dataset_hashes_sha256': sha256(run_dir / 'dataset_hashes.json'),
                  'trainer_source_sha256': sha256(__file__),
                  'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT.parent, text=True).strip(),
                  'seed': config['seed'], 'test_split_loaded': False}
        write_json(run_dir / 'run_manifest.json', frozen)
        write_json(RESULTS / 'run_manifest.json', frozen)
        with (run_dir / 'environment.lock.txt').open('w') as environment:
            subprocess.run([sys.executable, '-m', 'pip', 'freeze'], stdout=environment, check=True)
        train_args = {key: config[key] for key in ('imgsz', 'batch', 'workers', 'seed', 'deterministic', 'amp', 'cache')}
        train_args.update(device=device, project=str(run_dir), task='segment', plots=True,
                          exist_ok=False, verbose=False, pretrained=True)

        # One tiny training-only pass tests the actual accelerator, masks and losses.
        smoke_yaml, smoke_rows = make_smoke_data(dataset, run_dir / 'smoke_data', config['smoke_images'])
        record(phase='smoke_training', smoke_training_images=len(smoke_rows), smoke_batches_seen=0)
        probe = YOLO(str(weights), task='segment')

        def check_loss(trainer):
            if not torch.isfinite(trainer.loss.detach()).all().item():
                raise FloatingPointError('Nonfinite training loss; stopping before further optimization')

        def smoke_batch_finished(trainer):
            check_loss(trainer)
            first = not state['training_started']
            record(training_started=True, smoke_batches_seen=state['smoke_batches_seen'] + 1,
                   last_smoke_loss=float(trainer.loss.detach().cpu().item()))
            if first:
                update_public_plan(state)

        probe.add_callback('on_train_batch_end', smoke_batch_finished)
        probe.train(data=str(smoke_yaml), name='smoke', epochs=config['smoke_epochs'],
                    patience=0, val=False, save=False, **dict(train_args, batch=min(2, config['batch']), plots=False))
        del probe
        gc.collect()
        if device == 'mps':
            torch.mps.empty_cache()
        record(phase='starting_full_training', smoke_passed=True)
        model = YOLO(str(weights), task='segment')

        def check_loader(trainer):
            for split, loader in [('train', trainer.train_loader), ('val', trainer.test_loader)]:
                loaded = loader.dataset.labels
                expected = report['splits'][split]
                if len(loaded) != expected['images'] or sum(len(row['cls']) for row in loaded) != expected['objects']:
                    raise ValueError(f'{split}: YOLO image/object counts differ from the verified source')
                if any(len(row['segments']) != len(row['cls']) for row in loaded):
                    raise ValueError(f'{split}: YOLO loader lost instance polygons')
            record(phase='full_data_verified', save_directory=str(trainer.save_dir),
                   effective_batch=int(trainer.batch_size))

        def batch_finished(trainer):
            check_loss(trainer)
            state['main_batches_seen'] += 1
            if state['main_batches_seen'] == 1 or state['main_batches_seen'] % 10 == 0:
                record(phase='training', full_run_started=True, current_epoch=int(trainer.epoch) + 1,
                       effective_batch=int(trainer.batch_size),
                       last_training_loss=float(trainer.loss.detach().cpu().item()))
                if state['main_batches_seen'] == 1:
                    update_public_plan(state)

        def epoch_finished(trainer):
            # The framework also fires this callback after final best-checkpoint
            # evaluation; count actual CSV epochs, not its temporary epoch index.
            with Path(trainer.csv).open(newline='') as stream:
                epochs_done = sum(1 for _ in csv.DictReader(stream))
            record(completed_epochs=epochs_done, metrics=getattr(trainer, 'metrics', {}),
                   best_checkpoint=str(trainer.best), last_checkpoint=str(trainer.last))

        model.add_callback('on_pretrain_routine_end', check_loader)
        model.add_callback('on_train_batch_end', batch_finished)
        model.add_callback('on_fit_epoch_end', epoch_finished)
        model.train(data=str(data_yaml), name='fit', epochs=config['epochs'], patience=config['patience'],
                    save=True, save_period=config['save_period'], **train_args)
        record(phase='completed', finished_at=now())
        update_public_plan(state)
    except BaseException as exc:
        record(phase='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
               error=type(exc).__name__ + ': ' + str(exc))
        update_public_plan(state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--epochs', type=int)
    parser.add_argument('--batch', type=int)
    parser.add_argument('--device')
    parser.add_argument('--preflight-report', type=Path)
    args = parser.parse_args()
    # Kernel-released lock prevents two local trainers from sharing the latest status.
    import fcntl
    PROJECT.mkdir(parents=True, exist_ok=True)
    with (PROJECT / '.training.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('Another YOLOv8 training process is already running')
        run(args)


if __name__ == '__main__':
    main()
