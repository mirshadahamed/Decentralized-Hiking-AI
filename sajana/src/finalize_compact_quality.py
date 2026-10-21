"""Select validated compact models, reject inaccurate conversions, freeze and test."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .assess_compact_models import OUTPUT, REPORTS, environment, evaluate
from .component2_photo_contract import quality_checks
from .component2_presence import calibrate_presence, presence_counts
from .prepare_compact_component2 import configuration, verify_compact
from .train_yolov8 import ROOT, now, sha256, write_json

EXPORT_PYTHON = ROOT / '.venv-export/bin/python'
MOBILE = ROOT / 'results/component2_training/mobile_exports'
STAGES = ROOT / 'results/component2_training'


def child(command, log):
    with Path(log).open('w') as stream:
        subprocess.run(command, cwd=ROOT.parent, stdout=stream, stderr=subprocess.STDOUT, check=True)


def export_evaluation(artifact, task, size, tag, split='val', threshold=None):
    path = REPORTS / (tag + '.json')
    if path.exists():
        result = json.loads(path.read_text())
        if result['checkpoint_sha256'] != sha256(artifact):
            raise ValueError('Cached evaluation refers to a different artifact')
        return result
    command = [str(EXPORT_PYTHON), '-u', '-B', '-m', 'sajana.src.assess_compact_models',
               '--device', 'cpu', '--checkpoint', str(artifact), '--task', task,
               '--imgsz', str(size), '--tag', tag, '--split', split]
    if threshold is not None:
        command += ['--threshold', str(threshold)]
    child(command, STAGES / (tag + '.log'))
    return json.loads(path.read_text())


def choose_native(candidates):
    best = max(candidates, key=lambda r: r['AP50_95'])
    small = [r for r in candidates if r['imgsz'] == 416 and
             best['AP50_95'] - r['AP50_95'] <= .02 and
             best['mean_recall_at_threshold'] - r['mean_recall_at_threshold'] <= .03]
    return max(small, key=lambda r: r['AP50_95']) if small else best


def export_parity(native, converted):
    reasons = []
    baseline = {r['class_name']: r for r in native['per_class']}
    if {r['class_name'] for r in converted['per_class']} != set(baseline):
        reasons.append('Class evidence differs')
    for row in converted['per_class']:
        old = baseline.get(row['class_name'])
        if old is None:
            continue
        if old['AP50_95'] - row['AP50_95'] > .02:
            reasons.append(row['class_name'] + ': AP drop exceeds 0.02')
        if old['recall_at_threshold'] - row['recall_at_threshold'] > .03:
            reasons.append(row['class_name'] + ': recall drop exceeds 0.03')
    return {'passed': not reasons, 'reasons': reasons}


def finalize():
    cfg = configuration(); dataset = verify_compact(cfg)
    spec = json.loads((ROOT / 'configs/component2_refinement.json').read_text())
    complete = {}
    while len(complete) != len(spec['experiments']):
        for key in spec['experiments']:
            path = ROOT / 'runs/component2_refinement' / key / 'status.json'
            if not path.exists():
                continue
            state = json.loads(path.read_text())
            if state['phase'] in ('failed', 'interrupted'):
                raise ValueError('Refinement requires recovery: ' + key)
            if state['phase'] == 'completed':
                complete[key] = state
        if len(complete) != len(spec['experiments']):
            print('Waiting for recorded refinements to finish', now(), flush=True)
            time.sleep(10)
    for size in (416, 640):
        tag = 'refined_litter_' + str(size)
        if not (REPORTS / (tag + '.json')).exists():
            # Training has completed. Serialize accelerator validation with its lock.
            import fcntl
            with (ROOT / 'runs/yolov8_litter/.training.lock').open('a+') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                evaluate(complete['litter_detail']['best_checkpoint'], 'litter', size, tag, 'cpu')

    models, comparisons, presence = {}, {}, {}
    for task in ('litter', 'obstacle'):
        candidates = [json.loads(p.read_text()) for p in REPORTS.glob('*_' + task + '_*.json')
                      if p.stem.startswith(('baseline_', 'refined_'))]
        native = choose_native(candidates)
        exported = next((json.loads(p.read_text()) for p in MOBILE.glob('*.json')
                         if json.loads(p.read_text())['source_sha256'] == native['checkpoint_sha256'] and
                         json.loads(p.read_text())['imgsz'] == native['imgsz']), None)
        if exported is None:
            export_tag = task + '_' + native['checkpoint_sha256'][:10] + '_' + str(native['imgsz'])
            child([str(EXPORT_PYTHON), '-u', '-B', '-m', 'sajana.src.export_component2_mobile',
                   '--checkpoint', native['checkpoint'], '--task', task, '--imgsz', str(native['imgsz']),
                   '--tag', export_tag], STAGES / (export_tag + '.log'))
            exported = json.loads((MOBILE / (export_tag + '.json')).read_text())
        options = []
        for precision, artifact in exported['artifacts'].items():
            tag = 'export_' + task + '_' + precision
            existing = REPORTS / (tag + '.json')
            if existing.exists() and json.loads(existing.read_text())['checkpoint_sha256'] != artifact['sha256']:
                tag += '_' + artifact['sha256'][:8]
            result = export_evaluation(artifact['path'], task, native['imgsz'], tag)
            parity = export_parity(native, result)
            options.append(dict(artifact=artifact, precision=precision, validation=result, parity=parity))
        passed = [o for o in options if o['parity']['passed']]
        if not passed:
            raise ValueError('No export preserves native accuracy: ' + task)
        chosen = min(passed, key=lambda o: o['artifact']['bytes'])
        result = chosen['validation']
        rows = json.loads((OUTPUT / result['tag'] / 'predictions.json').read_text())
        presence[task] = calibrate_presence(rows, cfg[task]['names'], result['threshold'])
        models[task] = dict(result, precision=chosen['precision'],
                            names=cfg[task]['names'],
                            class_thresholds={k: v['threshold'] for k, v in presence[task].items()})
        comparisons[task] = {'native': native, 'exports': options, 'chosen_precision': chosen['precision']}
    selection = {'frozen_at': now(), 'validation_selection_complete': True,
                 'dataset_inventory_sha256': dataset['inventory_sha256'],
                 'models': models, 'test_used_to_select': False,
                 'quality_accepted_for_app': False,
                 'operating_point_policy': 'Object localization uses validation F1; photo-presence thresholds use validation photo F1 only when both positive and negative images exist, otherwise the object threshold.',
                 'validation_presence': presence}
    selection_path = REPORTS / 'frozen_selection.json'
    if selection_path.exists():
        raise ValueError('Selection already frozen; inspect prior results rather than retuning after test')
    write_json(selection_path, selection)
    write_json(REPORTS / 'model_comparisons.json', comparisons)
    tests, test_presence = {}, {}
    for task, model in models.items():
        tag = 'final_test_' + task
        tests[task] = export_evaluation(model['checkpoint'], task, model['imgsz'], tag,
                                        'test', model['threshold'])
        rows = json.loads((OUTPUT / tag / 'predictions.json').read_text())
        test_presence[task] = {name: presence_counts(rows, int(class_id), model['class_thresholds'][name])
                               for class_id, name in model['names'].items()}
    checks = quality_checks(models, spec['provisional_quality_checks_not_release_guarantees'])
    write_json(REPORTS / 'public_test_results.json', {'completed_at': now(), 'tests': tests,
               'photo_presence_at_frozen_thresholds': test_presence, 'selection_sha256': sha256(selection_path),
               'validation_checks': checks, 'test_used_to_tune': False, 'full_component_ready': False})
    assets = ROOT.parent / 'assets/models'; assets.mkdir(parents=True, exist_ok=True)
    development = {'schema_version': 1, 'use': 'development_only',
                   'quality_accepted_for_app': checks['public_validation_quality_passed'],
                   'full_component_ready': False, 'models': {}}
    for task, model in models.items():
        target = assets / ('component2_' + task + '.tflite')
        shutil.copyfile(model['checkpoint'], target)
        development['models'][task] = dict(checkpoint=str(target), asset='assets/models/' + target.name,
                                           checkpoint_sha256=sha256(target), names=model['names'],
                                           imgsz=model['imgsz'], threshold=model['threshold'],
                                           class_thresholds=model['class_thresholds'], precision=model['precision'],
                                           bytes=target.stat().st_size)
    write_json(ROOT / 'configs/component2_development_models.json', development)
    write_json(assets / 'component2_manifest.json', dict(development, models={
        k: {field: value for field, value in v.items() if field != 'checkpoint'}
        for k, v in development['models'].items()}))
    print('Frozen validation choices, completed reserved tests and prepared development assets', flush=True)


if __name__ == '__main__':
    environment()
    import torch
    torch.set_num_threads(2)
    finalize()
