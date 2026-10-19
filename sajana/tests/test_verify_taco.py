"""Readiness regressions: missing data, provenance, geometry, and decode failures."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.verify_taco_ready import verify

try:
    from PIL import Image
except ImportError:
    Image = None


class VerifyTacoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dataset = self.root / 'dataset'
        self.source = self.root / 'annotations.json'
        self.data = {'images': [], 'annotations': []}
        self.rows = {}
        for index, (split, batch) in enumerate((('train', 'batch_1'), ('val', 'batch_3'),
                                                ('test', 'batch_14'))):
            source_name = f'{batch}/000001.jpg'
            flat_name = f'{batch}__000001.jpg'
            self.data['images'].append({'id': index, 'width': 40, 'height': 20,
                                        'file_name': source_name})
            self.data['annotations'].append({'id': index, 'image_id': index,
                                             'category_id': 0,
                                             'segmentation': [[4, 2, 20, 2, 20, 10, 4, 10]]})
            self.rows[split] = [{'image_id': index, 'batch': batch,
                                 'source_file_name': source_name,
                                 'flat_file_name': flat_name,
                                 'width': 40, 'height': 20, 'object_count': 1}]
            (self.dataset / 'labels' / split).mkdir(parents=True)
            (self.dataset / 'images' / split).mkdir(parents=True)
            self.label(split).write_text('0 0.1 0.1 0.5 0.1 0.5 0.5 0.1 0.5\n')
        self.write_source()
        self.write_manifests()

    def write_source(self):
        self.source.write_text(json.dumps(self.data), encoding='utf-8')

    def write_manifests(self):
        (self.dataset / 'manifests').mkdir(exist_ok=True)
        for split, rows in self.rows.items():
            with (self.dataset / 'manifests' / f'{split}.csv').open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(self.rows['train'][0]))
                writer.writeheader()
                writer.writerows(rows)

    def label(self, split):
        return self.dataset / 'labels' / split / Path(self.rows[split][0]['flat_file_name']).with_suffix('.txt')

    def image(self, split):
        return self.dataset / 'images' / split / self.rows[split][0]['flat_file_name']

    def write_images(self):
        for split, color in (('train', 'red'), ('val', 'green'), ('test', 'blue')):
            Image.new('RGB', (40, 20), color).save(self.image(split), 'JPEG')

    def audit(self, labels_only=True):
        return verify(self.dataset, labels_only=labels_only, annotations=self.source)

    def assert_issue(self, report, fragment):
        self.assertFalse(report['passed'], report)
        self.assertFalse(report['training_ready'])
        self.assertTrue(any(fragment in issue for issue in report['issues']), report['issues'])

    def test_labels_only_needs_no_pillow_and_never_certifies_images(self):
        with mock.patch.dict(sys.modules, {'PIL': None, 'PIL.Image': None}):
            report = self.audit()
        self.assertTrue(report['passed'], report['issues'])
        self.assertFalse(report['training_ready'])
        self.assertFalse(report['image_checks_performed'])
        self.assertEqual(sum(split['missing_images'] for split in report['splits'].values()), 3)
        self.assertEqual(report['source_coverage']['images'], 3)

    def test_full_without_pillow_returns_actionable_failure(self):
        with mock.patch.dict(sys.modules, {'PIL': None, 'PIL.Image': None}):
            self.assert_issue(self.audit(False), 'Pillow is required')

    def test_missing_source_returns_report_instead_of_crashing(self):
        self.source.unlink()
        self.assert_issue(self.audit(), 'source annotations: cannot read')

    def test_manifest_omission_is_checked_against_source(self):
        self.rows['test'] = []
        self.write_manifests()
        self.assert_issue(self.audit(), 'source coverage: 1 images missing')

    def test_changed_polygon_is_rejected_even_with_valid_normalized_coordinates(self):
        self.label('train').write_text('0 0.2 0.1 0.5 0.1 0.5 0.5 0.1 0.5\n')
        self.assert_issue(self.audit(), 'polygon differs from source')

    def test_multipart_bridge_can_repeat_source_vertices(self):
        self.data['annotations'][0]['segmentation'].append([24, 2, 32, 2, 28, 6])
        self.write_source()
        self.label('train').write_text(
            '0 0.1 0.1 0.5 0.1 0.6 0.1 0.8 0.1 0.7 0.3 '
            '0.6 0.1 0.5 0.1 0.5 0.5 0.1 0.5\n')
        report = self.audit()
        self.assertTrue(report['passed'], report['issues'])

    def test_multipart_cannot_omit_a_source_segment(self):
        self.data['annotations'][0]['segmentation'].append([24, 2, 32, 2, 28, 6])
        self.write_source()
        self.assert_issue(self.audit(), 'polygon differs from source')

    def test_manifest_and_label_cannot_hide_an_object_together(self):
        self.rows['train'][0]['object_count'] = 0
        self.write_manifests()
        self.label('train').write_text('')
        self.assert_issue(self.audit(), 'object count differs from source')

    def test_unsupported_source_segmentation_cannot_be_silently_skipped(self):
        self.data['annotations'][0]['segmentation'] = {'counts': 'rle', 'size': [20, 40]}
        self.write_source()
        self.assert_issue(self.audit(), 'RLE is unsupported')

    def test_source_outside_one_pixel_allowance_is_rejected(self):
        self.data['annotations'][0]['segmentation'][0][0] = -2
        self.write_source()
        self.assert_issue(self.audit(), 'more than one pixel')

    def test_collinear_vertices_are_not_a_segmentation_polygon(self):
        self.label('train').write_text('0 0.1 0.1 0.2 0.2 0.3 0.3\n')
        self.assert_issue(self.audit(), 'zero-area polygon')

    def test_malformed_manifest_is_reported(self):
        (self.dataset / 'manifests' / 'train.csv').write_text('image_id\n0\n')
        self.assert_issue(self.audit(), 'missing columns')

    def test_wrong_batch_assignment_is_rejected(self):
        self.rows['train'], self.rows['val'] = self.rows['val'], self.rows['train']
        self.write_manifests()
        self.assert_issue(self.audit(), 'batch is not assigned')

    def test_repeated_official_annotation_ids_across_images_retain_every_object(self):
        self.data['annotations'][1]['id'] = 0
        self.write_source()
        report = self.audit()
        self.assertTrue(report['passed'], report['issues'])
        self.assertEqual(sum(split['objects'] for split in report['splits'].values()), 3)
        self.assertTrue(any('repeated' in warning for warning in report['warnings']))

    def make_train_only_pool(self):
        # One source image is retained; the pool deliberately has no evaluation split.
        self.data['images'] = self.data['images'][:1]
        self.data['annotations'] = self.data['annotations'][:1]
        for split in ('val', 'test'):
            self.label(split).unlink()
            self.rows[split] = []
        self.write_source()
        self.write_manifests()

    def test_train_only_pool_allows_empty_evaluation_manifests(self):
        self.make_train_only_pool()
        report = verify(self.dataset, labels_only=True, annotations=self.source, split_policy='train_only')
        self.assertTrue(report['passed'], report['issues'])
        self.assertFalse(report['training_ready'])
        self.assertFalse(report['training_pool_ready'])
        # Selecting a pool policy cannot silently relax the default benchmark audit.
        self.assertFalse(self.audit()['passed'])

    def test_train_only_rejects_evaluation_images(self):
        report = verify(self.dataset, labels_only=True, annotations=self.source, split_policy='train_only')
        self.assert_issue(report, 'train-only pool must not contain evaluation images')

    @unittest.skipUnless(Image, 'Pillow not installed')
    def test_verified_train_only_pool_does_not_certify_a_benchmark(self):
        self.make_train_only_pool()
        Image.new('RGB', (40, 20), 'red').save(self.image('train'), 'JPEG')
        report = verify(self.dataset, labels_only=False, annotations=self.source, split_policy='train_only')
        self.assertTrue(report['passed'], report['issues'])
        self.assertTrue(report['training_pool_ready'])
        self.assertFalse(report['training_ready'])

    @unittest.skipUnless(Image, 'Pillow not installed')
    def test_full_complete_dataset_is_ready(self):
        self.write_images()
        report = self.audit(False)
        self.assertTrue(report['passed'], report['issues'])
        self.assertTrue(report['training_ready'])
        self.assertEqual(sum(split['verified_images'] for split in report['splits'].values()), 3)

    @unittest.skipUnless(Image, 'Pillow not installed')
    def test_full_reports_missing_images(self):
        self.write_images()
        self.image('train').unlink()
        self.assert_issue(self.audit(False), 'missing image')

    @unittest.skipUnless(Image, 'Pillow not installed')
    def test_proportional_fallback_is_ready_and_counted(self):
        self.write_images()
        Image.new('RGB', (20, 10), 'red').save(self.image('train'), 'JPEG')
        report = self.audit(False)
        self.assertTrue(report['passed'], report['issues'])
        self.assertEqual(report['splits']['train']['resized_images'], 1)

    @unittest.skipUnless(Image, 'Pillow not installed')
    def test_wrong_aspect_ratio_is_not_ready(self):
        self.write_images()
        Image.new('RGB', (20, 40), 'red').save(self.image('train'), 'JPEG')
        self.assert_issue(self.audit(False), 'aspect ratio differs')

    @unittest.skipUnless(Image, 'Pillow not installed')
    def test_manifest_dimensions_cannot_redefine_annotation_geometry(self):
        self.write_images()
        self.rows['train'][0]['width'], self.rows['train'][0]['height'] = 20, 40
        self.write_manifests()
        Image.new('RGB', (20, 40), 'red').save(self.image('train'), 'JPEG')
        report = self.audit(False)
        self.assert_issue(report, 'manifest dimensions differ')
        self.assertTrue(any('aspect ratio differs' in issue for issue in report['issues']))

    @unittest.skipUnless(Image, 'Pillow not installed')
    def test_truncated_decode_is_not_ready(self):
        self.write_images()
        self.image('train').write_bytes(self.image('train').read_bytes()[:-10])
        self.assert_issue(self.audit(False), 'invalid image')

    @unittest.skipUnless(Image, 'Pillow not installed')
    def test_exif_rotation_requires_normalization(self):
        self.write_images()
        exif = Image.Exif()
        exif[274] = 6
        Image.new('RGB', (40, 20), 'red').save(self.image('train'), 'JPEG', exif=exif)
        self.assert_issue(self.audit(False), 'EXIF orientation')

    @unittest.skipUnless(Image, 'Pillow not installed')
    def test_identical_pixels_across_splits_are_leakage(self):
        self.write_images()
        shutil.copyfile(self.image('train'), self.image('val'))
        self.assert_issue(self.audit(False), 'identical decoded pixels')


if __name__ == '__main__':
    unittest.main()
