"""Validation-only selection followed by a frozen public holdout evaluation.

No local trail or Android readiness is inferred from these public task metrics.
"""
from __future__ import annotations

import gc
import json
import math
import os
from pathlib import Path

from .component2_training_data import PROJECT, check_frozen, configuration, data_yaml
from .train_yolov8 import ROOT, finite_json, now, sha256, write_json

RESULTS = ROOT/'results/component2_training'
POLICY = ROOT/'configs/component2_model_selection.json'


def choose_litter(candidates, policy):
    valid = [c for c in candidates if all(math.isfinite(c[k]) for k in ('mask_map', 'mask_recall'))]
    if not valid:
        raise ValueError('No finite validation candidate')
    best = max(valid, key=lambda c: c['mask_map'])
    compact = [c for c in valid if c['imgsz'] == 416 and
               best['mask_map']-c['mask_map'] <= policy['prefer_416_when_mask_map_drop_at_most'] and
               best['mask_recall']-c['mask_recall'] <= policy['prefer_416_when_mask_recall_drop_at_most']]
    return max(compact, key=lambda c: c['mask_map']) if compact else best


def evaluate(checkpoint, dataset, names, task, imgsz, split, folder, expected_images, device, frozen_threshold=None):
    import numpy as np
    import torch
    from ultralytics import YOLO
    from ultralytics.utils.metrics import smooth
    from .yolov8_validation import CompleteSegmentationValidator
    from .yolov8_detection_validation import CompleteDetectionValidator
    folder.mkdir(parents=True, exist_ok=True)
    yaml = data_yaml(folder/'data.yaml', dataset, names, val='images/'+split)
    model = YOLO(str(checkpoint), task=task)
    captured = []

    def validator_factory(**kwargs):
        validator = (CompleteSegmentationValidator if task == 'segment' else CompleteDetectionValidator)(**kwargs)
        captured.append(validator)
        return validator

    metrics = model.val(data=str(yaml), validator=validator_factory,
                        device=device, imgsz=imgsz, batch=2, workers=0, cache=False, plots=False,
                        conf=0.001, iou=0.7, rect=False, project=str(folder), name='metrics',
                        save_dir=str(folder/'metrics'), verbose=False)
    if captured[0].complete_nms_images != expected_images:
        raise ValueError('Incomplete model evaluation')
    quality = metrics.seg if task == 'segment' else metrics.box
    curve = np.asarray(quality.f1_curve)
    if curve.size and split == 'val':
        index = int(smooth(curve.mean(0), 0.1).argmax())
        threshold = float(quality.px[index])
    else:
        threshold = None
    result = {'checkpoint': str(checkpoint), 'checkpoint_sha256': sha256(checkpoint), 'imgsz': imgsz,
              'split': split, 'images': expected_images, 'metrics': finite_json(metrics.results_dict),
              'validation_f1_threshold_candidate': threshold,
              'mask_map': float(metrics.seg.map) if task == 'segment' else None,
              'mask_recall': float(metrics.seg.mr) if task == 'segment' else None,
              'metrics_note': 'Standard AP confidence sweep; native precision/recall summaries use maximum F1, not a deployed threshold.'}
    if curve.size and frozen_threshold is not None:
        index = int(np.abs(np.asarray(quality.px)-frozen_threshold).argmin())
        result['at_frozen_validation_threshold'] = {
            'confidence': frozen_threshold, 'mean_precision': float(np.asarray(quality.p_curve)[:,index].mean()),
            'mean_recall': float(np.asarray(quality.r_curve)[:,index].mean()),
            'mean_f1': float(curve[:,index].mean())}
    captured.clear()
    del model, metrics; gc.collect()
    if device == 'mps':
        torch.mps.empty_cache()
    return result


