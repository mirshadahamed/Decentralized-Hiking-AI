"""Audit source coverage, segmentation labels, split isolation, and image readiness.

Labels-only mode uses the standard library and never certifies training readiness.
Full mode also requires Pillow and decodes every image, checks its geometry, and
checks for identical decoded pixels shared by different splits.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / 'data/processed/taco_litter_seg'
DEFAULT_ANNOTATIONS = ROOT / 'data/interim/taco/annotations_official_binary_litter.json'
SPLITS = ('train', 'val', 'test')
REQUIRED_COLUMNS = {'image_id', 'batch', 'source_file_name', 'flat_file_name',
                    'width', 'height', 'object_count'}
COORDINATE_TOLERANCE = 0.0000011  # Six-decimal output plus float32 rounding.
BATCH_SPLITS = {**{f'batch_{number}': 'train' for number in (1, 2, 5, 6, 7, 8, 9, 10, 12, 13)},
                **{f'batch_{number}': 'val' for number in (3, 4, 11)},
                **{f'batch_{number}': 'test' for number in (14, 15)}}


def _integer(value, minimum=0):
    if isinstance(value, bool):
        raise ValueError('expected an integer')
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('expected an integer') from exc
    if str(number) != str(value) or number < minimum:
        raise ValueError(f'expected an integer >= {minimum}')
    return number


def _source_records(annotations: Path, issues: list, warnings: list) -> tuple[dict, int]:
    """Read COCO records independently of preprocessing and optional packages."""
    try:
        source = json.loads(annotations.read_text(encoding='utf-8'))
        images, objects = source['images'], source['annotations']
        if not isinstance(images, list) or not isinstance(objects, list):
            raise ValueError('images and annotations must be lists')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        issues.append(f'source annotations: cannot read {annotations}: {exc}')
        return {}, 0
    records, names = {}, set()
    for index, image in enumerate(images):
        try:
            image_id = str(_integer(image['id']))
            width, height = _integer(image['width'], 1), _integer(image['height'], 1)
            name = image['file_name']
            if not isinstance(name, str):
                raise ValueError('expected a filename string')
            parts = PurePosixPath(name).parts
            if len(parts) != 2 or '..' in parts or '\\' in name or name.startswith('/'):
                raise ValueError('expected a relative batch/image filename')
            if image_id in records or name in names:
                raise ValueError('duplicate image ID or filename')
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(f'source image {index}: {exc}')
            continue
        names.add(name)
        records[image_id] = {'width': width, 'height': height, 'name': name,
                             'batch': parts[0], 'polygons': []}
    seen_annotations = {}
    for index, annotation in enumerate(objects):
        try:
            annotation_id = str(_integer(annotation['id']))
            image_id = str(_integer(annotation['image_id']))
            record = records[image_id]
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(f'source annotation {index}: invalid ID or image reference: {exc}')
            continue
        if annotation_id in seen_annotations:
            message = f'source annotation ID {annotation_id} is repeated; all records are retained'
            (issues if image_id in seen_annotations[annotation_id] else warnings).append(message)
        seen_annotations.setdefault(annotation_id, set()).add(image_id)
        polygons = None
        try:
            segments = annotation['segmentation']
            if not isinstance(segments, list) or not segments:
                raise ValueError('expected COCO polygons; RLE is unsupported')
            polygons = []
            for segment in segments:
                if not isinstance(segment, list) or len(segment) < 6 or len(segment) % 2:
                    raise ValueError('malformed source polygon')
                values = [float(value) for value in segment]
                if not all(math.isfinite(value) for value in values):
                    raise ValueError('nonfinite source coordinate')
                width, height = record['width'], record['height']
                if any(x < -1 or x > width or y < -1 or y > height
                       for x, y in zip(values[::2], values[1::2])):
                    raise ValueError('source polygon exceeds image bounds by more than one pixel')
                points = [(max(0, min(x, width - 1)) / width,
                           max(0, min(y, height - 1)) / height)
                          for x, y in zip(values[::2], values[1::2])]
                if len(set(points)) < 3:
                    raise ValueError('degenerate source polygon')
                polygons.append(points)
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(f'source annotation {annotation_id}: {exc}')
            polygons = None
        # Retain invalid annotations in the count; silently dropping them is an error.
        record['polygons'].append(polygons)
    return records, len(objects)


def _polygon(line: str):
    parts = line.split()
    if not parts or parts[0] != '0':
        raise ValueError('class must be 0 (litter)')
    values = [float(value) for value in parts[1:]]
    if (len(values) < 6 or len(values) % 2
            or not all(math.isfinite(value) and 0 <= value <= 1 for value in values)):
        raise ValueError('expected at least three finite normalized coordinate pairs')
    points = list(zip(values[::2], values[1::2]))
    if len(set(points)) < 3:
        raise ValueError('fewer than three distinct vertices')
    area = sum(x * ny - nx * y for (x, y), (nx, ny)
               in zip(points, points[1:] + points[:1]))
    if abs(area) <= 1e-12:
        raise ValueError('zero-area polygon')
    return points


def _close(first, second):
    return all(abs(a - b) <= COORDINATE_TOLERANCE for a, b in zip(first, second))


def _matches_source(points, polygons):
    if len(polygons) == 1:
        expected = polygons[0]
        return len(points) == len(expected) and all(_close(a, b) for a, b in zip(points, expected))
    # Multipart conversion adds bridges and may reverse or roll segments.
    expected = [point for polygon in polygons for point in polygon]
    return (all(any(_close(point, source) for source in expected) for point in points)
            and all(any(_close(source, point) for point in points) for source in expected))


def _same_geometry(width, height, expected_width, expected_height):
    if (width, height) == (expected_width, expected_height):
        return True
    # A proportional Flickr fallback can round its short edge by one pixel.
    return (width > 0 and height > 0
            and min(abs(width - height * expected_width / expected_height),
                    abs(height - width * expected_height / expected_width)) <= 1)


def verify(dataset: Path, labels_only: bool = False,
           annotations: Path = DEFAULT_ANNOTATIONS,
           split_policy: str = 'official_batches') -> dict:
    if split_policy not in ('official_batches', 'train_only'):
        raise ValueError(f'Unknown split policy: {split_policy}')
    dataset, annotations = Path(dataset), Path(annotations)
    issues, warnings, summary = [], [], {}
    records, source_object_count = _source_records(annotations, issues, warnings)
    seen_ids, seen_names, seen_batches, pixel_hashes = set(), set(), set(), {}
    image_module = None
    if not labels_only:
        try:
            from PIL import Image
            image_module = Image
        except ImportError:
            issues.append('Pillow is required for full verification; install requirements_preprocess.txt')
    for split in SPLITS:
        manifest = dataset / 'manifests' / f'{split}.csv'
        try:
            with manifest.open(newline='', encoding='utf-8') as stream:
                reader = csv.DictReader(stream)
                if not REQUIRED_COLUMNS.issubset(reader.fieldnames or []):
                    missing = ', '.join(sorted(REQUIRED_COLUMNS - set(reader.fieldnames or [])))
                    raise ValueError(f'missing columns: {missing}')
                rows = list(reader)
        except (OSError, ValueError, csv.Error) as exc:
            issues.append(f'{split}: cannot read manifest: {exc}')
            continue
        if not rows and (split_policy == 'official_batches' or split == 'train'):
            issues.append(f'{split}: empty manifest')
        if rows and split_policy == 'train_only' and split != 'train':
            issues.append(f'{split}: train-only pool must not contain evaluation images')
        batches = {row.get('batch') for row in rows}
        if batches & seen_batches:
            issues.append(f'{split}: batches shared across splits')
        seen_batches.update(batches)
        objects = missing_images = present_images = valid_images = resized_images = present_labels = 0
        expected_labels, expected_images = set(), set()
        for row_number, row in enumerate(rows, 2):
            name = row.get('flat_file_name')
            if (not isinstance(name, str) or not name or Path(name).name != name
                    or '\\' in name or Path(name).suffix.lower() != '.jpg'):
                issues.append(f'{split}: invalid filename on manifest row {row_number}: {name}')
                continue
            prefix = f'{split}/{name}'
            expected_images.add(name)
            label_name = Path(name).with_suffix('.txt').name
            expected_labels.add(label_name)
            try:
                image_id = str(_integer(row['image_id']))
                width, height = _integer(row['width'], 1), _integer(row['height'], 1)
                object_count = _integer(row['object_count'])
            except (TypeError, ValueError, KeyError) as exc:
                issues.append(f'{prefix}: invalid manifest values: {exc}')
                continue
            if image_id in seen_ids or name in seen_names:
                issues.append(f'{prefix}: duplicate image ID or filename')
            seen_ids.add(image_id)
            seen_names.add(name)
            record = records.get(image_id)
            if record is None:
                issues.append(f'{prefix}: image ID absent from source annotations')
            else:
                source_name = record['name']
                flat_name = f"{record['batch']}__{PurePosixPath(source_name).stem}.jpg"
                if (row['source_file_name'] != source_name or row['batch'] != record['batch']
                        or name != flat_name):
                    issues.append(f'{prefix}: filename or batch differs from source annotations')
                expected_split = 'train' if split_policy == 'train_only' else BATCH_SPLITS.get(record['batch'])
                if expected_split != split:
                    issues.append(f'{prefix}: batch is not assigned to the documented {split} split')
                if (width, height) != (record['width'], record['height']):
                    issues.append(f'{prefix}: manifest dimensions differ from source annotations')
                if object_count != len(record['polygons']):
                    issues.append(f'{prefix}: manifest object count differs from source annotations')
                width, height = record['width'], record['height']
            label = dataset / 'labels' / split / label_name
            try:
                lines = [line for line in label.read_text(encoding='utf-8').splitlines() if line.strip()]
                present_labels += 1
            except (OSError, UnicodeError) as exc:
                issues.append(f'{split}/{label_name}: missing or unreadable label: {exc}')
                lines = []
            if len(lines) != object_count:
                issues.append(f'{split}/{label_name}: object count differs from manifest')
            if record is not None and len(lines) != len(record['polygons']):
                issues.append(f'{split}/{label_name}: object count differs from source annotations')
            for number, line in enumerate(lines, 1):
                try:
                    points = _polygon(line)
                except ValueError as exc:
                    issues.append(f'{split}/{label_name}:{number}: invalid polygon: {exc}')
                    continue
                if record is not None and number <= len(record['polygons']):
                    source_polygons = record['polygons'][number - 1]
                    if source_polygons and not _matches_source(points, source_polygons):
                        issues.append(f'{split}/{label_name}:{number}: polygon differs from source annotations')
            objects += len(lines)
            image = dataset / 'images' / split / name
            if not image.is_file():
                missing_images += 1
                if not labels_only:
                    issues.append(f'{prefix}: missing image')
                continue
            present_images += 1
            if labels_only or image_module is None:
                continue
            try:
                with image_module.open(image) as im:
                    im.verify()
                with image_module.open(image) as im:
                    im.load()  # verify() alone does not detect every truncated decode.
                    actual_width, actual_height = im.size
                    if im.getexif().get(274, 1) != 1:
                        raise ValueError('EXIF orientation must be normalized before training')
                    if not _same_geometry(actual_width, actual_height, width, height):
                        raise ValueError(f'aspect ratio differs from annotation: {im.size} vs {(width, height)}')
                    rgb = im.convert('RGB')
                    digest = hashlib.sha256(f'{rgb.width}x{rgb.height}:'.encode() + rgb.tobytes()).hexdigest()
                if digest in pixel_hashes:
                    previous_split, previous_name = pixel_hashes[digest]
                    message = f'{prefix}: identical decoded pixels also in {previous_split}/{previous_name}'
                    (issues if previous_split != split else warnings).append(message)
                else:
                    pixel_hashes[digest] = (split, name)
                valid_images += 1
                resized_images += (actual_width, actual_height) != (width, height)
            except Exception as exc:
                issues.append(f'{prefix}: invalid image: {exc}')
        for directory, expected in (('labels', expected_labels), ('images', expected_images)):
            actual = {path.name for path in (dataset / directory / split).glob('*')
                      if path.is_file() and not path.name.startswith('.')}
            for extra in sorted(actual - expected):
                issues.append(f'{split}/{extra}: unexpected {directory} file')
        summary[split] = {'images': len(rows), 'objects': objects, 'present_labels': present_labels,
                          'present_images': present_images, 'missing_images': missing_images,
                          'verified_images': valid_images, 'resized_images': resized_images}
    missing_ids = set(records) - seen_ids
    if missing_ids:
        examples = ', '.join(sorted(missing_ids, key=int)[:10])
        issues.append(f'source coverage: {len(missing_ids)} images missing from manifests (IDs: {examples})')
    unexpected_ids = seen_ids - set(records)
    passed = not issues
    images_verified = passed and not labels_only
    benchmark_ready = images_verified and split_policy == 'official_batches'
    pool_ready = images_verified and split_policy == 'train_only'
    return {'mode': 'labels_only' if labels_only else 'full', 'passed': passed,
            'training_ready': benchmark_ready,
            'training_pool_ready': pool_ready,
            'split_policy': split_policy,
            'dataset_role': 'optional train-only pool' if split_policy == 'train_only' else 'official benchmark',
            'status': ('training_ready' if benchmark_ready else
                       'training_pool_verified_no_evaluation_split' if pool_ready else
                       'labels_verified_images_not_checked' if passed else 'incomplete_or_invalid'),
            'dataset': str(dataset.resolve()), 'annotations': str(annotations.resolve()),
            'source_coverage': {'images': len(records), 'annotations': source_object_count,
                                'manifest_images': len(seen_ids), 'missing_images': len(missing_ids),
                                'unexpected_images': len(unexpected_ids)},
            'image_checks_performed': not labels_only and image_module is not None,
            'source_polygon_check': 'ordered single polygons; vertex coverage for bridged multipart polygons',
            'splits': summary, 'warnings': warnings, 'issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--annotations', type=Path, default=DEFAULT_ANNOTATIONS,
                        help='COCO source used to generate the manifests and labels')
    parser.add_argument('--labels-only', action='store_true',
                        help='Audit source and labels without Pillow; does not certify images')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--split-policy', choices=('official_batches', 'train_only'), default='official_batches',
                        help='Train-only verifies a separate auxiliary pool without certifying an evaluation split')
    args = parser.parse_args()
    report = verify(args.dataset, args.labels_only, args.annotations, args.split_policy)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not report['passed']:
        raise SystemExit(1)
    print('Labels verified. Images have not been checked; training_ready=false.' if args.labels_only
          else 'Training pool verified; no evaluation split, training_ready=false.' if report['training_pool_ready']
          else 'Dataset verification passed; training_ready=true.')


if __name__ == '__main__':
    main()
