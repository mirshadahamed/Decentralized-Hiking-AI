"""Run one photo through the frozen development models and emit the app contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .assess_compact_models import environment
from .component2_photo_contract import photo_assessment
from .train_yolov8 import ROOT, now, sha256, write_json


def predict(image_path, manifest_path):
    from PIL import Image, ImageOps
    import numpy as np
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(2)
    manifest = json.loads(Path(manifest_path).read_text())
    with Image.open(image_path) as original:
        # Same orientation convention for decoded photos and overlay coordinates.
        image = np.asarray(ImageOps.exif_transpose(original).convert('RGB'))[:, :, ::-1].copy()
    detections = []
    for task, spec in manifest['models'].items():
        path = Path(spec['checkpoint'])
        if sha256(path) != spec['checkpoint_sha256']:
            raise ValueError('Frozen model artifact changed: ' + task)
        model = YOLO(str(path), task='segment' if task == 'litter' else 'detect')
        if model.names != {int(k): v for k, v in spec['names'].items()}:
            raise ValueError('Class mapping changed')
        thresholds = spec.get('class_thresholds', {name: spec['threshold'] for name in model.names.values()})
        threshold = min(float(v) for v in thresholds.values())
        result = model.predict(source=image, device='cpu', imgsz=spec['imgsz'], rect=False,
                               conf=threshold, iou=0.7, max_det=300, verbose=False)[0]
        for i, box in enumerate(result.boxes):
            label = model.names[int(box.cls.item())]
            if float(box.conf.item()) < float(thresholds[label]):
                continue
            normalized = box.xyxyn[0].clamp(0, 1).tolist()
            if normalized[0] >= normalized[2] or normalized[1] >= normalized[3]:
                continue
            row = {'task': task, 'label': label,
                   'confidence': float(box.conf.item()),
                   'box_xyxy_normalized': normalized}
            if result.masks is not None:
                row['mask_polygon_normalized'] = result.masks.xyn[i].tolist()
            detections.append(row)
        del model
    answer = photo_assessment(detections, model_quality_accepted=manifest.get('quality_accepted_for_app', False))
    answer.update(checked_at=now(), input_image_sha256=sha256(image_path),
                  manifest_sha256=sha256(manifest_path), image_width=image.shape[1], image_height=image.shape[0])
    return answer


if __name__ == '__main__':
    environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'configs/component2_development_models.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = predict(args.image, args.manifest)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))
