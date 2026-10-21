"""Photo-level object-presence checks, kept separate from box/mask accuracy."""
from __future__ import annotations


def presence_counts(records, class_id, threshold):
    counts = dict(tp=0, fp=0, fn=0, tn=0)
    for row in records:
        target = class_id in row['target_classes']
        detected = any(int(c) == class_id and score >= threshold
                       for c, score in zip(row['predicted_classes'], row['confidence']))
        counts['tp' if target and detected else 'fn' if target else 'fp' if detected else 'tn'] += 1
    positives, negatives = counts['tp'] + counts['fn'], counts['fp'] + counts['tn']
    predicted = counts['tp'] + counts['fp']
    precision = counts['tp'] / predicted if predicted else 0.0
    recall = counts['tp'] / positives if positives else 0.0
    return dict(counts, threshold=float(threshold), positive_images=positives, negative_images=negatives,
                observed_precision=precision, recall_on_positive_images=recall,
                f1=2 * precision * recall / (precision + recall) if precision + recall else 0.0,
                false_positive_rate=counts['fp'] / negatives if negatives else None,
                negative_image_evidence_available=bool(negatives),
                general_photo_accuracy_established=False)


def calibrate_presence(records, names, fallback_threshold):
    choices = {}
    for class_id, name in names.items():
        class_id = int(class_id)
        initial = presence_counts(records, class_id, fallback_threshold)
        if not initial['positive_images'] or not initial['negative_images']:
            result = initial
            result['threshold_source'] = 'object-validation fallback; photo threshold cannot be calibrated with one label only'
        else:
            candidates = [presence_counts(records, class_id, i / 100) for i in range(1, 96)]
            result = max(candidates, key=lambda r: (r['f1'], r['observed_precision'], r['threshold']))
            result['threshold_source'] = 'validation photo-presence F1; separate from localization quality'
        choices[name] = result
    return choices
