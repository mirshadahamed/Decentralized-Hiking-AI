"""Create a small inference-only preview without changing resumable checkpoints.

Run with the pinned training environment. Uses CPU only, reads no dataset images,
installs no packages and does not claim to export an Android runtime model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def stable_snapshot(source, target, attempts=3):
    """Avoid consuming a half-written checkpoint while training continues."""
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target or target.exists():
        raise ValueError('Snapshot requires a new file separate from the source checkpoint')
    for _ in range(attempts):
        before = source.stat()
        shutil.copyfile(source, target)
        after = source.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns):
            return
    target.unlink(missing_ok=True)
    raise RuntimeError('Checkpoint kept changing; retry after its next completed save')


def prepare(checkpoint, output):
    checkpoint, output = Path(checkpoint).resolve(), Path(output).resolve()
    if not checkpoint.is_file() or checkpoint.suffix != '.pt':
        raise ValueError('A trusted local .pt checkpoint is required')
    # Unique output avoids overwriting either a trainer artifact or an earlier preview.
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / 'source_snapshot.tmp'
    partial = output / 'inference_preview.partial.pt'
    target = output / 'litter_inference_preview.pt'
    try:
        stable_snapshot(checkpoint, snapshot)
        import torch
        import ultralytics
        from ultralytics.utils.torch_utils import strip_optimizer
        if ultralytics.__version__ != '8.4.183':
            raise ValueError('Use the pinned Ultralytics 8.4.183 environment')
        torch.set_num_threads(1)
        original = torch.load(snapshot, map_location='cpu', weights_only=False)
        source_model = original.get('ema') or original.get('model')
        if source_model is None or getattr(source_model, 'names', None) != {0: 'litter'}:
            raise ValueError('Expected the current one-class litter checkpoint')
        source_epoch = int(original.get('epoch', -1)) + 1
        source_hash = sha256(snapshot)
        source_bytes = snapshot.stat().st_size
        if not strip_optimizer(snapshot, s=str(partial)):
            raise ValueError('Inference checkpoint could not be created')
        packed = torch.load(partial, map_location='cpu', weights_only=False)
        packed_model = packed['model']
        before, after = source_model.state_dict(), packed_model.state_dict()
        if type(source_model) is not type(packed_model) or before.keys() != after.keys():
            raise ValueError('Model structure changed during packing')
        if any(not torch.equal(before[key], after[key]) for key in before):
            raise ValueError('Packing changed saved inference tensors')
        if packed.get('optimizer') is not None or packed.get('ema') is not None:
            raise ValueError('Training-only state remains in inference artifact')
        if packed_model.names != source_model.names:
            raise ValueError('Class mapping changed during packing')
        partial.replace(target)
        report = {
            'checked_at': datetime.now(ZoneInfo('Asia/Colombo')).isoformat(),
            'source_checkpoint': str(checkpoint), 'source_snapshot_sha256': source_hash,
            'source_checkpoint_epoch': source_epoch if source_epoch else None,
            'source_training_checkpoint_bytes': source_bytes,
            'preview_artifact': str(target), 'preview_sha256': sha256(target),
            'preview_bytes': target.stat().st_size,
            'size_reduction_percent': 100 * (1 - target.stat().st_size / source_bytes),
            'parameter_count': sum(p.numel() for p in packed_model.parameters()),
            'class_mapping': packed_model.names,
            'saved_inference_tensors_identical': True,
            'source_checkpoint_written_by_tool': False,
            'training_resume_supported_by_preview': False,
            'dataset_images_loaded': 0, 'test_model_evaluation_performed': False,
            'device_used_by_tool': 'cpu', 'android_runtime_exported': False,
            'physical_phone_memory_measured': False, 'app_release_ready': False,
            'note': 'Intermediate PyTorch snapshot from ongoing model development; not an Android release model. File-size savings do not measure inference RAM.',
        }
        (output / 'preview_report.json').write_text(json.dumps(report, indent=2) + '\n')
        return report
    finally:
        snapshot.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.checkpoint is None:
        state = json.loads((ROOT / 'results/yolov8_training/status.json').read_text())
        args.checkpoint = Path(state['best_checkpoint'])
    if args.output is None:
        stamp = datetime.now(ZoneInfo('Asia/Colombo')).strftime('%Y%m%d_%H%M%S_%f')
        args.output = ROOT / 'runs/mobile_litter_preview' / stamp
    # Explicitly prohibit automatic dependency installs in this training environment.
    os.environ.setdefault('YOLO_AUTOINSTALL', 'false')
    os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'data/raw/ultralytics_settings'))
    print(json.dumps(prepare(args.checkpoint, args.output), indent=2))


if __name__ == '__main__':
    main()
