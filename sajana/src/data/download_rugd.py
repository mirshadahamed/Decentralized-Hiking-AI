"""Resume official RUGD RGB/semantic annotation archives and safely extract data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import time
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath

from .preprocess_mju_waste import ROOT, sha256, write_json

RAW = ROOT / 'data/raw/rugd'
URLS = {
    'annotations': 'http://rugd.vision/data/RUGD_annotations.zip',
    'frames': 'http://rugd.vision/data/RUGD_frames-with-annotations.zip',
}


def ranged_download(url, target, workers=24, chunk_size=4 * 1024 * 1024):
    """Use the same official public S3 bucket, with checked resumable byte ranges."""
    import requests

    target = Path(target)
    if target.is_file():
        return download(url, target)
    transport = url.replace('http://rugd.vision/', 'https://s3.amazonaws.com/rugd.vision/')
    response = requests.get(transport, headers={'Range': 'bytes=0-0', 'Accept-Encoding': 'identity'}, timeout=(20, 45))
    response.raise_for_status()
    match = re.fullmatch(r'bytes 0-0/(\d+)', response.headers.get('Content-Range', ''))
    if response.status_code != 206 or not match or len(response.content) != 1:
        raise ValueError('Official S3 endpoint did not honor exact range probe')
    total, etag = int(match.group(1)), response.headers.get('ETag')
    cache = target.with_name(target.name + '.ranges')
    cache.mkdir(parents=True, exist_ok=True)
    state_path = cache / 'state.json'
    identity = {'source_url': url, 'transport_url': transport, 'bytes': total, 'etag': etag, 'chunk_size': chunk_size}
    state = json.loads(state_path.read_text()) if state_path.exists() else dict(identity, completed={})
    if any(state.get(k) != v for k, v in identity.items()):
        raise ValueError('Range cache belongs to another source version or chunk size')
    jobs = [(start, min(total - 1, start + chunk_size - 1)) for start in range(0, total, chunk_size)]

    def fetch(pair):
        start, end = pair
        key = f'{start}-{end}'
        path = cache / (key + '.part')
        expected = state['completed'].get(key)
        if expected and path.is_file() and path.stat().st_size == end - start + 1 and sha256(path) == expected:
            return key, expected
        last = None
        for attempt in range(3):
            try:
                result = requests.get(transport, headers={'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'}, timeout=(20, 90))
                result.raise_for_status()
                if result.status_code != 206 or result.headers.get('Content-Range') != f'bytes {start}-{end}/{total}':
                    raise ValueError('Range response offset/total mismatch')
                if etag and result.headers.get('ETag') != etag:
                    raise ValueError('Archive ETag changed during download')
                if len(result.content) != end - start + 1:
                    raise ValueError('Range body length mismatch')
                temporary = path.with_name(path.name + '.tmp')
                temporary.write_bytes(result.content)
                temporary.replace(path)
                return key, hashlib.sha256(result.content).hexdigest()
            except (OSError, ValueError, requests.RequestException) as exc:
                last = exc
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
        raise RuntimeError(f'Range {key} failed after 3 attempts: {last}')

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch, pair) for pair in jobs]
        errors = []
        for index, future in enumerate(as_completed(futures), 1):
            try:
                key, digest = future.result()
                state['completed'][key] = digest
            except Exception as exc:
                errors.append(str(exc))
            if index % 16 == 0 or index == len(jobs):
                write_json(state_path, state)
                print(f'RUGD {target.name}: {len(state["completed"])}/{len(jobs)} verified ranges', flush=True)
        if errors:
            raise RuntimeError('; '.join(errors[:4]))
    assembled = target.with_name(target.name + '.assembling')
    with assembled.open('wb') as output:
        for start, end in jobs:
            with (cache / f'{start}-{end}.part').open('rb') as source:
                while True:
                    data = source.read(1024 * 1024)
                    if not data:
                        break
                    output.write(data)
    if assembled.stat().st_size != total or not zipfile.is_zipfile(assembled):
        raise ValueError('Assembled ranges are not a complete ZIP archive')
    assembled.replace(target)
    return dict(identity, path=str(target), sha256=sha256(target), reused=False, verified_ranges=len(jobs))


def official_frames_index(raw):
    """Read the primary ZIP central directory without claiming a full archive."""
    import requests
    raw = Path(raw)
    inventory = raw / 'official_frames_index.json'
    if inventory.is_file():
        return json.loads(inventory.read_text())
    transport = 'https://s3.amazonaws.com/rugd.vision/data/RUGD_frames-with-annotations.zip'
    response = requests.get(transport, headers={'Range': 'bytes=0-0', 'Accept-Encoding': 'identity'}, timeout=(20, 45))
    response.raise_for_status()
    match = re.fullmatch(r'bytes 0-0/(\d+)', response.headers.get('Content-Range', ''))
    if response.status_code != 206 or not match:
        raise ValueError('Primary archive index probe did not honor Range')
    total = int(match.group(1))
    start = max(0, total - 2 * 1024 * 1024)
    tail = requests.get(transport, headers={'Range': f'bytes={start}-{total-1}', 'Accept-Encoding': 'identity'}, timeout=(20, 90))
    tail.raise_for_status()
    if tail.status_code != 206 or tail.headers.get('Content-Range') != f'bytes {start}-{total-1}/{total}' or len(tail.content) != total-start:
        raise ValueError('Primary archive index range mismatch')
    cache = raw / 'archives/rugd_frames_source_index.zip'
    cache.parent.mkdir(parents=True, exist_ok=True)
    with cache.open('wb') as f:
        f.truncate(total)
        f.seek(start)
        f.write(tail.content)
    with zipfile.ZipFile(cache) as z:
        infos = [row for row in z.infolist() if selected(row) and row.filename.endswith('.png')]
    result = {'canonical_url': URLS['frames'], 'transport_url': transport, 'official_archive_bytes': total,
              'etag': tail.headers.get('ETag'), 'index_only_sparse_cache': True,
              'files': [{'path': row.filename, 'bytes': row.file_size, 'crc32': f'{row.CRC:08x}'} for row in infos]}
    if len(result['files']) != 7436:
        raise ValueError('Official source photo inventory changed; review new release before downloading')
    write_json(inventory, result)
    return result


def mirror_frames(raw, workers=24):
    """Use pinned public mirror files only when exact primary size/CRC matches."""
    import requests
    raw = Path(raw)
    index = official_frames_index(raw)
    repo = 'WilliamBonilla62/RUGD'
    metadata = requests.get('https://huggingface.co/api/datasets/' + repo, timeout=(20, 45))
    metadata.raise_for_status()
    revision = metadata.json()['sha']
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Unexpected mirror revision')
    extracted = raw / 'extracted'
    entries, errors = [], []
    prior = raw / 'mirror_progress.json'

    def fetch(row):
        relative = PurePosixPath(row['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'RUGD_frames-with-annotations' or relative.suffix != '.png':
            raise ValueError('Unsafe/unexpected source photo index entry')
        path = extracted.joinpath(*relative.parts)
        last = None
        if path.is_file():
            data = path.read_bytes()
            if len(data) == row['bytes'] and f'{zlib.crc32(data):08x}' == row['crc32']:
                return dict(row, sha256=hashlib.sha256(data).hexdigest())
        url = f'https://huggingface.co/datasets/{repo}/resolve/{revision}/{row["path"]}'
        for attempt in range(3):
            try:
                response = requests.get(url, timeout=(20, 90))
                response.raise_for_status()
                data = response.content
                if len(data) != row['bytes'] or f'{zlib.crc32(data):08x}' != row['crc32']:
                    raise ValueError('Mirror file does not match exact official ZIP size/CRC')
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.name + '.part')
                temporary.write_bytes(data)
                temporary.replace(path)
                return dict(row, sha256=hashlib.sha256(data).hexdigest())
            except (OSError, ValueError, requests.RequestException) as exc:
                last = exc
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
        raise RuntimeError(f'{row["path"]}: {last}')

    acquisition = {'canonical_url': URLS['frames'], 'transport_url': f'https://huggingface.co/datasets/{repo}',
                   'mirror_revision': revision, 'method': 'pinned_original_PNG_mirror_verified_against_primary_ZIP_filename_size_CRC',
                   'official_archive_complete': False, 'official_archive_index_verified': True}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch, row) for row in index['files']]
        for i, future in enumerate(as_completed(futures), 1):
            try:
                entries.append(future.result())
            except Exception as exc:
                errors.append(str(exc))
            if i % 100 == 0 or i == len(futures):
                write_json(prior, dict(acquisition, complete=not errors and len(entries) == len(futures),
                                      completed_files=len(entries), expected_files=len(futures), errors=errors[:20]))
                print(f'RUGD mirror: {len(entries)}/{len(futures)} exact-source photos verified; {len(errors)} failures', flush=True)
    if errors:
        raise RuntimeError(f'{len(errors)} mirror photos failed; matching completed files retained: {errors[:3]}')
    write_json(raw / 'frames_inventory.json', {'archive': acquisition, 'files': sorted(entries, key=lambda row: row['path'])})
    return dict(acquisition, extracted_files=len(entries))


def selected(info):
    """Reject unsafe names and links; extract only photos, masks and label text."""
    path = PurePosixPath(info.filename)
    if path.is_absolute() or '..' in path.parts or '\\' in info.filename:
        raise ValueError(f'Unsafe archive path: {info.filename}')
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError(f'Archive symlink is not allowed: {info.filename}')
    if info.is_dir():
        return False
    if info.file_size > 64 * 1024 * 1024:
        raise ValueError(f'Unexpectedly large image/metadata member: {info.filename}')
    return path.suffix.lower() in {'.png', '.jpg', '.jpeg'} or (
        path.suffix.lower() == '.txt' and any(token in path.name.lower() for token in ('color', 'label', 'readme', 'license'))
    )


def extract(archive, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    with zipfile.ZipFile(archive) as z:
        if len(z.infolist()) > 30000:
            raise ValueError('Unexpected archive member count')
        infos = [info for info in z.infolist() if selected(info)]
        names = [info.filename for info in infos]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate archive member names')
        for info in infos:
            target = destination.joinpath(*PurePosixPath(info.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            # Reading through ZipFile verifies the stored CRC for every extracted member.
            data = z.read(info)
            if not target.is_file() or target.read_bytes() != data:
                tmp = target.with_name(target.name + '.part')
                tmp.write_bytes(data)
                tmp.replace(target)
            rows.append({'path': target.relative_to(destination).as_posix(), 'bytes': info.file_size,
                         'crc32': f'{info.CRC:08x}', 'sha256': hashlib.sha256(data).hexdigest()})
    return rows


def download(url, target, attempts=3):
    import requests

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if zipfile.is_zipfile(target):
            return {'url': url, 'path': str(target), 'bytes': target.stat().st_size, 'sha256': sha256(target), 'reused': True}
        raise ValueError(f'Existing final archive is invalid: {target}')
    part = target.with_name(target.name + '.part')
    last = None
    for attempt in range(attempts):
        try:
            offset = part.stat().st_size if part.exists() else 0
            headers = {'Accept-Encoding': 'identity'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            with requests.get(url, headers=headers, stream=True, timeout=(25, 90)) as response:
                if offset and response.status_code == 206:
                    value = response.headers.get('Content-Range', '')
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', value)
                    if not match or int(match.group(1)) != offset:
                        raise ValueError(f'Invalid resume Content-Range: {value}')
                    total = int(match.group(3))
                    mode = 'ab'
                elif response.status_code == 200:
                    # Servers may ignore Range. Restart instead of appending a full file.
                    total = int(response.headers['Content-Length'])
                    offset = 0
                    mode = 'wb'
                elif response.status_code == 416 and part.is_file() and zipfile.is_zipfile(part):
                    part.replace(target)
                    return {'url': url, 'path': str(target), 'bytes': target.stat().st_size, 'sha256': sha256(target), 'reused': True}
                else:
                    response.raise_for_status()
                    raise ValueError(f'Unexpected download status {response.status_code}')
                written = offset
                last_progress = offset // (128 * 1024 * 1024)
                with part.open(mode) as f:
                    for chunk in response.iter_content(1024 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        written += len(chunk)
                        progress = written // (128 * 1024 * 1024)
                        if progress != last_progress:
                            print(f'RUGD {target.name}: {written}/{total} bytes', flush=True)
                            last_progress = progress
                if written != total:
                    raise ValueError(f'Download length {written} != expected {total}')
                if not zipfile.is_zipfile(part):
                    raise ValueError('Downloaded response is not a complete ZIP archive')
                part.replace(target)
                return {'url': url, 'path': str(target), 'bytes': written, 'sha256': sha256(target), 'reused': False,
                        'etag': response.headers.get('ETag'), 'last_modified': response.headers.get('Last-Modified')}
        except (OSError, ValueError, requests.RequestException) as exc:
            last = exc
            print(f'RUGD download attempt {attempt + 1}/{attempts}: {exc}', flush=True)
            if attempt + 1 < attempts:
                time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f'Unable to finish {url}; resumable .part retained: {last}')


def run(raw=RAW, only=None, workers=24, use_mirror=False):
    raw = Path(raw).resolve()
    report = {'complete': False, 'official_page': 'http://rugd.vision/', 'archives': {}, 'extraction_crc_checked': False}
    try:
        for name, url in URLS.items():
            if only and name != only:
                continue
            if name == 'frames' and use_mirror:
                report['archives'][name] = mirror_frames(raw, workers=workers)
            else:
                archive = raw / 'archives' / Path(url).name
                report['archives'][name] = ranged_download(url, archive, workers=workers)
                print(f'RUGD: extracting {name} archive with CRC verification', flush=True)
                inventory = extract(archive, raw / 'extracted')
                write_json(raw / f'{name}_inventory.json', {'archive': report['archives'][name], 'files': inventory})
                report['archives'][name]['extracted_files'] = len(inventory)
            write_json(raw / 'download_status.json', report)
        report['complete'] = all((raw / f'{name}_inventory.json').is_file() for name in URLS)
        report['extraction_crc_checked'] = True
        report['requested_archives_complete'] = True
    except Exception as exc:
        report['error'] = str(exc)
        write_json(raw / 'download_status.json', report)
        raise
    write_json(raw / 'download_status.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, default=RAW)
    parser.add_argument('--only', choices=list(URLS))
    parser.add_argument('--workers', type=int, default=24)
    parser.add_argument('--mirror-frames', action='store_true', help='Use pinned exact-original photo mirror with primary ZIP size/CRC verification')
    args = parser.parse_args()
    print(json.dumps(run(args.raw_root, args.only, args.workers, args.mirror_frames), indent=2))


if __name__ == '__main__':
    main()
