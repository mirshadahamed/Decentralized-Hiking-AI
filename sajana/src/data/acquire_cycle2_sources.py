"""Acquire small pinned supplements and index large GOOSE archives selectively."""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

from .selective_zip import open_remote, read_member
from ..train_yolov8 import ROOT, now, sha256, write_json

BASE = ROOT / 'data/raw/component2_cycle2_sources'
URBAN = 'https://zenodo.org/api/records/17025661'
MOBIMA = 'https://radar.kit.edu/radar-backend/archives/glefEuwTUORWTWLs/versions/1/content'
URBAN_MD5 = '0784035419d611de391a4244e04900fd'
MOBIMA_MD5 = '5ed4d87b70ca10d00f6ef8ad5f0abef7'


def bounded_download(url, path, maximum_bytes, md5=None):
    path = Path(path)
    if path.exists():
        if path.stat().st_size <= maximum_bytes and (not md5 or hashlib.md5(path.read_bytes()).hexdigest() == md5):
            return
        raise ValueError('Existing source differs from the pinned release: ' + path.name)
    temp = path.with_suffix(path.suffix + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': 'Component2-research-dataset-acquisition'})
    count, digest = 0, hashlib.md5()
    with urllib.request.urlopen(request, timeout=180) as response, temp.open('wb') as stream:
        while True:
            body = response.read(1024 * 1024)
            if not body:
                break
            count += len(body)
            if count > maximum_bytes:
                raise ValueError('Source exceeds transfer budget')
            stream.write(body); digest.update(body)
    if md5 and digest.hexdigest() != md5:
        raise ValueError('Provider source checksum failed')
    temp.replace(path)


def acquire():
    BASE.mkdir(parents=True, exist_ok=True)
    metadata = BASE / 'urban_waste.txt'
    if not metadata.exists():
        bounded_download(URBAN, metadata, 2_000_000)
    urban = json.loads(metadata.read_text())
    if urban['metadata'].get('license', {}).get('id') != 'cc-by-4.0':
        raise ValueError('Urban dataset reuse terms differ from the verified release')
    for item in urban['files']:
        if Path(item['key']).name != item['key']:
            raise ValueError('Unsafe release filename')
        expected = item['checksum'].removeprefix('md5:')
        if item['key'].endswith('.zip') and expected != URBAN_MD5:
            raise ValueError('Urban archive changed from the reviewed release')
        bounded_download(item['links']['self'], BASE / item['key'], item['size'], expected)
    bounded_download(MOBIMA, BASE / 'MobimaSkidRoads.tar', 109_332_480, MOBIMA_MD5)
    archives = {}
    for key in ('train', 'val', 'ex_train', 'ex_val'):
        path = BASE / f'goose_{key}_index.json'
        if not path.exists():
            kind = 'gooseEx' if key.startswith('ex_') else 'goose'
            split = key.removeprefix('ex_')
            url = f'https://goose-dataset.de/storage/{kind}_2d_{split}.zip'
            reader, archive = open_remote(url, budget=10_000_000)
            entries = [{'name': i.filename, 'bytes': i.file_size, 'compressed': i.compress_size,
                        'offset': i.header_offset, 'crc': i.CRC} for i in archive.infolist() if not i.is_dir()]
            write_json(path, {'url': url, 'archive_bytes': reader.length, 'etag': reader.etag, 'entries': entries})
            for entry in entries:
                if Path(entry['name']).name in ('LICENSE', 'goose_label_mapping.csv'):
                    (BASE / ('goose_' + Path(entry['name']).name)).write_bytes(read_member(archive, entry['name']))
        index = json.loads(path.read_text())
        archives[key] = {'url': index['url'], 'archive_bytes': index['archive_bytes'],
                         'etag': index['etag'], 'local_index_sha256': sha256(path)}
    registry = {'acquired_at': now(), 'goose': {'homepage': 'https://goose-dataset.de/',
        'licence': 'CC BY-SA 4.0', 'archives': archives,
        'policy': 'Download selected native semantic/instance masks and RGB records only; never the full archives',
        'target_ids': {'4': 'obstacle_region', '28': 'tree_trunk', '29': 'debris_region',
                       '40': 'rock', '62': 'tree_root_region'},
        'void_ids': [0, 8, 56], 'blockage_ground_truth': False, 'erosion_ground_truth': False},
        'urban_waste': {'homepage': 'https://zenodo.org/records/17025661',
            'citation': 'Mahmood, I. (2025). Garbage Detection Dataset for Pakistan. DOI:10.5281/zenodo.17025661',
            'licence': 'CC BY 4.0', 'archive_md5': URBAN_MD5,
            'archive_sha256': sha256(BASE / 'Urban Waste Dataset for Pakistan.zip'),
            'metadata_sha256': sha256(BASE / 'Metadata.csv'),
            'policy': 'Coarse classification labels; source-labelled negatives require explicit visual review before empty segmentation labels'},
        'mobima': {'homepage': 'https://publikationen.bibliothek.kit.edu/1000162515',
            'doi': '10.35097/1750', 'licence': 'CC BY-SA 4.0', 'archive_md5': MOBIMA_MD5,
            'archive_sha256': sha256(BASE / 'MobimaSkidRoads.tar'),
            'photos': 293, 'classes': ['stem', 'tree', 'stump', 'obstacle', 'person'],
            'policy': 'Acquired and verified; not merged into a rock/log head or treated as garbage-negative',
            'included_in_current_training': False},
        'previous_public_test_reuse_for_tuning': False, 'target_active_profile_photos': 2000,
        'full_component_ready': False}
    write_json(ROOT / 'results/component2_cycle2/source_registry.json', registry)
    print('Verified pinned Urban/Mobima archives and four selective GOOSE indexes.', flush=True)
    return registry


if __name__ == '__main__':
    acquire()
