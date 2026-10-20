"""Prepare official WildScenes opt2d RGB/semantic masks, preserving source IDs."""
from __future__ import annotations
import argparse
import ast
import concurrent.futures
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
from .download_wildscenes import RAW, REVISION, REPOSITORY, split_records, file_digest
from .preprocess_mju_waste import ROOT, write_json

DATASET = ROOT / 'data/processed/wildscenes_terrain_semantic'
RESULTS = ROOT / 'results/wildscenes_preprocessing'


def source_classes(metadata):
    source = Path(metadata) / 'wildscenes/mmseg_wildscenes/dataset/wildscenes.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'METAINFO' for target in node.targets):
            values = ast.literal_eval(node.value)
            classes = list(values['classes']); palette = [list(color) for color in values['palette']]
            if len(classes) != len(palette) or len(classes) != len(set(classes)):
                raise ValueError('Source class definition is inconsistent')
            if classes[0] != 'unlabelled' or not 1 < len(classes) <= 255:
                raise ValueError('Unexpected source class definition')
            return classes, palette
    raise ValueError('Author class METAINFO was not found')


def source_pair(raw, record, class_count):
    image_path = raw / 'source' / record['im_path']
    mask_path = raw / 'source' / record['label_path']
    with Image.open(image_path) as image, Image.open(mask_path) as source_mask:
        image.load(); source_mask.load()
        if image.mode != 'RGB' or image.getexif().get(274, 1) != 1:
            raise ValueError('RGB image has unsupported mode/orientation')
        if source_mask.mode not in ('L', 'P'):
            raise ValueError('Expected an indexed source label, not a color visualization')
        if image.size != source_mask.size or source_mask.getexif().get(274, 1) != 1:
            raise ValueError('Image/mask dimensions or orientation differ')
        # P-mode bytes are indices; converting P -> L would corrupt IDs via palette luminance.
        mask = Image.frombytes('L', source_mask.size, source_mask.tobytes())
        histogram = mask.histogram()
        ids = [i for i, count in enumerate(histogram) if count]
        if any(i >= class_count for i in ids):
            raise ValueError('Mask contains IDs absent from the author class definition')
        pixel_hash = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
        mask_hash = hashlib.sha256(mask.tobytes()).hexdigest()
        return mask, image.size, pixel_hash, mask_hash, histogram


