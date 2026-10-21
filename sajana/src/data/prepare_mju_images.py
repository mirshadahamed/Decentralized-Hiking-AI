"""Import only manifest-matched MJU RGB images; preserve depth files separately."""
import argparse
from pathlib import Path
from .preprocess_mju_waste import DEFAULT_DATASET, DEFAULT_SOURCE, ROOT, prepare_images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, default=ROOT / 'data/raw/mju_waste/extracted')
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    result = prepare_images(args.raw_root, args.dataset, args.source)
    print(f'Imported {result["imported"]} RGB images; {len(result["failures"])} failures.')
    if not result['passed']: raise SystemExit(1)


if __name__ == '__main__': main()
