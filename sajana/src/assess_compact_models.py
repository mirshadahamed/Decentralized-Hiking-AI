"""Complete validation and error records for the bounded Component 2 models.

Validation selects settings. Reserved test evaluation requires an explicitly
frozen model/threshold record; test results never select candidates.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path

from .component2_training_data import data_yaml
from .prepare_compact_component2 import configuration, verify_compact
from .train_yolov8 import ROOT, finite_json, now, sha256, write_json

OUTPUT = ROOT / 'runs/component2_quality'
REPORTS = ROOT / 'results/component2_training/quality'


def check_test_identity(selection, task, digest, size, threshold):
    if selection.get('validation_selection_complete') is not True or selection.get('test_used_to_select') is not False:
        raise ValueError('Validation selection must finish before opening the reserved test')
    selected = selection['models'][task]
    if (selected['checkpoint_sha256'] != digest or selected['imgsz'] != size or
            selected['threshold'] != threshold):
        raise ValueError('Test requires the frozen checkpoint, resolution and threshold')


def environment():
    for name, value in {'YOLO_AUTOINSTALL': 'false', 'YOLO_OFFLINE': 'true',
                        'YOLO_CONFIG_DIR': str(ROOT / 'data/raw/ultralytics_settings'),
                        'MPLCONFIGDIR': str(ROOT / 'data/raw/matplotlib'),
                        'PYTORCH_ENABLE_MPS_FALLBACK': '1',
                        'PYTORCH_MPS_HIGH_WATERMARK_RATIO': '1.0',
                        'PYTORCH_MPS_LOW_WATERMARK_RATIO': '0.9'}.items():
        os.environ.setdefault(name, value)


def evaluate(checkpoint, task, size, tag, device='mps', split='val', threshold=None):
    import numpy as np
    import torch
    from ultralytics import YOLO
    from ultralytics.utils import ops
    from ultralytics.utils.metrics import smooth
    from .yolov8_validation import CompleteSegmentationValidator
    from .yolov8_detection_validation import CompleteDetectionValidator

    cfg = configuration(); report = verify_compact(cfg)
    job = cfg[task]; folder = OUTPUT / tag
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = Path(checkpoint)
    if split not in ('val', 'test'):
        raise ValueError('Unknown split')
    if split == 'test':
        frozen = json.loads((REPORTS / 'frozen_selection.json').read_text())
        check_test_identity(frozen, task, sha256(checkpoint), size, threshold)
        marker = folder / 'test_started.json'
        if marker.exists():
            raise ValueError('Test already started; inspect prior artifacts before any repeat')
        write_json(marker, {'started_at': now(), 'selection_sha256': sha256(REPORTS / 'frozen_selection.json')})
    yaml = data_yaml(folder / 'data.yaml', ROOT / cfg['output'] / task, job['names'], val='images/' + split)
    records, captured = [], []
    base = CompleteSegmentationValidator if task == 'litter' else CompleteDetectionValidator

    class Collector(base):
        def _process_batch(self, predictions, batch):
            matched = super()._process_batch(predictions, batch)
            boxes = ops.scale_boxes(batch['imgsz'], predictions['bboxes'].clone(),
                                    batch['ori_shape'], batch['ratio_pad'])
            targets = ops.scale_boxes(batch['imgsz'], batch['bboxes'].clone(),
                                      batch['ori_shape'], batch['ratio_pad'])
            records.append({'image': Path(batch['im_file']).name,
                            'target_classes': batch['cls'].cpu().tolist(),
                            'target_boxes': targets.cpu().tolist(),
                            'predicted_classes': predictions['cls'].cpu().tolist(),
                            'predicted_boxes': boxes.cpu().tolist(),
                            'confidence': predictions['conf'].cpu().tolist(),
                            'matched_box_iou50': matched['tp'][:, 0].tolist(),
                            'matched_mask_iou50': matched.get('tp_m', matched['tp'])[:, 0].tolist()})
            return matched

    def factory(**kwargs):
        instance = Collector(**kwargs); captured.append(instance); return instance

    model = YOLO(str(checkpoint), task=job['task'])
    if model.names != {int(k): v for k, v in job['names'].items()}:
        raise ValueError('Checkpoint class mapping does not match the task')
    metrics = model.val(data=str(yaml), validator=factory, device=device, imgsz=size,
                        batch=2, workers=0, cache=False, plots=False, conf=0.001, iou=0.7,
                        rect=False, project=str(folder), name='metrics', save_dir=str(folder / 'metrics'),
                        verbose=False)
    expected = report['tasks'][task]['splits'][split]['images']
    if captured[0].complete_nms_images != expected or len(records) != expected:
        raise ValueError('Validation skipped images')
    metric = metrics.seg if task == 'litter' else metrics.box
    curve = np.asarray(metric.f1_curve)
    if threshold is None:
        index = int(smooth(curve.mean(0), 0.1).argmax())
        threshold = float(metric.px[index])
    else:
        index = int(np.abs(np.asarray(metric.px) - threshold).argmin())
    per_class = []
    for i, class_id in enumerate(metric.ap_class_index):
        per_class.append({'class_id': int(class_id), 'class_name': model.names[int(class_id)],
                          'labelled_images': int(metrics.nt_per_image[class_id]),
                          'labelled_regions': int(metrics.nt_per_class[class_id]),
                          'AP50': float(metric.ap50[i]), 'AP50_95': float(metric.ap[i]),
                          'precision_at_threshold': float(metric.p_curve[i, index]),
                          'recall_at_threshold': float(metric.r_curve[i, index]),
                          'f1_at_threshold': float(curve[i, index])})
    result = {'checked_at': now(), 'tag': tag, 'task': task, 'checkpoint': str(checkpoint),
              'checkpoint_sha256': sha256(checkpoint), 'imgsz': size, 'split': split,
              'images': expected, 'configuration_sha256': report['configuration_sha256'],
              'dataset_inventory_sha256': report['inventory_sha256'],
              'metrics': finite_json(metrics.results_dict), 'threshold': threshold,
              'threshold_source': 'frozen validation choice' if split == 'test' else 'validation F1 curve',
              'per_class': per_class, 'AP50': float(metric.map50), 'AP50_95': float(metric.map),
              'mean_precision_at_threshold': float(np.asarray(metric.p_curve)[:, index].mean()),
              'mean_recall_at_threshold': float(np.asarray(metric.r_curve)[:, index].mean()),
              'mean_f1_at_threshold': float(curve[:, index].mean()),
              'metric_note': 'Class-averaged object/mask metrics, not photo classification accuracy; fixed threshold curve values use standard AP matching.',
              'native_speed_ms_per_image': finite_json(metrics.speed),
              'phone_benchmark': False, 'full_component_ready': False}
    write_json(folder / 'predictions.json', records)
    write_json(REPORTS / (tag + '.json'), result)
    print(json.dumps(result, indent=2), flush=True)
    captured.clear(); del model, metrics; gc.collect()
    if device == 'mps':
        torch.mps.empty_cache()
    return result


def baseline(device):
    l1 = json.loads((ROOT / 'results/yolov8_training/status.json').read_text())
    o1 = json.loads((ROOT / 'runs/component2_compact_2000/O1/status.json').read_text())
    for task, checkpoint in [('obstacle', o1['best_checkpoint']), ('litter', l1['best_checkpoint'])]:
        for size in (416, 640):
            tag = f'baseline_{task}_{size}'
            path = REPORTS / (tag + '.json')
            if path.exists():
                print('Existing completed validation:', tag, flush=True)
                continue
            evaluate(checkpoint, task, size, tag, device)


if __name__ == '__main__':
    environment()
    import fcntl
    import torch
    torch.set_num_threads(2)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', default='mps')
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--task', choices=['litter', 'obstacle'])
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--tag')
    parser.add_argument('--split', choices=['val', 'test'], default='val')
    parser.add_argument('--threshold', type=float)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    lock_path = OUTPUT / '.cpu_evaluation.lock' if args.device == 'cpu' else ROOT / 'runs/yolov8_litter/.training.lock'
    with lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.checkpoint:
            if not args.task or not args.tag:
                parser.error('Single evaluation requires --task and --tag')
            evaluate(args.checkpoint, args.task, args.imgsz, args.tag, args.device, args.split, args.threshold)
        else:
            baseline(args.device)
