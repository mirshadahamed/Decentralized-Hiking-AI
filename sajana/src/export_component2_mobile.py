"""Mac-compatible ONNX -> TensorFlow -> LiteRT export with frozen train calibration.

The pinned direct LiteRT Torch exporter requires Linux. This explicit, versioned
fallback keeps the YOLOv8 architecture and verifies the resulting tensors.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch

from .assess_compact_models import environment
from .prepare_compact_component2 import configuration, verify_compact
from .train_yolov8 import ROOT, now, sha256, write_json

OUTPUT = ROOT / 'runs/component2_mobile'
REPORTS = ROOT / 'results/component2_training/mobile_exports'


def image_tensor(path, size):
    import numpy as np
    from PIL import Image, ImageOps
    from ultralytics.data.augment import LetterBox
    with Image.open(path) as image:
        rgb = np.asarray(ImageOps.exif_transpose(image).convert('RGB'))
    padded = LetterBox(new_shape=(size, size), auto=False, stride=32)(image=rgb)
    return np.ascontiguousarray(padded[None], dtype=np.float32) / 255.0


def export(checkpoint, task, size, tag):
    import numpy as np
    import onnx
    import torch
    import tensorflow as tf
    from ai_edge_litert.interpreter import Interpreter
    from onnx2tf import convert
    from ultralytics import YOLO

    torch.set_num_threads(2)
    tf.config.threading.set_inter_op_parallelism_threads(2)
    tf.config.threading.set_intra_op_parallelism_threads(2)
    cfg = configuration(); verified = verify_compact(cfg)
    folder = OUTPUT / tag
    if folder.exists():
        raise ValueError('Use a fresh export tag; earlier exports are preserved')
    folder.mkdir(parents=True)
    source = folder / 'model.pt'; shutil.copyfile(checkpoint, source)
    model = YOLO(str(source), task=cfg[task]['task'])
    names = {int(k): v for k, v in cfg[task]['names'].items()}
    if model.names != names:
        raise ValueError('Export checkpoint classes do not match the intended task')
    onnx_path = Path(model.export(format='onnx', imgsz=size, batch=1, device='cpu',
                                 opset=17, simplify=True, dynamic=False, nms=False))
    graph = onnx.load(onnx_path)
    output = graph.graph.output[0]
    channels = output.type.tensor_type.shape.dim[1].dim_value
    if channels != 4 + len(names) + (32 if task == 'litter' else 0):
        raise ValueError('Unexpected YOLOv8 dense output contract')
    name = output.name; unscaled = name + '_pixel_coordinates'
    for node in graph.graph.node:
        for i, value in enumerate(node.output):
            if value == name:
                node.output[i] = unscaled
    scale = np.ones((1, channels, 1), dtype=np.float32); scale[:, :4] /= size
    graph.graph.initializer.append(onnx.numpy_helper.from_array(scale, name='coordinate_scale'))
    graph.graph.node.append(onnx.helper.make_node('Mul', [unscaled, 'coordinate_scale'], [name]))
    onnx.checker.check_model(graph); onnx.save(graph, onnx_path)
    # Normalized coordinate output avoids large pixel coordinates degrading INT8 class-score resolution.
    dataset = ROOT / cfg['output'] / task
    candidates = list((dataset / 'images/train').glob('*.jpg'))
    candidates.sort(key=lambda p: hashlib.sha256(('42:' + p.name).encode()).hexdigest())
    calibration = candidates[:64]
    sample = folder / 'train_sample.npy'
    np.save(sample, image_tensor(calibration[0], size))
    converted = folder / 'saved_model'
    # This converter otherwise downloads COCO dummy images even with custom input.
    # Keep both its shape checks and our quantization strictly on selected training photos.
    conversion_module = importlib.import_module('onnx2tf.onnx2tf')
    with patch.object(conversion_module, 'download_test_image_data', return_value=np.load(sample)):
        convert(input_onnx_file_path=str(onnx_path), output_folder_path=str(converted),
                output_signaturedefs=True, not_use_onnxsim=True, disable_strict_mode=False,
                custom_input_op_name_np_data_path=[['images', str(sample)]], non_verbose=True)
    sample.unlink()
    metadata = {'description': 'Component 2 development model; quality acceptance is separate',
                'version': '8.4.183', 'task': cfg[task]['task'], 'names': names,
                'stride': 32, 'batch': 1, 'imgsz': [size, size], 'channels': 3,
                'end2end': False, 'head': 'Segment' if task == 'litter' else 'Detect'}
    artifacts = {}
    for precision in ('fp32', 'fp16', 'dynamic_int8', 'int8'):
        path = folder / (task + '_' + precision + '.tflite')
        if precision == 'fp32':
            generated = next(converted.glob('*_float32.tflite'))
            shutil.copyfile(generated, path)
        else:
            converter = tf.lite.TFLiteConverter.from_saved_model(str(converted))
            converter.optimizations = [tf.lite.Optimize.DEFAULT]

            def representative():
                for photo in calibration:
                    yield [image_tensor(photo, size)]

            if precision == 'fp16':
                converter.target_spec.supported_types = [tf.float16]
            elif precision == 'int8':
                converter.representative_dataset = representative
                converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
            converter.inference_input_type = tf.float32
            converter.inference_output_type = tf.float32
            path.write_bytes(converter.convert())
        with zipfile.ZipFile(path, 'a', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('metadata.json', json.dumps(metadata))
        interpreter = Interpreter(model_path=str(path), num_threads=2)
        interpreter.allocate_tensors()
        artifacts[precision] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha256(path),
                                'inputs': [{'name': d['name'], 'shape': d['shape'].tolist(),
                                            'dtype': str(d['dtype'])} for d in interpreter.get_input_details()],
                                'outputs': [{'name': d['name'], 'shape': d['shape'].tolist(),
                                             'dtype': str(d['dtype'])} for d in interpreter.get_output_details()]}
    write_json(folder / 'calibration.json', [{'split': 'train', 'image': str(p), 'sha256': sha256(p)} for p in calibration])
    record = {'completed_at': now(), 'task': task, 'imgsz': size, 'source_checkpoint': str(checkpoint),
              'source_sha256': sha256(checkpoint), 'artifacts': artifacts,
              'conversion_route': 'Pinned ONNX opset17 -> onnx2tf 1.26.3 -> TensorFlow 2.19 LiteRT',
              'calibration_images': len(calibration), 'calibration_split': 'train',
              'calibration_manifest_sha256': sha256(folder / 'calibration.json'),
              'dataset_inventory_sha256': verified['inventory_sha256'],
              'coordinates': 'First four dense output channels are xywh normalized to square input; prototypes are NHWC.',
              'accuracy_validated_after_export': False, 'physical_phone_benchmarked': False,
              'full_component_ready': False}
    write_json(REPORTS / (tag + '.json'), record)
    print(json.dumps(record, indent=2))
    return record


if __name__ == '__main__':
    environment()
    os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
    os.environ.setdefault('TF_USE_LEGACY_KERAS', '1')
    os.environ.setdefault('KERAS_HOME', str(ROOT / 'data/raw/keras'))
    os.environ.setdefault('OMP_NUM_THREADS', '2')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--task', choices=['litter', 'obstacle'], required=True)
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    export(args.checkpoint, args.task, args.imgsz, args.tag)
