"""Read-only training health/ETA inspection; never loads held-out images or a model.

The core check uses the standard library; --plot requires the training environment's
matplotlib. Reports are snapshots, not certification of app accuracy. --watch
refreshes them while the detached trainer is active.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import statistics
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .train_yolov8 import finite_json

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results/yolov8_training'
TERMINAL_PHASES = {'completed', 'failed', 'interrupted'}


def completed_rows(path):
    """Ignore a partly written last CSV line during live training."""
    path = Path(path)
    if not path.exists():
        return []
    content = path.read_text()
    if content and not content.endswith('\n'):
        content = content.rpartition('\n')[0] + '\n'
    rows = []
    for raw in csv.DictReader(io.StringIO(content)):
        row = {key.strip(): float(value) for key, value in raw.items()}
        rows.append(row)
    return rows


def epoch_timing(rows, planned_epochs):
    """Estimate the full budget from recent epoch durations, including validation.

    The range is observed timing variation, not a statistical confidence interval.
    No predicted early-stopping time is claimed.
    """
    if not rows:
        return None
    times = [row['time'] for row in rows]
    durations = [b - a for a, b in zip([0.0] + times[:-1], times)]
    if any(not math.isfinite(x) or x <= 0 for x in durations):
        return None
    recent = durations[-5:]
    remaining = max(0, int(planned_epochs) - int(rows[-1]['epoch']))
    return {
        'recent_epochs': len(recent),
        'recent_seconds_per_epoch_median': statistics.median(recent),
        'recent_seconds_per_epoch_range': [min(recent), max(recent)],
        'remaining_epochs_after_last_completed': remaining,
        'remaining_seconds_to_epoch_budget': remaining * statistics.median(recent),
        'remaining_seconds_observed_range': [remaining * min(recent), remaining * max(recent)],
        'method': 'Last five completed epoch durations, including validation; current partial epoch not subtracted.',
        'early_stopping_finish_time_predictable': False,
    }


def inspect(status_path=RESULTS / 'status.json', checked_at=None):
    checked_at = checked_at or datetime.now(ZoneInfo('Asia/Colombo'))
    status = json.loads(Path(status_path).read_text())
    run = Path(status['run_directory'])
    rows = completed_rows(run / 'fit/results.csv')
    issues = []
    all_finite = all(math.isfinite(v) for row in rows for v in row.values())
    if not all_finite:
        issues.append('Nonfinite value in completed epoch results')
    batch_loss = status.get('last_training_loss')
    if batch_loss is not None and not math.isfinite(float(batch_loss)):
        issues.append('Nonfinite latest training loss')
    if status.get('error'):
        issues.append(status['error'])
    timing = epoch_timing(rows, status['planned_epochs'])
    age = (checked_at - datetime.fromisoformat(status['updated_at'])).total_seconds()
    stale_after = max(600, 3 * timing['recent_seconds_per_epoch_median']) if timing else 600
    if status['phase'] not in TERMINAL_PHASES and age > stale_after:
        issues.append('Training heartbeat is stale; inspect process and console before continuing')
    checkpoints = {}
    for name in ('best', 'last'):
        path = run / 'fit/weights' / (name + '.pt')
        checkpoints[name] = {'path': str(path), 'exists': path.is_file(),
                             'bytes': path.stat().st_size if path.exists() else 0}
        if rows and checkpoints[name]['bytes'] == 0:
            issues.append('Missing nonempty ' + name + ' checkpoint after a completed epoch')
    manifest_path = run / 'run_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    yaml = (run / 'data.yaml').read_text()
    test_excluded = (manifest.get('test_split_loaded') is False and
                     not any(line.strip().startswith('test:') for line in yaml.splitlines()))
    if not test_excluded:
        issues.append('Held-out test exclusion is not established by run records')
    trainer = ROOT / 'src/train_yolov8.py'
    source_matches = hashlib.sha256(trainer.read_bytes()).hexdigest() == manifest['trainer_source_sha256']
    if not source_matches:
        issues.append('Trainer source differs from frozen run; use the recorded commit when reproducing')
    trend_keys = ('train/seg_loss', 'train/cls_loss', 'val/seg_loss',
                  'metrics/mAP50(M)', 'metrics/mAP50-95(M)',
                  'metrics/precision(M)', 'metrics/recall(M)')
    trend = {key: {'first': rows[0][key], 'latest': rows[-1][key]} for key in trend_keys} if rows else {}
    report = {
        'checked_at': checked_at.isoformat(), 'run_directory': str(run),
        'phase': status['phase'], 'current_epoch': status.get('current_epoch'),
        'completed_epochs': len(rows), 'planned_epochs': status['planned_epochs'],
        'heartbeat_age_seconds': max(0, age), 'main_batches_seen': status.get('main_batches_seen', 0),
        'training_functioning_at_check': bool(status.get('full_run_started') and not issues and
                                              status['phase'] not in ('failed', 'interrupted')),
        'completed_epoch_values_finite': all_finite, 'issues': issues,
        'test_split_excluded_from_training': test_excluded,
        'trainer_source_matches_frozen_run': source_matches,
        'checkpoints': checkpoints, 'validation_trend': trend,
        'timing': timing, 'app_model_ready': False,
        'app_readiness_not_established_by_training_health': True,
        'current_trained_classes': status['target_classes'],
        'remaining_app_requirements': [
            'Finish validation-based model selection, including the planned TACO+MJU comparison',
            'Inspect validation misses/false alarms and select thresholds without using test',
            'Evaluate the selected approach once on the reserved test and independent local photos',
            'Collect reviewed trail-corridor, obstruction and clear-trail examples before obstacle training',
            'Validate exported predictions and measure speed/memory on the target Android phone',
        ],
    }
    if timing and status['phase'] not in TERMINAL_PHASES:
        report['estimated_full_budget_finish'] = (checked_at + timedelta(
            seconds=timing['remaining_seconds_to_epoch_budget'])).isoformat()
    return finite_json(report), rows


def save_report(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / 'health_report.tmp'
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    temporary.replace(output / 'health_report.json')
    timing = report['timing']
    lines = ['# YOLOv8 training check', '', 'Checked: ' + report['checked_at'], '',
             f"Completed epochs: {report['completed_epochs']}/{report['planned_epochs']}. Phase: {report['phase']}.",
             f"Training functioning at check: {report['training_functioning_at_check']}. App model ready: False.", '']
    if timing:
        lo, hi = timing['remaining_seconds_observed_range']
        lines += [f"Observed recent pace: {timing['recent_seconds_per_epoch_median']/60:.1f} minutes/epoch.",
                  f"Remaining to full budget: {lo/3600:.1f}–{hi/3600:.1f} hours at observed speeds.",
                  'This includes validation and excludes unpredictable early stopping, sleep or slowdown.', '']
    lines += ['| Metric | First epoch | Latest epoch |', '| --- | ---: | ---: |']
    for key, value in report['validation_trend'].items():
        first = f"{value['first']:.4f}" if value['first'] is not None else 'nonfinite'
        latest = f"{value['latest']:.4f}" if value['latest'] is not None else 'nonfinite'
        lines.append(f"| {key} | {first} | {latest} |")
    lines += ['', 'AP is not classification accuracy. The current checkpoint predicts litter only.',
              'No obstacle/clear-trail or Android release readiness is claimed.', '']
    if report['issues']:
        lines += ['Issues:', ''] + ['- ' + issue for issue in report['issues']] + ['']
    (output / 'HEALTH.md').write_text('\n'.join(lines))


def save_plot(rows, output):
    if not rows:
        return
    import os
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'data/raw/matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    epochs = [row['epoch'] for row in rows]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for key, label in [('train/seg_loss', 'Training'), ('val/seg_loss', 'Validation')]:
        axes[0].plot(epochs, [row[key] for row in rows], marker='o', label=label)
    axes[0].set(title='Segmentation loss', xlabel='Completed epoch', ylabel='Loss')
    for key, label in [('metrics/mAP50(M)', 'Mask mAP50'), ('metrics/mAP50-95(M)', 'Mask mAP50–95')]:
        axes[1].plot(epochs, [100*row[key] for row in rows], marker='o', label=label)
    axes[1].set(title='Validation masks — TACO', xlabel='Completed epoch', ylabel='AP (%)', ylim=(0, 100))
    for ax in axes:
        ax.legend(); ax.grid(alpha=0.2)
    fig.suptitle('YOLOv8n-seg litter baseline — early training, app readiness pending')
    fig.tight_layout()
    fig.savefig(Path(output) / 'learning_curves.png', dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status', type=Path, default=RESULTS / 'status.json')
    parser.add_argument('--output', type=Path, default=RESULTS)
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--interval', type=float, default=60)
    parser.add_argument('--plot', action='store_true')
    args = parser.parse_args()
    if args.interval < 10:
        parser.error('Refresh interval must be at least 10 seconds')
    plotted_epoch = None
    while True:
        report, rows = inspect(args.status)
        save_report(report, args.output)
        if args.plot and plotted_epoch != len(rows):
            save_plot(rows, args.output)
            plotted_epoch = len(rows)
        print(json.dumps({key: report[key] for key in ('checked_at', 'phase', 'completed_epochs',
              'training_functioning_at_check', 'issues', 'timing', 'app_model_ready')}, allow_nan=False), flush=True)
        if not args.watch or report['phase'] in TERMINAL_PHASES or report['issues']:
            break
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