def write_manifest(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ['id', 'sequence', 'split', 'flat_file_name', 'im_path', 'label_path', 'width', 'height',
              'label_ids', 'image_pixel_sha256', 'mask_pixel_sha256', 'source_image_sha256', 'source_mask_sha256']
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def metadata_report(raw, records, classes, palette):
    selected = raw / 'selected_source_inventory.json'
    source = json.loads(selected.read_text()) if selected.is_file() else {}
    return {'dataset': 'WildScenes2d', 'task': 'auxiliary_terrain_semantic_segmentation',
            'source_url': 'https://data.csiro.au/collection/csiro:61541', 'repository': REPOSITORY,
            'source_revision': REVISION, 'split_policy': 'author_opt2d', 'resize': False,
            'class_names': classes, 'palette': palette, 'ignore_index': 0,
            'source_id_mapping': {str(i): name for i, name in enumerate(classes)},
            'source_rgb_images': source.get('source_rgb_images'),
            'selected_pairs': sum(len(rows) for rows in records.values()),
            'author_unassigned_rgb_count': len(source.get('excluded_rgb_paths', [])),
            'author_unassigned_reason': 'Not assigned to the author opt2d train/val/test split; not missing downloads',
            'licence': 'CC BY-NC-SA 4.0',
            'scope_note': 'Terrain/object semantic classes provide auxiliary scene context; they are not hiking passability or trail-damage annotations.'}


def preprocess(raw=RAW, dataset=DATASET, workers=4):
    raw, dataset = Path(raw), Path(dataset)
    records = split_records(raw / 'official_metadata')
    classes, palette = source_classes(raw / 'official_metadata')
    report = metadata_report(raw, records, classes, palette)
    missing = [record[field] for rows in records.values() for record in rows for field in ('im_path', 'label_path')
               if not (raw / 'source' / record[field]).is_file()]
    if missing:
        report.update(preprocessed=False, training_ready=False, missing_files=missing, issues=['Source acquisition is incomplete'])
        write_json(dataset / 'conversion_report.json', report)
        return report
    for split, rows in records.items():
        expected = {record['flat_file_name'] for record in rows}
        for kind in ('images', 'masks'):
            folder = dataset / kind / split
            stale = {p.name for p in folder.glob('*') if p.is_file()} - expected
            if stale:
                raise ValueError('Output contains files outside the author split: ' + str(folder))
            folder.mkdir(parents=True, exist_ok=True)
    issues = []; manifest = {}; counts = {}; histograms = {}
    def convert(record):
        try:
            mask, size, image_hash, mask_hash, histogram = source_pair(raw, record, len(classes))
            image_path = raw / 'source' / record['im_path']; label_path = raw / 'source' / record['label_path']
            destination = dataset / 'images' / record['split'] / record['flat_file_name']
            if destination.exists() and not os.path.samefile(image_path, destination) and file_digest(image_path, 'sha256') != file_digest(destination, 'sha256'):
                raise ValueError('An existing processed image differs from its source')
            if not destination.exists():
                try:
                    os.link(image_path, destination)
                except OSError:
                    shutil.copy2(image_path, destination)
            target = dataset / 'masks' / record['split'] / record['flat_file_name']
            temp = target.with_suffix('.part'); mask.save(temp, format='PNG'); temp.replace(target)
            row = dict(record, width=size[0], height=size[1], label_ids=' '.join(str(i) for i,c in enumerate(histogram) if c),
                       image_pixel_sha256=image_hash, mask_pixel_sha256=mask_hash,
                       source_image_sha256=file_digest(image_path, 'sha256'), source_mask_sha256=file_digest(label_path, 'sha256'))
            return row, histogram, None
        except Exception as exc:
            return None, None, {'id': record['id'], 'split': record['split'], 'error': str(exc)}
    for split, rows in records.items():
        converted = []; totals = [0]*256
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(workers,6))) as pool:
            for index, (row, histogram, error) in enumerate(pool.map(convert, rows), 1):
                if error:
                    issues.append(error)
                else:
                    converted.append(row)
                    for i,c in enumerate(histogram):totals[i] += c
                if index % 250 == 0:
                    print(f'WildScenes {split}: {index}/{len(rows)} pairs prepared', flush=True)
        write_manifest(dataset / 'manifests' / (split + '.csv'), converted)
        manifest[split] = converted; counts[split] = len(converted)
        histograms[split] = {str(i):c for i,c in enumerate(totals) if c}
    source_hashes = {str(path.relative_to(raw / 'official_metadata')):file_digest(path, 'sha256')
                     for path in (raw / 'official_metadata').rglob('*') if path.is_file()}
    report.update(preprocessed=not issues, training_ready=False, split_counts=counts,
                  class_pixel_counts=histograms, issues=issues, source_metadata_sha256=source_hashes)
    write_json(dataset / 'conversion_report.json', report)
    write_json(dataset / 'class_mapping.json', {k: report[k] for k in ('source_id_mapping','palette','ignore_index','scope_note')})
    yaml = ['# Native semantic IDs are preserved; class 0 is unlabelled and ignored.',
            'path: ' + str(dataset.resolve()), 'task: semantic_segmentation', 'mask_format: class_id_png', 'ignore_index: 0',
            'train_images: images/train', 'train_masks: masks/train', 'val_images: images/val', 'val_masks: masks/val',
            'test_images: images/test', 'test_masks: masks/test', 'names:']
    yaml.extend('  ' + str(i) + ': ' + json.dumps(name) for i,name in enumerate(classes))
    if not issues:
        (dataset / 'data.yaml').write_text('\n'.join(yaml)+'\n')
    elif (dataset/'data.yaml').exists():
        (dataset/'data.yaml').replace(dataset/'data.yaml.invalid')
    return report


