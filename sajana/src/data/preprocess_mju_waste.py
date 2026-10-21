"""Source-checked MJU-Waste RGB polygons, manifests and readiness auditing.

The supplied flat polygons are authoritative. COCO bboxes are retained in the
source but are not used to scale masks or derive YOLO labels.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / 'data/interim/mju_waste'
DEFAULT_DATASET = ROOT / 'data/processed/mju_waste_litter_seg'
SPLITS = ('train', 'val', 'test')
FIELDS = ['image_id', 'file_name', 'flat_file_name', 'width', 'height', 'annotation_count',
          'object_count', 'annotation_ids', 'license']
BOUNDARY_TOLERANCE = 2.0  # Two supplied annotations contain x=-1.07; recorded explicitly.


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def normalized_polygon(annotation, image):
    values = annotation.get('segmentation')
    if not isinstance(values, list) or len(values) < 6 or len(values) % 2:
        raise ValueError(f"Annotation {annotation.get('id')}: expected flat polygon coordinate pairs")
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in values):
        raise ValueError('Polygon coordinates must be finite numbers')
    width, height = image['width'], image['height']
    points, fixes = [], []
    for index, (x, y) in enumerate(zip(values[::2], values[1::2])):
        if x < -BOUNDARY_TOLERANCE or x > width + BOUNDARY_TOLERANCE or y < -BOUNDARY_TOLERANCE or y > height + BOUNDARY_TOLERANCE:
            raise ValueError(f"Annotation {annotation['id']}: polygon outside image beyond 2px tolerance")
        cx, cy = min(width, max(0, x)), min(height, max(0, y))
        if (cx, cy) != (x, y):
            fixes.append({'vertex': index, 'original': [x, y], 'clipped': [cx, cy]})
        points.append((cx / width, cy / height))
    area = sum(x * ny - nx * y for (x, y), (nx, ny) in zip(points, points[1:] + points[:1]))
    if len(set(points)) < 3 or abs(area) <= 1e-12:
        raise ValueError('Polygon is degenerate after normalization')
    return points, fixes


def load_sources(source):
    records, hashes, seen_names, seen_images, seen_annotations = {}, {}, set(), set(), set()
    for split in SPLITS:
        path = source / f'{split}.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        if not data.get('images') or not data.get('categories'):
            raise ValueError(f'{split}: source images/categories must not be empty')
        hashes[split] = sha256(path)
        categories = {category['id'] for category in data['categories']}
        images, grouped = {}, defaultdict(list)
        for image in data['images']:
            name = image['file_name']
            if Path(name).name != name or '\\' in name or not name.endswith('_color.png'):
                raise ValueError(f'Invalid RGB filename: {name}')
            if name in seen_names or image['id'] in seen_images:
                raise ValueError('Duplicate image filename/ID across MJU splits')
            for dimension in ('width', 'height'):
                if isinstance(image[dimension], bool) or not isinstance(image[dimension], int) or image[dimension] <= 0:
                    raise ValueError('Invalid image dimensions')
            seen_names.add(name); seen_images.add(image['id']); images[image['id']] = image
        for index, annotation in enumerate(data['annotations']):
            if annotation['id'] in seen_annotations:
                raise ValueError('Duplicate source annotation ID')
            seen_annotations.add(annotation['id'])
            if annotation['image_id'] not in images or annotation['category_id'] not in categories:
                raise ValueError('Annotation references an unknown image/category')
            if annotation.get('iscrowd', 0):
                raise ValueError('Crowd masks are unsupported')
            points, fixes = normalized_polygon(annotation, images[annotation['image_id']])
            grouped[annotation['image_id']].append((annotation, points, fixes, index))
        records[split] = [(image, grouped[image['id']]) for image in data['images']]
    return records, hashes


def temporal_audit(records):
    frames = []
    for split, rows in records.items():
        for image, _ in rows:
            try:
                stamp = datetime.strptime(image['file_name'], '%Y-%m-%d_%H_%M_%S-%f_color.png')
                frames.append((stamp, split, image['file_name']))
            except ValueError:
                continue
    frames.sort()
    adjacent, cross, examples = 0, 0, []
    for first, second in zip(frames, frames[1:]):
        gap = (second[0] - first[0]).total_seconds()
        if 0 <= gap <= 10:
            adjacent += 1
            if first[1] != second[1]:
                cross += 1
                if len(examples) < 10:
                    examples.append({'first': first[2], 'second': second[2], 'gap_seconds': gap})
    return {'adjacent_pairs_within_10s': adjacent, 'cross_split_pairs_within_10s': cross,
            'timestamped_images': len(frames), 'examples': examples,
            'interpretation': 'Filename timestamps indicate adjacent frames across splits; use MJU train as auxiliary training, with TACO/local holdouts for evaluation.'}


def preprocess(source=DEFAULT_SOURCE, dataset=DEFAULT_DATASET):
    source, dataset = Path(source), Path(dataset)
    records, hashes = load_sources(source)  # Validate all splits before writing any labels.
    for split, rows in records.items():
        expected = {Path(image['file_name']).with_suffix('.txt').name for image, _ in rows}
        actual = {path.name for path in (dataset / 'labels' / split).glob('*.txt')}
        if actual - expected:
            raise ValueError(f'{split}: stale labels; use a fresh output folder')
    fixes, totals = [], {}
    for split, rows in records.items():
        (dataset / 'labels' / split).mkdir(parents=True, exist_ok=True)
        (dataset / 'images' / split).mkdir(parents=True, exist_ok=True)
        (dataset / 'manifests').mkdir(parents=True, exist_ok=True)
        manifests = []
        for image, objects in rows:
            name = image['file_name']
            lines = []
            for annotation, points, clipped, index in objects:
                lines.append('0 ' + ' '.join(f'{v:.8f}' for point in points for v in point))
                if clipped:
                    fixes.append({'split': split, 'image_id': image['id'], 'file_name': name,
                                  'annotation_id': annotation['id'], 'source_annotation_index': index, 'vertices': clipped})
            (dataset / 'labels' / split / Path(name).with_suffix('.txt')).write_text('\n'.join(lines) + ('\n' if lines else ''))
            manifests.append({'image_id': image['id'], 'file_name': name, 'flat_file_name': name,
                              'width': image['width'], 'height': image['height'],
                              'annotation_count': len(objects), 'object_count': len(objects),
                              'annotation_ids': '|'.join(str(a[0]['id']) for a in objects),
                              'license': image.get('license', '')})
        with (dataset / 'manifests' / f'{split}.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS); writer.writeheader(); writer.writerows(manifests)
        totals[split] = {'images': len(rows), 'instances': sum(len(a) for _, a in rows),
                         'negative_images': sum(not a for _, a in rows)}
    yaml = '# Generated local MJU RGB segmentation dataset.\n'
    yaml += ''.join(f'{split}: {json.dumps(str((dataset / "images" / split).resolve()))}\n' for split in SPLITS)
    (dataset / 'data.yaml').write_text(yaml + 'names:\n  0: litter\n')
    report = {'dataset': str(dataset.resolve()), 'source': str(source.resolve()), 'source_sha256': hashes,
              'class_mapping': {'Rubbish': '0 litter'}, 'bbox_policy': 'ignored; polygons normalized directly by image dimensions',
              'coordinate_tolerance_pixels': BOUNDARY_TOLERANCE, 'coordinate_fixes': fixes, 'splits': totals,
              'temporal_audit': temporal_audit(records), 'dataset_role': 'auxiliary litter training; official splits retained for reproducibility'}
    write_json(dataset / 'conversion_report.json', report)
    return report


def verify(dataset=DEFAULT_DATASET, source=DEFAULT_SOURCE, labels_only=False):
    from .verify_taco_ready import _polygon as read_polygon
    dataset, source = Path(dataset), Path(source)
    issues, label_issues, splits, fingerprints = [], [], {}, {}
    try:
        records, hashes = load_sources(source)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {'passed': False, 'labels_valid': False, 'training_ready': False, 'issues': [f'Source invalid: {exc}'], 'splits': {}}
    if not labels_only:
        from PIL import Image
    train_image_errors = []
    for split, rows in records.items():
        expected_names = {im['file_name'] for im, _ in rows}
        expected_labels = {Path(name).with_suffix('.txt').name for name in expected_names}
        try:
            with (dataset / 'manifests' / f'{split}.csv').open(newline='') as stream:
                manifest = list(csv.DictReader(stream))
            expected_manifest = {str(im['id']): (im, objects) for im, objects in rows}
            if len(manifest) != len(rows) or len({r['image_id'] for r in manifest}) != len(rows):
                label_issues.append(f'{split}: manifest coverage/uniqueness differs from source')
            for row in manifest:
                im, objects = expected_manifest[row['image_id']]
                if (row['file_name'] != im['file_name'] or int(row['width']) != im['width']
                        or int(row['height']) != im['height'] or int(row['annotation_count']) != len(objects)):
                    label_issues.append(f'{split}: manifest differs from source: {row.get("file_name")}')
        except (ValueError, KeyError, OSError, csv.Error) as exc:
            label_issues.append(f'{split}: manifest invalid: {exc}')
        objects_count = present_labels = missing_images = present_images = verified_images = negative_images = 0
        for im, objects in rows:
            name = im['file_name']; prefix = f'{split}/{name}'
            label = dataset / 'labels' / split / Path(name).with_suffix('.txt')
            try:
                lines = [line for line in label.read_text().splitlines() if line.strip()]
                present_labels += 1
                if len(lines) != len(objects):
                    raise ValueError('object count differs from source')
                for line, (_, expected, _, _) in zip(lines, objects):
                    points = read_polygon(line)
                    if len(points) != len(expected) or any(abs(v - e) > 0.0000011 for point, ep in zip(points, expected) for v, e in zip(point, ep)):
                        raise ValueError('polygon differs from source')
                objects_count += len(lines); negative_images += not lines
            except (OSError, ValueError) as exc:
                label_issues.append(f'{prefix}: invalid label: {exc}')
            image = dataset / 'images' / split / name
            image_errors = []
            if not image.is_file():
                missing_images += 1
                if not labels_only:
                    image_errors.append(f'{prefix}: missing image')
            else:
                present_images += 1
                if not labels_only:
                    try:
                        with Image.open(image) as picture: picture.verify()
                        with Image.open(image) as picture:
                            picture.load()
                            if picture.mode not in ('RGB', 'RGBA'):
                                raise ValueError('expected RGB photo, not an indexed/grayscale mask')
                            if picture.size != (im['width'], im['height']) or picture.getexif().get(274, 1) != 1:
                                raise ValueError('image geometry/orientation differs from source')
                            rgb = picture.convert('RGB')
                            digest = hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()
                        if digest in fingerprints and fingerprints[digest][0] != split:
                            image_errors.append(f'{prefix}: exact pixel duplicate across official splits')
                        fingerprints[digest] = (split, name)
                        verified_images += 1
                    except (OSError, ValueError, SyntaxError) as exc:
                        image_errors.append(f'{prefix}: invalid image: {exc}')
            issues.extend(image_errors)
            if split == 'train': train_image_errors.extend(image_errors)
        for directory, expected in (('labels', expected_labels), ('images', expected_names)):
            actual = {p.name for p in (dataset / directory / split).glob('*') if p.is_file() and not p.name.startswith('.')}
            if actual - expected: label_issues.append(f'{split}: unexpected files in {directory}')
        splits[split] = {'images': len(rows), 'instances': objects_count, 'present_labels': present_labels,
                         'present_images': present_images, 'missing_images': missing_images,
                         'verified_images': verified_images, 'negative_images': negative_images}
    issues = label_issues + issues
    passed = not issues
    return {'dataset': str(dataset.resolve()), 'source': str(source.resolve()), 'source_sha256': hashes,
            'labels_only': labels_only, 'passed': passed, 'labels_valid': not label_issues,
            'training_ready': passed and not labels_only,
            'auxiliary_train_ready': not labels_only and not label_issues and not train_image_errors and splits['train']['verified_images'] == splits['train']['images'],
            'independent_evaluation_supported': False, 'temporal_audit': temporal_audit(records),
            'splits': splits, 'issue_count': len(issues), 'issues': issues,
            'warnings': ['MJU official splits contain temporally adjacent frames; use TACO/local held-out data for the component evaluation.']}


def prepare_images(raw_root, dataset=DEFAULT_DATASET, source=DEFAULT_SOURCE):
    from PIL import Image
    records, _ = load_sources(Path(source)); dataset = Path(dataset)
    index = defaultdict(list)
    for path in Path(raw_root).rglob('*_color.png'):
        if path.is_file(): index[path.name].append(path)
    failures, imported = [], 0
    for split, rows in records.items():
        (dataset / 'images' / split).mkdir(parents=True, exist_ok=True)
        for im, _ in rows:
            try:
                hits = index[im['file_name']]
                rgb_hits = [path for path in hits if 'JPEGImages' in path.parts]
                if rgb_hits: hits = rgb_hits
                if not hits: raise ValueError('missing RGB source image')
                if len(hits) > 1 and len({sha256(path) for path in hits}) > 1:
                    raise ValueError('ambiguous source images with different bytes')
                original = hits[0]
                with Image.open(original) as image: image.verify()
                with Image.open(original) as image:
                    image.load()
                    if image.mode not in ('RGB', 'RGBA'):
                        raise ValueError('expected RGB photo, not an indexed/grayscale mask')
                    if image.size != (im['width'], im['height']) or image.getexif().get(274, 1) != 1:
                        raise ValueError('source geometry/orientation differs from annotation')
                target = dataset / 'images' / split / im['file_name']
                if target.exists() and sha256(target) == sha256(original): continue
                temporary = target.with_suffix('.part')
                try:
                    try: os.link(original, temporary)
                    except OSError: shutil.copy2(original, temporary)
                    temporary.replace(target)
                finally:
                    if temporary.exists(): temporary.unlink()
                imported += 1
            except (OSError, ValueError, SyntaxError) as exc:
                failures.append({'split': split, 'file_name': im['file_name'], 'error': str(exc)})
    result = {'imported': imported, 'passed': not failures, 'failures': failures}
    write_json(dataset / 'image_import_report.json', result)
    return result


def refresh_component_status(report, root=ROOT):
    """Attach MJU readiness without overwriting existing TACO source evidence."""
    root = Path(root)
    status_path = root / 'results/taco_preprocessing/supplied_preprocessing_status.json'
    if not status_path.is_file():
        return None
    status = json.loads(status_path.read_text())
    split_rows = list(report.get('splits', {}).values())
    entry = {'dataset': report.get('dataset'), 'role': 'auxiliary one-class litter training',
             'images': sum(row['images'] for row in split_rows),
             'annotations': sum(row['instances'] for row in split_rows),
             'labels_valid': report.get('labels_valid', False),
             'training_ready': report.get('training_ready', False),
             'auxiliary_train_ready': report.get('auxiliary_train_ready', False), 'verification': report}
    status['mju'] = entry
    combined = root / 'data/processed/litter_taco_mju_aux'
    if (combined / 'readiness.json').is_file():
        status['taco_mju_auxiliary'] = dict(json.loads((combined / 'readiness.json').read_text()),
                                           dataset=str(combined.resolve()))
    status['preprocessing_complete'] = (status.get('official', {}).get('verification', {}).get('passed', False)
                                        and status.get('unofficial', {}).get('verification', {}).get('passed', False)
                                        and entry['labels_valid'])
    status['all_prepared_images_present'] = all(
        row.get('missing_images', 0) == 0
        for name in ('official', 'unofficial', 'mju')
        for row in status.get(name, {}).get('verification', {}).get('splits', {}).values())
    write_json(status_path, status)
    register = status_path.with_name('supplied_dataset_register.csv')
    if register.is_file():
        with register.open(newline='') as stream:
            reader = csv.DictReader(stream); fields = reader.fieldnames
            rows = [row for row in reader if row['dataset'] != 'mju']
        values = {'dataset': 'mju', 'role': entry['role'], 'raw_source': report.get('source', ''),
                  'raw_source_sha256': json.dumps(report.get('source_sha256', {}), sort_keys=True),
                  'split_policy': 'official MJU splits; training-only auxiliary use', 'class_mapping': 'Rubbish -> litter',
                  'images': entry['images'], 'annotations': entry['annotations'],
                  'label_files': sum(row['present_labels'] for row in split_rows),
                  'present_images': sum(row['present_images'] for row in split_rows),
                  'missing_images': sum(row['missing_images'] for row in split_rows),
                  'training_ready': entry['training_ready'], 'training_pool_ready': entry['auxiliary_train_ready'],
                  'path': entry['dataset']}
        rows.append({field: values.get(field, '') for field in fields})
        with register.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--out', type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    try:
        report = preprocess(args.source, args.out)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'MJU conversion failed: {exc}\n')
    print(json.dumps(report['splits'], indent=2))
    print(f'Labels converted; clipped annotations: {len(report["coordinate_fixes"])}. Verify image readiness separately.')


if __name__ == '__main__': main()
