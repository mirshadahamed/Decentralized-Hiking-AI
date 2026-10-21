"""Build a small, source-audited YOLO detection set from GOOSE and Mobima.

The profile is intentionally separate from the frozen cycle-one dataset. GOOSE
semantic regions and Mobima object labels retain distinct meanings; neither is
presented as a verified clear/blocked trail decision.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import csv
import hashlib
import io
import json
import random
import tarfile
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from .selective_zip import fetch_indexed_member
from ..train_yolov8 import ROOT, now, sha256, write_json

BASE = ROOT / 'data/raw/component2_cycle2_sources'
OUT = ROOT / 'data/processed/component2_cycle2_trail_v4'
GOOSE_LABELS = BASE / 'goose_labels_48_with_ex.json'
MOBIMA_TAR = BASE / 'MobimaSkidRoads.tar'
NAMES = ['tree', 'stump', 'stem', 'obstacle_region', 'non_passable_obstacle', 'debris', 'rock']
MOBIMA_CLASSES = {0: 2, 1: 0, 2: 1, 3: 4}
GOOSE_CLASSES = {4: 3, 28: 0, 29: 5, 40: 6}  # class 62 tree-root has too few examples


def sample_goose(rows, split, count, seed, allowed_sequences=None):
    """Deterministic sequence-balanced sample, prioritizing sparse target classes."""
    candidates = [r for r in rows if r['source_split'] == split and
                  (allowed_sequences is None or r['sequence'] in allowed_sequences) and
                  any(int(r['pixels'].get(str(cid), 0)) for cid in GOOSE_CLASSES)]
    rng = random.Random(seed)
    rng.shuffle(candidates)
    # Greedy rarity score prevents an easy, repetitive single-class sample.
    remaining = list(candidates)
    chosen = []
    seq_counts = collections.Counter()
    class_counts = collections.Counter()
    while remaining and len(chosen) < count:
        def score(row):
            labels = [GOOSE_CLASSES[cid] for cid in GOOSE_CLASSES
                      if int(row['pixels'].get(str(cid), 0)) > 0]
            return sum(1 / (1 + class_counts[c]) for c in labels) - 0.15 * seq_counts[row['sequence']]
        best = max(remaining, key=score)
        remaining.remove(best)
        chosen.append(best)
        seq_counts[best['sequence']] += 1
        for cid, target in GOOSE_CLASSES.items():
            if int(best['pixels'].get(str(cid), 0)):
                class_counts[target] += 1
    return chosen


def get_yolo_boxes(mask):
    """Convert each connected semantic region to a normalized YOLO box."""
    h, w = mask.shape
    result = []
    for source_id, target_id in GOOSE_CLASSES.items():
        binary = (mask == source_id).astype(np.uint8)
        n, _, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
        for x, y, bw, bh, area in stats[1:]:
            if area < 12:
                continue
            xc, yc = (x + bw / 2) / w, (y + bh / 2) / h
            result.append((target_id, xc, yc, bw / w, bh / h))
    return result


def write_photo(body, out_image, max_edge=640):
    with Image.open(io.BytesIO(body)) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        if max(im.size) > max_edge:
            ratio = max_edge / max(im.size)
            im = im.resize((round(im.width * ratio), round(im.height * ratio)), Image.Resampling.LANCZOS)
        im.save(out_image, 'JPEG', quality=88, optimize=True)


def image_entry(index, label_member):
    prefix = label_member.rsplit('_labelids.png', 1)[0]
    if 'gooseEx_2d_' in label_member:
        # *_color.png under labels/ is a colorized segmentation mask, not a
        # camera photograph. Pair the semantic label to the synchronized RGB.
        image_prefix = prefix.replace('/labels/val/', '/images/val/')
        matches = [e for e in index['entries'] if e['name'] in
                   (image_prefix + '_front.png', image_prefix + '_camera_left.png',
                    image_prefix + '_realsense.png')]
        if len(matches) != 1:
            raise ValueError(f'Matching RGB frame absent for GOOSE extension mask: {label_member}')
        return matches[0]
    split = 'train' if '/train/' in label_member else 'val'
    # GOOSE 2D RGB observations are the windshield-visible frames.
    expected = f'images/{split}/' + prefix.split(f'labels/{split}/', 1)[1] + '_windshield_vis.png'
    found = next((e for e in index['entries'] if e['name'] == expected), None)
    if not found:
        raise ValueError(f'Matching RGB frame absent for semantic mask: {label_member}')
    return found


def emit_item(split, stem, image_bytes, boxes, source, source_member):
    name = stem + '.jpg'
    image_path = OUT / 'images' / split / name
    label_path = OUT / 'labels' / split / (stem + '.txt')
    image_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    write_photo(image_bytes, image_path)
    label_path.write_text(''.join(f'{c} {x:.7f} {y:.7f} {w:.7f} {h:.7f}\n'
                                  for c, x, y, w, h in boxes))
    return {'split': split, 'image': image_path.relative_to(OUT).as_posix(),
            'label': label_path.relative_to(OUT).as_posix(), 'source': source,
            'source_member': source_member, 'sha256': sha256(image_path),
            'object_counts': dict(collections.Counter(str(b[0]) for b in boxes))}


def build(goose_train=157, goose_test=51):
    if (OUT / 'manifest.csv').exists():
        raise FileExistsError(f'Refusing to overwrite a completed processed set: {OUT}')
    rows = json.loads(GOOSE_LABELS.read_text())
    mobima_metadata = {}
    mobima_annotations = {}
    with tarfile.open(MOBIMA_TAR) as outer:
        inner_member = outer.getmember('10.35097-1750/data/dataset/MobimaSkidRoads.zip')
        with zipfile.ZipFile(outer.extractfile(inner_member)) as archive:
            for split in ('train', 'val'):
                data = json.loads(archive.read(f'MobimaSkidRoads/{split}.json'))
                for image in data['images']:
                    mobima_metadata[(split, image['id'])] = image
                by_image = collections.defaultdict(list)
                for ann in data['annotations']:
                    target = MOBIMA_CLASSES.get(ann['category_id'])
                    if target is None:
                        continue
                    x, y, w, h = map(float, ann['bbox'])
                    iw, ih = next(x['width'] for x in data['images'] if x['id'] == ann['image_id']), next(x['height'] for x in data['images'] if x['id'] == ann['image_id'])
                    # Source boxes can extend one pixel past image boundaries.
                    x0, y0 = max(0., x), max(0., y)
                    x1, y1 = min(iw, x + w), min(ih, y + h)
                    if x1 <= x0 or y1 <= y0:
                        continue
                    by_image[(split, ann['image_id'])].append((target, (x0+x1)/(2*iw),
                        (y0+y1)/(2*ih), (x1-x0)/iw, (y1-y0)/ih))
                mobima_annotations.update(by_image)
            manifest = []
            for split, image_id in sorted(mobima_metadata):
                image = mobima_metadata[(split, image_id)]
                member = f"MobimaSkidRoads/{image['file_name']}"
                # Keep the publisher's source split: train and val stay separated.
                out_split = split
                body = archive.read(member)
                ih, iw = image['height'], image['width']
                boxes = mobima_annotations.get((split, image_id), [])
                if not boxes:
                    continue
                stem = 'mobima_' + Path(image['file_name']).stem
                manifest.append(emit_item(out_split, stem, body, boxes, 'MobimaSkidRoads', member))

    # The original GOOSE train and val partitions share recording sequences.
    # Hold out whole train sequences for validation to avoid adjacent-frame
    # leakage. The extension validation set is a separate final test domain.
    val_sequences = {'2023-02-13_touareg_neuperlach', '2023-02-23_campus_roads',
                     '2023-01-20_aying_mangfall_2'}
    train_sequences = {r['sequence'] for r in rows if r['source_split'] == 'train'} - val_sequences
    goose_sets = {'train': sample_goose(rows, 'train', goose_train, 42, train_sequences),
                  'val': sample_goose(rows, 'train', 59, 84, val_sequences),
                  'test': sample_goose(rows, 'ex_val', goose_test, 96)}
    goose_jobs = []
    for source_split, output_split in [('train', 'train'), ('train', 'val'), ('ex_val', 'test')]:
        index = json.loads((BASE / f'goose_{source_split}_index.json').read_text())
        chosen = goose_sets[output_split]
        for row in chosen:
            goose_jobs.append((output_split, index, row))

    def process_goose(job):
        output_split, index, row = job
        label_body = (BASE / 'goose_selected' / row['member']).read_bytes()
        with Image.open(io.BytesIO(label_body)) as im:
            mask = np.asarray(im, dtype=np.uint8)
        boxes = get_yolo_boxes(mask)
        rgb = image_entry(index, row['member'])
        digest = hashlib.sha256(row['member'].encode()).hexdigest()[:12]
        stem = 'goose_' + digest
        image_path = OUT / 'images' / output_split / (stem + '.jpg')
        label_path = OUT / 'labels' / output_split / (stem + '.txt')
        if image_path.exists() and label_path.exists():
            return {'split': output_split, 'image': image_path.relative_to(OUT).as_posix(),
                    'label': label_path.relative_to(OUT).as_posix(), 'source': 'GOOSE',
                    'source_member': rgb['name'], 'sha256': sha256(image_path),
                    'object_counts': dict(collections.Counter(str(b[0]) for b in boxes))}
        if output_split != 'test':
            previous = ROOT / 'data/processed/component2_cycle2_trail_v3'
            previous_image = previous / 'images' / output_split / (stem + '.jpg')
            previous_label = previous / 'labels' / output_split / (stem + '.txt')
            if previous_image.is_file() and previous_label.is_file():
                image_path.parent.mkdir(parents=True, exist_ok=True)
                label_path.parent.mkdir(parents=True, exist_ok=True)
                image_path.write_bytes(previous_image.read_bytes())
                label_path.write_bytes(previous_label.read_bytes())
                return {'split': output_split, 'image': image_path.relative_to(OUT).as_posix(),
                        'label': label_path.relative_to(OUT).as_posix(), 'source': 'GOOSE',
                        'source_member': rgb['name'], 'sha256': sha256(image_path),
                        'object_counts': dict(collections.Counter(str(b[0]) for b in boxes))}
        img_body = fetch_indexed_member(index, rgb)
        return emit_item(output_split, stem, img_body, boxes, 'GOOSE', rgb['name'])

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for i, row in enumerate(pool.map(process_goose, goose_jobs), start=1):
            manifest.append(row)
            if i % 25 == 0:
                print(f'Prepared {i}/{len(goose_jobs)} GOOSE records', flush=True)

    # Manifests, class counts and exact 2,000-photo budget (1,499 existing
    # garbage + 501 supplemental trail photos) are recorded for reproducibility.
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'manifest.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['split','image','label','source','source_member','sha256','object_counts'])
        writer.writeheader()
        for row in manifest:
            row = dict(row); row['object_counts'] = json.dumps(row['object_counts'], sort_keys=True)
            writer.writerow(row)
    (OUT / 'data.yaml').write_text('path: ' + json.dumps(str(OUT.resolve())) + '\ntrain: images/train\nval: images/val\nnames:\n' +
        ''.join(f'  {i}: {name}\n' for i, name in enumerate(NAMES)))
    by_split = collections.defaultdict(collections.Counter)
    for row in manifest:
        by_split[row['split']].update(row['object_counts'])
    report = {'created_at': now(), 'dataset': str(OUT), 'photo_count': len(manifest),
              'profile_total_with_existing_litter': 1499 + len(manifest),
              'photos_by_split': dict(collections.Counter(r['split'] for r in manifest)),
              'sources_by_split': {s: dict(collections.Counter(r['source'] for r in manifest if r['split']==s))
                                   for s in ('train','val','test')},
              'objects_by_split_and_class': {s: dict(by_split[s]) for s in ('train','val','test')},
              'classes': dict(enumerate(NAMES)), 'goose_root_excluded_positive_photos': 8,
              'goose_root_class_trained': False, 'route_blockage_ground_truth': False,
              'garbage_dataset_included': False,
              'note': 'Mobima obstacle, GOOSE semantic obstacle, and object classes retain separate labels. Does not predict passability.'}
    write_json(ROOT / 'results/component2_cycle2/trail_preprocessing.json', report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--goose-train', type=int, default=157)
    parser.add_argument('--goose-test', type=int, default=51)
    args = parser.parse_args()
    build(args.goose_train, args.goose_test)
