"""Derive YOLO rock/log region boxes from verified WildScenes semantic labels.

Connected semantic regions are not physical object instances or obstruction labels.
This separate detection task never treats missing litter/path labels as negatives.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from .download_wildscenes import RAW, split_records
from .preprocess_mju_waste import ROOT, write_json

SOURCE = ROOT / 'data/processed/wildscenes_terrain_semantic'
DATASET = ROOT / 'data/processed/wildscenes_rock_log_detection'
RESULTS = ROOT / 'results/obstacle_context'
SOURCE_IDS = {14: 'rock_region', 15: 'log_region'}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def region_boxes(mask):
    import cv2
    cv2.setNumThreads(1)
    mask = np.asarray(mask)
    if mask.ndim != 2 or np.any(mask > 18) or np.any(mask == 0):
        raise ValueError('Region export requires fully labelled native IDs 1–18; void is not background')
    height, width = mask.shape
    boxes = {}; components = Counter()
    for class_id, source_id in enumerate(SOURCE_IDS):
        count, _, stats, _ = cv2.connectedComponentsWithStats((mask == source_id).astype(np.uint8), connectivity=8)
        for x, y, w, h, area in stats[1:count]:
            # Keep even tiny positive components: silently dropping them would
            # incorrectly supervise their pixels as background in ordinary YOLO.
            key = (class_id, int(x), int(y), int(w), int(h))
            boxes[key] = (class_id, (x + w/2) / width, (y + h/2) / height, w/width, h/height)
            components[SOURCE_IDS[source_id]] += 1
    return sorted(boxes.values()), dict(components)


def write_manifest(path, rows):
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def build(source=SOURCE, output=DATASET, results=RESULTS):
    source, output, results = Path(source), Path(output), Path(results)
    if source.resolve() == output.resolve():
        raise ValueError('Derived export must not overwrite the source dataset')
    certificate_path = ROOT / 'results/wildscenes_preprocessing/local_readiness.json'
    certificate = json.loads(certificate_path.read_text())
    mapping = json.loads((source/'class_mapping.json').read_text())['source_id_mapping']
    if not (certificate.get('passed') and certificate.get('training_ready') and
            certificate.get('complete_author_split_coverage')):
        raise ValueError('Full verified WildScenes source is required')
    if any(mapping.get(str(key)) != name.removesuffix('_region') for key, name in SOURCE_IDS.items()):
        raise ValueError('Source class IDs changed')
    author = split_records(RAW/'official_metadata')
    results.mkdir(parents=True, exist_ok=True); (output/'manifests').mkdir(parents=True, exist_ok=True)
    report = {'source': 'WildScenes2d opt2d', 'source_certificate_sha256': digest(certificate_path),
              'task': 'detect', 'names': {'0': 'rock_region', '1': 'log_region'},
              'source_ids': {str(k):v for k,v in SOURCE_IDS.items()},
              'licence': certificate['licence'], 'source_repository': certificate['repository'],
              'source_revision': certificate['source_revision'],
              'box_policy': '8-connected native semantic-region bounding boxes; keep all positive pixels/components; deduplicate identical boxes only',
              'physical_instance_labels': False, 'obstruction_labels': False,
              'litter_labels': False, 'trail_corridor_labels': False,
              'alternative_route_labels': False, 'training_ready': False,
              'obstruction_training_ready': False, 'app_ready': False, 'splits': {}, 'issues': []}
    write_json(output/'readiness.json',report);write_json(results/'readiness.json',report)
    seen = {}; review_rows = []
    for split in ('train', 'val', 'test'):
        rows = list(csv.DictReader((source/'manifests'/f'{split}.csv').open()))
        expected = {row['id']:row for row in author[split]}
        if len(rows) != len(expected) or {r['id'] for r in rows} != set(expected):
            raise ValueError('Source membership differs from author split: ' + split)
        images, labels = output/'images'/split, output/'labels'/split
        images.mkdir(parents=True, exist_ok=True); labels.mkdir(parents=True, exist_ok=True)
        expected_images = {r['flat_file_name'] for r in rows}
        expected_labels = {Path(r['flat_file_name']).with_suffix('.txt').name for r in rows}
        if ({p.name for p in images.iterdir()} - expected_images or
                {p.name for p in labels.iterdir()} - expected_labels):
            raise ValueError('Unexpected stale export files in ' + split)
        prepared = []; counts = Counter(); box_counts = Counter()
        for index, row in enumerate(rows, 1):
            if any(row[k] != expected[row['id']][k] for k in ('sequence', 'split', 'flat_file_name', 'im_path', 'label_path')):
                raise ValueError('Source identity/split mismatch: ' + row['id'])
            name = row['flat_file_name']
            if Path(name).name != name:
                raise ValueError('Invalid flat filename')
            photo, mask_path = source/'images'/split/name, source/'masks'/split/name
            with Image.open(mask_path) as im:
                if im.mode != 'L' or im.size != (int(row['width']), int(row['height'])):
                    raise ValueError('Source mask geometry/mode mismatch: ' + name)
                native = np.asarray(im).copy()
            if hashlib.sha256(native.tobytes()).hexdigest() != row['mask_pixel_sha256']:
                raise ValueError('Source mask changed: ' + name)
            if digest(photo) != row['source_image_sha256']:
                raise ValueError('Source photo changed: ' + name)
            image_hash = row['image_pixel_sha256']
            if image_hash in seen and seen[image_hash] != split:
                raise ValueError('Cross-split source image duplicate')
            seen[image_hash] = split
            boxes, component_counts = region_boxes(native)
            target = images/name
            if target.exists():
                if not os.path.samefile(photo, target) and digest(target) != row['source_image_sha256']:
                    raise ValueError('Existing export image changed: ' + name)
            else:
                try: os.link(photo, target)
                except OSError: shutil.copy2(photo, target)
            label = labels/Path(name).with_suffix('.txt')
            text = ''.join(str(int(b[0])) + ' ' + ' '.join(f'{v:.12f}' for v in b[1:]) + '\n' for b in boxes)
            label.write_text(text)
            decoded = [[float(v) for v in line.split()] for line in label.read_text().splitlines()]
            if len(decoded) != len(boxes) or any(not np.allclose(a,b,rtol=0,atol=1e-11) for a,b in zip(decoded,boxes)):
                raise ValueError('Saved region boxes differ from extracted geometry')
            counts.update(SOURCE_IDS[source_id] for source_id in SOURCE_IDS if np.any(native == source_id))
            for box in boxes: box_counts[SOURCE_IDS[list(SOURCE_IDS)[int(box[0])]]] += 1
            record = {'source_id': row['id'], 'sequence': row['sequence'], 'split': split,
                      'flat_file_name': name, 'width': row['width'], 'height': row['height'],
                      'source_image_sha256': row['source_image_sha256'],
                      'source_mask_pixel_sha256': row['mask_pixel_sha256'],
                      'label_sha256': digest(label), 'region_boxes': len(boxes),
                      'rock_components': component_counts.get('rock_region',0),
                      'log_components': component_counts.get('log_region',0),
                      'litter_review_state': 'unreviewed', 'obstruction_review_state': 'unreviewed',
                      'corridor_review_state': 'unreviewed'}
            prepared.append(record)
            if split == 'train': review_rows.append(record)
            if index % 250 == 0: print(f'{split}: {index}/{len(rows)} region exports verified', flush=True)
        write_manifest(output/'manifests'/f'{split}.csv', prepared)
        report['splits'][split] = {'images': len(prepared), 'images_with_class': dict(counts),
                                   'region_boxes_by_class': dict(box_counts),
                                   'background_images': sum(r['region_boxes'] == 0 for r in prepared)}
    # A small, sequence-diverse training-only queue helps collect the missing
    # corridor/obstruction review. Absence of rock/log is not a clear-trail label.
    queue = []; selected = set()
    for key in ('rock_components', 'log_components', 'context_absent'):
        candidates = [r for r in review_rows if (r['region_boxes'] == 0 if key == 'context_absent' else r[key] > 0)]
        groups = {}
        for row in candidates: groups.setdefault(row['sequence'], []).append(row)
        for sequence, group in sorted(groups.items()):
            for i in range(min(6,len(group))):
                row = group[round(i*(len(group)-1)/max(1,min(6,len(group))-1))]
                if row['source_id'] not in selected:
                    queue.append(dict(row, sampling_reason=key, review_decision='unreviewed'))
                    selected.add(row['source_id'])
    if queue: write_manifest(output/'review_queue.csv',queue)
    report.update(passed=True, training_ready=True, object_context_training_ready=True,
                  review_queue_images=len(queue), review_queue_split='train',
                  native_semantic_ids_used=[14,15], source_split_membership_preserved=True,
                  numeric_class_ids_shared_with_litter=False,
                  limitations=['Region boxes are derived context supervision, not physical instance counts',
                               'Object presence does not prove a blocked trail or a usable bypass',
                               'Water, vegetation, erosion and roots require their own reviewed task labels',
                               'Author validation contains only three rock images; report weak per-class evidence',
                               'No litter/corridor/passability labels are supplied by this export'])
    write_json(output/'readiness.json',report);write_json(results/'readiness.json',report)
    config = ['path: '+json.dumps(str(output.resolve())), 'train: images/train', 'val: images/val',
              'test: images/test', 'names:', '  0: rock_region', '  1: log_region']
    (output/'data.yaml').write_text('\n'.join(config)+'\n')
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=SOURCE);p.add_argument('--output',type=Path,default=DATASET)
    args=p.parse_args();print(json.dumps(build(args.source,args.output),indent=2))


if __name__ == '__main__': main()
