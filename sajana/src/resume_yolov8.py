"""Resume an existing litter run with complete, timeout-free validation.

Preserve the original run/checkpoints, optimizer and EMA; re-establish a complete
validation baseline and checkpoint selection before further training.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .train_yolov8 import ROOT, RESULTS, PROJECT, STATUS, now, sha256, write_json, update_public_plan


def revalidate_checkpoint(trainer, expected_images, reset_selection):
    """Preserve a valid best checkpoint and patience when resuming after a reboot."""
    metrics = trainer.validator(trainer)
    fitness = metrics.pop('fitness')
    if trainer.validator.complete_nms_images != expected_images:
        raise ValueError('Incomplete baseline validation')
    trainer.metrics = metrics
    trainer.fitness = fitness
    if reset_selection:
        # Only the first migration from the timeout-prone validator needs a new
        # selection baseline. Ordinary resumes retain the restored stopper.
        trainer.best_fitness = fitness
        trainer.stopper.best_fitness = fitness
        trainer.stopper.best_epoch = trainer.start_epoch
        trainer.stopper.possible_stop = False
        if not trainer.save_model():
            raise ValueError('Corrected checkpoint baseline was not saved')


def run(run_dir, device):
    state=json.loads(STATUS.read_text())
    if Path(state['run_directory']).resolve()!=run_dir.resolve():
        raise ValueError('Latest training status belongs to a different run')
    if state['phase'] not in ('interrupted','failed'):
        raise ValueError('Interrupt and preserve the existing trainer before resuming')
    old_state=dict(state);stamp=datetime.now(ZoneInfo('Asia/Colombo')).strftime('%Y%m%d_%H%M%S')
    recovery=run_dir/('validation_recovery_'+stamp);recovery.mkdir(exist_ok=False)
    write_json(recovery/'prior_status.json',old_state)
    if (RESULTS/'launch.json').exists():shutil.copy2(RESULTS/'launch.json',recovery/'launch_at_resume.json')
    original=json.loads((run_dir/'run_manifest.json').read_text())
    state.pop('error',None)
    reset_selection = not (old_state.get('validation_policy') == 'complete_nms_no_wall_clock_cutoff'
                           and old_state.get('baseline_validation_complete'))
    provisional_through = (old_state['completed_epochs'] if reset_selection else
                           old_state.get('historical_validation_provisional_through_epoch', 0))

    def record(**values):
        state.update(values,updated_at=now());write_json(STATUS,state);write_json(run_dir/'status.json',state)

    record(phase='verifying_resume',pid=os.getpid(),active_console_log=os.environ.get('C2_TRAIN_LOG'),
           validation_policy='complete_nms_no_wall_clock_cutoff',
           historical_validation_provisional_through_epoch=provisional_through)
    try:
        inventory=json.loads((run_dir/'dataset_hashes.json').read_text())
        dataset=ROOT/original['configuration']['dataset']
        for split, files in inventory.items():
            for relative, expected in files.items():
                if sha256(dataset/relative)!=expected:
                    raise ValueError('Frozen data changed: '+relative)
        if sha256(ROOT/original['configuration']['annotations'])!=original['annotations_sha256']:
            raise ValueError('Source annotations changed')
        if sha256(run_dir/'data.yaml')!=original['data_yaml_sha256']:
            raise ValueError('Frozen training YAML changed')
        for name in ('best.pt','last.pt'):
            shutil.copy2(run_dir/'fit/weights'/name,recovery/name)
        shutil.copy2(run_dir/'fit/results.csv',recovery/'results_before_resume.csv')
        os.environ.setdefault('PYTORCH_ENABLE_MPS_FALLBACK','1')
        os.environ.setdefault('PYTORCH_MPS_HIGH_WATERMARK_RATIO','1.0')
        os.environ.setdefault('PYTORCH_MPS_LOW_WATERMARK_RATIO','0.9')
        os.environ.setdefault('YOLO_CONFIG_DIR',str(ROOT/'data/raw/ultralytics_settings'))
        os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'data/raw/matplotlib'))
        os.environ.setdefault('MPLBACKEND','Agg');os.environ.setdefault('YOLO_OFFLINE','true')
        os.environ.setdefault('YOLO_AUTOINSTALL','false')
        import torch
        import ultralytics
        from ultralytics import YOLO
        from .yolov8_validation import CompleteSegmentationTrainer
        if ultralytics.__version__!='8.4.183':raise ValueError('Validator requires the pinned Ultralytics version')
        torch.set_num_threads(min(4,os.cpu_count() or 1))
        checkpoint=run_dir/'fit/weights/last.pt'
        ckpt=torch.load(checkpoint,map_location='cpu',weights_only=False)
        completed=int(ckpt['epoch'])+1
        if not ckpt.get('optimizer') or ckpt.get('ema') is None:
            raise ValueError('Checkpoint lacks resumable optimizer/EMA state')
        loss_keys=[key.removeprefix('val/') for key in ckpt['train_metrics'] if key.startswith('val/')]
        if not loss_keys:raise ValueError('Checkpoint does not record validation loss names')
        manifest={'created_at':now(),'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                  'resume_source_sha256':sha256(__file__),
                  'validator_source_sha256':sha256(ROOT/'src/yolov8_validation.py'),
                  'original_run_manifest_sha256':sha256(run_dir/'run_manifest.json'),
                  'original_resume_checkpoint_sha256':sha256(checkpoint),'resume_completed_epochs':completed,
                  'checkpoint_backup_directory':str(recovery),'optimizer_and_ema_restored':True,
                  'frozen_data_hashes_rechecked':True,'test_model_evaluation_performed':False,
                  'historical_epoch_scores_provisional':bool(provisional_through),
                  'historical_validation_provisional_through_epoch':provisional_through,
                  'selection_state_reset':reset_selection,
                  'previous_recovery_manifest':old_state.get('recovery_manifest_path'),
                  'selection_policy':('Complete current-checkpoint validation establishes a new baseline; preserve old best/snapshots for later validation-only review.' if reset_selection else
                                      'Revalidate the current checkpoint while retaining saved best fitness, best checkpoint and early-stopping state.')}
        del ckpt
        write_json(recovery/'manifest.json',manifest);write_json(RESULTS/'validation_recovery.json',manifest)
        record(recovery_manifest_path=str(recovery/'manifest.json'),completed_epochs=completed,
               resumed_from_completed_epoch=completed,phase='restoring_optimizer')
        expected=json.loads((run_dir/'preflight.json').read_text())['splits']
        model=YOLO(str(checkpoint),task='segment')

        def prepared(trainer):
            if Path(trainer.save_dir).resolve()!=(run_dir/'fit').resolve():
                raise ValueError('Resume attempted to change the original output directory')
            for split, loader in [('train',trainer.train_loader),('val',trainer.test_loader)]:
                rows=loader.dataset.labels
                if len(rows)!=expected[split]['images'] or sum(len(r['cls']) for r in rows)!=expected[split]['objects']:
                    raise ValueError('Resume native loader counts changed: '+split)
            trainer.epoch=trainer.start_epoch-1
            # The pinned trainer normally learns these accumulator names on its
            # first training forward pass. Resume already records the names;
            # initialize zero accumulators without a new optimization/BN step.
            trainer.loss_items={key:torch.zeros((),device=trainer.device) for key in loss_keys}
            trainer.loss_names=tuple(loss_keys)
            record(phase='revalidating_checkpoint',baseline_validation_complete=False)
            revalidate_checkpoint(trainer, expected['val']['images'], reset_selection)
            write_json(recovery/'complete_baseline_validation.json',{'metrics':trainer.metrics,
                        'fitness':trainer.fitness,'images_processed':trainer.validator.complete_nms_images,
                        'completed_epochs':completed,'test_used':False})
            record(phase='resuming_training',metrics=trainer.metrics,baseline_validation_complete=True,
                   complete_validation_images=trainer.validator.complete_nms_images,
                   best_checkpoint=str(trainer.best),last_checkpoint=str(trainer.last))
            update_public_plan(state)

        def batch(trainer):
            if not torch.isfinite(trainer.loss.detach()).all().item():raise FloatingPointError('Nonfinite resumed loss')
            state['main_batches_seen']+=1
            if state['main_batches_seen']%10==0:
                record(phase='training',current_epoch=int(trainer.epoch)+1,
                       last_training_loss=float(trainer.loss.detach().cpu().item()),effective_batch=int(trainer.batch_size))

        def epoch(trainer):
            with Path(trainer.csv).open(newline='') as stream:count=sum(1 for _ in csv.DictReader(stream))
            if trainer.validator.complete_nms_images!=expected['val']['images']:
                raise ValueError('Incomplete resumed epoch validation')
            record(completed_epochs=count,metrics=trainer.metrics,
                   complete_validation_images=trainer.validator.complete_nms_images,
                   best_checkpoint=str(trainer.best),last_checkpoint=str(trainer.last))

        model.add_callback('on_pretrain_routine_end',prepared)
        model.add_callback('on_train_batch_end',batch);model.add_callback('on_fit_epoch_end',epoch)
        model.train(resume=True,trainer=CompleteSegmentationTrainer,device=device,workers=0,
                    save_dir=str(run_dir/'fit'),val=True)
        record(phase='completed',finished_at=now());update_public_plan(state)
    except BaseException as exc:
        record(phase='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',
               error=type(exc).__name__+': '+str(exc));update_public_plan(state);raise


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--device',default='mps');args=parser.parse_args()
    with (PROJECT/'.training.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);run(args.run.resolve(),args.device)


if __name__=='__main__':main()
