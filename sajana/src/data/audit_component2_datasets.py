"""Ordered, source-specific Component 2 readiness catalog (never combines unknown labels).

Consumes source verification certificates and checks prepared file-pair coverage.
Use each source's verifier to refresh its full pixel/annotation audit first.
"""
from __future__ import annotations
import argparse,csv,hashlib,json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from .preprocess_mju_waste import ROOT,write_json

SOURCES=[
 ('taco','litter instance segmentation','required','data/processed/taco_litter_seg_clean',['results/taco_preprocessing/official_clean_readiness.json'],'labels'),
 ('mju','auxiliary litter instance segmentation','selected_auxiliary','data/processed/mju_waste_litter_seg',['results/mju_preprocessing/local_readiness.json'],'labels'),
 ('taco_mju','combined binary litter baseline','derived','data/processed/litter_taco_mju_aux',['data/processed/litter_taco_mju_aux/readiness.json'],'labels'),
 ('unofficial_taco','unreviewed litter auxiliary pool','optional','data/processed/taco_unofficial_litter_seg_available',['results/taco_preprocessing/unofficial_available_readiness.json'],'labels'),
 ('plitter','litter and trash-bin object detection','required','data/processed/plitter_street_det',['results/plitter_preprocessing/local_readiness.json'],'labels'),
 ('orfd','auxiliary vehicle freespace segmentation','selected_auxiliary','data/processed/orfd_path_seg',['results/orfd_preprocessing/full_readiness.json','data/processed/orfd_path_seg/readiness.json','results/orfd_preprocessing/local_readiness.json'],'masks'),
 ('rugd','natural terrain semantic segmentation','required','data/processed/rugd_semantic',['results/rugd_preprocessing/local_readiness.json'],'masks'),
 ('wildscenes','forest terrain semantic segmentation','required','data/processed/wildscenes_terrain_semantic',['results/wildscenes_preprocessing/local_readiness.json'],'masks'),
]

