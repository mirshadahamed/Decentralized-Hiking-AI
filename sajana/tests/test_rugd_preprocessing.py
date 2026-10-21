import csv
import io
import json
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from sajana.src.data.download_rugd import extract, ranged_download, mirror_frames
from sajana.src.data.preprocess_rugd import load_colormap, make_lookup, preprocess, semantic_mask, verify


class RugdTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.raw, self.out = self.root / 'extracted', self.root / 'prepared'
        self.colors = self.raw / 'RUGD_annotations/RUGD_annotation-colormap.txt'
        self.colors.parent.mkdir(parents=True)
        self.colors.write_text('0 void 0 0 0\n' + ''.join(f'{i} class{i} {i} 0 0\n' for i in range(1, 25)))
        for index, sequence in enumerate(('park-2', 'park-8', 'creek')):
            photo = self.raw / 'RUGD_frames-with-annotations' / sequence / (sequence + '_00001.png')
            mask = self.raw / 'RUGD_annotations' / sequence / photo.name
            photo.parent.mkdir(parents=True)
            mask.parent.mkdir(parents=True)
            Image.new('RGB', (12, 8), (50 + index, 20, 10)).save(photo)
            im = Image.new('RGB', (12, 8), (0, 0, 0))
            im.putpixel((2, 2), (1, 0, 0))
            im.putpixel((3, 2), (21, 0, 0))
            im.save(mask)

    def test_source_class_ids_and_void_are_preserved(self):
        classes = load_colormap(self.colors)
        mask, counts = semantic_mask(self.raw / 'RUGD_annotations/park-2/park-2_00001.png', (12, 8), make_lookup(classes))
        self.assertEqual(mask.mode, 'L')
        self.assertEqual(mask.getpixel((2, 2)), 1)
        self.assertEqual(mask.getpixel((3, 2)), 21)
        self.assertEqual(counts, {'0': 94, '1': 1, '21': 1})

    def test_unknown_colors_fail_without_nearest_color_guess(self):
        mask = self.raw / 'RUGD_annotations/park-2/park-2_00001.png'
        Image.new('RGB', (12, 8), (1, 1, 0)).save(mask)
        report = preprocess(self.raw, self.out)
        self.assertFalse(report['preprocessed'])
        self.assertIn('Unknown source colors', report['issues'][0])
        self.assertFalse(verify(self.raw, self.out)['passed'])

    def test_geometry_mismatch_is_not_silently_resized(self):
        Image.new('RGB', (10, 8), (0, 0, 0)).save(self.raw / 'RUGD_annotations/park-2/park-2_00001.png')
        self.assertFalse(preprocess(self.raw, self.out)['preprocessed'])

    def test_published_sequence_splits_preserved_but_tiny_fixture_not_complete(self):
        preprocess(self.raw, self.out)
        report = verify(self.raw, self.out)
        self.assertTrue(report['passed'])
        self.assertFalse(report['training_ready'])
        self.assertFalse(report['available_source_complete'])
        self.assertEqual(report['splits']['train']['source_sequences'], ['park-2'])
        self.assertEqual(report['splits']['val']['source_sequences'], ['park-8'])
        self.assertEqual(report['splits']['test']['source_sequences'], ['creek'])

    def test_source_pair_omission_and_unknown_sequence_refused(self):
        mask = self.raw / 'RUGD_annotations/park-2/park-2_00001.png'
        mask.unlink()
        with self.assertRaises(ValueError):
            preprocess(self.raw, self.out)

    def test_mask_and_manifest_tampering_detected(self):
        preprocess(self.raw, self.out)
        stored = next((self.out / 'masks/train').glob('*.png'))
        Image.new('L', (12, 8), 1).save(stored)
        self.assertFalse(verify(self.raw, self.out)['passed'])
        preprocess(self.raw, self.out)
        manifest = self.out / 'manifests/train.csv'
        with manifest.open(newline='') as f:
            reader = csv.DictReader(f)
            fields, rows = reader.fieldnames, list(reader)
        rows[0]['source_sequence'] = 'park-8'
        with manifest.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        self.assertFalse(verify(self.raw, self.out)['passed'])

    def test_exact_rgb_leakage_across_source_splits_detected(self):
        photo = self.raw / 'RUGD_frames-with-annotations/park-2/park-2_00001.png'
        other = self.raw / 'RUGD_frames-with-annotations/park-8/park-8_00001.png'
        other.write_bytes(photo.read_bytes())
        preprocess(self.raw, self.out)
        self.assertFalse(verify(self.raw, self.out)['passed'])

    def test_safe_archive_extraction_filters_scripts_and_blocks_traversal(self):
        archive = self.root / 'test.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('RUGD_annotations/park-2/a.png', b'png-data')
            z.writestr('run.py', b'not executed')
        rows = extract(archive, self.root / 'safe')
        self.assertEqual(len(rows), 1)
        self.assertFalse((self.root / 'safe/run.py').exists())
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('../escape.png', b'never extract')
        with self.assertRaises(ValueError):
            extract(archive, self.root / 'unsafe')
        self.assertFalse((self.root / 'escape.png').exists())

    def test_exact_ranges_assembled_and_wrong_offsets_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as z:
            z.writestr('data.png', b'x' * 100)
        payload = buffer.getvalue()

        class Response:
            status_code = 206

            def __init__(self, start, end, wrong=False):
                self.content = payload[start:end + 1]
                self.headers = {'Content-Range': f'bytes {start + int(wrong)}-{end}/{len(payload)}', 'ETag': 'same-source'}

            def raise_for_status(self):
                pass

        def get(_url, headers, **_kwargs):
            start, end = map(int, headers['Range'][6:].split('-'))
            return Response(start, end)

        with patch('requests.get', side_effect=get):
            report = ranged_download('http://rugd.vision/test.zip', self.root / 'download.zip', workers=2, chunk_size=64)
        self.assertEqual((self.root / 'download.zip').read_bytes(), payload)
        self.assertGreater(report['verified_ranges'], 1)

        def wrong_get(_url, headers, **_kwargs):
            start, end = map(int, headers['Range'][6:].split('-'))
            return Response(start, end, wrong=not (start == 0 and end == 0))

        with patch('requests.get', side_effect=wrong_get), patch('time.sleep'):
            with self.assertRaises(RuntimeError):
                ranged_download('http://rugd.vision/test.zip', self.root / 'wrong.zip', workers=2, chunk_size=64)
        self.assertFalse((self.root / 'wrong.zip').exists())

    def test_mirror_photos_must_match_primary_source_crc_and_size(self):
        payload = (self.raw / 'RUGD_frames-with-annotations/park-2/park-2_00001.png').read_bytes()
        relative = 'RUGD_frames-with-annotations/park-2/park-2_00001.png'
        index = {'files': [{'path': relative, 'bytes': len(payload), 'crc32': f'{zlib.crc32(payload):08x}'}]}

        class Response:
            def __init__(self, content):
                self.content = content

            def json(self):
                return {'sha': 'a' * 40}

            def raise_for_status(self):
                pass

        for label, data, valid in [('good', payload, True), ('bad', payload[:-1] + b'x', False)]:
            folder = self.root / label
            folder.mkdir()
            (folder / 'official_frames_index.json').write_text(json.dumps(index))
            with patch('requests.get', return_value=Response(data)), patch('time.sleep'):
                if valid:
                    report = mirror_frames(folder, workers=1)
                    self.assertEqual(report['extracted_files'], 1)
                    self.assertEqual((folder / 'extracted' / relative).read_bytes(), payload)
                else:
                    with self.assertRaises(RuntimeError):
                        mirror_frames(folder, workers=1)
                    self.assertFalse((folder / 'extracted' / relative).exists())


if __name__ == '__main__':
    unittest.main()
