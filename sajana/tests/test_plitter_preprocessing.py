import csv
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from PIL import Image

from sajana.src.data import download_plitter as acquisition
from sajana.src.data.preprocess_plitter import load, prepare_images, preprocess, verify
from sajana.src.data.preprocess_plitter_mawanella import preprocess as preprocess_geo


class PLitterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source, self.out, self.raw = self.root / 'source', self.root / 'out', self.root / 'raw'
        self.source.mkdir()
        self.raw.mkdir()
        categories = [{'id': i, 'name': n} for i, n in enumerate(('Plastic', 'Pile', 'Face mask', 'Trash bin'), 1)]
        for i, split in enumerate(('train', 'val', 'test'), 1):
            image = {'id': i, 'file_name': f'{split}.png', 'width': 12, 'height': 10,
                     'path': f'/datasets/Mawanella/sequence/{split}.png', 'dataset_id': 4,
                     'metadata': {'source_gps_present': False}}
            data = {'categories': categories, 'images': [image],
                    'annotations': [{'id': i, 'image_id': i, 'category_id': 4 if i == 1 else 1,
                                     'bbox': [2, 1, 4, 3], 'iscrowd': False}]}
            (self.source / f'annotations_{split}.json').write_text(json.dumps(data))
            Image.new('RGB', (12, 10), (i * 50, 0, 0)).save(self.raw / image['file_name'])

    def test_native_classes_source_ids_and_box_targets(self):
        result = preprocess(self.source, self.out)
        self.assertEqual(result['category_mapping']['4'], 3)
        label = next((self.out / 'labels/train').glob('*.txt'))
        self.assertEqual(len(label.read_text().split()), 5)
        self.assertTrue(label.read_text().startswith('3 '))
        with (self.out / 'manifests/train.csv').open(newline='') as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row['image_id'], '1')
        self.assertEqual(row['annotation_ids'], '1')
        self.assertIn('source_gps_present', row['source_metadata_json'])
        self.assertTrue(verify(self.source, self.out, labels_only=True)['passed'])
        self.assertFalse((self.out / 'data.yaml').exists())

    def test_bad_object_quarantines_entire_image(self):
        path = self.source / 'annotations_train.json'
        data = json.loads(path.read_text())
        data['annotations'].append({'id': 10, 'image_id': 1, 'category_id': 1, 'bbox': [2, 2, 20, 3]})
        path.write_text(json.dumps(data))
        result = preprocess(self.source, self.out)
        self.assertEqual(result['quarantined_images'], 1)
        self.assertEqual(result['quarantined_annotations'], 2)
        self.assertFalse(list((self.out / 'labels/train').glob('*.txt')))

    def test_repeated_image_id_across_splits_fails_before_output(self):
        path = self.source / 'annotations_val.json'
        data = json.loads(path.read_text())
        data['images'][0]['id'] = 1
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            preprocess(self.source, self.out)
        self.assertFalse(self.out.exists())

    def test_images_required_and_source_label_tamper_detected(self):
        preprocess(self.source, self.out)
        self.assertFalse(verify(self.source, self.out)['training_ready'])
        self.assertTrue(prepare_images(self.source, self.out, self.raw)['passed'])
        self.assertTrue(verify(self.source, self.out)['training_ready'])
        label = next((self.out / 'labels/train').glob('*.txt'))
        label.write_text('0 0.5 0.5 0.25 0.25\n')
        self.assertFalse(verify(self.source, self.out)['passed'])
        self.assertFalse((self.out / 'data.yaml').exists())

    def test_cross_split_decoded_duplicates_block_readiness(self):
        Image.new('RGB', (12, 10), (50, 0, 0)).save(self.raw / 'test.png')
        preprocess(self.source, self.out)
        prepare_images(self.source, self.out, self.raw)
        report = verify(self.source, self.out)
        self.assertFalse(report['passed'])
        self.assertTrue(report['duplicate_images'])

    def test_geospatial_fractional_counts_excluded_duplicates_preserved(self):
        source = self.root / 'geo.csv'
        source.write_text('lon,lat,plastic_c,bin_c\n80.4,7.2,3,0\n80.4,7.2,3,0\n80.4,7.2,1.7,0\nNaN,7.2,1,0\n')
        report = preprocess_geo(source, self.root / 'geo_out', self.root / 'geo_report.json')
        self.assertEqual(report['valid_rows'], 2)
        self.assertEqual(report['excluded_rows'], 2)
        self.assertEqual(report['exact_duplicate_rows'], 1)
        self.assertEqual(report['plastic_observation_sum'], 6)
        self.assertFalse(report['image_training_ready'])

    def test_archive_data_only_and_traversal_rejected(self):
        archive = self.root / 'annotations.zip'
        with zipfile.ZipFile(archive, 'w') as zipped:
            zipped.writestr('annotations/source.json', '{}')
            zipped.writestr('annotations/run.py', 'raise RuntimeError("not data")')
        self.assertEqual(acquisition.extract_data(archive, self.root / 'extract', 'annotations'), 1)
        self.assertFalse((self.root / 'extract/annotations/run.py').exists())
        with zipfile.ZipFile(archive, 'w') as zipped:
            zipped.writestr('../bad.jpg', 'bad')
        with self.assertRaises(ValueError):
            acquisition.extract_data(archive, self.root / 'extract2', 'images')

    def test_range_resume_preserves_prefix_and_checks_final_checksum(self):
        content = b'prefix--chunk--tail'
        raw = self.root / 'download'
        raw.mkdir()
        (raw / 'images.zip.part').write_bytes(content[:5])

        class Response:
            status_code = 206

            def __init__(self, start, end):
                self.headers = {'Content-Range': f'bytes {start}-{end}/{len(content)}'}
                self.payload = content[start:end + 1]

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def raise_for_status(self):
                pass

            def iter_content(self, *args):
                yield self.payload

        def get(url, headers, **kwargs):
            start, end = map(int, headers['Range'].split('=')[1].split('-'))
            return Response(start, end)

        with mock.patch.object(acquisition, 'FILES', {'images.zip': (len(content), hashlib.md5(content).hexdigest())}), \
                mock.patch.object(acquisition.requests, 'get', side_effect=get):
            acquisition.download_ranges('images.zip', raw, workers=2, chunk_bytes=4)
        self.assertEqual((raw / 'images.zip').read_bytes(), content)
        self.assertFalse((raw / 'images.zip.part').exists())

    def test_range_pause_file_keeps_existing_prefix_without_network(self):
        raw = self.root / 'paused'
        raw.mkdir()
        (raw / 'images.zip.part').write_bytes(b'existing prefix')
        pause = raw / 'pause'
        pause.touch()
        with mock.patch.object(acquisition.requests, 'get') as get:
            with self.assertRaises(acquisition.DownloadPaused):
                acquisition.download_ranges('images.zip', raw, workers=12, pause_file=pause)
        get.assert_not_called()
        self.assertEqual((raw / 'images.zip.part').read_bytes(), b'existing prefix')

    def test_range_chunk_limit_retains_resume_checkpoint(self):
        content = b'12345678'
        raw = self.root / 'limited'
        raw.mkdir()

        class Response:
            status_code = 206
            headers = {'Content-Range': 'bytes 0-3/8'}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def raise_for_status(self):
                pass

            def iter_content(self, *args):
                yield content[:4]

        with mock.patch.object(acquisition, 'FILES', {'images.zip': (8, hashlib.md5(content).hexdigest())}), \
                mock.patch.object(acquisition.requests, 'get', return_value=Response()) as get:
            with self.assertRaises(acquisition.DownloadPaused):
                acquisition.download_ranges('images.zip', raw, workers=12, chunk_bytes=4, max_chunks=1)
        self.assertEqual(get.call_count, 1)
        self.assertEqual((raw / 'images.zip.ranges/0-3.chunk').read_bytes(), content[:4])
        self.assertFalse((raw / 'images.zip').exists())


if __name__ == '__main__':
    unittest.main()
