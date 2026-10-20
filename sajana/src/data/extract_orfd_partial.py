"""Recover complete RGB/mask pairs from saved, partially downloaded ORFD ZIP ranges."""
from __future__ import annotations
import argparse,json,zipfile
from collections import Counter
from pathlib import Path,PurePosixPath
from .download_orfd_rgb import selected,SOURCE,merged_completed_ranges,member_covered
from .preprocess_mju_waste import ROOT,write_json

def extract(raw,out):
    raw,out=Path(raw),Path(out)
    state=json.loads((raw/'drive_completed_ranges.json').read_text())
    archive=raw/'orfd_rgb_ranges.zip'
    merged=merged_completed_ranges(state,archive.stat().st_size)
    files=[];counts=Counter();failed_pairs=[];unavailable_pairs=0
    with archive.open('rb') as saved, zipfile.ZipFile(archive) as z:
        def covered(info):
            return member_covered(saved,info,merged)
        for info in z.infolist():
            if not selected(info) or '/image_data/' not in info.filename:continue
            if not covered(info):
                unavailable_pairs+=1;continue
            gt_name=info.filename.replace('/image_data/','/gt_image/').replace('.png','_fillcolor.png')
            try:gt=z.getinfo(gt_name)
            except KeyError:
                unavailable_pairs+=1;continue
            if not selected(gt) or not covered(gt):
                unavailable_pairs+=1;continue
            if any((member.external_attr>>16)&0o170000==0o120000 or member.file_size>100*1024*1024 for member in (info,gt)):
                raise ValueError('Unsafe ZIP member')
            # Validate both members before writing either member of the pair.
            try:
                pair=[(member,z.read(member)) for member in (info,gt)]
            except (zipfile.BadZipFile,EOFError,RuntimeError) as exc:
                failed_pairs.append({'image':info.filename,'mask':gt.filename,'error':str(exc)})
                continue
            for member,data in pair:
                if (member.external_attr>>16)&0o170000==0o120000 or member.file_size>100*1024*1024:raise ValueError('Unsafe ZIP member')
                name='ORFD/'+'/'.join(PurePosixPath(member.filename).parts[1:]);target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists() and target.read_bytes()==data:pass
                else:
                    temp=target.with_suffix('.part');temp.write_bytes(data);temp.replace(target)
                files.append({'path':name,'bytes':member.file_size,'archive_member':member.filename,'zip_crc32':member.CRC})
            counts[PurePosixPath(info.filename).parts[1]]+=1
    if not files:
        write_json(out/'partial_extraction_failures.json',{'failed_pairs':failed_pairs,'unavailable_pairs':unavailable_pairs})
        raise ValueError('No complete CRC-valid RGB/mask pairs available')
    report={'files':files,'partial':True,'source_url':SOURCE,'full_mirror_pairs':11830,'available_pairs':sum(counts.values()),'source_split_counts':dict(counts),'crc_checks_passed':True,'unavailable_pairs':unavailable_pairs,'failed_pairs':failed_pairs}
    write_json(out/'selected_source_inventory.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--raw-root',type=Path,default=ROOT/'data/raw/orfd');ap.add_argument('--out',type=Path,default=ROOT/'data/raw/orfd/partial');args=ap.parse_args();extract(args.raw_root,args.out)

if __name__=='__main__':main()
