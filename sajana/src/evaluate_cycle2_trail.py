"""Evaluate the already selected cycle-two checkpoint once on its held-out set."""
from __future__ import annotations

import collections
import csv
import json
from pathlib import Path

from .train_yolov8 import ROOT, now, sha256, write_json

DATA = ROOT / 'data/processed/component2_cycle2_trail_v4'
RUN = ROOT / 'runs/component2_cycle2/trail_yolov8n'
CHECKPOINT = RUN / 'fit/weights/best.pt'
OUT = ROOT / 'results/component2_cycle2/trail_training.json'
NAMES = ['tree', 'stump', 'stem', 'obstacle_region', 'non_passable_obstacle', 'debris', 'rock']


def main():
    status = json.loads((RUN/'status.json').read_text())
    if status.get('state') not in ('training_complete', 'complete') or not CHECKPOINT.is_file():
        raise ValueError('Training is not complete or the selected checkpoint is absent')
    test_yaml = RUN/'test.yaml'
    test_yaml.write_text('path: '+json.dumps(str(DATA.resolve()))+
        '\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n'+
        ''.join(f'  {i}: {name}\n' for i,name in enumerate(NAMES)))
    from ultralytics import YOLO
    model = YOLO(str(CHECKPOINT))
    val = model.val(data=str(DATA/'data.yaml'), split='val', imgsz=416,
                    batch=2, device='cpu', workers=0, plots=False, verbose=False)
    test = model.val(data=str(test_yaml), split='test', imgsz=416,
                     batch=2, device='cpu', workers=0, plots=False, verbose=False)

    def metrics_record(metrics):
        box=metrics.box
        class_rows=[]
        for cid,name in enumerate(NAMES):
            if cid in list(map(int,box.ap_class_index)):
                position=list(map(int,box.ap_class_index)).index(cid)
                p,r,ap50,ap=box.class_result(position)
            else:
                p=r=ap50=ap=0.0
            class_rows.append({'class_id':cid,'class_name':name,'precision':float(p),
                'recall':float(r),'AP50':float(ap50),'AP50_95':float(ap)})
        return {'precision':float(box.mp),'recall':float(box.mr),'mAP50':float(box.map50),
                'mAP50_95':float(box.map),'per_class':class_rows}

    # A single, fixed 0.25 inference threshold provides an interpretable
    # photo-presence check. It is not adjusted using test outcomes.
    rows=list(csv.DictReader((DATA/'manifest.csv').open(newline='')))
    test_rows=[r for r in rows if r['split']=='test']
    preds=model.predict(source=[str(DATA/r['image']) for r in test_rows],imgsz=416,
                        conf=0.25,device='cpu',workers=0,verbose=False,stream=False)
    presence={}
    for cid,name in enumerate(NAMES):
        tp=fp=fn=tn=0
        for row,result in zip(test_rows,preds):
            truth={int(x.split()[0]) for x in (DATA/row['label']).read_text().splitlines()}
            found=set(map(int,result.boxes.cls.tolist())) if result.boxes is not None else set()
            actual=cid in truth; detected=cid in found
            if actual and detected: tp+=1
            elif actual: fn+=1
            elif detected: fp+=1
            else: tn+=1
        presence[name]={'tp':tp,'fn':fn,'fp':fp,'tn':tn,
            'positive_photos':tp+fn,'negative_photos':fp+tn,'threshold':0.25,
            'recall':tp/(tp+fn) if tp+fn else None,
            'precision':tp/(tp+fp) if tp+fp else None,
            'false_positive_rate':fp/(fp+tn) if fp+tn else None}
    result={'completed_at':now(),'model':'YOLOv8n','task':'trail-object-detection',
        'training_epochs_completed':16,'early_stopped':True,'imgsz':416,'batch':2,
        'device':'CPU','checkpoint':str(CHECKPOINT),'checkpoint_sha256':sha256(CHECKPOINT),
        'checkpoint_bytes':CHECKPOINT.stat().st_size,
        'data_manifest_sha256':status['data_manifest_sha256'],
        'photos_by_split':status['photos_by_split'],
        'goose_sequences_by_split':status['goose_sequences_by_split'],
        'validation':metrics_record(val),'test':metrics_record(test),
        'photo_presence_test':presence,'test_used_for_tuning':False,
        'full_component_ready':False,
        'limitations':['No garbage classes are in this detector; retain the existing litter model separately.',
          'GOOSE obstacle_region is a semantic object class, not route-passability ground truth.',
          'non_passable_obstacle has 32 training boxes and one validation box; no independent test examples.',
          'Exposed roots have only eight source-positive frames and are excluded; erosion is not annotated.',
          'The held-out test uses the GOOSE extension domain; local trail and Android evaluation are absent.']}
    write_json(OUT,result)
    status.update(state='complete',completed_at=now(),results=str(OUT),test_split_used_for_training=False,
                  full_component_ready=False,completed_epochs=16)
    write_json(ROOT/'results/component2_cycle2/trail_training_status.json',status)
    write_json(RUN/'status.json',status)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
