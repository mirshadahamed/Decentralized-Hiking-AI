"""Prevent unbounded downloads and corrupt or unsafe dataset members."""
import io
import unittest
import zipfile
from unittest.mock import patch

from sajana.src.data.selective_zip import RangeReader, decode_indexed_member, safe_member


class Response(io.BytesIO):
    def __init__(self, body, status=206, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


class SelectiveZipTests(unittest.TestCase):
    def fixture(self, compression):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=compression) as archive:
            archive.writestr('labels/train/example.png', b'a native label image' * 20)
        body = stream.getvalue()
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            info = archive.infolist()[0]
        entry = dict(name=info.filename, bytes=info.file_size, compressed=info.compress_size,
                     offset=info.header_offset, crc=info.CRC)
        return body, entry

    def test_stored_and_deflated_members_match_original(self):
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            body, entry = self.fixture(compression)
            self.assertEqual(decode_indexed_member(body, entry), b'a native label image' * 20)

    def test_changed_crc_or_identity_is_rejected(self):
        body, entry = self.fixture(zipfile.ZIP_STORED)
        for changed in (dict(entry, crc=0), dict(entry, name='labels/train/other.png')):
            with self.assertRaises(ValueError):
                decode_indexed_member(body, changed)

    def test_unsafe_names_are_rejected(self):
        for name in ('../escape.png', '/tmp/escape.png', 'labels/../../escape', 'C:/escape', 'labels\\escape'):
            with self.assertRaises(ValueError):
                safe_member(name)

    def test_range_ignored_by_server_never_reads_full_archive(self):
        response = Response(b'large archive', status=200)
        with patch('urllib.request.urlopen', return_value=response):
            with self.assertRaisesRegex(ValueError, 'full download refused'):
                RangeReader('https://example.invalid/huge.zip')

    def test_oversized_or_truncated_range_rejected(self):
        for body in (b'short', b'01234567890'):
            response = Response(body, headers={'Content-Range': 'bytes 0-9/10', 'ETag': 'v1'})
            with patch('urllib.request.urlopen', return_value=response):
                with self.assertRaises(ValueError):
                    RangeReader('https://example.invalid/file.zip')

    def test_read_budget_is_enforced_before_body_download(self):
        response = Response(b'0123456789', headers={'Content-Range': 'bytes 0-9/10', 'ETag': 'v1'})
        with patch('urllib.request.urlopen', return_value=response):
            with self.assertRaisesRegex(ValueError, 'budget'):
                RangeReader('https://example.invalid/file.zip', budget=5)


if __name__ == '__main__':
    unittest.main()
