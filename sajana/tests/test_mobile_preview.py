import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sajana.src.prepare_mobile_yolov8 import sha256, stable_snapshot


class MobilePreviewTests(unittest.TestCase):
    def test_snapshot_retries_a_concurrent_checkpoint_save(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'best.pt', Path(folder)/'snapshot.tmp'
            source.write_bytes(b'old')
            import shutil
            copy = shutil.copyfile
            calls = []

            def writing_source(a, b):
                copy(a, b)
                if not calls:
                    source.write_bytes(b'new completed checkpoint')
                calls.append(True)

            with patch('sajana.src.prepare_mobile_yolov8.shutil.copyfile', side_effect=writing_source):
                stable_snapshot(source, target)
            self.assertEqual(target.read_bytes(), b'new completed checkpoint')
            self.assertEqual(len(calls), 2)

    def test_snapshot_refuses_to_overwrite_source_or_existing_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'best.pt', Path(folder)/'prior.pt'
            source.write_bytes(b'resumable'); target.write_bytes(b'prior preview')
            for destination in (source, target):
                with self.assertRaises(ValueError):
                    stable_snapshot(source, destination)
            self.assertEqual(source.read_bytes(), b'resumable')
            self.assertEqual(target.read_bytes(), b'prior preview')

    def test_packing_preserves_source_and_weights_without_export_or_dataset_access(self):
        # Run the pinned packing API in isolation: Ultralytics patches global
        # Pillow on import and must not affect unrelated image verifier tests.
        import torch
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder)/'best.pt', Path(folder)/'preview'
            model = torch.nn.Linear(4, 2).half(); model.names = {0: 'litter'}
            torch.save({'model': None, 'ema': model, 'epoch': 12,
                        'optimizer': {'fixture': torch.ones(4096)}, 'train_args': {}}, source)
            source_hash = sha256(source)
            env = dict(os.environ, YOLO_CONFIG_DIR=str(Path.cwd()/'sajana/data/raw/ultralytics_settings'),
                       YOLO_AUTOINSTALL='false')
            result = subprocess.run([sys.executable, '-B', '-m', 'sajana.src.prepare_mobile_yolov8',
                                     '--checkpoint', str(source), '--output', str(output)],
                                    env=env, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output/'preview_report.json').read_text())
            self.assertEqual(sha256(source), source_hash)
            self.assertEqual(report['source_checkpoint_epoch'], 13)
            self.assertTrue(report['saved_inference_tensors_identical'])
            self.assertFalse(report['training_resume_supported_by_preview'])
            self.assertFalse(report['android_runtime_exported'])
            self.assertFalse(report['physical_phone_memory_measured'])
            self.assertFalse(report['app_release_ready'])
            self.assertEqual(report['dataset_images_loaded'], 0)
            self.assertLess(report['preview_bytes'], report['source_training_checkpoint_bytes'])
            self.assertEqual({p.name for p in output.iterdir()}, {'litter_inference_preview.pt', 'preview_report.json'})


if __name__ == '__main__':
    unittest.main()
