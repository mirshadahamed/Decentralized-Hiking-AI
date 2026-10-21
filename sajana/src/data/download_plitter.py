"""Download checksummed pLitterStreet release data, never archive code."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import signal
import stat
import threading
import time
import zipfile
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path, PurePosixPath

import requests

ROOT = Path(__file__).resolve().parents[2]
RECORD = 'https://zenodo.org/records/8288500'
FILES = {'annotations.zip': (8764662, '2484e076b1e9d66036b0a15e9928692f'),
         'images.zip': (13728630001, '02382a3b9620ae7b086ff4c7fd11891d')}
# bucket_id is returned by the public /api/records/8288500/files/images.zip metadata.
IMAGE_ENDPOINTS = {
    'record': f'{RECORD}/files/images.zip?download=1',
    'legacy': 'https://zenodo.org/api/files/156fc23b-83e1-41c4-b3c3-642eeaeb89c5/images.zip?download=1',
}


class DownloadPaused(RuntimeError):
    """An intentional pause which preserves all downloaded bytes for resuming."""


def checksum(path):
    digest = hashlib.md5()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def download(name, directory, attempts=4):
    expected_size, expected_md5 = FILES[name]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    final, partial = directory / name, directory / (name + '.part')
    if final.is_file():
        if final.stat().st_size != expected_size or checksum(final) != expected_md5:
            raise ValueError(f'Existing {final} differs from the release checksum; review it before retrying')
        return {'file': str(final), 'bytes': expected_size, 'md5': expected_md5, 'status': 'existing_valid'}
    last_error = None
    for attempt in range(attempts):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > expected_size:
            raise ValueError(f'Resume file exceeds release size: {partial}')
        try:
            if offset < expected_size:
                headers = {'Range': f'bytes={offset}-'} if offset else {}
                with requests.get(f'{RECORD}/files/{name}?download=1', headers=headers,
                                  stream=True, timeout=(30, 90)) as response:
                    response.raise_for_status()
                    if offset and (response.status_code != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')):
                        raise ValueError('Server did not honor resume range; retained partial file without appending')
                    received = offset
                    next_update = offset + 256 * 1024 * 1024
                    with partial.open('ab' if offset else 'wb') as stream:
                        for block in response.iter_content(1024 * 1024):
                            if not block:
                                continue
                            if received + len(block) > expected_size:
                                raise ValueError('Response exceeds published release size')
                            stream.write(block)
                            received += len(block)
                            if received >= next_update:
                                print(f'{name}: {received:,}/{expected_size:,} bytes', flush=True)
                                next_update = received + 256 * 1024 * 1024
                if partial.stat().st_size != expected_size:
                    raise ValueError('Download ended before published release size')
            actual_md5 = checksum(partial)
            if actual_md5 != expected_md5:
                raise ValueError(f'Release MD5 mismatch: {actual_md5}; partial retained for review')
            partial.replace(final)
            return {'file': str(final), 'bytes': expected_size, 'md5': actual_md5, 'status': 'downloaded_verified'}
        except (requests.RequestException, OSError, ValueError) as exc:
            last_error = exc
            print(f'{name}: attempt {attempt + 1}/{attempts}: {exc}', flush=True)
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f'{name}: {last_error}')


def download_ranges(name, directory, workers=4, chunk_bytes=8 * 1024 * 1024,
                    pause_file=None, max_chunks=None, endpoint='legacy'):
    """Hold an OS lock so two processes cannot modify the same checkpoints."""
    import fcntl
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'plitter_download.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another pLitter downloader owns this directory; pause that process first') from exc
        try:
            return _download_ranges(name, directory, workers, chunk_bytes, pause_file, max_chunks, endpoint)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _download_ranges(name, directory, workers, chunk_bytes, pause_file, max_chunks, endpoint):
    """Resume a contiguous prefix and bounded concurrent HTTP byte-range chunks."""
    if not 1 <= workers <= 12 or (max_chunks is not None and max_chunks < 1):
        raise ValueError('workers must be 1..12 and max_chunks must be positive')
    if endpoint not in IMAGE_ENDPOINTS:
        raise ValueError('Expected documented public record or legacy file endpoint')
    stopped = threading.Event()
    pause_file = Path(pause_file) if pause_file else None

    def check_pause():
        if stopped.is_set() or (pause_file and pause_file.exists()):
            stopped.set()
            raise DownloadPaused('Download paused; prefix and range checkpoints are preserved')

    check_pause()
    size, md5 = FILES[name]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    final, prefix = directory / name, directory / (name + '.part')
    if final.exists():
        return download(name, directory)
    initial = prefix.stat().st_size if prefix.exists() else 0
    if initial > size:
        raise ValueError('Resume prefix exceeds published archive size')
    chunks = directory / (name + '.ranges')
    chunks.mkdir(exist_ok=True)
    journal = chunks / 'index.json'
    descriptor = {'release_bytes': size, 'release_md5': md5, 'prefix_bytes': initial, 'chunk_bytes': chunk_bytes}
    if journal.exists():
        previous = json.loads(journal.read_text())
        if previous != descriptor:
            raise ValueError('Resume prefix/chunk policy differs from saved range journal')
    else:
        journal.write_text(json.dumps(descriptor, indent=2) + '\n')
    ranges = [(start, min(start + chunk_bytes, size) - 1) for start in range(initial, size, chunk_bytes)]

    def acquire(pair):
        check_pause()
        start, end = pair
        target = chunks / f'{start}-{end}.chunk'
        expected = end - start + 1
        if target.exists() and target.stat().st_size == expected:
            return expected
        part = target.with_suffix('.part')
        for attempt in range(4):
            check_pause()
            resumed = part.stat().st_size if part.exists() else 0
            if resumed > expected:
                raise ValueError(f'Range chunk exceeds expected size: {part}')
            try:
                if resumed < expected:
                    offset = start + resumed
                    started = time.monotonic()
                    base_url = IMAGE_ENDPOINTS[endpoint] if name == 'images.zip' else f'{RECORD}/files/{name}?download=1'
                    with requests.get(f'{base_url}&range_start={offset}',
                                      headers={'Range': f'bytes={offset}-{end}'}, stream=True,
                                      timeout=(30, 60)) as response:
                        if response.status_code == 429:
                            try:
                                delay = min(max(float(response.headers.get('Retry-After', 30)), 1), 120)
                            except ValueError:
                                delay = 30
                            print(f'{name}: server requested rate-limit backoff ({delay:g}s)', flush=True)
                            for _ in range(int(delay)):
                                check_pause()
                                time.sleep(1)
                        response.raise_for_status()
                        if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {offset}-{end}/{size}':
                            raise ValueError('Server returned an unexpected byte range; no data appended')
                        received = resumed
                        with part.open('ab' if resumed else 'wb') as stream:
                            for block in response.iter_content(256 * 1024):
                                check_pause()
                                if received + len(block) > expected:
                                    raise ValueError('Range response exceeds declared bounds')
                                stream.write(block)
                                received += len(block)
                                if time.monotonic() - started > 240:
                                    raise TimeoutError('Range request exceeded four-minute bound; progress retained')
                if part.stat().st_size != expected:
                    raise ValueError('Range response ended early')
                part.replace(target)
                return expected
            except (requests.RequestException, OSError, ValueError) as exc:
                if attempt == 3:
                    raise RuntimeError(f'Range {start}-{end} failed after four attempts: {exc}') from exc
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError('Unreachable range retry state')

    completed = initial
    pending = []
    for pair in ranges:
        start, end = pair
        path = chunks / f'{start}-{end}.chunk'
        if path.exists() and path.stat().st_size == end - start + 1:
            completed += path.stat().st_size
        else:
            pending.append(pair)
    selected = iter(pending[:max_chunks] if max_chunks else pending)
    updated = time.monotonic()
    checkpoint = directory / 'plitter_download_progress.json'

    def progress(status):
        current_bytes = size if status == 'archive_verified' else initial + sum(
            p.stat().st_size for p in chunks.glob('*') if p.suffix in ('.chunk', '.part'))
        checkpoint.write_text(json.dumps({'status': status, 'downloaded_bytes': current_bytes,
                                         'completed_range_bytes': completed, 'expected_bytes': size,
                                         'workers': workers, 'endpoint': endpoint,
                                         'updated_unix': time.time()}, indent=2) + '\n')

    progress('downloading')
    pool = ThreadPoolExecutor(max_workers=workers)
    futures = set()
    try:
        for _ in range(workers):
            pair = next(selected, None)
            if pair is not None:
                futures.add(pool.submit(acquire, pair))
        while futures:
            check_pause()
            done, futures = wait(futures, timeout=1, return_when=FIRST_COMPLETED)
            for future in done:
                completed += future.result()
                pair = next(selected, None)
                if pair is not None:
                    futures.add(pool.submit(acquire, pair))
            if time.monotonic() - updated > 30 or completed == size:
                print(f'{name}: {completed:,}/{size:,} bytes across {workers} workers', flush=True)
                progress('downloading')
                updated = time.monotonic()
    except BaseException:
        stopped.set()
        for future in futures:
            future.cancel()
        progress('paused_or_interrupted')
        raise
    finally:
        stopped.set()
        # Only running requests remain; they check the stop flag after each read.
        pool.shutdown(wait=True, cancel_futures=True)
    if completed != size:
        progress('paused_at_chunk_limit')
        raise DownloadPaused('Configured max-chunks reached; rerun to resume remaining ranges')
    assembled = directory / (name + '.assembled')
    digest = hashlib.md5()
    with assembled.open('wb') as output:
        for path in [prefix] + [chunks / f'{start}-{end}.chunk' for start, end in ranges]:
            if not path.exists() and path == prefix and not initial:
                continue
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    output.write(block)
                    digest.update(block)
    if assembled.stat().st_size != size or digest.hexdigest() != md5:
        raise ValueError('Assembled archive differs from published release checksum; all resume data retained')
    assembled.replace(final)
    # Remove only this downloader's verified resume fragments after the final checksum passes.
    if prefix.exists():
        prefix.unlink()
    shutil.rmtree(chunks)
    progress('archive_verified')
    return {'file': str(final), 'bytes': size, 'md5': md5, 'status': 'downloaded_ranges_verified'}


def extract_data(archive, destination, kind):
    """Reject traversal/links; extract JSON annotations or RGB image files only."""
    destination = Path(destination)
    accepted = 0
    seen = set()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in member.filename:
                raise ValueError(f'Unsafe archive member: {member.filename}')
            if member.is_dir():
                continue
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError(f'Archive symlink is unsupported: {member.filename}')
            if kind == 'annotations':
                keep = path.suffix.lower() == '.json' and path.parts[0] == 'annotations'
            else:
                keep = path.suffix.lower() in ('.jpg', '.jpeg', '.png')
            if not keep:
                continue
            if member.filename in seen or member.file_size > 500 * 1024 * 1024:
                raise ValueError(f'Duplicate or oversized member: {member.filename}')
            seen.add(member.filename)
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.stat().st_size == member.file_size:
                import zlib
                crc = 0
                with target.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        crc = zlib.crc32(block, crc)
                if crc & 0xffffffff == member.CRC:
                    accepted += 1
                    continue
            temporary = target.with_suffix(target.suffix + '.part')
            with zipped.open(member) as source, temporary.open('wb') as output:
                shutil.copyfileobj(source, output)
            temporary.replace(target)
            accepted += 1
    if not accepted:
        raise ValueError(f'No permitted {kind} data in archive')
    return accepted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, default=ROOT / 'data/raw/plitter')
    parser.add_argument('--annotations-out', type=Path, default=ROOT / 'data/interim/plitter')
    parser.add_argument('--annotations-only', action='store_true')
    parser.add_argument('--workers', type=int, default=4, choices=range(1, 13))
    parser.add_argument('--endpoint', choices=tuple(IMAGE_ENDPOINTS), default='legacy',
                        help='Public Zenodo storage endpoint; final release MD5 is verified for either')
    parser.add_argument('--max-chunks', type=int, help='Stop successfully acquired range work after this many new chunks; exit 75 if incomplete')
    parser.add_argument('--pause-file', type=Path, help='Creating this file gracefully pauses range downloads; remove it before resuming')
    parser.add_argument('--preprocess-after-download', action='store_true', help='After checksummed extraction, import and fully audit detection data')
    args = parser.parse_args()
    if args.max_chunks is not None and args.max_chunks < 1:
        parser.error('--max-chunks must be positive')
    pause_file = args.pause_file or args.raw / 'plitter_pause_requested'

    def pause_signal(signum, frame):
        pause_file.parent.mkdir(parents=True, exist_ok=True)
        pause_file.touch()
        print('Pause requested; current network blocks will stop and checkpoints will be retained.', flush=True)

    signal.signal(signal.SIGINT, pause_signal)
    signal.signal(signal.SIGTERM, pause_signal)
    report = {'record': RECORD, 'doi': '10.5281/zenodo.8288500', 'license': 'CC-BY-4.0',
              'files': [], 'passed': False, 'executed_archive_content': False}
    try:
        for name in ('annotations.zip',) if args.annotations_only else FILES:
            acquired = download_ranges(name, args.raw, args.workers, pause_file=pause_file,
                                       max_chunks=args.max_chunks, endpoint=args.endpoint) if name == 'images.zip' else download(name, args.raw)
            report['files'].append(acquired)
            kind = 'annotations' if name.startswith('annotations') else 'images'
            destination = args.annotations_out if kind == 'annotations' else args.raw / 'extracted'
            report['files'][-1]['extracted_data_files'] = extract_data(args.raw / name, destination, kind)
        report['passed'] = True
        if args.preprocess_after_download and not args.annotations_only:
            from .preprocess_plitter import DEFAULT_OUT, prepare_images, preprocess, verify
            source = args.annotations_out / 'annotations/4_class_splits'
            preprocess(source, DEFAULT_OUT)
            imported = prepare_images(source, DEFAULT_OUT, args.raw / 'extracted')
            checked = verify(source, DEFAULT_OUT)
            report['detection_training_ready'] = imported['passed'] and checked['training_ready']
            if not report['detection_training_ready']:
                raise ValueError('Archive downloaded but detection image/label verification failed; inspect pLitter reports')
    except DownloadPaused as exc:
        report.update(paused=True, error=str(exc))
    except Exception as exc:
        report['passed'] = False
        report['error'] = str(exc)
        raise
    finally:
        args.raw.mkdir(parents=True, exist_ok=True)
        (args.raw / 'download_status.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if report.get('paused'):
        raise SystemExit(75)


if __name__ == '__main__':
    main()
