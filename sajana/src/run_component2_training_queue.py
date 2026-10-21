"""Prepare and run the remaining compact YOLOv8 jobs sequentially after L1."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .component2_training_data import CONFIG, PROJECT, check_frozen, configuration, freeze
from .train_yolov8 import ROOT, now, sha256, write_json

RESULTS = ROOT/'results/component2_training'


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def predecessor_gate(state, process_alive, lock_available):
    if state.get('experiment') != 'L1':
        return 'wrong_predecessor'
    if state.get('phase') == 'completed':
        return 'ready' if lock_available else 'waiting_for_release'
    if state.get('phase') in ('failed', 'interrupted') or not process_alive:
        return 'predecessor_recovery_required'
    return 'waiting_for_L1'


def lock_free(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True


def acquire_weights(job_id, job):
    weights = ROOT/'data/raw/pretrained'/job['model']
    record_path = PROJECT/'weights'/f'{job_id}.json'
    trusted_prefix = 'https://github.com/ultralytics/assets/releases/download/v8.3.0/'
    if job['weights_url'] != trusted_prefix+job['model']:
        raise ValueError('Only the declared official YOLOv8 checkpoint release is allowed')
    if weights.exists():
        prior_path = record_path if record_path.exists() else ROOT/'results/yolov8_training/pretrained_weights.json'
        prior = json.loads(prior_path.read_text())
        if prior['model'] != job['model'] or prior['sha256'] != sha256(weights):
            raise ValueError('Existing initial weights lack matching acquisition evidence')
    else:
        import requests
        weights.parent.mkdir(parents=True, exist_ok=True)
        temporary = weights.with_suffix('.part')
        with requests.get(job['weights_url'], stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            with temporary.open('wb') as stream:
                for chunk in response.iter_content(1024*1024):
                    stream.write(chunk)
                    if stream.tell() > 100*1024*1024:
                        raise ValueError('Unexpected checkpoint size')
        if temporary.stat().st_size < 1024*1024:
            raise ValueError('Incomplete checkpoint acquisition')
        temporary.replace(weights)
    record = {'checked_at': now(), 'job': job_id, 'model': job['model'],
              'source_url': job['weights_url'], 'sha256': sha256(weights), 'bytes': weights.stat().st_size}
    write_json(record_path, record)
    return record


def prepare():
    cfg = configuration(); RESULTS.mkdir(parents=True, exist_ok=True)
    record = {'prepared_at': now(), 'configuration_sha256': sha256(CONFIG), 'jobs': {},
              'selection_policy_sha256': sha256(ROOT/'configs/component2_model_selection.json'),
              'training_started_by_preparation': False, 'test_model_evaluation_performed': False,
              'full_component_ready': False, 'remaining_data_gaps': cfg['unavailable_capabilities']}
    for job_id in cfg['job_order']:
        record['jobs'][job_id] = {'weights': acquire_weights(job_id, cfg['jobs'][job_id]),
                                  'preflight': freeze(job_id, cfg)}
    from .train_component2_yolov8 import source_hashes
    record['source_sha256'] = source_hashes()
    write_json(PROJECT/'prepared.json', record)
    write_json(RESULTS/'preparation.json', record)
    return record


def refresh_prepared():
    """Retain completed source audits while rehashing every frozen input byte."""
    cfg = configuration()
    record = json.loads((PROJECT/'prepared.json').read_text())
    if record['configuration_sha256'] != sha256(CONFIG):
        raise ValueError('Dataset/job configuration changed; run a full preparation')
    write_json(PROJECT/'prepared_before_refresh.json', record)
    for job_id in cfg['job_order']:
        check_frozen(job_id, cfg)
        acquire_weights(job_id, cfg['jobs'][job_id])
    from .train_component2_yolov8 import source_hashes
    record.update(refreshed_at=now(), all_frozen_input_bytes_rechecked=True,
                  source_sha256=source_hashes(),
                  selection_policy_sha256=sha256(ROOT/'configs/component2_model_selection.json'))
    write_json(PROJECT/'prepared.json', record); write_json(RESULTS/'preparation.json', record)
    return record


def job_state(job_id):
    path = PROJECT/'jobs'/job_id/'status.json'
    return json.loads(path.read_text()) if path.exists() else {'job': job_id, 'phase': 'queued'}


def save_status(state):
    state.update(updated_at=now())
    write_json(RESULTS/'queue_status.json', state)
    lines = ['# Component 2 YOLOv8 training queue', '', 'Checked: '+state['updated_at'], '',
             'Queue phase: **'+state['phase']+'**. Full component ready: **False**.', '',
             '| Experiment | Task | Phase | Completed epochs |', '| --- | --- | --- | ---: |']
    prior = state.get('L1', {})
    lines.append(f"| L1 | TACO litter segmentation | {prior.get('phase', 'unknown')} | {prior.get('completed_epochs', 0)} |")
    for key, job in state.get('jobs', {}).items():
        lines.append(f"| {key} | {job.get('task', 'pending')} | {job['phase']} | {job.get('completed_epochs', 0)} |")
    lines += ['', 'New jobs: YOLOv8 nano; 416-pixel inputs; batch 2; workers 0; no image cache; no plots; best/last only.',
              'Held-out tests are excluded from optimization, calibration and model selection.',
              'Rock/log presence is context, not a trail blockage decision.', '', 'Still required:', '']
    lines += ['- '+entry for entry in state['remaining_data_gaps']]
    if state.get('error'):
        lines += ['', 'Issue: '+state['error']]
    (RESULTS/'HEALTH.md').write_text('\n'.join(lines)+'\n')


def run_queue(interval=30):
    cfg = configuration()
    prepared = json.loads((PROJECT/'prepared.json').read_text())
    from .train_component2_yolov8 import source_hashes
    if prepared['configuration_sha256'] != sha256(CONFIG) or prepared['source_sha256'] != source_hashes():
        raise ValueError('Prepared source/configuration changed; repeat preparation')
    if prepared['selection_policy_sha256'] != sha256(ROOT/'configs/component2_model_selection.json'):
        raise ValueError('Selection policy changed after preparation')
    for job_id in cfg['job_order']:
        smoke = json.loads((PROJECT/'smoke'/job_id/'status.json').read_text())
        if smoke['phase'] != 'completed' or not smoke.get('batches_seen'):
            raise ValueError('Training-only smoke check not complete: '+job_id)
    state = {'started_at': now(), 'pid': os.getpid(), 'phase': 'waiting_for_L1',
             'jobs': {key: job_state(key) for key in cfg['job_order']},
             'remaining_data_gaps': cfg['unavailable_capabilities'], 'full_component_ready': False}
    lock_path = ROOT/'runs/yolov8_litter/.training.lock'
    try:
        while True:
            predecessor = json.loads((ROOT/cfg['predecessor_status']).read_text())
            gate = predecessor_gate(predecessor, alive(predecessor.get('pid')), lock_free(lock_path))
            state.update(phase=gate, L1=predecessor); save_status(state)
            if gate == 'ready':
                break
            if gate in ('wrong_predecessor', 'predecessor_recovery_required'):
                raise RuntimeError('L1 must complete successfully before dependent training; inspect its status and resume if interrupted')
            time.sleep(interval)
        for job_id in cfg['job_order']:
            prior = job_state(job_id)
            if prior['phase'] == 'completed':
                continue
            process = None
            if not (prior['phase'] not in ('failed', 'interrupted', 'queued') and alive(prior.get('pid'))):
                while not lock_free(lock_path):
                    state['phase'] = 'waiting_for_accelerator'; save_status(state); time.sleep(interval)
                command = [sys.executable, '-u', '-B', '-m', 'sajana.src.train_component2_yolov8',
                           '--job', job_id, '--device', cfg['device']]
                log = RESULTS/(job_id+'_'+time.strftime('%Y%m%d_%H%M%S')+'.log')
                with log.open('wb') as out:
                    process = subprocess.Popen(command, cwd=ROOT.parent, stdin=subprocess.DEVNULL,
                                               stdout=out, stderr=subprocess.STDOUT)
                state['active_console_log'] = str(log)
            while True:
                current = job_state(job_id); state['jobs'][job_id] = current
                state['phase'] = 'running_'+job_id; save_status(state)
                if process is not None:
                    code = process.poll()
                    if code is not None:
                        if code or current['phase'] != 'completed':
                            raise RuntimeError(f'{job_id} stopped with exit {code}; inspect its saved status/checkpoint')
                        break
                elif current['phase'] == 'completed':
                    break
                elif not alive(current.get('pid')):
                    raise RuntimeError('Adopted trainer stopped: '+job_id)
                time.sleep(interval)
        state['phase'] = 'validation_selection_and_public_evaluation'
        save_status(state)
        # Evaluation shares the same accelerator lock as all trainers.
        with lock_path.open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            from .finalize_component2_training import finalize
            finalize(cfg['device'])
        state['phase'] = 'public_jobs_completed_local_data_missing'
        state['jobs'] = {key: job_state(key) for key in cfg['job_order']}
        save_status(state)
        # Model selection and local/mobile acceptance are separate gates: successful
        # jobs must never automatically turn full_component_ready into True.
    except BaseException as exc:
        state.update(phase='stopped', error=type(exc).__name__+': '+str(exc)); save_status(state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--interval', type=int, default=30)
    parser.add_argument('--refresh-prepared', action='store_true')
    args = parser.parse_args()
    if args.interval < 10:
        parser.error('Interval must be at least 10 seconds')
    PROJECT.mkdir(parents=True, exist_ok=True); RESULTS.mkdir(parents=True, exist_ok=True)
    with (PROJECT/'.queue.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.prepare and args.refresh_prepared:
            parser.error('Choose preparation or refresh, not both')
        if args.prepare:
            print(json.dumps(prepare(), indent=2))
        elif args.refresh_prepared:
            print(json.dumps(refresh_prepared(), indent=2))
        else:
            run_queue(args.interval)


if __name__ == '__main__':
    main()
