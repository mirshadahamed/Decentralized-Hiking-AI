"""Audit source-labelled garbage negatives; do not assume coarse labels are exhaustive."""
from __future__ import annotations

import collections
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from ..train_yolov8 import ROOT, now, write_json
from .selective_zip import safe_member

BASE = ROOT / 'data/raw/component2_cycle2_sources'


def normalized_path(path):
    return path.replace('\\', '/').casefold()


def perceptual_hash(image):
    array = np.asarray(image.convert('L').resize((32, 32), Image.Resampling.LANCZOS), dtype=np.float32)
    values = cv2.dct(array)[:8, :8].reshape(-1)
    bits = values > np.median(values[1:])
    return int.from_bytes(np.packbits(bits).tobytes(), 'big')


def audit():
    metadata = list(csv.DictReader((BASE / 'Metadata.csv').open()))
    expected = {normalized_path(r['image_id']): r for r in metadata}
    archive_path = BASE / 'Urban Waste Dataset for Pakistan.zip'
    rows = []
    with zipfile.ZipFile(archive_path) as archive:
        names = sorted(n for n in archive.namelist() if n.lower().endswith(('.jpg', '.jpeg', '.png')))
        if len(names) != len(expected):
            raise ValueError('Photo count differs from source metadata')

        def check(name):
            safe_member(name)
            relative = '/'.join(name.split('/')[1:])
            record = expected[normalized_path(relative)]
            body = archive.read(name)
            with Image.open(io.BytesIO(body)) as source:
                if source.size != (int(record['width']), int(record['height'])):
                    raise ValueError('Source metadata image geometry differs')
                rgb = ImageOps.exif_transpose(source).convert('RGB')
                return {'member': name, 'source_split': record['split'],
                        'source_label': record['label'], 'source_image_sha256': hashlib.sha256(body).hexdigest(),
                        'pixel_sha256': hashlib.sha256(rgb.tobytes()).hexdigest(),
                        'phash': f'{perceptual_hash(rgb):016x}', 'width': rgb.width, 'height': rgb.height}

        # Python 3.9.6's shared ZipFile reader can race under concurrent reads.
        # Keep decompression sequential so a correct source never becomes corrupt.
        for name in names:
            rows.append(check(name))
    # Conservative near-duplicate clusters: <=4 bits in a 64-bit perceptual hash.
    # Five disjoint hash bands ensure all pairs within radius four are candidates.
    parents = list(range(len(rows)))

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    bands, exact = collections.defaultdict(list), {}
    for i, row in enumerate(rows):
        value = int(row['phash'], 16)
        candidates = set()
        for j in range(5):
            key = (j, (value >> (j * 13)) & 8191)
            candidates.update(bands[key]); bands[key].append(i)
        if row['pixel_sha256'] in exact:
            candidates.add(exact[row['pixel_sha256']])
        exact[row['pixel_sha256']] = i
        for other in candidates:
            if bin(value ^ int(rows[other]['phash'], 16)).count('1') <= 4 or row['pixel_sha256'] == rows[other]['pixel_sha256']:
                parents[find(i)] = find(other)
    groups = collections.defaultdict(list)
    for i in range(len(rows)):
        groups[find(i)].append(i)
    conflicts, cross_split = 0, 0
    for members in groups.values():
        labels = {rows[i]['source_label'].casefold() for i in members}
        splits = {rows[i]['source_split'] for i in members}
        reasons = []
        if len(labels) > 1:
            reasons.append('conflicting source labels in exact/near-duplicate cluster'); conflicts += len(members)
        if len(splits) > 1:
            reasons.append('source cross-split duplicate/near-duplicate cluster'); cross_split += len(members)
        cluster_id = min(rows[i]['source_image_sha256'] for i in members)
        for i in members:
            rows[i]['duplicate_group'] = cluster_id
            rows[i]['quarantine_reasons'] = reasons
            rows[i]['eligible_for_visual_review'] = not reasons
    write_json(BASE / 'urban_verified_inventory.json', rows)
    report = {'checked_at': now(), 'source': 'Urban Waste Dataset for Pakistan',
              'official_record': 'https://zenodo.org/records/17025661', 'licence': 'CC BY 4.0',
              'actual_metadata_and_archive_photos': len(rows), 'description_claims_photos': 3693,
              'description_count_differs_from_verified_archive': len(rows) != 3693,
              'source_split_counts': dict(collections.Counter(r['source_split'] for r in rows)),
              'conflicting_label_cluster_photos': conflicts, 'cross_split_cluster_photos': cross_split,
              'review_eligible_negatives': dict(collections.Counter(r['source_split'] for r in rows
                  if r['eligible_for_visual_review'] and r['source_label'].casefold() == 'not garbage')),
              'negative_labels_are_exhaustive_litter_masks': False,
              'coarse_negative_cannot_enter_segmentation_without_visual_review': True,
              'training_ready': False, 'full_component_ready': False}
    write_json(ROOT / 'results/component2_cycle2/urban_source_audit.json', report)
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == '__main__':
    audit()
