"""Acquire official WildScenes 2D RGB/index masks using public CSIRO S3 access."""
from __future__ import annotations
import argparse
import concurrent.futures
import csv
import datetime
import hashlib
import hmac
import json
import itertools
import re
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
import requests
from .preprocess_mju_waste import ROOT, write_json

RAW = ROOT / 'data/raw/wildscenes'
COLLECTION = 'https://data.csiro.au/dap/api/v2/collections/61541'
REVISION = '9eb4e10b4483a634159e2b371be0437e465fe218'
REPOSITORY = 'https://github.com/csiro-robotics/WildScenes'
SOURCE_ROOT = 'https://raw.githubusercontent.com/csiro-robotics/WildScenes/' + REVISION + '/'
SOURCE_FILES = ['data/splits/opt2d/' + split + '.csv' for split in ('train', 'val', 'test')] + [
    'wildscenes/mmseg_wildscenes/dataset/wildscenes.py',
    'wildscenes/configs/benchmark_palette_remap.py', 'wildscenes/tools/utils2d.py', 'README.md']


def safe_relative(name):
    parts = PurePosixPath(name).parts
    if not parts or '..' in parts or name.startswith('/') or '\\' in name or ':' in name:
        raise ValueError('Unsafe WildScenes source path')
    return Path(*parts)


def split_records(metadata):
    result, seen = {}, set()
    for split in ('train', 'val', 'test'):
        rows = []
        with (Path(metadata) / 'data/splits/opt2d' / (split + '.csv')).open(newline='') as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != ['id', 'im_path', 'label_path']:
                raise ValueError('Unexpected author split CSV schema')
            for record in reader:
                sample_id = record['id']
                if not re.fullmatch(r'\d+-\d+', sample_id) or sample_id in seen:
                    raise ValueError('Duplicate or unsafe author split ID')
                image, mask = (safe_relative(record[field]) for field in ('im_path', 'label_path'))
                if (len(image.parts) != 4 or image.parts[0] != 'WildScenes2d' or image.parts[2] != 'image'
                        or image.name != sample_id + '.png' or mask.parts != image.parts[:2] + ('indexLabel', image.name)):
                    raise ValueError('Author split image/mask paths do not form a pair')
                seen.add(sample_id)
                rows.append(dict(record, split=split, sequence=image.parts[1], flat_file_name=image.parts[1] + '__' + image.name))
        if not rows:
            raise ValueError('An author split is empty')
        result[split] = rows
    return result


