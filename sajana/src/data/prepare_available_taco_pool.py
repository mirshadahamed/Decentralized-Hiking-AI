"""Derive a verified available unofficial TACO pool without inventing missing photos.

Whole missing/invalid examples, exact duplicates and benchmark-pixel matches
are excluded with source IDs and reasons. The complete expected source remains
unchanged, and this output remains an optional unreviewed auxiliary train pool.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,shutil
from collections import Counter,defaultdict
from pathlib import Path
from PIL import Image
from .preprocess_taco import preprocess
from .verify_taco_ready import verify,_same_geometry
from .preprocess_mju_waste import ROOT,sha256,write_json
SOURCE=ROOT/'data/interim/taco/annotations_unofficial_validated.json'
DATASET=ROOT/'data/processed/taco_unofficial_litter_seg'
OUT=ROOT/'data/processed/taco_unofficial_litter_seg_available'
DERIVED=ROOT/'data/interim/taco/annotations_unofficial_available.json'

def fingerprint(path,width=None,height=None):
    with Image.open(path) as im:im.verify()
    with Image.open(path) as im:
        im.load()
        if im.getexif().get(274,1)!=1:raise ValueError('unreviewed EXIF orientation')
        if width and not _same_geometry(*im.size,width,height):raise ValueError('image geometry differs from annotation')
        rgb=im.convert('RGB')
        return hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest()

def prepare(source=SOURCE,dataset=DATASET,out=OUT,derived_path=DERIVED,benchmark=None):
    source,dataset,out,derived_path=map(Path,(source,dataset,out,derived_path))
    audit=verify(dataset,labels_only=True,annotations=source,split_policy='train_only')
    if not audit['passed']:raise ValueError('Expected source labels failed audit; do not derive an available pool')
    raw=json.loads(source.read_text());source_hash=sha256(source)
    benchmark=Path(benchmark) if benchmark else ROOT/'data/processed/taco_litter_seg_clean'
    holdouts={}
    for split in ('val','test'):
        for path in sorted((benchmark/'images'/split).glob('*')):
            if path.is_file():holdouts[fingerprint(path)]=f'{split}/{path.name}'
    errors={}
    history=dataset/'download_failures.csv'
    if history.is_file():
        with history.open(newline='') as f:errors={r['source_file_name']:r.get('error','') for r in csv.DictReader(f)}
    grouped=defaultdict(list);excluded=[];counts=Counter(a['image_id'] for a in raw['annotations'])
    paths={}
    for index,image in enumerate(raw['images']):
        flat=image['file_name'].replace('/','__');path=dataset/'images/train'/flat
        try:
            if not path.is_file():raise FileNotFoundError('photo unavailable')
            digest=fingerprint(path,image['width'],image['height'])
            if digest in holdouts:
                excluded.append({'image_id':image['id'],'file_name':image['file_name'],'reason':'exact_pixels_in_official_holdout','reference':holdouts[digest]});continue
            grouped[digest].append(image);paths[image['id']]=path
        except (OSError,ValueError,SyntaxError) as exc:
            excluded.append({'image_id':image['id'],'file_name':image['file_name'],'reason':'missing_or_invalid_photo','detail':str(exc),'acquisition_error':errors.get(image['file_name'],'')})
        if (index+1)%250==0:print(f'Available unofficial pool: checked {index+1}/{len(raw["images"])}',flush=True)
    kept=[]
    for digest,images in grouped.items():
        images.sort(key=lambda im:(-counts[im['id']],im['id']));winner=images[0];kept.append(winner)
        for duplicate in images[1:]:excluded.append({'image_id':duplicate['id'],'file_name':duplicate['file_name'],'reason':'exact_duplicate_in_auxiliary_pool','kept_image_id':winner['id'],'pixel_sha256':digest})
    if not kept:raise ValueError('No usable photographed examples available')
    kept.sort(key=lambda x:x['id']);ids={im['id'] for im in kept};derived=dict(raw)
    derived['images']=kept;derived['annotations']=[a for a in raw['annotations'] if a['image_id'] in ids]
    if 'scene_annotations' in raw:derived['scene_annotations']=[a for a in raw['scene_annotations'] if a['image_id'] in ids]
    derived['available_subset_provenance']={'source_sha256':source_hash,'source_expected_images':len(raw['images']),'retained_images':len(kept),'policy':'existing valid photos only; exact-pixel official holdout matches and within-pool duplicates excluded; no fabricated images or labels'}
    write_json(derived_path,derived);preprocess(derived_path,out,split_policy='train_only')
    for image in kept:
        original=paths[image['id']];target=out/'images/train'/original.name
        if target.exists():
            if sha256(target)!=sha256(original):raise ValueError('Existing subset photo differs from expected source')
        else:
            try:os.link(original,target)
            except OSError:shutil.copy2(original,target)
    ready=verify(out,annotations=derived_path,split_policy='train_only')
    ready.update(expected_source_images=len(raw['images']),available_subset=True,canonical_source_complete=not any(x['reason']=='missing_or_invalid_photo' for x in excluded),source_sha256=source_hash,excluded_images=len(excluded),exclusion_reason_counts=dict(Counter(x['reason'] for x in excluded)),originals_preserved=True,annotation_review_status='unofficial source annotations remain unreviewed; optional auxiliary training only')
    write_json(out/'readiness.json',ready)
    write_json(out/'available_subset_exclusions.json',{'source':str(source.resolve()),'source_sha256':source_hash,'retained_images':len(kept),'retained_annotations':len(derived['annotations']),'excluded':excluded})
    if out.resolve()==OUT.resolve():write_json(ROOT/'results/taco_preprocessing/unofficial_available_readiness.json',ready)
    if sha256(source)!=source_hash:raise ValueError('Expected source changed during preparation')
    return ready

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=SOURCE);p.add_argument('--dataset',type=Path,default=DATASET);p.add_argument('--out',type=Path,default=OUT);p.add_argument('--derived-source',type=Path,default=DERIVED);p.add_argument('--benchmark',type=Path);a=p.parse_args()
    report=prepare(a.source,a.dataset,a.out,a.derived_source,a.benchmark)
    print(json.dumps({k:report.get(k) for k in ('passed','training_pool_ready','expected_source_images','excluded_images','exclusion_reason_counts','splits')},indent=2))
    if not report.get('training_pool_ready'):p.exit(1,'Available unofficial pool failed verification\n')
if __name__=='__main__':main()
