"""Select a bounded, source-label-only GOOSE inventory before any model fitting."""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import io
import json
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

from .selective_zip import fetch_indexed_member
from ..train_yolov8 import ROOT, now, write_json

BASE = ROOT / 'data/raw/component2_cycle2_sources'
TARGET_IDS = {4: 'obstacle_region', 29: 'debris_region', 40: 'rock',
              62: 'tree_root_region', 28: 'tree_trunk'}


def jobs_per_sequence(per_sequence, include_ex=False):
    chosen = []
    splits = ('train', 'val', 'ex_train', 'ex_val') if include_ex else ('train', 'val')
    for split in splits:
        index = json.loads((BASE / f'goose_{split}_index.json').read_text())
        groups = collections.defaultdict(list)
        for entry in index['entries']:
            if entry['name'].endswith('_labelids.png'):
                groups[Path(entry['name']).parent.name].append(entry)
        for sequence, entries in sorted(groups.items()):
            entries.sort(key=lambda e: e['name'])
            count = min(per_sequence, len(entries))
            selected = sorted({round(i*(len(entries)-1)/max(1, count-1)) for i in range(count)})
            chosen.extend((split, index, entries[i]) for i in selected)
    return chosen


def scan(job):
    split, index, entry = job
    path = BASE / 'goose_selected' / entry['name']
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        body = path.read_bytes()
        if len(body) != entry['bytes'] or zlib.crc32(body) & 0xffffffff != entry['crc']:
            raise ValueError('Cached source label changed')
    else:
        body = fetch_indexed_member(index, entry)
        path.write_bytes(body)
    with Image.open(io.BytesIO(body)) as im:
        array = np.asarray(im)
        if array.ndim != 2 or int(array.max()) > 63:
            raise ValueError('Not the native 64-class semantic mask')
        counts = collections.Counter(map(int, array.reshape(-1)))
        return {'source_split': split, 'sequence': Path(entry['name']).parent.name,
                'member': entry['name'], 'sha256': hashlib.sha256(body).hexdigest(),
                'width': im.width, 'height': im.height, 'pixels': dict(counts),
                'source_crc32': entry['crc']}


def audit(per_sequence=24, include_ex=False, roots_expand=False):
    jobs = jobs_per_sequence(per_sequence, include_ex=include_ex)
    suffix = '_with_ex' if include_ex else ''
    output = BASE / f'goose_labels_{per_sequence}{suffix}.json'
    if roots_expand:
        pilot = json.loads((BASE / 'goose_labels_48_with_ex.json').read_text())
        groups = {r['sequence'] for r in pilot if int(r['pixels'].get('62', 0)) > 0}
        jobs = [job for job in jobs_per_sequence(10000) if Path(job[2]['name']).parent.name in groups]
        output = BASE / 'goose_root_expansion.json'
    print(f'Label-only inventory: {len(jobs)} masks; no RGB photos yet.', flush=True)
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for row in pool.map(scan, jobs):
            rows.append(row)
            if len(rows) % 50 == 0:
                print(f'Scanned {len(rows)}/{len(jobs)} native masks', flush=True)
    write_json(output, rows)
    counts = {}
    for class_id, name in TARGET_IDS.items():
        positive = [r for r in rows if r['pixels'].get(class_id, 0) > 0]
        counts[name] = {'positive_images': len(positive), 'sequences': dict(
            collections.Counter(r['sequence'] for r in positive))}
    report = {'checked_at': now(), 'label_inventory': str(output), 'photos_scanned': len(rows),
              'rgb_downloaded_in_this_step': False, 'selection_uses_model_predictions': False,
              'class_coverage': counts, 'full_component_ready': False}
    report_name = 'root_source_coverage.json' if roots_expand else 'source_label_coverage.json'
    write_json(ROOT / 'results/component2_cycle2' / report_name, report)
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--per-sequence', type=int, default=24)
    parser.add_argument('--include-ex', action='store_true')
    parser.add_argument('--roots-expand', action='store_true')
    args = parser.parse_args()
    audit(args.per_sequence, include_ex=args.include_ex, roots_expand=args.roots_expand)
