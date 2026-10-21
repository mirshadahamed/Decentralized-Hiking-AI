"""Prepare pLitter GPS/count observations without treating them as image labels."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / 'data/interim/plitter/Mawanella_January_2022_Sample.csv'
DEFAULT_OUT = ROOT / 'data/processed/plitter_mawanella'
FIELDS = ['lon', 'lat', 'plastic_c', 'bin_c']


def _number(value, low=None, high=None, integer=False):
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError('expected a finite numeric value') from exc
    if not number.is_finite() or (low is not None and number < low) or (high is not None and number > high):
        raise ValueError('numeric value outside permitted range')
    if integer and number != number.to_integral_value():
        raise ValueError('counts must be nonnegative integers; fractional counts cannot be truncated')
    return number


def _csv(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def preprocess(source=DEFAULT_SOURCE, out=DEFAULT_OUT, report=None):
    source, out = Path(source), Path(out)
    raw = source.read_bytes()
    with source.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError(f'Expected columns {FIELDS}; found {reader.fieldnames}')
        rows = list(reader)
    clean, excluded, seen, grouped = [], [], Counter(), defaultdict(list)
    for line, row in enumerate(rows, 2):
        try:
            values = (_number(row['lon'], -180, 180), _number(row['lat'], -90, 90),
                      _number(row['plastic_c'], 0, integer=True), _number(row['bin_c'], 0, integer=True))
        except (ValueError, KeyError) as exc:
            excluded.append(dict(source_row=line, reason=str(exc), **row))
            continue
        item = dict(source_row=line, lon=str(values[0]), lat=str(values[1]),
                    plastic_c=int(values[2]), bin_c=int(values[3]),
                    repeated_exact_observation=int(seen[values] > 0))
        seen[values] += 1
        clean.append(item)
        grouped[values[:2]].append(item)
    aggregated = []
    for (lon, lat), records in sorted(grouped.items()):
        aggregated.append({'lon': str(lon), 'lat': str(lat), 'observations': len(records),
                           'plastic_observation_sum': sum(x['plastic_c'] for x in records),
                           'plastic_observation_max': max(x['plastic_c'] for x in records),
                           'bin_observation_sum': sum(x['bin_c'] for x in records),
                           'bin_observation_max': max(x['bin_c'] for x in records),
                           'repeated_exact_observations': sum(x['repeated_exact_observation'] for x in records)})
    out.mkdir(parents=True, exist_ok=True)
    _csv(out / 'mawanella_clean_observations.csv', clean, ['source_row'] + FIELDS + ['repeated_exact_observation'])
    _csv(out / 'mawanella_coordinate_aggregated.csv', aggregated,
         ['lon', 'lat', 'observations', 'plastic_observation_sum', 'plastic_observation_max',
          'bin_observation_sum', 'bin_observation_max', 'repeated_exact_observations'])
    _csv(out / 'mawanella_excluded_observations.csv', excluded, ['source_row', 'reason'] + FIELDS)
    result = {'source': str(source.resolve()), 'source_sha256': hashlib.sha256(raw).hexdigest(),
              'dataset': str(out.resolve()), 'role': 'geospatial mapping observations; not image training annotations',
              'passed': not excluded, 'preprocessing_complete': True, 'image_training_ready': False,
              'rows': len(rows), 'valid_rows': len(clean), 'excluded_rows': len(excluded),
              'exact_duplicate_rows': sum(x['repeated_exact_observation'] for x in clean),
              'unique_coordinates': len(grouped),
              'plastic_observation_sum': sum(x['plastic_c'] for x in clean),
              'bin_observation_sum': sum(x['bin_c'] for x in clean),
              'coordinate_reference': 'Longitude/latitude degrees retained; WGS84 assumed from mapping usage, CRS not declared in CSV',
              'warnings': ['All valid source observations are retained with source line numbers. Repeated counts may describe the same physical litter.',
                           'Observation sums are not verified counts of unique physical litter objects.',
                           'The CSV contains no image/frame identifiers, bounding boxes or segmentation masks.']}
    target = Path(report) if report else ROOT / 'results/plitter_preprocessing/mawanella_audit.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = preprocess(args.source, args.out, args.report)
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
