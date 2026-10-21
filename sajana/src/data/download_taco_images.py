"""Acquire manifest-matched images from a local TACO folder or source URLs.

Run from the repository root with python -m sajana.src.data.download_taco_images.
Existing files are checked before resuming; failures always return a nonzero exit.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .taco_images import decode_image, save_image, validate_existing

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / 'data/processed/taco_litter_seg'
DEFAULT_OVERRIDES = Path(__file__).resolve().parents[2] / 'configs/taco_orientation_overrides.json'


def acquire_one(row: dict, dataset: Path, image_root: Path, timeout: float,
                quality: int, skip_existing: bool, orientation_overrides: dict = None) -> dict:
    destination = dataset / 'images' / row['split'] / row['flat_file_name']
    width, height = int(row['width']), int(row['height'])
    result = {key: row[key] for key in ('split', 'source_file_name', 'flat_file_name')}
    if skip_existing and validate_existing(destination, width, height):
        return dict(result, status='existing_valid', source=str(destination), error='')
    errors = []
    if image_root:
        candidates = [image_root / row['source_file_name'], image_root / row['flat_file_name'],
                      image_root / 'images' / row['split'] / row['flat_file_name']]
        sources = [str(path) for path in candidates if path.is_file()]
    else:
        sources = list(dict.fromkeys(row.get(key, '') for key in ('flickr_url', 'flickr_640_url')))
        sources = [url for url in sources if url.startswith(('http://', 'https://'))]
    with requests.Session() as session:
        session.headers['User-Agent'] = 'Decentralized-Hiking-AI/Component2 academic research'
        session.mount('https://', HTTPAdapter(max_retries=Retry(total=2, backoff_factor=0.5,
                       status_forcelist=(429, 500, 502, 503, 504))))
        for source in sources:
            try:
                if image_root:
                    content = Path(source).read_bytes()
                else:
                    with session.get(source, timeout=timeout) as response:
                        response.raise_for_status()
                        content = response.content
                override = (orientation_overrides or {}).get(row['source_file_name'])
                policy = None
                if override:
                    if hashlib.sha256(content).hexdigest() != override['source_sha256']:
                        raise ValueError('Reviewed orientation source hash changed; review the new source bytes')
                    policy = override['orientation']
                try:
                    image, action = decode_image(content, width, height, policy)
                except ValueError as exc:
                    if 'EXIF' in str(exc):
                        review = dataset / 'orientation_review' / row['flat_file_name']
                        review.parent.mkdir(parents=True, exist_ok=True)
                        review.write_bytes(content)
                    raise
                save_image(image, destination, quality)
                return dict(result, status='saved', source=source, width=image.width,
                            height=image.height, orientation_action=action, error='')
            except (OSError, ValueError, SyntaxError, requests.RequestException) as exc:
                errors.append(f'{source}: {exc}')
    return dict(result, status='failed', source='', error=' | '.join(errors) or 'No source image found')


def acquire(dataset: Path, image_root: Path = None, timeout: float = 20,
            quality: int = 95, skip_existing: bool = True, workers: int = 4,
            limit: int = None, retry_failures: bool = False,
            orientation_overrides: dict = None) -> list:
    rows = []
    for split in ('train', 'val', 'test'):
        with (dataset / 'manifests' / f'{split}.csv').open(newline='') as stream:
            rows.extend(dict(row, split=split) for row in csv.DictReader(stream))
    for row in rows:
        for key in ('flat_file_name', 'source_file_name'):
            path = Path(row[key])
            if path.is_absolute() or '..' in path.parts or (key == 'flat_file_name' and path.name != row[key]):
                raise ValueError(f'Unsafe manifest path: {row[key]}')
    manifest_total = len(rows)
    expected_keys = {(row['split'], row['flat_file_name']) for row in rows}
    previous = {}
    history = dataset / 'image_acquisition.csv'
    if history.is_file():
        with history.open(newline='') as stream:
            previous = {(row['split'], row['flat_file_name']): row for row in csv.DictReader(stream)
                        if (row['split'], row['flat_file_name']) in expected_keys}
    if retry_failures:
        rows = [row for row in rows if previous.get((row['split'], row['flat_file_name']), {}).get('status') == 'failed']
    if limit:
        grouped = [[row for row in rows if row['split'] == split] for split in ('train', 'val', 'test')]
        rows = [group[index] for index in range(max(map(len, grouped))) for group in grouped if index < len(group)][:limit]
    results = []
    pool = ThreadPoolExecutor(max_workers=workers)
    futures = []
    try:
        futures = [pool.submit(acquire_one, row, dataset, image_root, timeout, quality, skip_existing, orientation_overrides) for row in rows]
        for future in as_completed(futures):
            result = future.result()
            key = (result['split'], result['flat_file_name'])
            if result['status'] == 'existing_valid' and key in previous:
                for field in ('source', 'width', 'height', 'orientation_action'):
                    if previous[key].get(field):
                        result[field] = previous[key][field]
            results.append(result)
            if len(results) % 25 == 0 or len(results) == len(rows):
                print(f'Images checked: {len(results)}/{len(rows)}; failures: '
                      f'{sum(r["status"] == "failed" for r in results)}', flush=True)
    finally:
        # Cancel queued work on interruption; active requests finish within their timeouts.
        pool.shutdown(wait=True, cancel_futures=True)
        dataset.mkdir(parents=True, exist_ok=True)
        previous.update({(row['split'], row['flat_file_name']): row for row in results})
        cumulative = list(previous.values())
        fields = ['split', 'source_file_name', 'flat_file_name', 'status', 'source', 'width', 'height', 'orientation_action', 'error']
        for name, entries in (('image_acquisition.csv', cumulative),
                              ('download_failures.csv', [r for r in cumulative if r['status'] == 'failed'])):
            with (dataset / name).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(sorted(entries, key=lambda r: (r['split'], r['flat_file_name'])))
        scope = {'updated_at_utc': datetime.now(timezone.utc).isoformat(),
                 'manifest_images': manifest_total, 'requested_images': len(rows),
                 'completed_images': len(results), 'limit': limit,
                 'complete_manifest_run': len(results) == manifest_total,
                 'last_run_failures': sum(r['status'] == 'failed' for r in results),
                 'known_failures': sum(r['status'] == 'failed' for r in cumulative),
                 'note': 'Acquisition history is cumulative; run full verification for current readiness.'}
        (dataset / 'image_acquisition_scope.json').write_text(json.dumps(scope, indent=2) + '\n')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--image-root', type=Path, help='Folder containing batch_* source folders; no network when set')
    parser.add_argument('--timeout', type=float, default=20)
    parser.add_argument('--quality', type=int, default=95)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--limit', type=int, help='Acquire only this many images for a smoke check; not training readiness')
    parser.add_argument('--skip-existing', action='store_true')
    parser.add_argument('--retry-failures', action='store_true', help='Retry only known failures from acquisition history')
    parser.add_argument('--orientation-overrides', type=Path, default=DEFAULT_OVERRIDES,
                        help='Reviewed, source-hash-bound raw/exif decisions for ambiguous orientations')
    args = parser.parse_args()
    if args.workers < 1 or args.timeout <= 0 or not 1 <= args.quality <= 100 or (args.limit is not None and args.limit < 1):
        parser.error('workers, timeout and limit must be positive; quality must be 1..100')
    if args.image_root and not args.image_root.is_dir():
        parser.error('--image-root must be an existing folder')
    overrides = json.loads(args.orientation_overrides.read_text()) if args.orientation_overrides.is_file() else {}
    results = acquire(args.dataset, args.image_root, args.timeout, args.quality, args.skip_existing,
                      args.workers, args.limit, args.retry_failures, overrides)
    failures = sum(row['status'] == 'failed' for row in results)
    print(f'{len(results)} images checked; {failures} failed. Run full verification before training.')
    if failures or (not results and not args.retry_failures):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
