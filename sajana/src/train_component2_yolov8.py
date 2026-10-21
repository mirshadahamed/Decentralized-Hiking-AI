"""Recorded compact YOLOv8 litter/context jobs; test is never used by a model."""
from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from .component2_training_data import CONFIG, PROJECT, check_frozen, configuration, data_yaml, smoke_data
from .train_yolov8 import ROOT, now, sha256, write_json


def source_hashes():
    return {name: sha256(ROOT/'src'/name) for name in
            ['train_component2_yolov8.py', 'component2_training_data.py',
             'yolov8_detection_validation.py', 'yolov8_validation.py',
             'run_component2_training_queue.py', 'finalize_component2_training.py']}


def update_plan(job_id, state):
    path = ROOT/'configs/component2_training_plan.json'
    plan = json.loads(path.read_text())
    target = (next(row for row in plan['first_experiments'] if row['experiment_id'] == job_id)
              if job_id == 'L2' else plan['next_context_experiment'])
    target.update(training_started=bool(state.get('batches_seen')), training_phase=state['phase'],
                  completed_epochs=state.get('completed_epochs', 0), device=state['device'],
                  model_and_library_versions=state.get('versions'),
                  runtime_status=f'sajana/runs/component2_training/jobs/{job_id}/status.json')
    write_json(path, plan)