def signed_request(info, method, path, query=None):
    """Sign standard S3 requests with credentials publicly issued by CSIRO."""
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp = now.strftime('%Y%m%dT%H%M%SZ'); day = stamp[:8]
    host = urllib.parse.urlparse(info['endPointUrl']).netloc
    query = '&'.join(urllib.parse.quote(k, safe='~') + '=' + urllib.parse.quote(str(v), safe='~')
                     for k, v in sorted((query or {}).items()))
    payload = hashlib.sha256(b'').hexdigest()
    names = 'host;x-amz-content-sha256;x-amz-date'
    canonical_path = urllib.parse.quote(path, safe='/~')
    canonical = '\n'.join([method, canonical_path, query,
        'host:' + host + '\nx-amz-content-sha256:' + payload + '\nx-amz-date:' + stamp + '\n', names, payload])
    scope = day + '/us-east-1/s3/aws4_request'
    to_sign = 'AWS4-HMAC-SHA256\n' + stamp + '\n' + scope + '\n' + hashlib.sha256(canonical.encode()).hexdigest()
    key = ('AWS4' + info['secretAccessKey']).encode()
    for value in (day, 'us-east-1', 's3', 'aws4_request'):
        key = hmac.new(key, value.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers = {'Host': host, 'X-Amz-Date': stamp, 'X-Amz-Content-Sha256': payload,
        'Authorization': 'AWS4-HMAC-SHA256 Credential=' + info['accessKey'] + '/' + scope +
                         ', SignedHeaders=' + names + ', Signature=' + signature}
    return info['endPointUrl'] + canonical_path + ('?' + query if query else ''), headers


def limited_response(response, maximum=16 * 1024 * 1024):
    response.raise_for_status()
    data = bytearray()
    for chunk in response.iter_content(65536):
        data.extend(chunk)
        if len(data) > maximum:
            raise ValueError('Metadata response exceeds its size limit')
    return bytes(data)


def prepare_sources(raw):
    metadata = raw / 'official_metadata'
    for name in SOURCE_FILES:
        target = metadata / safe_relative(name)
        if not target.is_file():
            with requests.get(SOURCE_ROOT + name, stream=True, timeout=(15, 45)) as response:
                content = limited_response(response)
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    return metadata


def connection_info(raw):
    # Public temporary credentials are never included in reports or versioned files.
    with requests.get(COLLECTION + '/files/s3', stream=True, timeout=(15, 45)) as response:
        info = json.loads(limited_response(response))
    if info.get('endPointUrl') != 'https://s3.data.csiro.au' or info.get('bucket') != 'dapprd':
        raise ValueError('Unexpected CSIRO public S3 endpoint')
    return info


def source_inventory(info, raw):
    bucket = info['bucket']; remote = info['remoteDirectory']
    if not remote.startswith(bucket + '/'):
        raise ValueError('Unexpected CSIRO collection prefix')
    base = remote[len(bucket) + 1:] + 'data/WildScenes/'
    prefix = base + 'WildScenes2d/'
    objects, token = [], None
    while True:
        query = {'list-type': '2', 'max-keys': '1000', 'prefix': prefix}
        if token:
            query['continuation-token'] = token
        url, headers = signed_request(info, 'GET', '/' + bucket, query)
        with requests.get(url, headers=headers, timeout=(15, 60), stream=True) as response:
            data = limited_response(response)
        xml = ET.fromstring(data)
        for row in xml.findall('{*}Contents'):
            key = row.findtext('{*}Key'); name = key[len(base):]
            parts = PurePosixPath(name).parts
            if len(parts) == 4 and parts[2] in ('image', 'indexLabel') and name.endswith('.png'):
                safe_relative(name)
                objects.append({'key': key, 'path': name, 'bytes': int(row.findtext('{*}Size')),
                                'etag': row.findtext('{*}ETag').strip('"')})
        token = xml.findtext('{*}NextContinuationToken')
        if xml.findtext('{*}IsTruncated') != 'true':
            break
        if not token:
            raise ValueError('Truncated public S3 inventory has no continuation token')
        print(f'WildScenes inventory: {len(objects)} RGB/index objects', flush=True)
    if not objects:
        raise ValueError('Official collection contains no 2D image/index objects')
    write_json(raw / 'source_inventory.json', {'source_url': COLLECTION, 'repository': REPOSITORY,
               'revision': REVISION, 'objects': objects, 'object_bytes': sum(x['bytes'] for x in objects)})
    return objects


def file_digest(path, algorithm='md5'):
    value = hashlib.new(algorithm)
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def verified_object(target, row):
    return (target.is_file() and target.stat().st_size == row['bytes'] and
            (not re.fullmatch('[0-9a-fA-F]{32}', row['etag']) or file_digest(target) == row['etag'].lower()))


def download_object(info, row, root, abort=None):
    target = root / safe_relative(row['path'])
    if verified_object(target, row):
        return 'reused'
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + '.part')
    last_error = None
    for attempt in range(3):
        if abort is not None and abort.is_set():
            raise RuntimeError('Transfer paused; partial object retained')
        try:
            start = part.stat().st_size if part.exists() else 0
            if start > row['bytes']:
                part.unlink(); start = 0
            if start == row['bytes']:
                if verified_object(part, row):
                    part.replace(target); return 'downloaded'
                part.unlink(); start = 0
            url, headers = signed_request(info, 'GET', '/' + info['bucket'] + '/' + row['key'])
            if start:
                headers['Range'] = f'bytes={start}-'
            with requests.get(url, headers=headers, stream=True, timeout=(15, 75)) as response:
                response.raise_for_status()
                if start and response.status_code != 206:
                    # A server ignoring Range is safely restarted from byte zero.
                    if response.status_code != 200:
                        raise ValueError('S3 did not honor a resumable object range')
                    start = 0
                if start and response.headers.get('Content-Range') != f'bytes {start}-{row["bytes"]-1}/{row["bytes"]}':
                    raise ValueError('S3 returned the wrong object range')
                with part.open('ab' if start else 'wb') as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        if abort is not None and abort.is_set():
                            raise RuntimeError('Transfer paused; partial object retained')
                        stream.write(chunk)
                        if stream.tell() > row['bytes']:
                            raise ValueError('Object response exceeds inventoried size')
            if not verified_object(part, row):
                part.unlink(missing_ok=True)
                raise ValueError('Downloaded object size/ETag checksum mismatch')
            part.replace(target)
            return 'downloaded'
        except (requests.RequestException, ValueError) as exc:
            if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code in (401,403):
                if abort is not None:abort.set()
                raise RuntimeError('Public S3 access expired or was refused; resume to refresh CSIRO credentials') from exc
            # Error text deliberately excludes request headers/credentials.
            last_error = type(exc).__name__ + ': ' + str(exc).split('?')[0]
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(last_error)


