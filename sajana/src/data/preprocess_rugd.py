"""Preserve official RUGD semantic IDs, geometry and published sequence splits."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path

from .preprocess_mju_waste import ROOT, sha256, write_json

RAW = ROOT / 'data/raw/rugd/extracted'
OUT = ROOT / 'data/processed/rugd_semantic'
RESULTS = ROOT / 'results/rugd_preprocessing'
PAPER = 'http://rugd.vision/pdfs/RUGD_IROS2019.pdf'
SEQUENCES = {
    'train': ['park-2', 'trail', 'trail-3', 'trail-4', 'trail-6', 'trail-9', 'trail-10', 'trail-11', 'trail-12', 'trail-14', 'trail-15', 'village'],
    'val': ['park-8', 'trail-5'],
    'test': ['creek', 'park-1', 'trail-7', 'trail-13'],
}
PUBLISHED = {'train': 4759, 'val': 733, 'test': 1964}
# Counts in the current official annotation archive, preserving Table I sequences.
# These differ from Table I totals; retain and disclose the discrepancy.
RELEASE = {'train': 4779, 'val': 733, 'test': 1924}
FIELDS = ['file_name', 'source_sequence', 'source_image', 'source_mask', 'width', 'height',
          'image_sha256', 'source_mask_sha256', 'mask_sha256', 'class_pixel_counts']


def colormap_path(raw):
    paths = sorted(Path(raw).rglob('*colormap*.txt'))
    if len(paths) != 1:
        raise ValueError(f'Expected exactly one official colormap file, found {len(paths)}')
    return paths[0]


def load_colormap(path):
    classes = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f'Invalid colormap row: {line}')
        index = int(fields[0])
        rgb = tuple(map(int, fields[2:]))
        if not 0 <= index <= 254 or any(not 0 <= value <= 255 for value in rgb):
            raise ValueError('Colormap ID or RGB out of range')
        classes.append({'id': index, 'name': fields[1], 'rgb': list(rgb)})
    if len({c['id'] for c in classes}) != len(classes) or len({tuple(c['rgb']) for c in classes}) != len(classes):
        raise ValueError('Duplicate source class ID or color')
    if {c['id'] for c in classes} != set(range(25)) or classes[0]['name'] != 'void':
        raise ValueError('RUGD source catalog must contain void 0 and semantic IDs 1..24')
    return sorted(classes, key=lambda row: row['id'])


def source_rgb(path):
    from PIL import Image
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        im.load()
        if im.getexif().get(274, 1) != 1:
            raise ValueError('Ambiguous source EXIF orientation')
        if im.mode not in ('RGB', 'RGBA', 'P'):
            raise ValueError(f'Unexpected source color mode {im.mode}')
        return im.convert('RGB')


def make_lookup(classes):
    import numpy as np
    lookup = np.full(256 ** 3, 255, dtype=np.uint8)
    for row in classes:
        r, g, b = row['rgb']
        lookup[(r << 16) | (g << 8) | b] = row['id']
    return lookup


def semantic_mask(path, size, lookup):
    import numpy as np
    from PIL import Image
    rgb = source_rgb(path)
    if rgb.size != size:
        raise ValueError(f'Mask geometry {rgb.size} differs from RGB {size}')
    data = np.asarray(rgb, dtype=np.uint32)
    codes = (data[:, :, 0] << 16) | (data[:, :, 1] << 8) | data[:, :, 2]
    labels = lookup[codes]
    if np.any(labels == 255):
        colors = np.unique(codes[labels == 255])
        raise ValueError(f'Unknown source colors: {[f"#{int(c):06x}" for c in colors[:10]]}')
    counts = np.bincount(labels.ravel(), minlength=25)
    return Image.fromarray(labels), {str(i): int(count) for i, count in enumerate(counts) if count}


def discover(raw):
    raw = Path(raw)
    photo_roots = [p for p in raw.rglob('RUGD_frames-with-annotations') if p.is_dir()]
    mask_roots = [p for p in raw.rglob('RUGD_annotations') if p.is_dir()]
    if len(photo_roots) != 1 or len(mask_roots) != 1:
        raise ValueError('Expected exactly one RUGD_frames-with-annotations and RUGD_annotations root')
    photo_root, mask_root = photo_roots[0], mask_roots[0]
    mapping = {sequence: split for split, sequences in SEQUENCES.items() for sequence in sequences}
    photos = {p.relative_to(photo_root).as_posix(): p for p in photo_root.rglob('*.png')}
    masks = {p.relative_to(mask_root).as_posix(): p for p in mask_root.rglob('*.png')}
    if not photos or set(photos) != set(masks):
        raise ValueError(f'RGB/mask source coverage differs: {len(photos)} photos, {len(masks)} masks; '
                         f'missing masks {len(set(photos)-set(masks))}, missing photos {len(set(masks)-set(photos))}')
    records = []
    for name, photo in sorted(photos.items()):
        relative = Path(name)
        if len(relative.parts) != 2 or relative.parts[0] not in mapping:
            raise ValueError(f'Unmapped source sequence/file: {name}')
        sequence = relative.parts[0]
        records.append({'split': mapping[sequence], 'file_name': sequence + '__' + photo.name,
                        'source_sequence': sequence, 'source_image': photo.relative_to(raw).as_posix(),
                        'source_mask': masks[name].relative_to(raw).as_posix()})
    return records


def link_source(source, target):
    if target.exists():
        if sha256(target) != sha256(source):
            raise ValueError('Existing prepared photo differs from source')
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def inventory_issues(raw):
    """Compare extracted files with CRC-checked downloader inventory hashes."""
    issues = []
    for kind in ('annotations', 'frames'):
        path = Path(raw).parent / (kind + '_inventory.json')
        if path.is_file():
            for row in json.loads(path.read_text()).get('files', []):
                source = Path(raw) / row['path']
                if not source.is_file() or source.stat().st_size != row['bytes'] or sha256(source) != row['sha256']:
                    issues.append(f'{row["path"]}: source differs from archive inventory')
    return issues


def preprocess(raw=RAW, out=OUT):
    raw, out = Path(raw).resolve(), Path(out).resolve()
    classes = load_colormap(colormap_path(raw))
    lookup = make_lookup(classes)
    records = discover(raw)
    issues = inventory_issues(raw)
    if issues:
        raise ValueError(f'Source archive correspondence failed: {issues[:3]}')
    rows = {split: [] for split in SEQUENCES}
    totals = {split: Counter() for split in SEQUENCES}
    for split in SEQUENCES:
        expected = {r['file_name'] for r in records if r['split'] == split}
        for kind in ('images', 'masks'):
            folder = out / kind / split
            if {p.name for p in folder.glob('*') if p.is_file()} - expected:
                raise ValueError(f'Stale output {kind}/{split}; use a fresh output folder')
            folder.mkdir(parents=True, exist_ok=True)
    for index, record in enumerate(records, 1):
        try:
            photo, gt = raw / record['source_image'], raw / record['source_mask']
            rgb = source_rgb(photo)
            mask, counts = semantic_mask(gt, rgb.size, lookup)
            image_out = out / 'images' / record['split'] / record['file_name']
            mask_out = out / 'masks' / record['split'] / record['file_name']
            link_source(photo, image_out)
            temporary = mask_out.with_name(mask_out.name + '.part')
            mask.save(temporary, format='PNG')
            temporary.replace(mask_out)
            row = {k: v for k, v in record.items() if k != 'split'}
            row.update(width=rgb.width, height=rgb.height, image_sha256=sha256(photo),
                       source_mask_sha256=sha256(gt), mask_sha256=sha256(mask_out),
                       class_pixel_counts=json.dumps(counts, sort_keys=True))
            rows[record['split']].append(row)
            totals[record['split']].update(counts)
        except (OSError, ValueError, SyntaxError) as exc:
            issues.append(f'{record["source_image"]}: {exc}')
        if index % 250 == 0:
            print(f'RUGD: converted {index}/{len(records)} pairs', flush=True)
    (out / 'manifests').mkdir(parents=True, exist_ok=True)
    for split in SEQUENCES:
        with (out / 'manifests' / (split + '.csv')).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows[split])
    report = {'preprocessed': not issues, 'dataset': str(out), 'source': str(raw),
              'task': 'source_24_class_semantic_context', 'classes': classes, 'void_id': 0,
              'source_class_ids_preserved': True, 'final_damage_labels_supplied': False,
              'split_policy': 'official_paper_Table_I_sequence_membership', 'split_source': PAPER,
              'sequences': SEQUENCES, 'splits': {s: {'images': len(rows[s]), 'class_pixel_counts': dict(totals[s])} for s in SEQUENCES},
              'colormap_sha256': sha256(colormap_path(raw)), 'published_split_counts': PUBLISHED,
              'official_release_split_counts': RELEASE,
              'license_status': 'dataset_license_not_stated_in_reviewed_primary_page_or_paper; website_template_license_is_not_dataset_license',
              'issues': issues}
    write_json(out / 'source_colormap.json', {'classes': classes, 'void_id': 0})
    write_json(out / 'conversion_report.json', report)
    return report


def verify(raw=RAW, out=OUT):
    from PIL import Image
    raw, out = Path(raw).resolve(), Path(out).resolve()
    issues = []
    try:
        classes = load_colormap(colormap_path(raw))
        records = discover(raw)
        lookup = make_lookup(classes)
    except (OSError, ValueError) as exc:
        report = {'passed': False, 'training_ready': False, 'issues': [str(exc)], 'dataset': str(out)}
        write_json(out / 'readiness.json', report)
        return report
    issues.extend(inventory_issues(raw))
    expected = {(r['split'], r['file_name']): r for r in records}
    seen_pixels, split_sequences, counts = {}, {}, {}
    try:
        catalog = json.loads((out / 'source_colormap.json').read_text())
        if catalog != {'classes': classes, 'void_id': 0}:
            issues.append('Prepared class catalog differs from source colormap')
    except (OSError, ValueError) as exc:
        issues.append(f'Prepared class catalog missing/invalid: {exc}')
    for split in SEQUENCES:
        valid, split_sequences[split] = 0, set()
        try:
            with (out / 'manifests' / (split + '.csv')).open(newline='') as f:
                rows = list(csv.DictReader(f))
            keys = [(split, row['file_name']) for row in rows]
            if len(keys) != len(set(keys)) or set(keys) != {key for key in expected if key[0] == split}:
                issues.append(f'{split}: manifest coverage differs from source')
            for row in rows:
                try:
                    record = expected[(split, row['file_name'])]
                    if any(row[key] != record[key] for key in ('source_sequence', 'source_image', 'source_mask')):
                        raise ValueError('Manifest source/sequence mapping changed')
                    photo, gt = raw / record['source_image'], raw / record['source_mask']
                    image_path = out / 'images' / split / row['file_name']
                    mask_path = out / 'masks' / split / row['file_name']
                    source, prepared = source_rgb(photo), source_rgb(image_path)
                    mask, pixels = semantic_mask(gt, source.size, lookup)
                    with Image.open(mask_path) as stored:
                        stored.load()
                        if stored.mode != 'L' or stored.size != source.size or stored.tobytes() != mask.tobytes():
                            raise ValueError('Prepared mask does not preserve exact source class IDs')
                    if prepared.size != source.size or prepared.tobytes() != source.tobytes():
                        raise ValueError('Prepared photo differs from source pixels')
                    if (int(row['width']), int(row['height'])) != source.size or json.loads(row['class_pixel_counts']) != pixels:
                        raise ValueError('Manifest dimensions/class counts differ from source')
                    for key, path in [('image_sha256', photo), ('source_mask_sha256', gt), ('mask_sha256', mask_path)]:
                        if row[key] != sha256(path):
                            raise ValueError(f'{key} mismatch')
                    if sha256(image_path) != row['image_sha256']:
                        raise ValueError('Prepared photo encoded bytes differ from source')
                    digest = hashlib.sha256(str(source.size).encode() + source.tobytes()).hexdigest()
                    if digest in seen_pixels and seen_pixels[digest] != split:
                        raise ValueError('Identical RGB pixels occur across source splits')
                    seen_pixels[digest] = split
                    split_sequences[split].add(record['source_sequence'])
                    valid += 1
                except (OSError, ValueError, KeyError, SyntaxError) as exc:
                    issues.append(f'{split}/{row.get("file_name")}: {exc}')
            for kind in ('images', 'masks'):
                actual = {p.name for p in (out / kind / split).glob('*') if p.is_file()}
                if actual != {name for s, name in expected if s == split}:
                    issues.append(f'{split}: prepared {kind} coverage differs from source')
        except (OSError, ValueError, KeyError, csv.Error) as exc:
            issues.append(f'{split}: invalid/missing manifest: {exc}')
        counts[split] = {'images': sum(r['split'] == split for r in records), 'verified_pairs': valid,
                         'source_sequences': sorted(split_sequences[split])}
        print(f'RUGD {split}: {valid} pairs verified', flush=True)
    for first, second in [('train', 'val'), ('train', 'test'), ('val', 'test')]:
        if split_sequences[first] & split_sequences[second]:
            issues.append(f'{first}/{second}: source sequence leakage')
    complete = all(counts[s]['images'] == RELEASE[s] for s in SEQUENCES)
    ready = not issues and complete and all(counts[s]['verified_pairs'] > 0 for s in SEQUENCES)
    report = {'passed': not issues, 'training_ready': ready, 'source_context_training_ready': ready,
              'dataset': str(out), 'source': str(raw), 'available_pairs': len(records),
              'published_split_counts': PUBLISHED,
              'published_count_complete': all(counts[s]['images'] == PUBLISHED[s] for s in SEQUENCES),
              'official_release_split_counts': RELEASE, 'available_source_complete': complete,
              'splits': counts, 'split_policy': 'official_paper_Table_I_sequence_membership', 'split_source': PAPER,
              'source_class_ids_preserved': True, 'semantic_class_ids': list(range(1, 25)), 'void_ignore_id': 0,
              'independent_hiking_evaluation_supported': False, 'final_damage_labels_supplied': False,
              'license_status': 'unspecified_in_reviewed_primary_dataset_material',
              'issue_count': len(issues), 'issues': issues,
              'warnings': ['Official release has 7436 pairs (4779/733/1924) using published sequence membership; paper Table I states 7456 (4759/733/1964). No records or splits are invented to reconcile this discrepancy.',
                           'Natural terrain/object classes are context, not erosion, exposed-root, route-obstruction or hiking-safety ground truth.',
                           'The website footer CC BY 3.0 statement applies to the Colorlib template, not the dataset. Dataset reuse terms remain unverified.']}
    write_json(out / 'readiness.json', report)
    if out == OUT.resolve():
        write_json(RESULTS / 'local_readiness.json', report)
    return report


def previews(out=OUT, destination=RESULTS):
    from PIL import Image, ImageDraw, ImageOps
    out, destination = Path(out), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    classes = json.loads((out / 'source_colormap.json').read_text())['classes']
    palette = [0] * 768
    for row in classes:
        palette[row['id'] * 3:row['id'] * 3 + 3] = row['rgb']
    for split in SEQUENCES:
        with (out / 'manifests' / (split + '.csv')).open(newline='') as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        chosen = [rows[round(i * (len(rows) - 1) / max(1, min(5, len(rows) - 1)))] for i in range(min(6, len(rows)))]
        sheet = Image.new('RGB', (1000, 270 * len(chosen)), '#202629')
        draw = ImageDraw.Draw(sheet)
        for index, row in enumerate(chosen):
            rgb = source_rgb(out / 'images' / split / row['file_name'])
            with Image.open(out / 'masks' / split / row['file_name']) as mask:
                colored = mask.convert('P')
                colored.putpalette(palette)
                overlay = Image.blend(rgb, colored.convert('RGB'), 0.5)
            sheet.paste(ImageOps.contain(rgb, (500, 240)), (0, index * 270))
            sheet.paste(ImageOps.contain(overlay, (500, 240)), (500, index * 270))
            draw.text((5, index * 270 + 243), row['file_name'], fill='white')
        sheet.save(destination / (split + '_overlays.jpg'), quality=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, default=RAW)
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if not args.verify_only:
        preprocess(args.raw_root, args.out)
    report = verify(args.raw_root, args.out)
    if report['passed']:
        previews(args.out)
    print(json.dumps(report, indent=2))
    if not report['training_ready']:
        parser.exit(1, 'RUGD is not a complete verified source-context dataset; inspect readiness.json\n')


if __name__ == '__main__':
    main()