def finalize(device='mps'):
    cfg = configuration(); policy = json.loads(POLICY.read_text())
    output = PROJECT/'evaluation'; output.mkdir(parents=True, exist_ok=True)
    if (RESULTS/'public_evaluation.json').exists():
        return json.loads((RESULTS/'public_evaluation.json').read_text())
    os.environ.setdefault('PYTORCH_ENABLE_MPS_FALLBACK','1')
    os.environ.setdefault('PYTORCH_MPS_HIGH_WATERMARK_RATIO','1.0')
    os.environ.setdefault('PYTORCH_MPS_LOW_WATERMARK_RATIO','0.9')
    os.environ.setdefault('YOLO_CONFIG_DIR',str(ROOT/'data/raw/ultralytics_settings'))
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'data/raw/matplotlib'))
    os.environ.setdefault('YOLO_AUTOINSTALL','false');os.environ.setdefault('YOLO_OFFLINE','true')
    import torch
    import ultralytics
    if ultralytics.__version__ != '8.4.183':
        raise ValueError('Pinned validator environment required')
    torch.set_num_threads(2)
    l1 = json.loads((ROOT/'results/yolov8_training/status.json').read_text())
    if l1['phase'] != 'completed':
        raise ValueError('L1 must finish before final selection')
    for job_id in cfg['job_order']:
        if json.loads((PROJECT/'jobs'/job_id/'status.json').read_text())['phase'] != 'completed':
            raise ValueError('Training incomplete: '+job_id)
        check_frozen(job_id, cfg)
    selection_path = output/'frozen_selection.json'
    if selection_path.exists():
        selection = json.loads(selection_path.read_text())
        if selection['policy_sha256'] != sha256(POLICY):
            raise ValueError('Selection policy changed after freezing')
    else:
        checkpoints = [Path(l1['best_checkpoint']), PROJECT/'jobs/L2/fit/weights/best.pt']
        # Include the original provisional candidates using complete validation.
        run = Path(l1['run_directory'])
        for recovery in run.glob('validation_recovery_*/prior_status.json'):
            prior = json.loads(recovery.read_text())
            if prior.get('validation_policy') != 'complete_nms_no_wall_clock_cutoff':
                checkpoints.append(recovery.parent/'best.pt')
        for p in (run/'fit/weights').glob('epoch*.pt'):
            epoch = int(p.stem.removeprefix('epoch'))+1
            if epoch <= l1.get('historical_validation_provisional_through_epoch', 0):
                checkpoints.append(p)
        unique, seen = [], set()
        for p in checkpoints:
            digest = sha256(p)
            if digest not in seen:
                unique.append(p); seen.add(digest)
        candidates = []
        for checkpoint in unique:
            for size in policy['litter_resolution_candidates']:
                tag = sha256(checkpoint)[:12]+'_'+str(size)
                record = output/('val_'+tag+'.json')
                if record.exists():
                    result = json.loads(record.read_text())
                else:
                    result = evaluate(checkpoint, ROOT/cfg['jobs']['L2']['dataset'], cfg['jobs']['L2']['names'],
                                      'segment', size, 'val', output/tag, 286, device)
                    write_json(record, result)
                candidates.append(result)
        selected = choose_litter(candidates, policy)
        obstacle = evaluate(PROJECT/'jobs/O1/fit/weights/best.pt', ROOT/cfg['jobs']['O1']['dataset'],
                            cfg['jobs']['O1']['names'], 'detect', 416, 'val', output/'O1_val', 283, device)
        selection = {'frozen_at': now(), 'policy_sha256': sha256(POLICY), 'litter_candidates': candidates,
                     'litter': selected, 'rock_log_context': obstacle, 'test_used_to_select': False,
                     'full_component_ready': False}
        write_json(selection_path, selection); write_json(RESULTS/'model_selection.json', selection)
    tests = {}
    for key, job_id, task in [('litter','L2','segment'), ('rock_log_context','O1','detect')]:
        chosen = selection[key]
        if sha256(chosen['checkpoint']) != chosen['checkpoint_sha256']:
            raise ValueError('Selected checkpoint changed after freezing')
        record = output/(key+'_public_test.json')
        if record.exists():
            result = json.loads(record.read_text())
        else:
            # Mark before evaluation: an interrupted test is not silently rerun.
            marker = output/(key+'_test_started.json')
            if marker.exists():
                raise ValueError('Prior holdout evaluation interrupted; inspect its artifacts before continuing')
            write_json(marker, {'started_at': now(), 'selection_sha256': sha256(selection_path)})
            result = evaluate(Path(chosen['checkpoint']), ROOT/cfg['jobs'][job_id]['dataset'], cfg['jobs'][job_id]['names'],
                              task, chosen['imgsz'], 'test', output/(key+'_test'),
                              cfg['jobs'][job_id]['expected']['test'][0], device,
                              frozen_threshold=chosen['validation_f1_threshold_candidate'])
            result.pop('validation_f1_threshold_candidate', None)  # Never select thresholds from test.
            result['frozen_validation_threshold'] = chosen['validation_f1_threshold_candidate']
            write_json(record, result)
        tests[key] = result
    report = {'completed_at': now(), 'public_models_trained_and_evaluated': True,
              'selection_sha256': sha256(selection_path), 'public_tests': tests,
              'selected_checkpoint_bytes': {key: Path(selection[key]['checkpoint']).stat().st_size
                                            for key in ('litter', 'rock_log_context')},
              'full_component_ready': False, 'android_ready': False,
              'remaining': cfg['unavailable_capabilities']}
    write_json(RESULTS/'public_evaluation.json', report)
    return report
