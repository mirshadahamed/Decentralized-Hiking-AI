"""MJU regressions for source geometry, negative samples, RGB/mask separation and combination."""
from __future__ import annotations
import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image

from sajana.src.data.preprocess_mju_waste import preprocess, verify, prepare_images
from sajana.src.data.download_mju_waste import extract_rgb
from sajana.src.data.build_litter_aux_combined import build
from sajana.src.data.preprocess_taco import preprocess as preprocess_taco


class MjuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'sources'; self.source.mkdir()
        self.dataset = self.root / 'mju'; self.raw = self.root / 'raw'; self.raw.mkdir()
        self.data = {}
        for index, split in enumerate(('train', 'val', 'test')):
            name = f'2020-01-07_16_00_{index * 4:02d}-00_color.png'
            self.data[split] = {'categories': [{'id': 0, 'name': 'Rubbish'}],
                                'images': [{'id': index, 'width': 64, 'height': 48, 'file_name': name}],
                                'annotations': [{'id': index, 'image_id': index, 'category_id': 0,
                                                 'segmentation': [4, 4, 30, 4, 30, 30, 4, 30],
                                                 'bbox': [999, 999, 999, 999]}]}
        self.data['train']['images'].append({'id': 3, 'width': 64, 'height': 48,
                                             'file_name': '2020-01-07_16_00_02-00_color.png'})
        self.write_source()

    def write_source(self):
        for split, data in self.data.items(): (self.source / f'{split}.json').write_text(json.dumps(data))

    def write_images(self):
        for split, color in [('train', 'red'), ('val', 'green'), ('test', 'blue')]:
            for index, image in enumerate(self.data[split]['images']):
                Image.new('RGB', (64, 48), 'purple' if index else color).save(self.raw / image['file_name'])

    def prepare(self):
        preprocess(self.source, self.dataset); self.write_images()
        self.assertTrue(prepare_images(self.raw, self.dataset, self.source)['passed'])

    def taco(self):
        source = self.root / 'taco.json'; out = self.root / 'taco'
        data = {'categories': [{'id': 0, 'name': 'litter'}], 'images': [], 'annotations': []}
        for i, (split, batch, color) in enumerate([('train','batch_1','yellow'), ('val','batch_3','cyan'), ('test','batch_14','orange')]):
            data['images'].append({'id':i, 'width':64, 'height':48, 'file_name':f'{batch}/a.jpg'})
            data['annotations'].append({'id':i, 'image_id':i, 'category_id':0, 'segmentation':[[4,4,30,4,30,30,4,30]]})
        source.write_text(json.dumps(data)); preprocess_taco(source, out)
        for split, batch, color in [('train','batch_1','yellow'), ('val','batch_3','cyan'), ('test','batch_14','orange')]:
            Image.new('RGB',(64,48),color).save(out/'images'/split/f'{batch}__a.jpg')
        return source, out

    def test_negative_images_preserved_and_bbox_does_not_scale_polygons(self):
        report = preprocess(self.source, self.dataset)
        self.assertEqual(report['splits']['train']['negative_images'], 1)
        name = self.data['train']['images'][0]['file_name']
        vals = (self.dataset/'labels/train'/Path(name).with_suffix('.txt')).read_text().split()
        self.assertEqual(float(vals[1]), 4/64)
        negative = self.data['train']['images'][1]['file_name']
        self.assertEqual((self.dataset/'labels/train'/Path(negative).with_suffix('.txt')).read_text(), '')
        audit = verify(self.dataset, self.source, labels_only=True)
        self.assertTrue(audit['passed']); self.assertFalse(audit['training_ready'])
        self.assertEqual(audit['temporal_audit']['cross_split_pairs_within_10s'], 2)

    def test_small_negative_coordinate_clipped_and_reported(self):
        self.data['train']['annotations'][0]['segmentation'][0] = -1.07; self.write_source()
        report = preprocess(self.source, self.dataset)
        self.assertEqual(report['coordinate_fixes'][0]['vertices'][0]['original'][0], -1.07)
        self.assertTrue(verify(self.dataset, self.source, labels_only=True)['passed'])

    def test_invalid_sources_fail_before_writing(self):
        original = copy.deepcopy(self.data)
        for kind in ('bounds', 'nan', 'reference', 'flat-shape'):
            with self.subTest(kind=kind):
                self.data = copy.deepcopy(original)
                ann = self.data['train']['annotations'][0]
                if kind == 'bounds': ann['segmentation'][0] = -3
                if kind == 'nan': ann['segmentation'][0] = float('nan')
                if kind == 'reference': ann['image_id'] = 999
                if kind == 'flat-shape': ann['segmentation'] = [[1,1,2,2,3,3]]
                self.write_source()
                with self.assertRaises(ValueError): preprocess(self.source, self.dataset)
                self.assertFalse(self.dataset.exists())

    def test_label_tampering_detected_against_source(self):
        preprocess(self.source, self.dataset)
        name = self.data['train']['images'][0]['file_name']
        (self.dataset/'labels/train'/Path(name).with_suffix('.txt')).write_text('0 0.2 0.2 0.4 0.2 0.4 0.4\n')
        self.assertFalse(verify(self.dataset, self.source, labels_only=True)['labels_valid'])

    def test_images_required_before_training_ready(self):
        preprocess(self.source, self.dataset)
        report = verify(self.dataset, self.source)
        self.assertFalse(report['training_ready']); self.assertFalse(report['auxiliary_train_ready'])
        self.prepare()
        report = verify(self.dataset, self.source)
        self.assertTrue(report['training_ready'], report['issues'])
        self.assertTrue(report['auxiliary_train_ready']); self.assertFalse(report['independent_evaluation_supported'])

    def test_rgb_masks_with_same_filename_are_not_imported_as_photos(self):
        preprocess(self.source, self.dataset); self.write_images()
        name = self.data['train']['images'][0]['file_name']
        (self.raw/'JPEGImages').mkdir(); (self.raw/'SegmentationClass').mkdir()
        (self.raw/name).replace(self.raw/'JPEGImages'/name)
        Image.new('L', (64,48), 1).save(self.raw/'SegmentationClass'/name)
        report = prepare_images(self.raw, self.dataset, self.source)
        self.assertTrue(report['passed'], report)
        with Image.open(self.dataset/'images/train'/name) as image: self.assertEqual(image.mode,'RGB')

    def test_wrong_geometry_and_mask_images_are_rejected(self):
        self.prepare(); name = self.data['train']['images'][0]['file_name']
        target = self.dataset/'images/train'/name
        # Replace the hardlink instead of modifying the raw image in place.
        tmp = target.with_suffix('.bad.png'); Image.new('RGB',(48,64),'red').save(tmp); tmp.replace(target)
        self.assertFalse(verify(self.dataset,self.source)['training_ready'])
        Image.new('L',(64,48),1).save(tmp);tmp.replace(target)
        report=verify(self.dataset,self.source)
        self.assertTrue(any('indexed/grayscale mask' in i for i in report['issues']))

    def test_archive_extracts_only_photos_with_expected_names(self):
        name = self.data['train']['images'][0]['file_name']; stream = io.BytesIO()
        Image.new('RGB',(64,48),'red').save(stream,'PNG'); rgb=stream.getvalue()
        archive = self.root/'archive.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('JPEGImages/'+name,rgb)
            z.writestr('SegmentationClass/'+name,b'mask data')
            z.writestr('../escape.txt',b'unsafe')
        out=self.root/'extracted'
        self.assertEqual(extract_rgb(archive,out,{name}),1)
        self.assertEqual((out/name).read_bytes(),rgb);self.assertFalse((self.root/'escape.txt').exists())

    def test_combined_uses_only_mju_train_and_taco_holdouts(self):
        self.prepare(); source,taco=self.taco();out=self.root/'combined'
        report=build(taco,self.dataset,out,source,self.source)
        self.assertTrue(report['training_ready'],report['issues'])
        self.assertEqual(report['splits']['train']['images'],3)
        self.assertEqual(report['splits']['val']['images'],1)
        self.assertTrue(all(p.name.startswith('taco__') for p in (out/'images/val').iterdir()))
        self.assertTrue(all(p.name.startswith('taco__') for p in (out/'images/test').iterdir()))

    def test_combined_refuses_missing_images_and_cross_source_pixel_leakage(self):
        preprocess(self.source,self.dataset);source,taco=self.taco();out=self.root/'combined'
        report=build(taco,self.dataset,out,source,self.source)
        self.assertFalse(report['training_ready']);self.assertFalse((out/'data.yaml').exists())
        self.prepare()
        target=self.dataset/'images/train'/self.data['train']['images'][0]['file_name']
        with Image.open(taco/'images/val/batch_3__a.jpg') as image:
            temporary=target.with_suffix('.new.png');image.convert('RGB').save(temporary);temporary.replace(target)
        report=build(taco,self.dataset,out,source,self.source)
        self.assertFalse(report['training_ready'])
        self.assertTrue(any('identical pixels across combined splits' in issue for issue in report['issues']))
        self.assertFalse((out/'data.yaml').exists())


if __name__=='__main__':unittest.main()