def train(job_id, device, smoke=False):
    cfg = configuration(); job = cfg['jobs'][job_id]
    report = check_frozen(job_id, cfg)
    weights = ROOT/'data/raw/pretrained'/job['model']
    evidence = json.loads((PROJECT/'weights'/f'{job_id}.json').read_text())
    if evidence['sha256'] != sha256(weights):
        raise ValueError('Initial checkpoint changed')
    folder = PROJECT/('smoke' if smoke else 'jobs')/job_id
    folder.mkdir(parents=True, exist_ok=True); status_path = folder/'status.json'
    prior = json.loads(status_path.read_text()) if status_path.exists() else {}
    if prior.get('phase') == 'completed':
        return prior
    if smoke and prior:
        raise ValueError('Smoke output already exists; inspect its failure before rerunning')
    state = dict(prior, job=job_id, task=job['task'], model=job['model'], names=job['names'],
                 device=device, pid=os.getpid(), role=job['role'],
                 test_split_used_for_training=False, full_component_ready=False)
    state.pop('error', None)

    def record(**values):
        state.update(values, updated_at=now()); write_json(status_path, state)
        if not smoke and (state['phase'] in ('completed', 'failed', 'interrupted') or
                          (state['phase'] == 'training' and state.get('batches_seen') == 1)):
            update_plan(job_id, state)

    record(phase='preparing', configuration=cfg['training'])
    try:
        os.environ.setdefault('PYTORCH_ENABLE_MPS_FALLBACK', '1')
        os.environ.setdefault('PYTORCH_MPS_HIGH_WATERMARK_RATIO', '1.0')
        os.environ.setdefault('PYTORCH_MPS_LOW_WATERMARK_RATIO', '0.9')
        os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT/'data/raw/ultralytics_settings'))
        os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'data/raw/matplotlib'))
        os.environ.setdefault('YOLO_AUTOINSTALL', 'false'); os.environ.setdefault('YOLO_OFFLINE', 'true')
        import torch
        import ultralytics
        from ultralytics import YOLO, settings
        from .yolov8_validation import CompleteSegmentationTrainer
        from .yolov8_detection_validation import CompleteDetectionTrainer
        if ultralytics.__version__ != '8.4.183':
            raise ValueError('Use pinned Ultralytics 8.4.183')
        torch.set_num_threads(1 if device == 'cpu' else 2)
        for key in ('sync', 'hub', 'wandb', 'mlflow', 'comet', 'clearml', 'neptune', 'raytune', 'tensorboard', 'dvc'):
            if key in settings:
                settings.update({key: False})
        versions = {'python': platform.python_version(), 'torch': torch.__version__, 'ultralytics': ultralytics.__version__}
        record(versions=versions)
        expected = report['splits']
        if smoke:
            yaml, count = smoke_data(job, folder/'data')
            expected = {split: {'images': count} for split in ('train', 'val')}
        else:
            smoke_state = json.loads((PROJECT/'smoke'/job_id/'status.json').read_text())
            if smoke_state.get('phase') != 'completed' or not smoke_state.get('batches_seen'):
                raise ValueError('Successful training-only smoke check required')
            yaml = data_yaml(folder/'data.yaml', ROOT/job['dataset'], job['names'])
        fit = folder/'fit'; last = fit/'weights/last.pt'
        resume = not smoke and last.is_file()
        manifest_path = folder/'run_manifest.json'
        if resume:
            manifest = json.loads(manifest_path.read_text())
            if (manifest['source_sha256'] != source_hashes() or
                    manifest['configuration_sha256'] != sha256(CONFIG) or
                    manifest['dataset_inventory_sha256'] != sha256(PROJECT/'preflight'/job_id/'dataset_hashes.json') or
                    manifest['data_yaml_sha256'] != sha256(yaml)):
                raise ValueError('Frozen run configuration/source/data changed; refusing resume')
            checkpoint = torch.load(last, map_location='cpu', weights_only=False)
            if checkpoint.get('optimizer') is None or checkpoint.get('ema') is None:
                raise ValueError('Last checkpoint lacks resumable optimizer and EMA')
            record(resumed_from_epoch=int(checkpoint['epoch'])+1)
            del checkpoint
        elif fit.exists():
            raise ValueError('Existing fit directory has no resumable checkpoint; inspect before retrying')
        else:
            manifest = {'created_at': now(), 'job': job_id, 'configuration': cfg['training'],
                        'configuration_sha256': sha256(CONFIG), 'source_sha256': source_hashes(),
                        'dataset_inventory_sha256': sha256(PROJECT/'preflight'/job_id/'dataset_hashes.json'),
                        'preflight_sha256': sha256(PROJECT/'preflight'/job_id/'preflight.json'),
                        'data_yaml_sha256': sha256(yaml), 'initial_weights_sha256': evidence['sha256'],
                        'versions': versions, 'code_commit': subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                        'test_split_loaded': False, 'smoke_training_only': smoke,
                        'selection': 'Best validation fitness; no test tuning', 'role': job['role']}
            write_json(manifest_path, manifest)
            with (folder/'environment.lock.txt').open('w') as out:
                subprocess.run([sys.executable, '-m', 'pip', 'freeze'], stdout=out, check=True)
        model = YOLO(str(last if resume else weights), task=job['task'])
        record(batches_seen=prior.get('batches_seen', 0), planned_epochs=1 if smoke else cfg['training']['epochs'])

        def prepared(trainer):
            if Path(trainer.save_dir).resolve() != fit.resolve():
                raise ValueError('Unexpected training output directory')
            for split, loader in [('train', trainer.train_loader), ('val', trainer.test_loader)]:
                labels = loader.dataset.labels
                if len(labels) != expected[split]['images']:
                    raise ValueError('Native loader dropped images: '+split)
                objects = sum(len(row['cls']) for row in labels)
                if not smoke and objects != expected[split]['objects']:
                    raise ValueError('Native loader dropped labels: '+split)
                if job['task'] == 'segment' and any(len(r['segments']) != len(r['cls']) for r in labels):
                    raise ValueError('Native loader lost segmentation polygons')
                record(**{split+'_loader_images': len(labels), split+'_loader_objects': objects})
            record(phase='starting_training', optimizer_resume=resume)

        def batch(trainer):
            if not torch.isfinite(trainer.loss.detach()).all().item():
                raise FloatingPointError('Nonfinite loss; stopped training')
            state['batches_seen'] += 1
            if state['batches_seen'] == 1 or state['batches_seen'] % 10 == 0:
                record(phase='training', current_epoch=int(trainer.epoch)+1,
                       latest_loss=float(trainer.loss.detach().cpu().item()))

        def epoch(trainer):
            images = getattr(trainer.validator, 'complete_nms_images', 0)
            if images != expected['val']['images']:
                raise ValueError('Validation did not process every image')
            with Path(trainer.csv).open(newline='') as stream:
                completed = sum(1 for _ in csv.DictReader(stream))
            record(completed_epochs=completed, validation_images=images, metrics=trainer.metrics,
                   best_checkpoint=str(trainer.best), last_checkpoint=str(trainer.last))

        model.add_callback('on_pretrain_routine_end', prepared)
        model.add_callback('on_train_batch_end', batch)
        model.add_callback('on_fit_epoch_end', epoch)
        trainer_class = CompleteSegmentationTrainer if job['task'] == 'segment' else CompleteDetectionTrainer
        training = dict(cfg['training'])
        if smoke:
            training.update(epochs=1, patience=0)
        if resume:
            model.train(resume=True, trainer=trainer_class, device=device, workers=0,
                        cache=False, plots=False, save_period=-1, save_dir=str(fit), val=True)
        else:
            model.train(data=str(yaml), trainer=trainer_class, device=device,
                        project=str(folder), name='fit', save_dir=str(fit),
                        save=not smoke, val=True, verbose=False, **training)
        record(phase='completed', finished_at=now(), full_component_ready=False)
        return state
    except BaseException as exc:
        record(phase='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
               error=type(exc).__name__+': '+str(exc))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', choices=['L2', 'O1'], required=True)
    parser.add_argument('--device', default='mps'); parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    PROJECT.mkdir(parents=True, exist_ok=True)
    # CPU-only 8-photo smoke checks may run during L1; full accelerator jobs
    # share L1's kernel lock and can never overlap it.
    lock_path = PROJECT/'.cpu_smoke.lock' if args.smoke and args.device == 'cpu' else ROOT/'runs/yolov8_litter/.training.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        train(args.job, args.device, args.smoke)


if __name__ == '__main__':
    main()
