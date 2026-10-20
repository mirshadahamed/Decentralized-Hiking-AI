import csv
import json
import tempfile
import unittest
from pathlib import Path

from sajana.src.train_yolov8 import finite_json, make_smoke_data, require_full_report, write_data_yaml
from sajana.src.data.audit_component2_datasets import catalog


class TrainingGuardrailTests(unittest.TestCase):
    def test_labels_only_or_wrong_dataset_never_authorizes_training(self):
        with tempfile.TemporaryDirectory() as folder:
            dataset, annotations = Path(folder)/'dataset', Path(folder)/'source.json'
            report = {'passed': True, 'training_ready': True, 'mode': 'labels_only',
                      'image_checks_performed': False, 'dataset': str(dataset), 'annotations': str(annotations),
                      'splits': {s: {'images': 1, 'verified_images': 1} for s in ('train','val','test')}}
            with self.assertRaises(ValueError): require_full_report(report, dataset, annotations)
            report.update(mode='full', image_checks_performed=True)
            require_full_report(report, dataset, annotations)
            with self.assertRaises(ValueError): require_full_report(report, dataset/'other', annotations)
            report['splits']['val']['verified_images'] = 0
            with self.assertRaises(ValueError): require_full_report(report, dataset, annotations)

    def test_training_yaml_excludes_the_test_split(self):
        with tempfile.TemporaryDirectory() as folder:
            path=write_data_yaml(Path(folder)/'data.yaml',Path(folder)/'dataset')
            self.assertNotIn('test:',path.read_text())
            self.assertIn('val: "images/val"',path.read_text())
            self.assertIn('0: litter',path.read_text())

    def test_smoke_data_uses_only_train_images_and_unchanged_labels(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);dataset=root/'dataset';(dataset/'manifests').mkdir(parents=True)
            for kind in ('images','labels'):
                for split in ('train','val','test'):(dataset/kind/split).mkdir(parents=True)
            rows=[{'flat_file_name':f'train_{i}.jpg'} for i in range(4)]
            with (dataset/'manifests/train.csv').open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=['flat_file_name']);writer.writeheader();writer.writerows(rows)
            for row in rows:
                name=row['flat_file_name'];(dataset/'images/train'/name).write_bytes(name.encode())
                (dataset/'labels/train'/Path(name).with_suffix('.txt')).write_text('0 0 0 1 0 1 1\n')
            (dataset/'images/test/heldout.jpg').write_bytes(b'never train on this')
            yaml,chosen=make_smoke_data(dataset,root/'smoke',3)
            self.assertEqual(len(chosen),3)
            self.assertIn('val: "images/train"',yaml.read_text())
            self.assertFalse(list((root/'smoke').rglob('heldout.jpg')))
            for row in chosen:
                label=Path(row['flat_file_name']).with_suffix('.txt')
                self.assertEqual((root/'smoke/labels/train'/label).read_bytes(),(dataset/'labels/train'/label).read_bytes())

    def test_active_training_status_is_reported_without_claiming_damage_data_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'results/yolov8_training/status.json';path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'training_started':True,'phase':'training','main_batches_seen':4}))
            report=catalog(root)
            self.assertTrue(report['model_training_started'])
            self.assertEqual(report['model_training']['main_batches_seen'],4)
            self.assertFalse(report['full_concurrent_model_data_ready'])

    def test_status_json_does_not_write_nonfinite_numeric_tokens(self):
        self.assertEqual(finite_json({'loss':float('nan'),'metric':float('inf')}),{'loss':None,'metric':None})


if __name__=='__main__':unittest.main()
