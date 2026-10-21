"""Source-checked ORFD RGB/binary semantic masks; preserves the downloaded splits."""
from __future__ import annotations
import argparse,csv,hashlib,json,os,shutil
from collections import Counter
from pathlib import Path
from .preprocess_mju_waste import ROOT,write_json,sha256
RAW=ROOT/'data/raw/orfd/ORFD'
OUT=ROOT/'data/processed/orfd_path_seg'
SPLITS={'training':'train','validation':'val','testing':'test'}
FIELDS=['file_name','source_split','sequence','source_image','source_gt','width','height','positive_pixels','image_sha256','gt_sha256','mask_sha256']

def discover(raw):
    """Support both original sequence folders and the author-linked flattened mirror."""
    raw=Path(raw);records=[];issues=[]
    for source_split,split in SPLITS.items():
        photos=sorted((raw/source_split).rglob('image_data/*.png'))
        if not photos:issues.append(f'{source_split}: no RGB photos')
        for photo in photos:
            parent=photo.parent.parent
            gt=parent/'gt_image'/f'{photo.stem}_fillcolor.png'
            sequence='' if parent==raw/source_split else parent.relative_to(raw/source_split).as_posix()
            name=f'{sequence.replace("/","__")}__{photo.name}' if sequence else photo.name
            records.append({'split':split,'file_name':name,'source_split':source_split,'sequence':sequence,'source_image':photo.relative_to(raw).as_posix(),'source_gt':gt.relative_to(raw).as_posix()})
            if not gt.is_file():issues.append(f'{source_split}/{name}: missing ground-truth mask')
    return records,issues

def source_image(path):
    from PIL import Image
    with Image.open(path) as im:im.verify()
    with Image.open(path) as im:
        im.load()
        if im.getexif().get(274,1)!=1:raise ValueError('ambiguous source orientation')
        return im.convert('RGB')

def binary_mask(gt,size):
    rgb=source_image(gt)
    if rgb.size!=size:raise ValueError(f'GT geometry {rgb.size} differs from RGB {size}')
    # Official loader converts BGR to RGB and selects RGB channel 2 > 200.
    return rgb.getchannel('B').point([int(v>200) for v in range(256)],mode='L'),Counter(dict((color,count) for count,color in rgb.getcolors(rgb.width*rgb.height)))

def inventory_check(raw):
    path=raw.parent/'selected_source_inventory.json'
    issues=[]
    if path.is_file():
        for row in json.loads(path.read_text())['files']:
            if '/image_data/' not in row['path'] and '/gt_image/' not in row['path']:continue
            p=raw.parent/row['path']
            if not p.is_file() or p.stat().st_size!=row['bytes']:issues.append(f'{row["path"]}: missing or incomplete download')
    return issues

