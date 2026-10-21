"""Create hash-bound visual review pages for coarse source-negative photos."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .audit_urban_supplement import BASE
from ..train_yolov8 import ROOT, write_json


def make_pages():
    rows = json.loads((BASE / 'urban_verified_inventory.json').read_text())
    output = ROOT / 'runs/component2_cycle2/negative_review'
    output.mkdir(parents=True, exist_ok=True)
    candidates = []
    with zipfile.ZipFile(BASE / 'Urban Waste Dataset for Pakistan.zip') as archive:
        for split, limit in [('test', 60), ('val', 100), ('train', 240)]:
            seen = set()
            chosen = []
            eligible = sorted((r for r in rows if r['source_split'] == split and not r['quarantine_reasons']
                and r['source_label'].casefold() == 'not garbage'),
                key=lambda r: hashlib.sha256(('cycle2-review:'+r['source_image_sha256']).encode()).hexdigest())
            for row in eligible:
                if row['duplicate_group'] in seen:
                    continue
                seen.add(row['duplicate_group']); chosen.append(dict(row))
                if len(chosen) >= limit:
                    break
            for i, row in enumerate(chosen):
                row['review_id'] = f'{split[0].upper()}{i:03d}'
            for start in range(0, len(chosen), 12):
                grid = Image.new('RGB', (1600, 1290), 'white')
                draw = ImageDraw.Draw(grid)
                for tile, row in enumerate(chosen[start:start+12]):
                    im = ImageOps.exif_transpose(Image.open(io.BytesIO(archive.read(row['member'])))).convert('RGB')
                    im.thumbnail((400, 400))
                    x, y = (tile % 4) * 400, (tile // 4) * 430
                    grid.paste(im, (x, y))
                    draw.text((x+4, y+403), row['review_id']+' '+Path(row['member']).name, fill='black')
                    row['contact_page'] = f'{split}_{start//12:02d}.jpg'
                grid.save(output / f'{split}_{start//12:02d}.jpg', quality=95)
            candidates.extend(chosen)
    write_json(output / 'candidates.json', candidates)
    print(f'{len(candidates)} unique, source-labelled negatives prepared for explicit visual review.')
    return candidates


if __name__ == '__main__':
    make_pages()
