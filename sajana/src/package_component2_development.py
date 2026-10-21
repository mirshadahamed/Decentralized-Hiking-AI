"""Package only frozen development assets and quality evidence, never datasets."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from .train_yolov8 import ROOT, now, sha256, write_json


def package():
    manifest_path = ROOT / 'configs/component2_development_models.json'
    manifest = json.loads(manifest_path.read_text())
    evidence = ROOT / 'results/component2_training/quality/public_test_results.json'
    if not evidence.exists():
        raise ValueError('Frozen holdout evidence is required before the development handoff')
    files = [(ROOT.parent / 'assets/models/component2_manifest.json', 'component2_manifest.json'),
             (ROOT / 'docs/COMPONENT2_DEVELOPMENT_HANDOFF.md', 'README.md'),
             (ROOT / 'results/component2_training/FINAL_QUALITY_REPORT.md', 'FINAL_QUALITY_REPORT.md'),
             (evidence, 'public_test_results.json')]
    for task, spec in manifest['models'].items():
        path = Path(spec['checkpoint'])
        if sha256(path) != spec['checkpoint_sha256']:
            raise ValueError('Frozen development model changed: ' + task)
        files.append((path, path.name))
    output = ROOT / 'runs/component2_quality/component2_development_bundle.zip'
    checksums = '\n'.join(sha256(path) + '  ' + name for path, name in files) + '\n'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, name in files:
            archive.write(path, name)
        archive.writestr('SHA256SUMS.txt', checksums)
    report = {'packaged_at': now(), 'bundle': str(output), 'bundle_bytes': output.stat().st_size,
              'sha256': sha256(output), 'models_bytes': sum(r['bytes'] for r in manifest['models'].values()),
              'contains_training_photos': False, 'contains_python_environment': False,
              'use': 'development_only', 'quality_accepted_for_app': manifest['quality_accepted_for_app'],
              'full_component_ready': False}
    write_json(ROOT / 'results/component2_training/development_bundle.json', report)
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    package()