def preprocess(raw=RAW,out=OUT,train_only=False,allow_incomplete=False):
    raw,out=Path(raw).resolve(),Path(out).resolve();records,issues=discover(raw)
    if train_only:
        records=[r for r in records if r['split']=='train']
        issues=[issue for issue in issues if not issue.startswith(('validation:', 'testing:'))]
    if allow_incomplete:
        issues=[issue for issue in issues if issue not in ('validation: no RGB photos','testing: no RGB photos')]
    issues+=inventory_check(raw)
    if issues:
        report={'preprocessed':False,'training_ready':False,'issues':issues,'expected_pairs':len(records)}
        write_json(out/'conversion_report.json',report)
        raise ValueError(f'{len(issues)} missing/incomplete source files; finish download first')
    names=set();colors=Counter();rows={s:[] for s in SPLITS.values()}
    for r in records:
        key=(r['split'],r['file_name'])
        if key in names:raise ValueError(f'Duplicate output filename: {key}')
        names.add(key)
    for split in rows:
        expected={r['file_name'] for r in records if r['split']==split}
        for kind in ('images','masks'):
            extra={p.name for p in (out/kind/split).glob('*') if p.is_file()}-expected
            if extra:raise ValueError(f'Stale {kind}/{split} files; use fresh output')
            (out/kind/split).mkdir(parents=True,exist_ok=True)
    for index,r in enumerate(records):
        photo,gt=raw/r['source_image'],raw/r['source_gt']
        try:
            rgb=source_image(photo);mask,palette=binary_mask(gt,rgb.size);colors.update(palette)
            target=out/'images'/r['split']/r['file_name'];mp=out/'masks'/r['split']/r['file_name']
            image_hash=sha256(photo)
            if target.exists():
                if sha256(target)!=image_hash:raise ValueError('existing image differs from source')
            else:
                try:os.link(photo,target)
                except OSError:shutil.copy2(photo,target)
            temp=mp.with_suffix('.part');mask.save(temp,format='PNG');temp.replace(mp)
            row={k:v for k,v in r.items() if k!='split'}
            row.update(width=rgb.width,height=rgb.height,positive_pixels=mask.histogram()[1],image_sha256=image_hash,gt_sha256=sha256(gt),mask_sha256=sha256(mp))
            rows[r['split']].append(row)
        except (OSError,ValueError,SyntaxError) as exc:issues.append(f'{r["source_image"]}: {exc}')
        if (index+1)%250==0:print(f'ORFD: converted {index+1}/{len(records)} pairs',flush=True)
    (out/'manifests').mkdir(parents=True,exist_ok=True)
    for split,data in rows.items():
        with (out/'manifests'/f'{split}.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(data)
    report={'preprocessed':not issues,'training_ready':False,'source':str(raw),'dataset':str(out),'splits':{s:len(v) for s,v in rows.items()},'mask_values':{'0':'non_freespace','1':'freespace_traversable_proxy'},'mask_rule':'source RGB blue channel > 200; matches official loader','source_colors':{','.join(map(str,c)):n for c,n in colors.items()},'published_image_count':12198,'downloaded_source_pairs':len(records),'source_sequence_metadata_available':all(r['sequence'] for r in records),'issues':issues}
    write_json(out/'conversion_report.json',report)
    return report

def verify(raw=RAW,out=OUT,train_only=False,allow_incomplete=False):
    from PIL import Image
    raw,out=Path(raw).resolve(),Path(out).resolve();records,issues=discover(raw)
    if train_only:
        records=[r for r in records if r['split']=='train']
        issues=[issue for issue in issues if not issue.startswith(('validation:', 'testing:'))]
    if allow_incomplete:
        issues=[issue for issue in issues if issue not in ('validation: no RGB photos','testing: no RGB photos')]
    issues+=inventory_check(raw)
    expected={(r['split'],r['file_name']):r for r in records};counts={};pixels={};sequences={s:set() for s in SPLITS.values()}
    for split in SPLITS.values():
        valid=0
        try:
            with (out/'manifests'/f'{split}.csv').open(newline='') as f:rows=list(csv.DictReader(f))
            keys=[(split,r['file_name']) for r in rows]
            if len(set(keys))!=len(keys) or set(keys)!={k for k in expected if k[0]==split}:issues.append(f'{split}: manifest coverage differs from source')
            for row in rows:
                try:
                    r=expected[(split,row['file_name'])]
                    if any(row[k]!=r[k] for k in ('source_split','sequence','source_image','source_gt')):raise ValueError('manifest source mapping changed')
                    photo,gt=raw/r['source_image'],raw/r['source_gt'];image=source_image(out/'images'/split/r['file_name']);source=source_image(photo)
                    mask,palette=binary_mask(gt,source.size)
                    with Image.open(out/'masks'/split/r['file_name']) as stored:
                        stored.load()
                        if stored.mode!='L' or stored.size!=source.size or stored.tobytes()!=mask.tobytes():raise ValueError('prepared mask differs from source conversion')
                    if image.size!=source.size or image.tobytes()!=source.tobytes():raise ValueError('prepared RGB differs from source')
                    if (int(row['width']),int(row['height']))!=image.size or int(row['positive_pixels'])!=mask.histogram()[1]:raise ValueError('manifest geometry/count differs from source')
                    for key,p in [('image_sha256',photo),('gt_sha256',gt),('mask_sha256',out/'masks'/split/r['file_name'])]:
                        if row[key]!=sha256(p):raise ValueError(f'{key} mismatch')
                    digest=hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()
                    if digest in pixels and pixels[digest]!=split:raise ValueError('exact RGB pixels cross dataset splits')
                    pixels[digest]=split
                    if r['sequence']:sequences[split].add(r['sequence'])
                    valid+=1
                except (OSError,KeyError,ValueError,SyntaxError) as exc:issues.append(f'{split}/{row.get("file_name")}: {exc}')
            for kind in ('images','masks'):
                actual={p.name for p in (out/kind/split).glob('*') if p.is_file()}
                if actual!={r['file_name'] for r in records if r['split']==split}:issues.append(f'{split}: {kind} coverage differs from source')
        except (OSError,KeyError,ValueError,csv.Error) as exc:issues.append(f'{split}: manifest unavailable/invalid: {exc}')
        counts[split]={'images':sum(r['split']==split for r in records),'verified_pairs':valid}
        print(f'ORFD {split}: {valid} pairs verified',flush=True)
    for a,b in [('train','val'),('train','test'),('val','test')]:
        if sequences[a]&sequences[b]:issues.append(f'{a}/{b}: source sequence overlap')
    report={'passed':not issues,'training_ready':not issues and bool(records) and not train_only and not allow_incomplete,'training_pool_ready':not issues and any(r['split']=='train' for r in records) and (train_only or allow_incomplete),'train_only':train_only,'partial_available_source':allow_incomplete,'dataset':str(out),'source':str(raw),'splits':counts,'issue_count':len(issues),'issues':issues,'published_image_count':12198,'available_image_count':len(records),'published_split_counts':{'train':8398,'val':1245,'test':2555},'published_count_complete':len(records)==12198,'independent_hiking_evaluation_supported':False,'source_sequence_metadata_available':bool(records) and all(r['sequence'] for r in records),'warnings':['Author-linked mirror may omit source frames; available counts are not the full published dataset.','Freespace is an auxiliary vehicle traversability proxy, not hiking safety or damage ground truth.','Flattened mirror lacks original sequence names; do not claim verified sequence independence.']}
    write_json(out/'readiness.json',report)
    if out==OUT.resolve():write_json(ROOT/'results/orfd_preprocessing/local_readiness.json',report)
    if out==OUT.resolve():refresh_component_status(report)
    elif out==(ROOT/'data/processed/orfd_path_seg_partial').resolve():
        summary=dict(report,phase='partial_preprocessed',download_complete=False,full_mirror_ready=False,expected_mirror_pairs=11830)
        download=ROOT/'data/raw/orfd/download_status.json'
        if download.is_file():
            summary['download']=json.loads(download.read_text())
            if 'Quota exceeded' in summary['download'].get('error',''):
                summary['phase']='partial_preprocessed_download_quota_exceeded'
        write_json(ROOT/'results/orfd_preprocessing/local_readiness.json',summary)
        write_json(ROOT/'results/orfd_preprocessing/partial/local_readiness.json',summary)
        refresh_component_status(summary)
    return report

def refresh_component_status(report,root=ROOT):
    root=Path(root);status_path=root/'results/taco_preprocessing/supplied_preprocessing_status.json'
    if status_path.is_file():
        status=json.loads(status_path.read_text());status['orfd']=report;write_json(status_path,status)
    register=status_path.with_name('supplied_dataset_register.csv')
    if register.is_file():
        with register.open(newline='') as f:
            reader=csv.DictReader(f);fields=reader.fieldnames;rows=[r for r in reader if r['dataset']!='orfd']
        splits=list(report.get('splits',{}).values());images=sum(r['images'] for r in splits);verified=sum(r['verified_pairs'] for r in splits)
        values={'dataset':'orfd','role':'auxiliary RGB binary semantic freespace; incomplete published coverage',
                'raw_source':report.get('source',''),'split_policy':'mirror official split membership; source sequences unavailable',
                'class_mapping':'0 non_freespace; 1 freespace_traversable_proxy; PNG semantic masks',
                'images':images,'annotations':images,'label_files':verified,'present_images':verified,
                'missing_images':images-verified,'training_ready':report.get('training_ready',False),
                'training_pool_ready':report.get('training_pool_ready',report.get('training_ready',False)),'path':report.get('dataset','')}
        inventory=Path(report.get('source',str(root/'data/raw/orfd/ORFD'))).parent/'selected_source_inventory.json'
        if inventory.is_file():values['raw_source_sha256']=sha256(inventory)
        rows.append({field:values.get(field,'') for field in fields})
        with register.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def previews(out=OUT,destination=None):
    from PIL import Image,ImageOps,ImageDraw
    out=Path(out);destination=Path(destination or ROOT/'results/orfd_preprocessing');destination.mkdir(parents=True,exist_ok=True)
    for split in SPLITS.values():
        with (out/'manifests'/f'{split}.csv').open(newline='') as f:rows=list(csv.DictReader(f))
        if not rows:continue
        chosen=[rows[round(i*(len(rows)-1)/min(5,len(rows)-1))] for i in range(min(6,len(rows)))] if len(rows)>1 else rows
        sheet=Image.new('RGB',(800,len(chosen)*250),'#202629');draw=ImageDraw.Draw(sheet)
        for i,row in enumerate(chosen):
            rgb=source_image(out/'images'/split/row['file_name'])
            with Image.open(out/'masks'/split/row['file_name']) as mask:
                tint=Image.new('RGB',rgb.size,(30,230,90));overlay=Image.composite(Image.blend(rgb,tint,.45),rgb,mask.point([0,255]+[0]*254))
            for x,picture in [(0,rgb),(400,overlay)]:sheet.paste(ImageOps.contain(picture,(400,225)),(x,i*250))
            draw.text((5,i*250+228),f'{split}/{row["file_name"]}',fill='white')
        sheet.save(destination/f'{split}_overlays.jpg',quality=90)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--raw-root',type=Path,default=RAW);ap.add_argument('--out',type=Path,default=OUT);ap.add_argument('--verify-only',action='store_true');ap.add_argument('--train-only',action='store_true',help='Prepare an auxiliary train pool; never certifies benchmark readiness');ap.add_argument('--allow-incomplete',action='store_true',help='Preserve available source splits; never certifies benchmark readiness');args=ap.parse_args()
    if not args.verify_only:preprocess(args.raw_root,args.out,args.train_only,args.allow_incomplete)
    report=verify(args.raw_root,args.out,args.train_only,args.allow_incomplete)
    if report['passed']:
        destination=None if args.out.resolve()==OUT.resolve() else ROOT/'results/orfd_preprocessing/partial'
        previews(args.out,destination)
    print(json.dumps({k:v for k,v in report.items() if k!='issues'},indent=2))
    if not (report['training_ready'] or report['training_pool_ready']):ap.exit(1,'ORFD has readiness issues; inspect readiness.json\n')

if __name__=='__main__':main()