def acquire(raw=RAW, workers=6, inventory_only=False, max_files=0):
    raw = Path(raw); raw.mkdir(parents=True, exist_ok=True)
    metadata = prepare_sources(raw); records = split_records(metadata)
    info = connection_info(raw)
    saved = raw / 'source_inventory.json'
    objects = json.loads(saved.read_text())['objects'] if saved.is_file() else source_inventory(info, raw)
    by_name = {row['path']: row for row in objects}
    needed = {record[field] for rows in records.values() for record in rows for field in ('im_path', 'label_path')}
    missing = sorted(needed - by_name.keys())
    if missing:
        raise ValueError(f'{len(missing)} official split objects absent from the public source inventory')
    ordered_records = [record for group in itertools.zip_longest(*records.values()) for record in group if record]
    selected = [by_name[record[field]] for record in ordered_records for field in ('im_path', 'label_path')]
    excluded = sorted(row['path'] for row in objects if '/image/' in row['path'] and row['path'] not in needed)
    report = {'dataset': 'WildScenes2d', 'source_url': 'https://data.csiro.au/collection/csiro:61541',
        'repository': REPOSITORY, 'source_revision': REVISION, 'split_policy': 'author_opt2d',
        'source_rgb_images': sum('/image/' in row['path'] for row in objects),
        'author_selected_pairs': sum(len(rows) for rows in records.values()),
        'split_counts': {split: len(rows) for split, rows in records.items()},
        'selected_files': len(selected), 'selected_bytes': sum(row['bytes'] for row in selected),
        'excluded_rgb_paths': excluded, 'excluded_reason': 'Not assigned to author opt2d train/val/test CSVs',
        'complete': False, 'phase': 'inventoried', 'resume_supported': True,
        'licence': 'CC BY-NC-SA 4.0', 'selected_modalities': ['RGB image', 'indexLabel semantic mask']}
    write_json(raw / 'selected_source_inventory.json', dict(report, files=selected))
    write_json(raw / 'download_status.json', report)
    print(json.dumps({k:v for k,v in report.items() if k!='excluded_rgb_paths'}, indent=2), flush=True)
    if inventory_only:
        return report
    pending = [row for row in selected if not verified_object(raw / 'source' / row['path'], row)]
    reused = len(selected)-len(pending)
    pending_names={row['path'] for row in pending}
    completed_bytes = sum(row['bytes'] for row in selected if row['path'] not in pending_names)
    batch = pending[:max_files] if max_files else pending
    done = 0; failures = []; lock = threading.Lock(); abort = threading.Event(); started=time.monotonic()
    report.update(phase='download',verified_files=reused,verified_bytes=completed_bytes,remaining_files=len(pending))
    write_json(raw/'download_status.json',report)
    def worker(row):
        nonlocal done, completed_bytes
        try:
            result = download_object(info, row, raw / 'source', abort)
        except Exception as exc:
            result = 'failed'
            with lock:
                failures.append({'path': row['path'], 'error': str(exc)})
        with lock:
            done += 1
            if result!='failed':completed_bytes += row['bytes']
            if done % 10 == 0 or done == len(batch):
                report.update(phase='download', verified_files=reused+done-len(failures), failures=failures,
                              remaining_files=len(selected)-reused-done+len(failures),verified_bytes=completed_bytes,
                              elapsed_seconds=round(time.monotonic()-started))
                write_json(raw / 'download_status.json', report)
                print(f'WildScenes objects: {reused+done}/{len(selected)}, verified {completed_bytes/1e9:.3f} GB, failed {len(failures)}', flush=True)
        return result
    pool=concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(workers,6)))
    futures=[pool.submit(worker,row) for row in batch]
    interrupted=False
    try:
        for future in concurrent.futures.as_completed(futures):future.result()
    except KeyboardInterrupt:
        interrupted=True;abort.set()
        for future in futures:future.cancel()
    finally:
        pool.shutdown(wait=True,cancel_futures=True)
    remaining=len(selected)-reused-done+len(failures)
    complete=not interrupted and remaining==0
    report.update(complete=complete,phase='complete' if complete else ('paused' if interrupted else 'incomplete'),
                  failures=failures,verified_files=reused+done-len(failures),remaining_files=remaining,
                  verified_bytes=completed_bytes,elapsed_seconds=round(time.monotonic()-started))
    write_json(raw / 'download_status.json', report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root',type=Path,default=RAW)
    parser.add_argument('--workers',type=int,default=6)
    parser.add_argument('--inventory-only',action='store_true')
    parser.add_argument('--max-files',type=int,default=0,help='Acquire at most this many missing objects; 0 means all')
    args=parser.parse_args()
    if args.max_files<0:parser.error('--max-files must be nonnegative')
    report=acquire(args.raw_root,args.workers,args.inventory_only,args.max_files)
    if not args.inventory_only and not report['complete']:
        raise SystemExit(1)

if __name__=='__main__':
    main()
