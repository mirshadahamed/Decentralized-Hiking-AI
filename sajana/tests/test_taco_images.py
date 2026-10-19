"""Regression checks for corrupt images, EXIF alignment, and safe resumability."""
import csv
import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from sajana.src.data.download_taco_images import acquire, acquire_one
from sajana.src.data.taco_images import decode_image, save_image, validate_existing


def image_bytes(size=(40, 20), orientation=None):
    stream = io.BytesIO()
    image = Image.new('RGB', size, 'red')
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    image.save(stream, 'JPEG', exif=exif)
    return stream.getvalue()


class ImageTests(unittest.TestCase):
    def test_fallback_geometry_and_mismatched_shape(self):
        image, action = decode_image(image_bytes(), 400, 200)
        self.assertEqual(image.size, (40, 20))
        self.assertEqual(action, 'unchanged')
        with self.assertRaises(ValueError):
            decode_image(image_bytes(), 200, 400)

    def test_exif_rotation_selected_using_annotation_geometry(self):
        image, action = decode_image(image_bytes(orientation=6), 200, 400)
        self.assertEqual(image.size, (20, 40))
        self.assertEqual(action, 'exif_rotation')
        self.assertNotIn(274, image.getexif())
        image, action = decode_image(image_bytes(orientation=6), 400, 200)
        self.assertEqual(image.size, (40, 20))
        self.assertEqual(action, 'raw_matches_annotations')

    def test_corruption_and_ambiguous_rotation_rejected(self):
        with self.assertRaises(OSError):
            decode_image(b'not an image', 40, 20)
        with self.assertRaises(ValueError):
            decode_image(image_bytes((40, 40), 6), 400, 400)
        with self.assertRaises(ValueError):
            decode_image(image_bytes(orientation=3), 40, 20)

    def test_invalid_zero_exif_preserves_pixels_and_strips_metadata(self):
        image, action = decode_image(image_bytes(orientation=0), 40, 20)
        self.assertEqual(image.size, (40, 20))
        self.assertEqual(action, 'invalid_exif_0_preserved_raw')
        self.assertNotIn(274, image.getexif())

    def test_ambiguous_orientation_requires_explicit_review_override(self):
        image, action = decode_image(image_bytes(orientation=3), 40, 20, 'raw')
        self.assertEqual(action, 'reviewed_override_raw')
        self.assertNotIn(274, image.getexif())

    def test_reviewed_orientation_cannot_be_reused_for_different_source_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = image_bytes(orientation=3)
            (root / 'batch_14').mkdir()
            (root / 'batch_14/000.jpg').write_bytes(content)
            row = {'split': 'test', 'source_file_name': 'batch_14/000.jpg',
                   'flat_file_name': 'batch_14__000.jpg', 'width': '40', 'height': '20'}
            override = {'batch_14/000.jpg': {'orientation': 'exif', 'source_sha256': '0' * 64}}
            result = acquire_one(row, root / 'output', root, 5, 95, True, override)
            self.assertEqual(result['status'], 'failed')
            self.assertIn('source hash changed', result['error'])
            override['batch_14/000.jpg']['source_sha256'] = hashlib.sha256(content).hexdigest()
            result = acquire_one(row, root / 'output', root, 5, 95, True, override)
            self.assertEqual(result['status'], 'saved')
            self.assertEqual(result['orientation_action'], 'reviewed_override_exif')

    def test_local_import_repairs_corrupt_existing_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset, raw = root / 'dataset', root / 'raw'
            (raw / 'batch_1').mkdir(parents=True)
            (raw / 'batch_1/000.jpg').write_bytes(image_bytes())
            (dataset / 'manifests').mkdir(parents=True)
            fields = ['source_file_name', 'flat_file_name', 'width', 'height']
            for split in ('train', 'val', 'test'):
                with (dataset / 'manifests' / f'{split}.csv').open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    if split == 'train':
                        writer.writerow(dict(zip(fields, ['batch_1/000.jpg', 'batch_1__000.jpg', 400, 200])))
            destination = dataset / 'images/train/batch_1__000.jpg'
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b'broken')
            results = acquire(dataset, image_root=raw, workers=1)
            self.assertEqual(results[0]['status'], 'saved')
            self.assertTrue(validate_existing(destination, 400, 200))
            results = acquire(dataset, image_root=raw, workers=1)
            self.assertEqual(results[0]['status'], 'existing_valid')
            self.assertEqual(results[0]['source'], str(raw / 'batch_1/000.jpg'))
            self.assertEqual(len((dataset / 'download_failures.csv').read_text().splitlines()), 1)

    def test_limited_resume_retains_unattempted_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset, raw = root / 'dataset', root / 'raw'
            (raw / 'batch_1').mkdir(parents=True)
            (raw / 'batch_1/000.jpg').write_bytes(image_bytes())
            (dataset / 'manifests').mkdir(parents=True)
            fields = ['source_file_name', 'flat_file_name', 'width', 'height']
            for split, batch in (('train', 'batch_1'), ('val', 'batch_3'), ('test', 'batch_14')):
                with (dataset / 'manifests' / f'{split}.csv').open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    if split != 'val':
                        writer.writerow(dict(zip(fields, [f'{batch}/000.jpg', f'{batch}__000.jpg', 400, 200])))
            acquire(dataset, image_root=raw, workers=1)
            acquire(dataset, image_root=raw, workers=1, limit=1)
            with (dataset / 'download_failures.csv').open(newline='') as stream:
                failures = list(csv.DictReader(stream))
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]['split'], 'test')


if __name__ == '__main__':
    unittest.main()
