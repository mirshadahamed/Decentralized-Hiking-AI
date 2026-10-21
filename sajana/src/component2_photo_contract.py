"""Photo-result contract shared by model verification and app preparation."""
from __future__ import annotations

import math

LABELS = {'litter': {'litter'}, 'obstacle': {'rock_region', 'log_region'}}


def photo_assessment(detections, *, model_quality_accepted=False):
    checked = []
    for detection in detections:
        task, label = detection['task'], detection['label']
        if task not in LABELS or label not in LABELS[task]:
            raise ValueError('Label does not belong to the declared model task')
        score = float(detection['confidence'])
        box = [float(v) for v in detection['box_xyxy_normalized']]
        if (not math.isfinite(score) or not 0 <= score <= 1 or len(box) != 4 or
                any(not math.isfinite(v) or not 0 <= v <= 1 for v in box) or
                box[0] >= box[2] or box[1] >= box[3]):
            raise ValueError('Invalid confidence or normalized box')
        checked.append(dict(detection, confidence=score, box_xyxy_normalized=box))
    return {
        'schema_version': 1,
        'detections': checked,
        'garbage_observation': 'detected' if any(d['task'] == 'litter' for d in checked) else 'not_detected',
        'rock_log_observation': 'detected' if any(d['task'] == 'obstacle' for d in checked) else 'not_detected',
        'trail_condition': 'not_assessed',
        'route_advisory': 'requires_map_and_reviewed_obstruction',
        'model_quality_accepted': bool(model_quality_accepted),
        'use': 'development',
    }


def quality_checks(models, requirements):
    failures = []
    if set(models) != set(LABELS):
        failures.append('Missing required model tasks')
    for task, model in models.items():
        if task not in LABELS or {r['class_name'] for r in model['per_class']} != LABELS[task]:
            failures.append(task + ': missing or unexpected class evidence')
        for row in model['per_class']:
            label = row['class_name']
            for key, target in [('precision_at_threshold', requirements['per_class_precision']),
                                ('recall_at_threshold', requirements['per_class_recall'])]:
                if not math.isfinite(row[key]) or row[key] < target:
                    failures.append(f'{task}/{label}: {key} below {target}')
            if row['labelled_images'] < requirements['minimum_validation_images_per_class']:
                failures.append(f'{task}/{label}: insufficient validation image coverage')
    return {'public_validation_quality_passed': not failures, 'failures': failures,
            'local_trail_evaluation_complete': False, 'physical_phone_benchmark_complete': False,
            'full_component_ready': False}
