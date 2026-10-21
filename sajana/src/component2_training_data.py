"""Freeze verified source-aligned data for the remaining YOLOv8 tasks."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
from pathlib import Path

from .train_yolov8 import ROOT, now, sha256, write_json

CONFIG = ROOT / 'configs/component2_training_queue.json'
PROJECT = ROOT / 'runs/component2_training'


def configuration(path=CONFIG):
    cfg = json.loads(Path(path).read_text())
    for job in cfg['jobs'].values():
        allowed = {'segment': 'yolov8n-seg.pt', 'detect': 'yolov8n.pt'}
        if allowed.get(job['task']) != job['model']:
            raise ValueError('Only the declared YOLOv8 nano task architectures are supported')
    training = cfg['training']
    if (training['batch'] > 2 or training['workers'] != 0 or training['cache'] is not False or
            training['plots'] is not False or training['save_period'] != -1 or training['amp'] is not False):
        raise ValueError('Queue settings exceed the declared memory/storage policy')
    if min(training['epochs'], training['batch'], training['imgsz']) <= 0:
        raise ValueError('Invalid training dimensions or budget')
    return cfg


def rows_for(job, split):
    dataset = ROOT / job['dataset']
    with (dataset/'manifests'/f'{split}.csv').open(newline='') as stream:
        return list(csv.DictReader(stream))


def data_yaml(path, dataset, names, train='images/train', val='images/val'):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = 'path: ' + json.dumps(str(Path(dataset).resolve())) + '\n'
    text += 'train: ' + json.dumps(train) + '\nval: ' + json.dumps(val) + '\nnames:\n'
    text += ''.join(f'  {int(key)}: {json.dumps(value)}\n' for key, value in names.items())
    path.write_text(text)
    return path


def label_count(path, task, names):
    lines = [line.split() for line in Path(path).read_text().splitlines() if line.strip()]
    for line in lines:
        values = [float(v) for v in line]
        if not all(math.isfinite(v) for v in values) or str(int(values[0])) not in names or values[0] != int(values[0]):
            raise ValueError('Nonfinite or unexpected class in ' + str(path))
        if task == 'detect':
            if len(values) != 5 or any(v < 0 or v > 1 for v in values[1:]) or min(values[3:]) <= 0:
                raise ValueError('Invalid detection box: ' + str(path))
        elif len(values) < 7 or len(values) % 2 != 1 or any(v < 0 or v > 1 for v in values[1:]):
            raise ValueError('Invalid segmentation polygon: ' + str(path))
    return len(lines)


def freeze(job_id, cfg=None):
    cfg = cfg or configuration()
    job = cfg['jobs'][job_id]; dataset = ROOT / job['dataset']
    readiness = json.loads((ROOT/job['readiness']).read_text())
    if not readiness.get('training_ready'):
        raise ValueError('Source readiness gate failed: ' + job_id)
    source_evidence = {}
    if job_id == 'L2':
        from .data.build_litter_aux_combined import TACO, MJU, TACO_SOURCE, MJU_SOURCE, verify_taco, verify_mju
        for name, audit in [('taco', verify_taco(TACO, labels_only=True, annotations=TACO_SOURCE)),
                            ('mju', verify_mju(MJU, MJU_SOURCE, labels_only=True))]:
            if not audit['passed']:
                raise ValueError('Current source annotation/label audit failed: ' + name)
            source_evidence[name] = audit
    else:
        certificate = ROOT/'results/wildscenes_preprocessing/local_readiness.json'
        if sha256(certificate) != readiness['source_certificate_sha256']:
            raise ValueError('WildScenes source certificate differs from the box-export audit')
        if readiness.get('names') != job['names'] or not readiness.get('source_split_membership_preserved'):
            raise ValueError('WildScenes mapping/split gate failed')
        source_evidence['wildscenes_certificate_sha256'] = sha256(certificate)
    inventory, counts, seen, memberships = {}, {}, {}, {}
    for split, expected in job['expected'].items():
        rows = rows_for(job, split); inventory[split] = {}; total = 0
        expected_names = {r['flat_file_name'] for r in rows}
        if len(expected_names) != len(rows) or len(rows) != expected[0]:
            raise ValueError('Manifest count/uniqueness mismatch: ' + split)
        for kind, suffix in [('images', None), ('labels', '.txt')]:
            expected_files = {Path(n).with_suffix(suffix).name if suffix else n for n in expected_names}
            actual = {p.name for p in (dataset/kind/split).iterdir() if p.is_file() and not p.name.startswith('.')}
            if actual != expected_files:
                raise ValueError('Dataset membership mismatch: ' + kind + '/' + split)
        if job_id == 'O1':
            with (ROOT/'data/processed/wildscenes_terrain_semantic/manifests'/f'{split}.csv').open() as stream:
                native = {r['id']: r for r in csv.DictReader(stream)}
            if {r['source_id'] for r in rows} != set(native):
                raise ValueError('Derived boxes differ from the certified source split')
        for index, row in enumerate(rows, 1):
            name = row['flat_file_name']
            if Path(name).name != name:
                raise ValueError('Unsafe flat filename')
            image = dataset/'images'/split/name; label = dataset/'labels'/split/Path(name).with_suffix('.txt')
            image_hash, label_hash = sha256(image), sha256(label)
            count = label_count(label, job['task'], job['names']); total += count
            if job_id == 'L2':
                source_name = row['source_dataset']
                if source_name not in ('taco', 'mju') or (split != 'train' and source_name != 'taco') or row['source_split'] != split:
                    raise ValueError('Auxiliary source/split policy changed')
                source_root = ROOT/'data/processed'/('taco_litter_seg_clean' if source_name == 'taco' else 'mju_waste_litter_seg')
                source_name_file = row['source_file_name']
                source_image = source_root/'images'/split/source_name_file
                source_label = source_root/'labels'/split/Path(source_name_file).with_suffix('.txt')
                if name != row['source_dataset']+'__'+source_name_file:
                    raise ValueError('Combined source identity mismatch')
                if image_hash != sha256(source_image) or label_hash != sha256(source_label) or label_hash != row['source_label_sha256']:
                    raise ValueError('Combined pair differs from certified source: ' + name)
                if count != int(row['object_count']):
                    raise ValueError('Combined instance count mismatch')
                # Fresh decoded-pixel check covers cross-source as well as cross-split leakage.
                from PIL import Image
                with Image.open(image) as im:
                    im.load()
                    if im.getexif().get(274, 1) != 1 or im.size != (int(row['width']), int(row['height'])):
                        raise ValueError('Combined geometry/orientation mismatch')
                    rgb = im.convert('RGB')
                    pixel_hash = hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest()
            else:
                original = native[row['source_id']]
                if (image_hash != row['source_image_sha256'] or label_hash != row['label_sha256'] or
                        row['flat_file_name'] != original['flat_file_name'] or
                        row['source_mask_pixel_sha256'] != original['mask_pixel_sha256'] or
                        image_hash != original['source_image_sha256'] or count != int(row['region_boxes'])):
                    raise ValueError('Certified rock/log export changed: ' + name)
                pixel_hash = original['image_pixel_sha256']
            if pixel_hash in seen and seen[pixel_hash] != split:
                raise ValueError('Identical decoded images cross splits')
            seen[pixel_hash] = split
            inventory[split][image.relative_to(dataset).as_posix()] = image_hash
            inventory[split][label.relative_to(dataset).as_posix()] = label_hash
            if index % 500 == 0:
                print(f'{job_id} {split}: {index}/{len(rows)} frozen pairs', flush=True)
        if total != expected[1]:
            raise ValueError('Verified instance total mismatch: ' + split)
        counts[split] = {'images': len(rows), 'objects': total}
        manifest = dataset/'manifests'/f'{split}.csv'
        memberships[split] = sha256(manifest)
    out = PROJECT/'preflight'/job_id; out.mkdir(parents=True, exist_ok=True)
    write_json(out/'dataset_hashes.json', inventory)
    write_json(out/'source_audits.json', source_evidence)
    report = {'checked_at': now(), 'job': job_id, 'passed': True, 'training_ready': True,
              'dataset': str(dataset), 'splits': counts, 'manifest_sha256': memberships,
              'readiness_sha256': sha256(ROOT/job['readiness']), 'source_tasks_kept_separate': True,
              'frozen_current_pairs': True, 'test_model_evaluation_performed': False,
              'image_policy': ('Fresh RGB geometry/orientation and cross-split decoded-pixel checks' if job_id == 'L2' else
                               'All current image/label bytes match the saved full source/derived certificates; certified pixel hashes and author membership retained'),
              'limitations': job.get('limitations', [])}
    write_json(out/'preflight.json', report)
    return report


def check_frozen(job_id, cfg=None):
    cfg = cfg or configuration(); job = cfg['jobs'][job_id]
    preflight = PROJECT/'preflight'/job_id
    report = json.loads((preflight/'preflight.json').read_text())
    if not report['passed'] or report['readiness_sha256'] != sha256(ROOT/job['readiness']):
        raise ValueError('Prepared certificate changed; repeat preflight')
    dataset = ROOT/job['dataset']
    for split, entries in json.loads((preflight/'dataset_hashes.json').read_text()).items():
        if sha256(dataset/'manifests'/f'{split}.csv') != report['manifest_sha256'][split]:
            raise ValueError('Frozen manifest changed: '+split)
        for relative, expected in entries.items():
            if sha256(dataset/relative) != expected:
                raise ValueError('Frozen training input changed: '+relative)
    return report


def smoke_data(job, output, count=8):
    dataset = ROOT/job['dataset']; rows = rows_for(job, 'train')
    selected = []
    # Include each target class and background when present, then spread samples.
    for class_id in job['names']:
        candidate = next((r for r in rows if any(line.split()[0] == class_id for line in
                         (dataset/'labels/train'/Path(r['flat_file_name']).with_suffix('.txt')).read_text().splitlines())), None)
        if candidate and candidate not in selected:
            selected.append(candidate)
    background = next((r for r in rows if not (dataset/'labels/train'/Path(r['flat_file_name']).with_suffix('.txt')).read_text().strip()), None)
    if background and background not in selected:
        selected.append(background)
    for i in range(count):
        candidate = rows[round(i*(len(rows)-1)/max(1,count-1))]
        if candidate not in selected:
            selected.append(candidate)
        if len(selected) == count:
            break
    for row in selected:
        name = row['flat_file_name']
        for kind, filename in [('images', name), ('labels', Path(name).with_suffix('.txt').name)]:
            target = Path(output)/kind/'train'/filename; target.parent.mkdir(parents=True, exist_ok=True)
            source = dataset/kind/'train'/filename
            if not target.exists():
                try:
                    os.link(source, target)
                except OSError:
                    shutil.copyfile(source, target)
    return data_yaml(Path(output)/'data.yaml', output, job['names'], val='images/train'), len(selected)
