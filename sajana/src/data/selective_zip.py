"""Read verified members of a remote ZIP without downloading the whole archive."""
from __future__ import annotations

import io
import re
import struct
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from pathlib import PurePosixPath


class RangeReader(io.RawIOBase):
    """Seekable HTTP ranges with strict identity, response-size and byte budgets."""

    def __init__(self, url, budget=1_500_000_000, timeout=45):
        self.url, self.budget, self.timeout = url, budget, timeout
        self.position = self.transferred = 0
        self.length = None
        self.etag = None
        self.cache = []
        tail = self._request('bytes=-65536')
        self.cache.append((self.length - len(tail), tail))

    def _request(self, span):
        for attempt in range(3):
            try:
                request = urllib.request.Request(self.url, headers={
                    'Range': span, 'User-Agent': 'Component2-selective-research-download',
                    'Accept-Encoding': 'identity'})
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    if response.status != 206:
                        raise ValueError('Server ignored byte range; full download refused')
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                    if not match:
                        raise ValueError('Invalid HTTP Content-Range')
                    start, end, length = map(int, match.groups())
                    expected = end - start + 1
                    if not (0 <= start <= end < length) or expected > 16 * 1024 * 1024:
                        raise ValueError('Invalid or excessive response span')
                    if span.startswith('bytes=-'):
                        if end != length - 1 or expected != min(length, int(span[7:])):
                            raise ValueError('Incorrect suffix range')
                    else:
                        wanted = tuple(map(int, span[6:].split('-')))
                        if (start, end) != wanted:
                            raise ValueError('Returned range differs from requested bytes')
                    if self.transferred + expected > self.budget:
                        raise ValueError('Remote ZIP transfer budget exceeded')
                    etag = response.headers.get('ETag')
                    if self.length is not None and (length != self.length or etag != self.etag):
                        raise ValueError('Remote archive identity changed during reading')
                    self.length, self.etag = length, etag
                    body = response.read(expected + 1)
                    self.transferred += len(body)
                    if len(body) != expected:
                        raise ValueError('Truncated or oversized HTTP range')
                    return body
            except (OSError, urllib.error.URLError):
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        position = offset if whence == io.SEEK_SET else (
            self.position + offset if whence == io.SEEK_CUR else self.length + offset)
        if position < 0:
            raise ValueError('Negative seek')
        self.position = position
        return position

    def read(self, size=-1):
        if size < 0:
            size = self.length - self.position
        size = min(size, self.length - self.position)
        if size <= 0:
            return b''
        start = self.position
        for cached_start, body in self.cache:
            if cached_start <= start and start + size <= cached_start + len(body):
                self.position += size
                return body[start-cached_start:start-cached_start+size]
        end = start + size - 1
        body = self._request(f'bytes={start}-{end}')
        # Cache headers, ZIP central directory and tiny metadata, not image payloads.
        if len(body) <= 4 * 1024 * 1024:
            self.cache.append((start, body))
            if len(self.cache) > 20:
                self.cache.pop(1)
        self.position += len(body)
        return body


def safe_member(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe ZIP member path')
    return name


def read_member(archive, name, maximum_size=12_000_000):
    safe_member(name)
    info = archive.getinfo(name)
    if info.is_dir() or info.file_size > maximum_size or info.flag_bits & 1:
        raise ValueError('Unsupported or excessive ZIP member')
    # ZipFile checks the complete uncompressed member CRC before returning.
    return archive.read(info)


def open_remote(url, budget=1_500_000_000):
    reader = RangeReader(url, budget=budget)
    return reader, zipfile.ZipFile(reader)


def decode_indexed_member(block, entry):
    """Decode one central-directory-indexed local record, including ZIP64 files."""
    safe_member(entry['name'])
    if len(block) < 30:
        raise ValueError('Truncated ZIP local header')
    header = struct.unpack('<4s5H3I2H', block[:30])
    signature, _, flags, method = header[:4]
    filename_size, extra_size = header[-2:]
    if signature != b'PK\x03\x04' or flags & 1 or method not in (0, 8):
        raise ValueError('Unsupported ZIP local record')
    name = block[30:30+filename_size].decode('utf-8' if flags & 2048 else 'cp437')
    if name != entry['name'] or entry['bytes'] > 12_000_000:
        raise ValueError('ZIP record differs from the frozen index')
    start = 30 + filename_size + extra_size
    compressed = block[start:start+entry['compressed']]
    if len(compressed) != entry['compressed']:
        raise ValueError('Truncated ZIP member')
    if method == 8:
        decoder = zlib.decompressobj(-15)
        body = decoder.decompress(compressed, entry['bytes'] + 1)
        if not decoder.eof or decoder.unused_data:
            raise ValueError('Incomplete or oversized compressed member')
    else:
        body = compressed
    if len(body) != entry['bytes'] or zlib.crc32(body) & 0xffffffff != entry['crc']:
        raise ValueError('ZIP member size or CRC mismatch')
    return body


def fetch_indexed_member(index, entry, timeout=45):
    """Fetch a single bounded record with frozen archive size/ETag checks."""
    safe_member(entry['name'])
    start = entry['offset']
    # Filename and extra-field allowance; the actual local header is checked below.
    end = min(index['archive_bytes'] - 1,
              start + 30 + len(entry['name'].encode('utf-8')) + 2048 + entry['compressed'] - 1)
    if end - start + 1 > 16 * 1024 * 1024:
        raise ValueError('Indexed transfer exceeds per-record bound')
    request = urllib.request.Request(index['url'], headers={
        'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity',
        'User-Agent': 'Component2-selective-research-download'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if (response.status != 206 or response.headers.get('Content-Range') !=
                        f'bytes {start}-{end}/{index["archive_bytes"]}' or
                        response.headers.get('ETag') != index['etag']):
                    raise ValueError('Remote record identity/range mismatch; full download refused')
                block = response.read(end - start + 2)
                if len(block) != end - start + 1:
                    raise ValueError('Truncated or excessive record response')
            return decode_indexed_member(block, entry)
        except (OSError, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
