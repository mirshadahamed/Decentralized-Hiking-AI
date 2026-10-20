"""Regression checks for bounded ORFD recovery without network requests."""
import hashlib
import json
import struct
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from sajana.src.data import download_orfd_rgb as downloader
from sajana.src.data.extract_orfd_partial import extract


class OrfdRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive = self.root / 'orfd_rgb_ranges.zip'

    def archive_fixture(self, completed=True):
        with zipfile.ZipFile(self.archive, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name in ('1.png', '2.png'):
                archive.writestr('Final_Dataset/training/image_data/' + name, b'RGB-' + name.encode())
                archive.writestr('Final_Dataset/training/gt_image/' + name.replace('.png', '_fillcolor.png'), b'mask')
        with zipfile.ZipFile(self.archive) as archive:
            self.central = archive.start_dir
        self.identity = {'file_id': downloader.FILE_ID, 'archive_bytes': self.archive.stat().st_size,
                         'central_offset': self.central, 'central_bytes': self.archive.stat().st_size - self.central - 22}
        self.state = {'identity': self.identity, 'completed': [f'0-{self.central - 1}'] if completed else []}
        (self.root / 'drive_completed_ranges.json').write_text(json.dumps(self.state))

    def test_bounded_batches_never_refetch_saved_ranges_or_exceed_budget(self):
        groups = [[0, 99], [100, 199], [200, 299], [300, 399]]
        self.assertEqual(downloader.pending_batch(groups, {'0-99'}, max_ranges=2), groups[1:3])
        self.assertEqual(downloader.pending_batch(groups, {'0-99'}, max_download_bytes=150), groups[1:2])
        self.assertEqual(downloader.pending_batch(groups, set(), max_download_bytes=50), [])

    def test_coalescing_keeps_markers_limits_and_skips_gaps(self):
        groups = [[0, 9], [8, 19], [20, 29], [31, 39], [40, 49]]
        merged = downloader.coalesce_requests(groups, 30)
        self.assertEqual(merged, [[0, 29, groups[:3]], [31, 49, groups[3:]]])
        pending = downloader.pending_batch(groups, {'8-19'}, max_ranges=2)
        self.assertEqual(downloader.coalesce_requests(pending, 128), [[0, 9, [groups[0]]], [20, 29, [groups[2]]]])
        self.assertEqual(downloader.coalesce_requests(groups, 10)[0], [0, 9, [groups[0]]])

    def test_coalesced_response_commits_original_keys_and_payload_hashes(self):
        self.archive_fixture(completed=False)
        original = self.archive.read_bytes()
        width = self.central // 4
        groups = [[0, width - 1], [width, 2*width - 1], [2*width, self.central - 1]]
        payload = original[:2*width]
        confirmation = Mock(text='confirmation')
        response = Mock(status_code=206, content=payload,
                        headers={'Content-Range': f'bytes 0-{2*width-1}/{len(original)}'})
        parser = types.SimpleNamespace(get_url_from_gdrive_confirmation=lambda _: 'https://public.example/archive')
        with patch.object(downloader.requests, 'get', side_effect=[confirmation, response]) as get, \
             patch.object(downloader.importlib, 'import_module', return_value=parser), \
             patch.object(downloader, 'range_plan', return_value=groups), \
             patch('sys.argv', ['download', '--out', str(self.root), '--workers', '1', '--max-ranges', '2', '--request-size-mib', '128']):
            downloader.main()
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args.kwargs['headers']['Range'], f'bytes=0-{2*width-1}')
        state = json.loads((self.root / 'drive_completed_ranges.json').read_text())
        self.assertEqual(state['completed'], sorted(f'{a}-{b}' for a,b in groups[:2]))
        for a,b in groups[:2]:
            self.assertEqual(state['range_sha256'][f'{a}-{b}'], hashlib.sha256(original[a:b+1]).hexdigest())
        self.assertEqual(self.archive.read_bytes(), original)
        self.assertEqual(json.loads((self.root / 'download_status.json').read_text())['phase'], 'batch_complete')
        with self.archive.open('r+b') as saved:
            with self.assertRaisesRegex(ValueError, 'does not cover'):
                downloader.save_request(saved.fileno(), 0, b'x', [[0, 1]])

    def test_completed_archive_resumes_and_crc_extracts_without_network(self):
        self.archive_fixture()
        with patch.object(downloader.requests, 'get') as get, patch('sys.argv', ['download', '--out', str(self.root)]):
            downloader.main()
        get.assert_not_called()
        report = json.loads((self.root / 'download_status.json').read_text())
        self.assertTrue(report['complete'])
        self.assertTrue(report['crc_checks_passed'])
        self.assertEqual(len(list((self.root / 'ORFD').rglob('*.png'))), 4)

    def test_cached_index_quota_failure_does_not_overwrite_saved_ranges(self):
        self.archive_fixture(completed=False)
        before = self.archive.read_bytes()
        confirmation = Mock(text='confirmation')
        quota = Mock(status_code=200, text='<title>Google Drive - Quota exceeded</title>')
        parser = types.SimpleNamespace(get_url_from_gdrive_confirmation=lambda _: 'https://public.example/archive')
        with patch.object(downloader.requests, 'get', side_effect=[confirmation, quota]) as get, \
             patch.object(downloader.importlib, 'import_module', return_value=parser), \
             patch('sys.argv', ['download', '--out', str(self.root), '--workers', '1', '--max-ranges', '1']):
            with self.assertRaisesRegex(RuntimeError, 'Quota exceeded'):
                downloader.main()
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args.kwargs['headers']['Range'], f'bytes=0-{self.central - 1}')
        self.assertEqual(self.archive.read_bytes(), before)
        self.assertEqual(json.loads((self.root / 'drive_completed_ranges.json').read_text()), self.state)

    def test_exact_payload_coverage_recovers_small_complete_members(self):
        self.archive_fixture()
        # Old extraction required an extra 65,535 bytes after every member;
        # a small complete ZIP was incorrectly considered uncovered.
        report = extract(self.root, self.root / 'recovered')
        self.assertEqual(report['available_pairs'], 2)
        with zipfile.ZipFile(self.archive) as archive, self.archive.open('rb') as saved:
            info = archive.infolist()[0]
            saved.seek(info.header_offset + 26)
            name_len, extra_len = struct.unpack('<HH', saved.read(4))
            end = info.header_offset + 30 + name_len + extra_len + info.compress_size - 1
            self.assertTrue(downloader.member_covered(saved, info, [[0, end]]))
            self.assertFalse(downloader.member_covered(saved, info, [[0, end - 1]]))

    def test_partial_crc_failure_preserves_other_valid_pairs(self):
        self.archive_fixture()
        with zipfile.ZipFile(self.archive) as archive:
            info = archive.infolist()[0]
        with self.archive.open('r+b') as saved:
            saved.seek(info.header_offset + 26)
            name_len, extra_len = struct.unpack('<HH', saved.read(4))
            saved.seek(info.header_offset + 30 + name_len + extra_len)
            saved.write(b'X')
        report = extract(self.root, self.root / 'recovered')
        self.assertEqual(report['available_pairs'], 1)
        self.assertEqual(len(report['failed_pairs']), 1)
        self.assertFalse((self.root / 'recovered/ORFD/training/gt_image/1_fillcolor.png').exists())
        self.assertTrue((self.root / 'recovered/ORFD/training/image_data/2.png').exists())

    def test_invalid_resume_markers_and_archive_size_fail_closed(self):
        self.archive_fixture()
        for marker in ('../outside', '-2-5', f'0-{self.archive.stat().st_size}'):
            with self.assertRaises(ValueError):
                downloader.merged_completed_ranges({'completed': [marker]}, self.archive.stat().st_size)
        self.assertEqual(downloader.merged_completed_ranges({'completed': ['10-19', '0-9', '15-30']}, 100), [[0, 30]])
        self.state['identity']['archive_bytes'] += 1
        with self.assertRaisesRegex(ValueError, 'does not match'):
            downloader.cached_identity(self.root, self.state)


if __name__ == '__main__':
    unittest.main()
