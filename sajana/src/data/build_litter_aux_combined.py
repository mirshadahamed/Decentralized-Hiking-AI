"""Build TACO-clean + MJU-train with unchanged TACO validation/test holdouts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path
from PIL import Image

from .preprocess_mju_waste import ROOT, DEFAULT_DATASET as MJU, DEFAULT_SOURCE as MJU_SOURCE, verify as verify_mju, write_json, sha256
from .verify_taco_ready import verify as verify_taco, _same_geometry

TACO = ROOT / 'data/processed/taco_litter_seg_clean'
TACO_SOURCE = ROOT / 'data/interim/taco/annotations_official_cleaned.json'
OUT = ROOT / 'data/processed/litter_taco_mju_aux'
SPLITS = ('train', 'val', 'test')


def build(taco=TACO, mju=MJU, out=OUT, taco_source=TACO_SOURCE, mju_source=MJU_SOURCE):
    taco, mju, out = Path(taco), Path(mju), Path(out)
    source_audits = {'taco': verify_taco(taco, labels_only=True, annotations=taco_source),
                     'mju': verify_mju(mju, mju_source, labels_only=True)}
    if not all(report['passed'] for report in source_audits.values()):
        raise ValueError('Source label audits failed; verify TACO and MJU before combining')
    plan, issues = {split: [] for split in SPLITS}, []
    for split in SPLITS:
        for source_name, dataset in [('taco', taco)] + ([('mju', mju)] if split == 'train' else []):
            with (dataset / 'manifests' / f'{split}.csv').open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                name = row.get('flat_file_name') or row['file_name']
                image = dataset / 'images' / split / name
                label = dataset / 'labels' / split / Path(name).with_suffix('.txt')
                if not image.is_file() or not label.is_file():
                    issues.append(f'{source_name}/{split}/{name}: missing image/label')
                plan[split].append({'source_dataset': source_name, 'source_split': split,
                                    'source_file_name': name, 'source_image': str(image), 'source_label': str(label),
                                    'flat_file_name': f'{source_name}__{name}',
                                    'width': int(row['width']), 'height': int(row['height']),
                                    'object_count': int(row['object_count']), 'source_label_sha256': ''})
    if issues:
        report = {'built': False, 'training_ready': False, 'issues': issues,
                  'split_policy': 'train=TACO train+MJU train; val/test=TACO only'}
        write_json(out / 'readiness.json', report)
        if (out / 'data.yaml').exists(): (out / 'data.yaml').replace(out / 'data.yaml.invalid')
        return report
    # Refuse stale content instead of silently retaining examples from older sources/splits.
    for split, rows in plan.items():
        expected_images = {row['flat_file_name'] for row in rows}
        expected_labels = {Path(name).with_suffix('.txt').name for name in expected_images}
        for kind, expected in [('images', expected_images), ('labels', expected_labels)]:
            extra = {p.name for p in (out / kind / split).glob('*') if p.is_file() and not p.name.startswith('.')} - expected
            if extra: raise ValueError(f'Unexpected {kind}/{split} files; use a fresh combined output')
    hashes, counts = {}, {}
    for split, rows in plan.items():
        for kind in ('images', 'labels'): (out / kind / split).mkdir(parents=True, exist_ok=True)
        for index, row in enumerate(rows):
            source_image, source_label = Path(row['source_image']), Path(row['source_label'])
            image_path = out / 'images' / split / row['flat_file_name']
            label_path = out / 'labels' / split / Path(row['flat_file_name']).with_suffix('.txt')
            try:
                with Image.open(source_image) as image: image.verify()
                with Image.open(source_image) as image:
                    image.load()
                    if image.getexif().get(274, 1) != 1 or not _same_geometry(*image.size, row['width'], row['height']):
                        raise ValueError('image geometry/orientation differs from source')
                    rgb = image.convert('RGB')
                    digest = hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()
                if digest in hashes and hashes[digest][0] != split:
                    issues.append(f'{split}/{row["flat_file_name"]}: identical pixels across combined splits: {hashes[digest]}')
                hashes[digest] = (split, row['flat_file_name'])
                if image_path.exists():
                    if not os.path.samefile(source_image, image_path) and sha256(source_image) != sha256(image_path):
                        raise ValueError('existing combined image differs from source')
                else:
                    try: os.link(source_image, image_path)
                    except OSError: shutil.copy2(source_image, image_path)
                # Labels are independent copies, preserving source evidence on regeneration.
                label_path.write_bytes(source_label.read_bytes())
                row['source_label_sha256'] = sha256(source_label)
                if len([line for line in label_path.read_text().splitlines() if line.strip()]) != row['object_count']:
                    raise ValueError('object count changed while copying labels')
            except (OSError, ValueError, SyntaxError) as exc:
                issues.append(f'{split}/{row["flat_file_name"]}: {exc}')
            if (index + 1) % 250 == 0:
                print(f'Combined {split}: verified {index+1}/{len(rows)} pairs', flush=True)
        (out / 'manifests').mkdir(parents=True, exist_ok=True)
        with (out / 'manifests' / f'{split}.csv').open('w', newline='') as stream:
            fields = list(rows[0]) if rows else ['flat_file_name']
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        counts[split] = {'images': len(rows), 'instances': sum(row['object_count'] for row in rows)}
    report = {'built': not issues, 'training_ready': not issues, 'splits': counts,
              'split_policy': 'train=TACO clean train+MJU train; val/test=TACO clean only',
              'evaluation_source': 'TACO official held-out batches; future local trail test remains separate',
              'source_label_audits_passed': True, 'issues': issues}
    write_json(out / 'readiness.json', report)
    if not issues:
        yaml = '# TACO clean + MJU auxiliary train; TACO-only evaluation.\n'
        yaml += ''.join(f'{split}: {json.dumps(str((out / "images" / split).resolve()))}\n' for split in SPLITS)
        (out / 'data.yaml').write_text(yaml + 'names:\n  0: litter\n')
    elif (out / 'data.yaml').exists():
        (out / 'data.yaml').replace(out / 'data.yaml.invalid')
    status_path = ROOT / 'results/taco_preprocessing/supplied_preprocessing_status.json'
    if out.resolve() == OUT.resolve() and status_path.is_file():
        status = json.loads(status_path.read_text()); status['taco_mju_auxiliary'] = dict(report, dataset=str(out.resolve()))
        write_json(status_path, status)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--taco', type=Path, default=TACO)
    parser.add_argument('--mju', type=Path, default=MJU)
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--taco-source', type=Path, default=TACO_SOURCE)
    parser.add_argument('--mju-source', type=Path, default=MJU_SOURCE)
    args = parser.parse_args()
    try: report = build(args.taco, args.mju, args.out, args.taco_source, args.mju_source)
    except (OSError, ValueError, KeyError) as exc: parser.exit(1, f'Cannot combine datasets: {exc}\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'issues'}, indent=2))
    if not report['training_ready']: parser.exit(1, f'{len(report["issues"])} issues; inspect {args.out}/readiness.json\n')


if __name__ == '__main__': main()