def read_json(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return None

def coverage(dataset,kind):
    images={};labels={}
    for split in ('train','val','test'):
        image_root=dataset/'images'/split;label_root=dataset/kind/split
        photos={p.relative_to(image_root).with_suffix('').as_posix() for p in image_root.rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg','.jpeg','.png')}
        targets={p.relative_to(label_root).with_suffix('').as_posix() for p in label_root.rglob('*') if p.is_file() and p.suffix.lower()==('.txt' if kind=='labels' else '.png')}
        images[split]={'images':len(photos),'labels':len(targets),'paired':len(photos&targets),'unpaired_images':len(photos-targets),'orphan_labels':len(targets-photos)}
    return images

def catalog(root=ROOT):
    root=Path(root);entries=[]
    for key,task,role,folder,reports,kind in SOURCES:
        selected=next(((root/name,read_json(root/name)) for name in reports if read_json(root/name) is not None),None)
        report=selected[1] if selected else {};dataset=root/folder
        if report.get('dataset'):
            stated=Path(report['dataset'])
            if stated.is_absolute() and stated.is_dir():dataset=stated
        actual=coverage(dataset,kind);expected={split:int(row.get('images',row.get('expected_pairs',0))) for split,row in report.get('splits',{}).items()}
        labels_only=bool(report.get('labels_only')) or report.get('mode')=='labels_only'
        certified=bool(report.get('training_ready') or report.get('training_pool_ready') or report.get('auxiliary_train_ready') or report.get('source_context_training_ready')) and not labels_only
        pair_coverage=bool(expected) and all(actual[s]['paired']==expected.get(s,0) and actual[s]['images']==actual[s]['labels']==actual[s]['paired'] for s in actual)
        ready=certified and pair_coverage and report.get('passed',report.get('built',False))
        source_complete=report.get('available_source_complete',report.get('source_complete',report.get('canonical_source_complete',not report.get('partial_available_source',False))))
        if not selected:state='not_prepared'
        elif ready:state='verified_auxiliary_pool' if report.get('partial_available_source') or key=='unofficial_taco' else 'verified_prepared'
        elif labels_only:state='labels_prepared_images_pending'
        else:state='not_ready'
        certificate_hash=hashlib.sha256(selected[0].read_bytes()).hexdigest() if selected else None
        acquisition={}
        if key in ('orfd','rugd','wildscenes','plitter'):
            progress=root/('data/raw/'+key)/('plitter_download_progress.json' if key=='plitter' else 'download_status.json')
            current=read_json(progress) or {}
            acquisition={name:current[name] for name in ('complete','phase','status','verified_files','remaining_files','verified_bytes','downloaded_bytes','expected_bytes','total_bytes','available_image_pairs','selected_files','selected_bytes') if name in current}
            if not selected and current:state='source_acquired_preprocessing_pending' if current.get('complete') else 'acquisition_incomplete'
        entries.append({'key':key,'task':task,'role':role,'state':state,'dataset':str(dataset.relative_to(root)) if dataset.is_relative_to(root) else str(dataset),'verification_report':str(selected[0].relative_to(root)) if selected else None,'verification_report_sha256':certificate_hash,'available_data_ready':bool(ready),'source_release_complete':bool(source_complete and ready),'published_count_complete':report.get('published_count_complete'),'labels_only':labels_only,'expected_splits':expected,'current_pairs':actual,'acquisition_snapshot':acquisition,'issues':report.get('issues',[])[:8],'warnings':report.get('warnings',[])})
    selected=[e for e in entries if e['role'] in ('required','selected_auxiliary')]
    public_complete=all(e['source_release_complete'] for e in selected)
    geo=read_json(root/'results/plitter_preprocessing/mawanella_audit.json') or {}
    local=root/'data/local_trails';local_photos=sum(1 for p in (local/'images').rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg','.jpeg','.png'))
    local_rows=[]
    try:
        with (local/'image_manifest.csv').open(newline='') as f:local_rows=list(csv.DictReader(f))
    except OSError:pass
    # Data presence does not establish reviewed ground truth or independent local holdouts.
    local_ready=False
    return {'schema_version':1,'checked_at':datetime.now(ZoneInfo('Asia/Colombo')).isoformat(),'verification_scope':'Per-source saved full verification certificates plus current prepared file-pair coverage; no replacement for source verifiers.','preparation_order':['source inventory and taxonomy','retain immutable source and verify acquisition checksums','source-specific label conversion and source-aware splits','full pair/geometry/label/duplicate verification','review overlays and freeze source data cards','collect and review joint local trail annotations before full component training'],'datasets':entries,'geospatial_observations':{'ready':geo.get('passed',False),'rows':geo.get('valid_rows',0),'image_training_labels':False},'local_trails':{'photos':local_photos,'manifest_rows':len(local_rows),'joint_ground_truth_ready':local_ready,'reason':'User confirmed no annotated local trail dataset; reviewed erosion, roots, obstruction, route-corridor and passability labels are still required.'},'all_selected_public_sources_preprocessed':public_complete,'all_component_datasets_preprocessed':public_complete and local_ready,'litter_baseline_data_ready':next(e['available_data_ready'] for e in entries if e['key']=='taco_mju'),'full_concurrent_model_data_ready':False,'model_training_started':False,'label_policy':'Keep source tasks/classes separate; unannotated target classes are unknown, never negative. No fabricated imagery, masks or severity labels.'}

def save(root=ROOT):
    root=Path(root);report=catalog(root);destination=root/'results/component2_preprocessing/status.json';write_json(destination,report)
    lines=['# Component 2 dataset preparation status','',f'Checked: {report["checked_at"]}','','| Source | Prepared pairs | State | Source release complete |','| --- | ---: | --- | --- |']
    for e in report['datasets']:
        lines.append(f'| {e["key"]} | {sum(s["paired"] for s in e["current_pairs"].values()):,} | {e["state"]} | {e["source_release_complete"]} |')
    lines+=['','Local jointly annotated trail dataset: **missing**. The annotation workspace and instructions are prepared in `sajana/data/local_trails/`.','','The full concurrent component cannot be certified until real local damage/path/passability annotations and independent local holdouts exist.','',f'Binary litter baseline data ready: **{report["litter_baseline_data_ready"]}**. No model training was started.','']
    (destination.parent/'STATUS.md').write_text('\n'.join(lines))
    shared=root/'results/taco_preprocessing/supplied_preprocessing_status.json'
    if shared.exists():
        status=read_json(shared) or {};status['component2_dataset_preparation']={'report':'sajana/results/component2_preprocessing/status.json','all_selected_public_sources_preprocessed':report['all_selected_public_sources_preprocessed'],'all_component_datasets_preprocessed':report['all_component_datasets_preprocessed'],'litter_baseline_data_ready':report['litter_baseline_data_ready'],'full_concurrent_model_data_ready':False,'local_ground_truth_missing':True};write_json(shared,status)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--component-root',type=Path,default=ROOT);a=p.parse_args();r=save(a.component_root)
    print(json.dumps({'all_selected_public_sources_preprocessed':r['all_selected_public_sources_preprocessed'],'full_concurrent_model_data_ready':False,'sources':{e['key']:e['state'] for e in r['datasets']}},indent=2))
if __name__=='__main__':main()
