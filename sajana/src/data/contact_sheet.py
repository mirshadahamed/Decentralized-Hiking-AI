"""Render paired source and YOLO polygon previews for human alignment review."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw

DEFAULT_DATASET = Path(__file__).resolve().parents[2] / 'data/processed/taco_litter_seg'
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / 'results/taco_preprocessing'


def contact_sheet(dataset: Path, split: str, output: Path, max_images: int = 12) -> int:
    with (dataset / 'manifests' / f'{split}.csv').open(newline='') as stream:
        rows = [row for row in csv.DictReader(stream)
                if (dataset / 'images' / split / row['flat_file_name']).is_file()]
    if not rows:
        raise ValueError(f'No images found for {split}. Download or import images first.')
    count = min(max_images, len(rows))
    # Even coverage rather than only the first filenames from one batch.
    indices = [round(i * (len(rows) - 1) / max(1, count - 1)) for i in range(count)]
    width, height, caption = 320, 260, 38
    sheet = Image.new('RGB', (width * 2, (height + caption) * count), '#20252a')
    draw = ImageDraw.Draw(sheet)
    for index, row_index in enumerate(indices):
        row = rows[row_index]
        name = row['flat_file_name']
        with Image.open(dataset / 'images' / split / name) as image:
            image.load()
            if image.getexif().get(274, 1) not in (None, 1):
                raise ValueError(f'{name}: unresolved EXIF orientation; normalize before previewing')
            image = image.convert('RGB')
        image.thumbnail((width, height))
        overlay = image.convert('RGBA')
        layer = Image.new('RGBA', image.size)
        polygons = ImageDraw.Draw(layer)
        label = dataset / 'labels' / split / Path(name).with_suffix('.txt')
        for line in label.read_text().splitlines():
            if not line.strip():
                continue
            values = list(map(float, line.split()[1:]))
            points = [(x * image.width, y * image.height) for x, y in zip(values[::2], values[1::2])]
            polygons.polygon(points, fill=(20, 235, 120, 75), outline=(20, 255, 120, 240))
        overlay = Image.alpha_composite(overlay, layer).convert('RGB')
        top = index * (height + caption)
        for column, tile in enumerate((image, overlay)):
            sheet.paste(tile, (column * width + (width - tile.width) // 2, top))
        draw.text((8, top + height + 3), f'{split}/{name}', fill='white')
        draw.text((8, top + height + 19), 'Source image', fill='white')
        draw.text((width + 8, top + height + 19), f'Litter polygons: {row["object_count"]}', fill='white')
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=90)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--split', choices=('train', 'val', 'test', 'all'), default='all')
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--max-images', type=int, default=12)
    args = parser.parse_args()
    if args.max_images < 1:
        parser.error('--max-images must be positive')
    failed = False
    for split in ('train', 'val', 'test') if args.split == 'all' else (args.split,):
        output = args.output_dir / f'{split}_overlays.jpg'
        try:
            count = contact_sheet(args.dataset, split, output, args.max_images)
            print(f'{output}: {count} source/label pairs; review alignment before training')
        except (OSError, ValueError) as exc:
            print(exc)
            failed = True
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
