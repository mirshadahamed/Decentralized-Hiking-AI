"""Verify MJU source coverage, polygon correspondence and RGB image readiness."""
import argparse
import json
from pathlib import Path
from .preprocess_mju_waste import DEFAULT_DATASET, DEFAULT_SOURCE, ROOT, verify, write_json, refresh_component_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--labels-only', action='store_true')
    parser.add_argument('--report', type=Path, default=ROOT / 'results/mju_preprocessing/local_readiness.json')
    args = parser.parse_args()
    report = verify(args.dataset, args.source, args.labels_only)
    write_json(args.report, report)
    if args.dataset.resolve() == DEFAULT_DATASET.resolve(): refresh_component_status(report)
    print(json.dumps({key: report.get(key) for key in ('passed', 'labels_valid', 'training_ready', 'auxiliary_train_ready', 'splits', 'issue_count')}, indent=2))
    if not report['passed']: raise SystemExit(1)


if __name__ == '__main__': main()
