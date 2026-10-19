"""Recover complete RGB/mask pairs from saved, partially downloaded ORFD ZIP ranges."""
from __future__ import annotations
import argparse,json,zipfile
from collections import Counter
from pathlib import Path,PurePosixPath
from .download_orfd_rgb import selected,SOURCE
from .preprocess_mju_waste import ROOT,write_json

def extract(raw,out):
    raw,out=Path(raw),Path(out)
    state=json.loads((raw/'drive_completed_ranges.json').read_text())
    ranges=sorted(tuple(map(int,key.split('-'))) for key in state['completed']);merged=[]
    for start,end in ranges:
        if merged and start<=merged[-1][1]+1:merged[-1][1]=max(end,merged[-1][1])
        else:merged.append([start,end])
    def covered(info):
        # Conservative allowance for variable ZIP header fields; z.read checks CRC.
        return any(a<=info.header_offset and b>=info.header_offset+info.compress_size+65535 for a,b in merged)
    files=[];counts=Counter()
    with zipfile.ZipFile(raw/'orfd_rgb_ranges.zip') as z:
        for info in z.infolist():
            if not selected(info) or '/image_data/' not in info.filename or not covered(info):continue
            gt_name=info.filename.replace('/image_data/','/gt_image/').replace('.png','_fillcolor.png')
            try:gt=z.getinfo(gt_name)
            except KeyError:continue
            if not selected(gt) or not covered(gt):continue
            if any((member.external_attr>>16)&0o170000==0o120000 or member.file_size>100*1024*1024 for member in (info,gt)):
                raise ValueError('Unsafe ZIP member')
            # Validate both members before writing either member of the pair.
            pair=[(member,z.read(member)) for member in (info,gt)]
            for member,data in pair:
                if (member.external_attr>>16)&0o170000==0o120000 or member.file_size>100*1024*1024:raise ValueError('Unsafe ZIP member')
                name='ORFD/'+'/'.join(PurePosixPath(member.filename).parts[1:]);target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists() and target.read_bytes()==data:pass
                else:
                    temp=target.with_suffix('.part');temp.write_bytes(data);temp.replace(target)
                files.append({'path':name,'bytes':member.file_size,'archive_member':member.filename,'zip_crc32':member.CRC})
            counts[PurePosixPath(info.filename).parts[1]]+=1
    if not files:raise ValueError('No complete CRC-valid RGB/mask pairs available')
    report={'files':files,'partial':True,'source_url':SOURCE,'full_mirror_pairs':11830,'available_pairs':sum(counts.values()),'source_split_counts':dict(counts),'crc_checks_passed':True}
    write_json(out/'selected_source_inventory.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--raw-root',type=Path,default=ROOT/'data/raw/orfd');ap.add_argument('--out',type=Path,default=ROOT/'data/raw/orfd/partial');args=ap.parse_args();extract(args.raw_root,args.out)

if __name__=='__main__':main()
