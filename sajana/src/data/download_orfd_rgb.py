"""Download only RGB/mask ZIP members from the author-linked ORFD Drive mirror.

Uses validated HTTP ranges, resumable chunks, and ZIP CRC checks. No archive
paths, scripts, links, depth maps or point clouds are extracted.
"""
from __future__ import annotations
import argparse,concurrent.futures,importlib,json,os,re,struct,threading,time,zipfile
from pathlib import Path,PurePosixPath
import requests
from .preprocess_mju_waste import ROOT,write_json
FILE_ID='1HMG6mIfI_sNQlYg4LyrNXubaHFxlM7d1'
SOURCE='https://github.com/chaytonmin/Off-Road-Freespace-Detection/issues/6#issuecomment-1347324143'

def selected(info):
    if '\\' in info.filename or ':' in info.filename:
        return False
    parts=PurePosixPath(info.filename).parts
    return (not info.is_dir() and len(parts)==4 and parts[0]=='Final_Dataset' and parts[1] in ('training','validation','testing') and parts[2] in ('image_data','gt_image') and parts[3].endswith('.png')) or (not info.is_dir() and len(parts)==2 and parts[0]=='Final_Dataset' and parts[1] in ('LICENSE','README.txt'))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,default=ROOT/'data/raw/orfd');ap.add_argument('--workers',type=int,default=8);args=ap.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    s=requests.Session();r=s.get(f'https://drive.google.com/uc?id={FILE_ID}',timeout=60);r.raise_for_status()
    url=importlib.import_module('gdown.download').get_url_from_gdrive_confirmation(r.text)
    abort=threading.Event()
    def rejected(response):
        title=re.search(r"<title>(.*?)</title>",response.text,re.S)
        return RuntimeError(f"Drive refused range: HTTP {response.status_code}; " + (title.group(1) if title else response.text[:250]))
    def fetch(start,end):
        for attempt in range(3):
            if abort.is_set():raise RuntimeError("Transfer cancelled after another range failed")
            try:
                response=requests.get(url,headers={'Range':f'bytes={start}-{end}'},timeout=(15,45));response.raise_for_status()
                if response.status_code!=206:raise rejected(response)
                if response.status_code!=206 or not response.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/') or len(response.content)!=end-start+1:raise ValueError('Server did not honor the requested byte range')
                return response.content
            except (requests.RequestException,ValueError):
                if attempt==2:raise
                time.sleep(2**attempt)
    r=s.get(url,headers={'Range':'bytes=-131072'},timeout=60);r.raise_for_status()
    if r.status_code!=206:raise rejected(r)
    total=int(r.headers['Content-Range'].split('/')[-1]);tail=r.content
    at=tail.rfind(b'PK\x06\x06')
    if at>=0:
        values=struct.unpack_from('<4sQ2H2L4Q',tail,at);size,offset=values[-2:]
    else:
        at=tail.rfind(b'PK\x05\x06');values=struct.unpack_from('<4s4H2LH',tail,at);size,offset=values[-3:-1]
    archive=out/'orfd_rgb_ranges.zip';state=out/'drive_completed_ranges.json'
    identity={'file_id':FILE_ID,'archive_bytes':total,'central_offset':offset,'central_bytes':size}
    prior=json.loads(state.read_text()) if state.is_file() else {}
    if prior and prior.get('identity')!=identity:raise ValueError('Remote archive changed; use fresh output')
    with archive.open('r+b' if archive.exists() else 'w+b') as f:
        f.truncate(total);f.seek(offset);f.write(fetch(offset,offset+size-1));f.seek(total-len(tail));f.write(tail)
    with zipfile.ZipFile(archive) as z:infos=sorted([i for i in z.infolist() if selected(i)],key=lambda i:i.header_offset)
    files=[];groups=[]
    for i in infos:
        parts=PurePosixPath(i.filename).parts
        if '..' in parts or i.file_size>100*1024*1024 or (i.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsafe/unexpected ZIP member')
        files.append({'path':'ORFD/'+'/'.join(parts[1:]),'bytes':i.file_size,'archive_member':i.filename,'zip_crc32':i.CRC})
        start=i.header_offset;end=start+30+len(i.filename.encode())+65535+i.compress_size+24
        end=min(end,offset-1)
        if groups and start<=groups[-1][1]+4096 and end-groups[-1][0]<=32*1024*1024:groups[-1][1]=max(groups[-1][1],end)
        else:groups.append([start,end])
    write_json(out/'selected_source_inventory.json',{'source_url':SOURCE,'mirror_file_id':FILE_ID,'files':files,'selected_bytes':sum(x['bytes'] for x in files),'published_count_complete':False})
    done=set(prior.get('completed',[]));lock=threading.Lock();started=time.monotonic();fd=os.open(archive,os.O_RDWR)
    def worker(group):
        start,end=group;key=f'{start}-{end}'
        if key not in done:
            data=fetch(start,end);written=0
            while written<len(data):written+=os.pwrite(fd,data[written:],start+written)
            with lock:
                done.add(key);write_json(state,{'identity':identity,'completed':sorted(done)})
        with lock:
            completed=sum(b-a+1 for a,b in groups if f'{a}-{b}' in done)
            report={'complete':False,'phase':'download','completed_ranges':len(done),'expected_ranges':len(groups),'downloaded_bytes':completed,'expected_bytes':sum(b-a+1 for a,b in groups),'elapsed_seconds':round(time.monotonic()-started),'source_url':SOURCE}
            write_json(out/'download_status.json',report)
            if len(done)%10==0:print(f'ORFD ranges: {len(done)}/{len(groups)}, {completed/1e9:.2f} GB',flush=True)
    print(f'Downloading {len(files)} selected files in {len(groups)} resumable ranges',flush=True)
    try:
        pool=concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(args.workers,12)))
        futures=[pool.submit(worker,g) for g in groups]
        try:
            for future in concurrent.futures.as_completed(futures):future.result()
        except Exception:
            abort.set()
            for future in futures:future.cancel()
            raise
        finally:pool.shutdown(wait=True,cancel_futures=True)
    finally:os.close(fd)
    extracted=0
    with zipfile.ZipFile(archive) as z:
        for i,row in zip(infos,files):
            target=out/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
            # Reading each member validates its CRC, including on resumed runs.
            data=z.read(i);temporary=target.with_suffix('.part');temporary.write_bytes(data);temporary.replace(target);extracted+=1
            if extracted%1000==0:print(f'Extracted/CRC checked {extracted}/{len(files)} files',flush=True)
    write_json(out/'download_status.json',{'complete':True,'phase':'extracted','files':extracted,'expected_files':len(files),'source_url':SOURCE,'mirror_file_id':FILE_ID,'crc_checks_passed':True,'published_image_count':12198,'available_image_pairs':sum('/image_data/' in x['path'] for x in files)})
    print('ORFD RGB/mask acquisition complete',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--out',type=Path,default=ROOT/'data/raw/orfd');options,_=parser.parse_known_args()
        out=options.out;p=out/'download_status.json'
        report=json.loads(p.read_text()) if p.exists() else {}
        report.update(complete=False,phase='download_failed',error=str(exc),resume_supported=True)
        write_json(p,report)
        raise SystemExit(f'ORFD acquisition stopped: {exc}. Completed ranges are retained for resume.')
