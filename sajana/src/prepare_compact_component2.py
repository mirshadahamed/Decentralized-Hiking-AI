"""Build a bounded, reproducible working set without deleting source data."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .component2_training_data import data_yaml, label_count
from .train_yolov8 import ROOT, now, sha256, write_json

CONFIG = ROOT / 'configs/component2_compact_2000.json'
REPORTS = ROOT / 'results/component2_training'


def configuration():
    cfg = json.loads(CONFIG.read_text())
    total = sum(sum(cfg[task]['counts'].values()) for task in ('litter', 'obstacle'))
    if total != cfg['total_image_limit'] or not 0 < total <= 2000:
        raise ValueError('The working set must contain at most 2,000 photos including holdouts')
    return cfg


def obstacle_stratum(row):
    if int(row['rock_components']):
        return 'rock'
    return 'log_only' if int(row['log_components']) else 'background'


def select_obstacles(rows, quotas, seed):
    """Disjoint label strata, deterministic seeded selection; no model predictions."""
    selected = []
    for stratum, count in quotas.items():
        candidates = [r for r in rows if obstacle_stratum(r) == stratum]
        if count < 0 or len(candidates) < count:
            raise ValueError('Insufficient source coverage: ' + stratum)
        candidates.sort(key=lambda r: hashlib.sha256(
            f"{seed}:{r['sequence']}:{r['source_id']}".encode()).hexdigest())
        selected.extend(candidates[:count])
    if len({r['flat_file_name'] for r in selected}) != len(selected):
        raise ValueError('Repeated selection')
    return sorted(selected, key=lambda r: r['flat_file_name'])


def verify_compact(cfg=None):
    cfg = cfg or configuration()
    target = ROOT / cfg['output']
    report = json.loads((target / 'readiness.json').read_text())
    if not report.get('passed') or report['configuration_sha256'] != sha256(CONFIG):
        raise ValueError('Compact set configuration is not frozen')
    if report['total_images'] != cfg['total_image_limit']:
        raise ValueError('Compact set exceeds the declared image budget')
    inventory = json.loads((target / 'inventory.json').read_text())
    if sha256(target / 'inventory.json') != report['inventory_sha256']:
        raise ValueError('Compact inventory changed')
    for relative, expected in inventory.items():
        if sha256(target / relative) != expected:
            raise ValueError('Compact input changed: ' + relative)
    for task in ('litter', 'obstacle'):
        for split, expected in report['tasks'][task]['splits'].items():
            if expected['images'] != cfg[task]['counts'][split]:
                raise ValueError('Compact report no longer matches the declared split budget')
            for kind, suffix in [('images', '.jpg'), ('labels', '.txt')]:
                prefix = f'{task}/{kind}/{split}/'
                wanted = {name.removeprefix(prefix) for name in inventory if name.startswith(prefix)}
                files = {p.name for p in (target / task / kind / split).iterdir()
                         if p.is_file() and not p.name.startswith('.')}
                if files != wanted or len(files) != expected['images'] or any(not n.endswith(suffix) for n in files):
                    raise ValueError('Compact membership count changed')
    return report


def prepare():
    from PIL import Image

    cfg = configuration()
    target = ROOT / cfg['output']
    if target.exists():
        return verify_compact(cfg)
    # Fail before writing output if any source report is unready or selection is impossible.
    selections = {}
    for task in ('litter', 'obstacle'):
        job = cfg[task]
        certificate = json.loads((ROOT / job['certificate']).read_text())
        if not certificate.get('training_ready') or not certificate.get('passed'):
            raise ValueError('Source data is not verified: ' + task)
        selections[task] = {}
        for split, expected in job['counts'].items():
            with (ROOT / job['source'] / 'manifests' / f'{split}.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            chosen = rows if task == 'litter' else select_obstacles(rows, job['strata'][split], cfg['seed'])
            if len(chosen) != expected:
                raise ValueError('Selected image count differs from the budget')
            selections[task][split] = chosen

    target.mkdir(parents=True)
    inventory, tasks, membership, pixels = {}, {}, [], {}
    image_bytes = label_bytes = source_bytes = 0
    manifest_rows = []
    for task, splits in selections.items():
        job = cfg[task]
        frozen = json.loads((ROOT / job['frozen_source']).read_text())
        tasks[task] = {'names': job['names'], 'task': job['task'], 'splits': {},
                       'source_certificate_sha256': sha256(ROOT / job['certificate']),
                       'source_inventory_sha256': sha256(ROOT / job['frozen_source'])}
        for split, rows in splits.items():
            counts = {'images': len(rows), 'objects': 0, 'background_images': 0,
                      'images_with_class': {key: 0 for key in job['names']}}
            for row in rows:
                name = row['flat_file_name']
                if Path(name).name != name:
                    raise ValueError('Unsafe source filename')
                source_image = ROOT / job['source'] / 'images' / split / name
                source_label = ROOT / job['source'] / 'labels' / split / Path(name).with_suffix('.txt')
                original_hash, label_hash = sha256(source_image), sha256(source_label)
                frozen_name = 'taco__' + name if task == 'litter' else name
                if (original_hash != frozen[split][f'images/{split}/{frozen_name}'] or
                        label_hash != frozen[split][f'labels/{split}/{Path(frozen_name).with_suffix(".txt")}']):
                    raise ValueError('Source pair differs from its verified frozen input: ' + name)
                objects = label_count(source_label, job['task'], job['names'])
                expected_objects = int(row['object_count' if task == 'litter' else 'region_boxes'])
                if objects != expected_objects:
                    raise ValueError('Source object count changed')
                counts['objects'] += objects
                counts['background_images'] += int(objects == 0)
                present = {line.split()[0] for line in source_label.read_text().splitlines() if line.strip()}
                for class_id in present:
                    counts['images_with_class'][class_id] += 1
                out_image = target / task / 'images' / split / Path(name).with_suffix('.jpg')
                out_label = target / task / 'labels' / split / Path(name).with_suffix('.txt')
                out_image.parent.mkdir(parents=True, exist_ok=True)
                out_label.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(source_image) as image:
                    if image.getexif().get(274, 1) != 1 or image.size != (int(row['width']), int(row['height'])):
                        raise ValueError('Unexpected source orientation/geometry')
                    rgb = image.convert('RGB')
                    # Uniform resize, no crop/rotation: normalized polygons/boxes remain valid.
                    rgb.thumbnail((cfg['maximum_image_edge'], cfg['maximum_image_edge']), Image.Resampling.LANCZOS)
                    size = rgb.size
                    rgb.save(out_image, format='JPEG', quality=cfg['jpeg_quality'], optimize=True)
                out_label.write_bytes(source_label.read_bytes())
                with Image.open(out_image) as converted:
                    converted.load()
                    digest = hashlib.sha256(str(converted.size).encode() + converted.tobytes()).hexdigest()
                if digest in pixels and pixels[digest] != split:
                    raise ValueError('Identical compact decoded photos cross holdouts')
                pixels[digest] = split
                for output in (out_image, out_label):
                    inventory[output.relative_to(target).as_posix()] = sha256(output)
                image_bytes += out_image.stat().st_size
                label_bytes += out_label.stat().st_size
                source_bytes += source_image.stat().st_size + source_label.stat().st_size
                membership.append({'task': task, 'split': split, 'source_file_name': name})
                manifest_rows.append(dict(membership[-1], source_image_sha256=original_hash,
                                          source_label_sha256=label_hash, width=size[0], height=size[1],
                                          objects=objects))
            tasks[task]['splits'][split] = counts
            print(f'{task} {split}: {len(rows)} verified compact pairs', flush=True)
        yaml = data_yaml(target / task / 'data.yaml', target / task, job['names'])
        inventory[yaml.relative_to(target).as_posix()] = sha256(yaml)

    with (target / 'manifest.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(manifest_rows[0]))
        writer.writeheader(); writer.writerows(manifest_rows)
    inventory['manifest.csv'] = sha256(target / 'manifest.csv')
    write_json(target / 'inventory.json', inventory)
    report = {
        'checked_at': now(), 'passed': True, 'total_images': len(membership),
        'configuration_sha256': sha256(CONFIG), 'inventory_sha256': sha256(target / 'inventory.json'),
        'tasks': tasks, 'compact_image_bytes': image_bytes, 'compact_label_bytes': label_bytes,
        'selected_source_bytes': source_bytes, 'source_split_membership_preserved': True,
        'selection_uses_model_scores': False, 'test_model_evaluation_performed': False,
        'maximum_image_edge': cfg['maximum_image_edge'], 'jpeg_quality': cfg['jpeg_quality'],
        'source_files_deleted': False, 'full_component_ready': False,
        'limitations': cfg['constraints']}
    write_json(target / 'readiness.json', report)
    verify_compact(cfg)
    REPORTS.mkdir(parents=True, exist_ok=True)
    with (REPORTS / 'compact_selection.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(membership[0]))
        writer.writeheader(); writer.writerows(membership)
    write_json(REPORTS / 'compact_readiness.json', report)
    return report


if __name__ == '__main__':
    print(json.dumps(prepare(), indent=2))