def verify(raw=RAW, dataset=DATASET, workers=4):
    raw, dataset = Path(raw), Path(dataset)
    records = split_records(raw / 'official_metadata'); classes, palette = source_classes(raw / 'official_metadata')
    report = metadata_report(raw, records, classes, palette)
    issues=[]; split_reports={}; seen_hashes={}; duplicates=[]
    for split, source_rows in records.items():
        manifest_path = dataset / 'manifests' / (split + '.csv')
        if not manifest_path.is_file():
            issues.append({'split':split,'error':'Manifest is missing'}); split_reports[split]={'expected_pairs':len(source_rows),'verified_pairs':0}; continue
        with manifest_path.open(newline='') as stream:rows=list(csv.DictReader(stream))
        by_id = {r['id']:r for r in rows}
        if len(by_id)!=len(rows) or set(by_id)!={r['id'] for r in source_rows}:
            issues.append({'split':split,'error':'Manifest does not cover the exact author split'})
        expected_files={r['flat_file_name'] for r in source_rows}
        for kind in ('images','masks'):
            actual={p.name for p in (dataset/kind/split).glob('*') if p.is_file()}
            if actual != expected_files:issues.append({'split':split,'error':kind+' file coverage differs from the author split'})
        def check(source_row):
            try:
                row=by_id[source_row['id']]
                for key in ('sequence','split','flat_file_name','im_path','label_path'):
                    if row.get(key)!=source_row[key]:raise ValueError('Manifest source identity changed: '+key)
                mask,size,image_hash,mask_hash,histogram=source_pair(raw,source_row,len(classes))
                image_path=dataset/'images'/split/source_row['flat_file_name'];mask_path=dataset/'masks'/split/source_row['flat_file_name']
                with Image.open(image_path) as image, Image.open(mask_path) as prepared:
                    image.load();prepared.load()
                    if image.mode!='RGB' or image.size!=size or image.getexif().get(274,1)!=1:
                        raise ValueError('Processed RGB geometry/mode changed')
                    if hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()!=image_hash:
                        raise ValueError('Processed image differs from source pixels')
                    if prepared.mode!='L' or prepared.size!=size or prepared.tobytes()!=mask.tobytes():
                        raise ValueError('Prepared mask differs from source class IDs')
                if (row['image_pixel_sha256']!=image_hash or row['mask_pixel_sha256']!=mask_hash or
                    row['width']!=str(size[0]) or row['height']!=str(size[1])):
                    raise ValueError('Manifest geometry/pixel evidence changed')
                if (row['source_image_sha256']!=file_digest(raw/'source'/source_row['im_path'],'sha256') or
                    row['source_mask_sha256']!=file_digest(raw/'source'/source_row['label_path'],'sha256')):
                    raise ValueError('Raw file checksum changed after preprocessing')
                return source_row['id'],image_hash,None
            except Exception as exc:
                return source_row['id'],None,{'split':split,'id':source_row['id'],'error':str(exc)}
        count=0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(workers,6))) as pool:
            for index,(sample_id,pixel_hash,error) in enumerate(pool.map(check,source_rows),1):
                if error:issues.append(error)
                else:
                    count+=1
                    if pixel_hash in seen_hashes and seen_hashes[pixel_hash]['split']!=split:
                        duplicates.append({'first':seen_hashes[pixel_hash],'second':{'split':split,'id':sample_id}})
                    else:seen_hashes[pixel_hash]={'split':split,'id':sample_id}
                if index%250==0:print(f'WildScenes {split}: {index}/{len(source_rows)} pairs verified',flush=True)
        split_reports[split]={'expected_pairs':len(source_rows),'verified_pairs':count}
    if duplicates:issues.append({'error':'Exact RGB duplicates cross author splits','pairs':duplicates})
    report.update(passed=not issues,training_ready=not issues,splits=split_reports,issues=issues,
                  exact_duplicate_check='decoded RGB SHA256 across author splits',complete_author_split_coverage=not issues,
                  model_trained=False)
    return report


def preview(dataset=DATASET, output=RESULTS/'overlays.jpg'):
    dataset,output=Path(dataset),Path(output)
    palette=json.loads((dataset/'class_mapping.json').read_text())['palette']
    padded=sum(palette,[])+[0]*(768-len(palette)*3)
    pairs=[]
    for split in ('train','val','test'):
        with (dataset/'manifests'/(split+'.csv')).open(newline='') as stream:rows=list(csv.DictReader(stream))
        if rows:pairs.append((split,rows[0]))
    sheet=Image.new('RGB',(720,270*len(pairs)),(18,22,25));draw=ImageDraw.Draw(sheet)
    for index,(split,row) in enumerate(pairs):
        with Image.open(dataset/'images'/split/row['flat_file_name']) as image, Image.open(dataset/'masks'/split/row['flat_file_name']) as mask:
            rgb=image.convert('RGB');colored=Image.frombytes('P',mask.size,mask.tobytes());colored.putpalette(padded)
            overlay=Image.blend(rgb,colored.convert('RGB'),0.45)
            sheet.paste(ImageOps.contain(rgb,(355,235)),(0,index*270+25))
            sheet.paste(ImageOps.contain(overlay,(355,235)),(365,index*270+25))
            draw.text((5,index*270+5),split+' '+row['sequence']+' '+row['id'],fill='white')
    output.parent.mkdir(parents=True,exist_ok=True);sheet.save(output)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root',type=Path,default=RAW);parser.add_argument('--dataset',type=Path,default=DATASET)
    parser.add_argument('--workers',type=int,default=4);parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--report',type=Path,default=RESULTS/'local_readiness.json')
    parser.add_argument('--preview',action='store_true');args=parser.parse_args()
    if not args.verify_only:
        prepared=preprocess(args.raw_root,args.dataset,args.workers)
        if not prepared['preprocessed']:
            write_json(args.report,prepared);raise SystemExit('WildScenes acquisition/preprocessing is incomplete')
    report=verify(args.raw_root,args.dataset,args.workers);write_json(args.report,report)
    if args.preview and report['passed']:preview(args.dataset,args.report.parent/'overlays.jpg')
    print(json.dumps({'training_ready':report['training_ready'],'splits':report['splits'],'issues':len(report['issues'])},indent=2))
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
