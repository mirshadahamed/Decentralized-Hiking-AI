"""Prepare pLitterStreet's official four-class COCO boxes as detection data.

Source masks are never fabricated. Any image with an invalid box is excluded as
a whole image, preserving complete targets for all retained images.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from .taco_images import decode_image, save_image

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / 'data/interim/plitter/annotations/4_class_splits'
DEFAULT_OUT = ROOT / 'data/processed/plitter_street_det'
DEFAULT_RAW = ROOT / 'data/raw/plitter/extracted'
SPLITS = ('train', 'val', 'test')
NAMES = ['plastic_litter', 'litter_pile', 'face_mask', 'trash_bin']
FIELDS = ['image_id', 'flat_file_name', 'source_file_name', 'source_image_path', 'source_dataset_id',
          'source_sequence', 'source_metadata_json', 'width', 'height', 'object_count', 'annotation_ids',
          'original_category_ids', 'raw_source_sha256']


def _digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def _reports(out):
    return ROOT / 'results/plitter_preprocessing' if Path(out).resolve() == DEFAULT_OUT.resolve() else Path(out) / 'audit'


def load(source):
    """Validate source structure; retain invalid object evidence for quarantine."""
    all_images, all_annotations, records, source_hashes = {}, set(), {}, {}
    excluded = []
    categories = None
    for split in SPLITS:
        path = Path(source) / f'annotations_{split}.json'
        source_hashes[split] = _digest(path)
        data = json.loads(path.read_text())
        cat = {x['id']: x['name'] for x in data['categories']}
        if set(cat) != {1, 2, 3, 4} or (categories is not None and categories != cat):
            raise ValueError('Expected consistent official pLitter four-class categories')
        categories = cat
        images = {}
        names = set()
        for image in data['images']:
            image_id, name = image['id'], image['file_name']
            if isinstance(image_id, bool) or not isinstance(image_id, int) or image_id < 0:
                raise ValueError('Image IDs must be nonnegative integers')
            if image_id in all_images or name in names:
                raise ValueError(f'Duplicate source image ID/filename: {image_id}/{name}')
            if not isinstance(name, str) or PurePosixPath(name).name != name or '\\' in name or name in ('', '.', '..'):
                raise ValueError(f'Unsafe source image basename: {name}')
            if any(isinstance(image.get(k), bool) or not isinstance(image.get(k), int) or image[k] <= 0 for k in ('width', 'height')):
                raise ValueError(f'Invalid dimensions for image {image_id}')
            images[image_id] = {'image': image, 'annotations': [], 'invalid': []}
            all_images[image_id] = split
            names.add(name)
        for ann in data['annotations']:
            ann_id = ann['id']
            if isinstance(ann_id, bool) or not isinstance(ann_id, int) or ann_id < 0 or ann_id in all_annotations:
                raise ValueError(f'Invalid/duplicate annotation ID: {ann_id}')
            all_annotations.add(ann_id)
            if ann['image_id'] not in images or ann['category_id'] not in cat:
                raise ValueError(f'Unknown image/category in annotation {ann_id}')
            row = images[ann['image_id']]
            image = row['image']
            bbox = ann.get('bbox')
            reason = None
            if not isinstance(bbox, list) or len(bbox) != 4 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in bbox):
                reason = 'Bounding box must contain four finite numeric values'
            elif ann.get('iscrowd', False):
                reason = 'Crowd annotations require explicit review'
            else:
                x, y, width, height = bbox
                if width <= 0 or height <= 0:
                    reason = 'Zero/negative bounding-box area'
                elif x < 0 or y < 0 or x + width > image['width'] or y + height > image['height']:
                    reason = 'Bounding box extends outside source image dimensions; no broad clipping'
            row['annotations'].append(ann)
            if reason:
                row['invalid'].append({'annotation_id': ann_id, 'bbox': bbox, 'reason': reason})
        kept = []
        for row in images.values():
            if row['invalid']:
                excluded.append({'split': split, 'image_id': row['image']['id'], 'file_name': row['image']['file_name'],
                                 'invalid_annotations': row['invalid'], 'excluded_annotations': len(row['annotations']),
                                 'reason': 'Whole image excluded to preserve complete object annotations'})
            else:
                kept.append(row)
        records[split] = kept
    return records, source_hashes, excluded, categories


def _lines(record):
    image = record['image']
    lines = []
    for ann in record['annotations']:
        x, y, width, height = ann['bbox']
        values = ((x + width / 2) / image['width'], (y + height / 2) / image['height'],
                  width / image['width'], height / image['height'])
        lines.append(str(ann['category_id'] - 1) + ' ' + ' '.join(f'{x:.8f}' for x in values))
    return lines


def _filename(image):
    return f"plitter_{image['id']}__{Path(image['file_name']).stem}.jpg"


def preprocess(source=DEFAULT_SOURCE, out=DEFAULT_OUT, report=None):
    source, out = Path(source), Path(out)
    records, hashes, excluded, categories = load(source)
    expected = {split: {_filename(x['image']) for x in entries} for split, entries in records.items()}
    for split in SPLITS:
        for kind, suffix in (('images', '.jpg'), ('labels', '.txt')):
            for path in (out / kind / split).glob('*'):
                if path.is_file() and path.with_suffix('.jpg').name not in expected[split]:
                    raise ValueError(f'Stale output file {path}; use a fresh output directory')
    summary = {}
    for split, entries in records.items():
        for kind in ('images', 'labels', 'manifests'):
            (out / kind / split if kind != 'manifests' else out / kind).mkdir(parents=True, exist_ok=True)
        rows = []
        for record in entries:
            image, anns = record['image'], record['annotations']
            name = _filename(image)
            (out / 'labels' / split / Path(name).with_suffix('.txt')).write_text('\n'.join(_lines(record)) + ('\n' if anns else ''))
            rows.append({'image_id': image['id'], 'flat_file_name': name, 'source_file_name': image['file_name'],
                         'source_image_path': image.get('path', ''), 'source_dataset_id': image.get('dataset_id', ''),
                         'source_sequence': str(PurePosixPath(image.get('path', '')).parent),
                         'source_metadata_json': json.dumps(image.get('metadata', {}), sort_keys=True),
                         'width': image['width'], 'height': image['height'], 'object_count': len(anns),
                         'annotation_ids': '|'.join(str(a['id']) for a in anns),
                         'original_category_ids': '|'.join(str(a['category_id']) for a in anns),
                         'raw_source_sha256': hashes[split]})
        with (out / 'manifests' / f'{split}.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        summary[split] = {'images': len(entries), 'objects': sum(len(r['annotations']) for r in entries)}
    sequences = defaultdict(set)
    for split, entries in records.items():
        for row in entries:
            sequences[str(PurePosixPath(row['image'].get('path', '')).parent)].add(split)
    result = {'dataset': str(out.resolve()), 'source': str(source.resolve()), 'source_sha256': hashes,
              'role': 'auxiliary four-class object detection; no instance segmentation targets',
              'passed': True, 'labels_ready': True, 'training_ready': False, 'splits': summary,
              'source_categories': categories, 'target_names': NAMES, 'category_mapping': {str(i): i - 1 for i in categories},
              'quarantined_images': len(excluded), 'quarantined_annotations': sum(x['excluded_annotations'] for x in excluded),
              'invalid_annotations': sum(len(x['invalid_annotations']) for x in excluded),
              'source_sequences_shared_across_splits': sum(len(splits) > 1 for splits in sequences.values()),
              'independent_sequence_evaluation_supported': False,
              'warnings': ['Official source split membership is retained. Source video/city groups occur across splits; neighboring frames may be correlated.',
                           'Trash bins retain a separate class. Bounding rectangles are not object segmentation masks.',
                           'Source metadata/path fields are preserved. The Mawanella GPS/count sample cannot be paired to these frames without frame identifiers.']}
    _write_json(out / 'conversion_report.json', result)
    _write_json(_reports(out) / 'quarantine.json', {'source_sha256': hashes, 'excluded_images': excluded})
    _write_json(report or _reports(out) / 'labels_readiness.json', result)
    return result


def prepare_images(source=DEFAULT_SOURCE, out=DEFAULT_OUT, raw=DEFAULT_RAW):
    from PIL import Image
    records, _, _, _ = load(source)
    index = defaultdict(list)
    for path in Path(raw).rglob('*'):
        if path.is_file() and path.suffix.lower() in ('.jpg', '.jpeg', '.png'):
            index[path.name].append(path)
    issues, counts = [], Counter()
    for split, entries in records.items():
        for row in entries:
            im = row['image']
            candidates = index[im['file_name']]
            if len(candidates) != 1:
                issues.append({'image_id': im['id'], 'reason': f'Expected one exact source basename, found {len(candidates)}'})
                continue
            source_path = candidates[0]
            target = Path(out) / 'images' / split / _filename(im)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with Image.open(source_path) as image:
                    image.load()
                    if image.mode not in ('RGB', 'RGBA'):
                        raise ValueError(f'Expected color RGB source, found {image.mode}')
                    if image.size != (im['width'], im['height']):
                        raise ValueError(f'Source image dimensions {image.size} differ from annotation {(im["width"], im["height"])}')
                    orientation = image.getexif().get(274, 1)
                    native_jpeg = image.format == 'JPEG' and orientation in (None, 1)
                if native_jpeg:
                    if target.exists():
                        if _digest(target) != _digest(source_path):
                            raise ValueError('Existing target differs from raw image')
                        counts['existing'] += 1
                        continue
                    try:
                        os.link(source_path, target)
                        counts['hardlinked'] += 1
                    except OSError:
                        shutil.copy2(source_path, target)
                        counts['copied'] += 1
                else:
                    image, _ = decode_image(source_path.read_bytes(), im['width'], im['height'])
                    save_image(image, target)
                    counts['normalized'] += 1
            except (OSError, ValueError, SyntaxError) as exc:
                issues.append({'image_id': im['id'], 'reason': str(exc)})
    result = {'passed': not issues, 'counts': dict(counts), 'issues': issues}
    _write_json(_reports(out) / 'image_import_report.json', result)
    return result


def verify(source=DEFAULT_SOURCE, out=DEFAULT_OUT, report=None, labels_only=False):
    from PIL import Image
    records, hashes, excluded, _ = load(source)
    out = Path(out)
    issues, summary, pixel_hashes, duplicates = [], {}, {}, []
    for split, entries in records.items():
        verified, present, object_count = 0, 0, 0
        if not entries:
            issues.append(f'{split}: no retained images after source quarantine')
        expected_images = {_filename(row['image']) for row in entries}
        manifest = out / 'manifests' / f'{split}.csv'
        with manifest.open(newline='') as stream:
            manifest_rows = list(csv.DictReader(stream))
        expected_ids = {str(row['image']['id']) for row in entries}
        if len(manifest_rows) != len(entries) or {row.get('image_id') for row in manifest_rows} != expected_ids:
            issues.append(f'{split}: manifest does not cover retained source images exactly')
        manifest_by_id = {row['image_id']: row for row in manifest_rows}
        for row in entries:
            im = row['image']
            name = _filename(im)
            manifest_row = manifest_by_id.get(str(im['id']), {})
            if any(str(manifest_row.get(key, '')) != str(value) for key, value in
                   [('flat_file_name', name), ('source_file_name', im['file_name']),
                    ('width', im['width']), ('height', im['height']), ('object_count', len(row['annotations'])),
                    ('annotation_ids', '|'.join(str(a['id']) for a in row['annotations'])), ('raw_source_sha256', hashes[split])]):
                issues.append(f'{split}/{name}: manifest metadata differs from source')
            expected = _lines(row)
            label = out / 'labels' / split / Path(name).with_suffix('.txt')
            try:
                actual = label.read_text().splitlines()
                if actual != expected:
                    raise ValueError('Detection rows differ from source category/bounding boxes')
                for line in actual:
                    values = line.split()
                    if len(values) != 5 or not 0 <= int(values[0]) <= 3 or not all(math.isfinite(float(x)) and 0 <= float(x) <= 1 for x in values[1:]):
                        raise ValueError('Expected one class and four normalized detection coordinates')
                object_count += len(actual)
            except (OSError, ValueError) as exc:
                issues.append(f'{split}/{name}: invalid labels: {exc}')
            image_path = out / 'images' / split / name
            if image_path.is_file():
                present += 1
            if labels_only:
                continue
            try:
                with Image.open(image_path) as image:
                    image.verify()
                with Image.open(image_path) as image:
                    image.load()
                    if image.size != (im['width'], im['height']) or image.getexif().get(274, 1) not in (None, 1):
                        raise ValueError('Source dimensions/normalized orientation mismatch')
                    rgb = image.convert('RGB')
                    digest = hashlib.sha256(f'{rgb.width}x{rgb.height}:'.encode() + rgb.tobytes()).hexdigest()
                if digest in pixel_hashes:
                    previous = pixel_hashes[digest]
                    duplicates.append({'image': f'{split}/{name}', 'previous': previous})
                    if previous.split('/')[0] != split:
                        issues.append(f'{split}/{name}: identical decoded pixels cross official splits: {previous}')
                else:
                    pixel_hashes[digest] = f'{split}/{name}'
                verified += 1
                if verified % 500 == 0:
                    print(f'pLitter {split}: {verified}/{len(entries)} decoded', flush=True)
            except (OSError, ValueError, SyntaxError) as exc:
                issues.append(f'{split}/{name}: image verification: {exc}')
        for kind, expected_names in [('images', expected_images), ('labels', {Path(name).with_suffix('.txt').name for name in expected_images})]:
            actual = {p.name for p in (out / kind / split).glob('*') if p.is_file() and not p.name.startswith('.')}
            if actual - expected_names:
                issues.append(f'{split}: unexpected {kind} files: {sorted(actual - expected_names)[:3]}')
        summary[split] = {'images': len(entries), 'objects': object_count, 'present_images': present,
                          'missing_images': len(entries) - present, 'verified_images': verified}
    result = {'dataset': str(out.resolve()), 'source': str(Path(source).resolve()), 'source_sha256': hashes,
              'passed': not issues, 'labels_only': labels_only, 'training_ready': not issues and not labels_only,
              'task': 'detect', 'target_names': NAMES, 'splits': summary, 'quarantined_images': len(excluded),
              'duplicate_images': duplicates, 'issues': issues, 'independent_sequence_evaluation_supported': False,
              'role': 'four-class detection auxiliary; official video frame splits may be correlated; no segmentation masks'}
    yaml = out / 'data.yaml'
    if result['training_ready']:
        yaml.write_text(f'path: {json.dumps(str(out.resolve()))}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n' +
                        ''.join(f'  {i}: {name}\n' for i, name in enumerate(NAMES)))
    elif yaml.exists():
        yaml.rename(out / 'data.yaml.invalid')
    _write_json(report or _reports(out) / 'local_readiness.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--raw', type=Path, default=DEFAULT_RAW)
    parser.add_argument('--prepare-images', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--labels-only', action='store_true')
    args = parser.parse_args()
    converted = preprocess(args.source, args.out)
    print(json.dumps(converted, indent=2))
    if args.prepare_images and not prepare_images(args.source, args.out, args.raw)['passed']:
        raise SystemExit(1)
    if args.verify:
        checked = verify(args.source, args.out, labels_only=args.labels_only)
        print(json.dumps({key: checked[key] for key in ('passed', 'training_ready', 'splits')}, indent=2))
        if not checked['passed']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
