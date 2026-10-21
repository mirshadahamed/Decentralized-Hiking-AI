"""Standalone CPU repeat-photo checks; explicitly not an Android RAM benchmark."""
from __future__ import annotations

import argparse
import gc
import json
import platform
import resource
import time
from pathlib import Path


def run(manifest_path, photo, output):
    import cv2
    import numpy as np
    import psutil
    from PIL import Image, ImageOps
    from ai_edge_litert.interpreter import Interpreter
    process = psutil.Process()
    baseline = process.memory_info().rss
    manifest = json.loads(Path(manifest_path).read_text())
    models = {}
    with Image.open(photo) as source:
        rgb = np.asarray(ImageOps.exif_transpose(source).convert('RGB'))
    for task, spec in manifest['models'].items():
        size = spec['imgsz']; height, width = rgb.shape[:2]
        gain = min(size / height, size / width)
        w, h = round(width * gain), round(height * gain)
        image = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_LINEAR)
        dw, dh = (size - w) / 2, (size - h) / 2
        image = cv2.copyMakeBorder(image, round(dh - .1), round(dh + .1), round(dw - .1),
                                   round(dw + .1), cv2.BORDER_CONSTANT, value=(114, 114, 114))
        tensor = image[None].astype(np.float32) / 255
        start = time.perf_counter()
        interpreter = Interpreter(model_path=spec['checkpoint'], num_threads=2)
        interpreter.allocate_tensors()
        cold = (time.perf_counter() - start) * 1000
        inp = interpreter.get_input_details()[0]; outputs = interpreter.get_output_details()
        if inp['shape'].tolist() != [1, size, size, 3] or inp['dtype'] != np.float32:
            raise ValueError('Unexpected exported image input contract')

        def invoke():
            interpreter.set_tensor(inp['index'], tensor)
            interpreter.invoke()
            result = [interpreter.get_tensor(o['index']) for o in outputs]
            if any(not np.isfinite(x).all() for x in result):
                raise ValueError('Nonfinite exported output')
            return result

        expected = invoke()
        for _ in range(3):
            actual = invoke()
            if any(not np.allclose(a, b, atol=1e-6, rtol=1e-5) for a, b in zip(actual, expected)):
                raise ValueError('Warm-up predictions are not repeatable')
        warm_rss = process.memory_info().rss
        times, memory_samples = [], []
        for repeat in range(40):
            start = time.perf_counter(); actual = invoke(); times.append((time.perf_counter() - start) * 1000)
            if any(not np.allclose(a, b, atol=1e-6, rtol=1e-5) for a, b in zip(actual, expected)):
                raise ValueError('Repeated identical photos changed model outputs')
            if (repeat + 1) % 10 == 0:
                memory_samples.append({'repeat': repeat + 1, 'rss_bytes': process.memory_info().rss})
        models[task] = {'cold_interpreter_ms': cold, 'warm_median_ms': float(np.median(times)),
                        'warm_p95_ms': float(np.percentile(times, 95)), 'repeated_photos': 40,
                        'all_outputs_finite_and_repeatable': True,
                        'steady_state_rss_change_bytes': process.memory_info().rss - warm_rss,
                        'memory_samples_after_warmup': memory_samples,
                        'artifact_bytes': Path(spec['checkpoint']).stat().st_size}
        del interpreter, expected, actual
        gc.collect()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() != 'Darwin':
        peak *= 1024
    record = {'platform': platform.platform(), 'runtime': 'ai-edge-litert 2.1.4 CPU, two threads',
              'python_torch_stack_used': False, 'physical_android_test': False,
              'process_rss_before_models_bytes': baseline, 'process_peak_rss_bytes': peak,
              'models': models, 'app_release_ready': False,
              'note': 'Mac Python process measurements include Python, NumPy, image decoding and interpreter overhead; they do not establish Android PSS, RAM, latency or battery behavior.'}
    Path(output).write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.manifest, args.image, args.output)
