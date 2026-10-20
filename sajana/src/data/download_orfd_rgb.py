"""Download only RGB/mask ZIP members from the author-linked ORFD Drive mirror.

Uses validated HTTP ranges, resumable chunks, and ZIP CRC checks. No archive
paths, scripts, links, depth maps or point clouds are extracted.
"""
from __future__ import annotations
import argparse,concurrent.futures,hashlib,importlib,json,os,re,struct,threading,time,zipfile
from pathlib import Path,PurePosixPath
import requests
from .preprocess_mju_waste import ROOT
FILE_ID='1HMG6mIfI_sNQlYg4LyrNXubaHFxlM7d1'
SOURCE='https://github.com/chaytonmin/Off-Road-Freespace-Detection/issues/6#issuecomment-1347324143'

def selected(info):
    if '\\' in info.filename or ':' in info.filename:
        return False
    parts=PurePosixPath(info.filename).parts
    return (not info.is_dir() and len(parts)==4 and parts[0]=='Final_Dataset' and parts[1] in ('training','validation','testing') and parts[2] in ('image_data','gt_image') and parts[3].endswith('.png')) or (not info.is_dir() and len(parts)==2 and parts[0]=='Final_Dataset' and parts[1] in ('LICENSE','README.txt'))

def save_json(path, value):
    """Keep resume markers intact if the process stops during a state update."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def pending_batch(groups, done, max_ranges=0, max_download_bytes=0):
    """Select a bounded batch without changing persisted legacy range boundaries."""
    pending = [g for g in groups if f'{g[0]}-{g[1]}' not in done]
    batch, size = [], 0
    for group in pending:
        amount = group[1] - group[0] + 1
        if max_ranges and len(batch) >= max_ranges:
            break
        if max_download_bytes and size + amount > max_download_bytes:
            break
        batch.append(group)
        size += amount
    return batch


def range_plan(infos, central_offset):
    """Keep the original 32 MiB plan stable for all existing resume markers."""
    groups = []
    for info in infos:
        start = info.header_offset
        end = min(start + 30 + len(info.filename.encode()) + 65535 + info.compress_size + 24, central_offset - 1)
        if groups and start <= groups[-1][1] + 4096 and end - groups[-1][0] <= 32 * 1024 * 1024:
            groups[-1][1] = max(groups[-1][1], end)
        else:
            groups.append([start, end])
    return groups


def coalesce_requests(groups, max_bytes):
    """Combine only touching/overlapping missing ranges, retaining every marker."""
    requests = []
    for start, end in groups:
        if requests and start <= requests[-1][1] + 1 and max(end, requests[-1][1]) - requests[-1][0] + 1 <= max_bytes:
            requests[-1][1] = max(end, requests[-1][1])
            requests[-1][2].append([start, end])
        else:
            requests.append([start, end, [[start, end]]])
    return requests


def save_request(fd, start, data, groups):
    """Write a validated request before returning checksums for its legacy keys."""
    if not data or any(a < start or b >= start + len(data) for a,b in groups):
        raise ValueError('Request payload does not cover its completed range markers')
    written = 0
    while written < len(data):
        amount = os.pwrite(fd, data[written:], start + written)
        if amount <= 0:
            raise OSError('Could not save downloaded range')
        written += amount
    return {f'{a}-{b}': hashlib.sha256(data[a-start:b-start+1]).hexdigest() for a,b in groups}


def merged_completed_ranges(state, archive_size):
    merged = []
    for key in state.get('completed', []):
        if not re.fullmatch(r'\d+-\d+', key):
            raise ValueError('Invalid completed range marker')
        start, end = map(int, key.split('-'))
        if not 0 <= start <= end < archive_size:
            raise ValueError('Completed range lies outside the saved archive')
        merged.append((start, end))
    result = []
    for start, end in sorted(merged):
        if result and start <= result[-1][1] + 1:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return result


def member_covered(archive, info, ranges):
    """Require every byte of the real local header and compressed payload."""
    start = info.header_offset
    containing = next(((a, b) for a, b in ranges if a <= start and b >= start + 29), None)
    if containing is None:
        return False
    archive.seek(start)
    header = archive.read(30)
    if len(header) != 30 or header[:4] != b'PK\x03\x04':
        return False
    name_len, extra_len = struct.unpack_from('<HH', header, 26)
    payload_end = start + 30 + name_len + extra_len + info.compress_size - 1
    return containing[1] >= payload_end


def cached_identity(out, prior):
    identity = prior.get('identity')
    archive = out / 'orfd_rgb_ranges.zip'
    if not identity:
        return None
    if identity.get('file_id') != FILE_ID or not archive.is_file() or archive.stat().st_size != identity.get('archive_bytes'):
        raise ValueError('Saved range identity does not match the archive; preserve it and use fresh output')
    try:
        with zipfile.ZipFile(archive) as saved:
            if not saved.infolist():
                raise ValueError('Saved ZIP index is empty')
    except zipfile.BadZipFile as exc:
        raise ValueError('Saved ZIP index is damaged; preserve it and use fresh output') from exc
    return identity


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=ROOT/'data/raw/orfd')
    ap.add_argument('--workers',type=int,default=2)
    ap.add_argument('--request-size-mib',type=int,default=32,help='Coalesce touching missing ranges up to this request size (1-256 MiB)')
    ap.add_argument('--max-ranges',type=int,default=0,help='Download at most this many missing ranges; 0 means all')
    ap.add_argument('--max-download-bytes',type=int,default=0,help='Maximum new range bytes this invocation; 0 means unlimited')
    args=ap.parse_args()
    if not 1 <= args.request_size_mib <= 256:
        ap.error('--request-size-mib must be between 1 and 256')
    if args.max_ranges < 0 or args.max_download_bytes < 0:
        ap.error('Batch limits must be nonnegative')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    archive=out/'orfd_rgb_ranges.zip';state=out/'drive_completed_ranges.json'
    prior=json.loads(state.read_text()) if state.is_file() else {}
    identity=cached_identity(out,prior)
    abort=threading.Event()
    url=None
    def rejected(response):
        title=re.search(r"<title>(.*?)</title>",response.text,re.S)
        return RuntimeError(f"Drive refused range: HTTP {response.status_code}; " + (title.group(1) if title else response.text[:250]))
    def download_url():
        nonlocal url
        if url is None:
            response=requests.get(f'https://drive.google.com/uc?id={FILE_ID}',timeout=(15,45))
            response.raise_for_status()
            url=importlib.import_module('gdown.download').get_url_from_gdrive_confirmation(response.text)
        return url
    def fetch(start,end):
        for attempt in range(3):
            if abort.is_set():raise RuntimeError("Transfer cancelled after another range failed")
            try:
                response=requests.get(download_url(),headers={'Range':f'bytes={start}-{end}'},timeout=(15,45))
                if response.status_code in (403,429):
                    abort.set();raise rejected(response)
                response.raise_for_status()
                if response.status_code!=206:
                    abort.set();raise rejected(response)
                content_range=response.headers.get('Content-Range','')
                if content_range != f'bytes {start}-{end}/{identity["archive_bytes"]}' or len(response.content)!=end-start+1:
                    abort.set();raise RuntimeError('Remote archive identity/range changed; saved bytes were retained')
                return response.content
            except requests.RequestException:
                if attempt==2:raise
                time.sleep(2**attempt)
    if identity is None:
        response=requests.get(download_url(),headers={'Range':'bytes=-131072'},timeout=(15,45))
        response.raise_for_status()
        if response.status_code!=206:raise rejected(response)
        match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
        if not match:raise ValueError('Server did not return a valid suffix byte range')
        tail_start,tail_end,total=map(int,match.groups());tail=response.content
        if tail_end!=total-1 or len(tail)!=total-tail_start:raise ValueError('Server returned an incomplete ZIP tail')
        at=tail.rfind(b'PK\x06\x06')
        if at>=0:
            values=struct.unpack_from('<4sQ2H2L4Q',tail,at);size,offset=values[-2:]
        else:
            at=tail.rfind(b'PK\x05\x06')
            if at<0:raise ValueError('ZIP central directory is missing')
            values=struct.unpack_from('<4s4H2LH',tail,at);size,offset=values[-3:-1]
        if not 0 < size <= total or not 0 <= offset < total-size:raise ValueError('Invalid ZIP central directory bounds')
        identity={'file_id':FILE_ID,'archive_bytes':total,'central_offset':offset,'central_bytes':size}
        with archive.open('r+b' if archive.exists() else 'w+b') as f:
            f.truncate(total);f.seek(offset);f.write(fetch(offset,offset+size-1));f.seek(tail_start);f.write(tail)
        save_json(state,{'identity':identity,'completed':[]})
    offset=identity['central_offset']
    with zipfile.ZipFile(archive) as z:infos=sorted([i for i in z.infolist() if selected(i)],key=lambda i:i.header_offset)
    files=[];groups=range_plan(infos,offset)
    for i in infos:
        parts=PurePosixPath(i.filename).parts
        if '..' in parts or i.file_size>100*1024*1024 or (i.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsafe/unexpected ZIP member')
        files.append({'path':'ORFD/'+'/'.join(parts[1:]),'bytes':i.file_size,'archive_member':i.filename,'zip_crc32':i.CRC})
    save_json(out/'selected_source_inventory.json',{'source_url':SOURCE,'mirror_file_id':FILE_ID,'files':files,'selected_bytes':sum(x['bytes'] for x in files),'published_count_complete':False})
    if not infos:raise ValueError('ZIP index has no selected RGB/mask files')
    merged_completed_ranges(prior, identity['archive_bytes'])
    expected_keys={f'{a}-{b}' for a,b in groups}
    if set(prior.get('completed',[]))-expected_keys:raise ValueError('Saved markers do not match this archive range plan')
    done=set(prior.get('completed',[]));lock=threading.Lock();started=time.monotonic();fd=os.open(archive,os.O_RDWR)
    batch=pending_batch(groups,done,args.max_ranges,args.max_download_bytes)
    request_groups=coalesce_requests(batch,args.request_size_mib*1024*1024)
    range_hashes=dict(prior.get('range_sha256',{}))
    def worker(request):
        start,end,members=request
        data=fetch(start,end)
        hashes=save_request(fd,start,data,members)
        with lock:
            done.update(hashes);range_hashes.update(hashes)
            save_json(state,{'identity':identity,'completed':sorted(done),'range_sha256':range_hashes})
        with lock:
            completed=sum(b-a+1 for a,b in groups if f'{a}-{b}' in done)
            report={'complete':False,'phase':'download','completed_ranges':len(done),'expected_ranges':len(groups),'downloaded_bytes':completed,'expected_bytes':sum(b-a+1 for a,b in groups),'elapsed_seconds':round(time.monotonic()-started),'source_url':SOURCE}
            save_json(out/'download_status.json',report)
            if len(done)%10==0:print(f'ORFD ranges: {len(done)}/{len(groups)}, {completed/1e9:.2f} GB',flush=True)
    print(f'ORFD resume: {len(done)}/{len(groups)} ranges already saved; downloading {len(batch)} missing ranges in {len(request_groups)} HTTP requests',flush=True)
    try:
        if batch:download_url()
        pool=concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(args.workers,12)))
        futures=[pool.submit(worker,g) for g in request_groups]
        try:
            for future in concurrent.futures.as_completed(futures):future.result()
        except Exception:
            abort.set()
            for future in futures:future.cancel()
            raise
        finally:pool.shutdown(wait=True,cancel_futures=True)
    finally:os.close(fd)
    if any(f'{a}-{b}' not in done for a,b in groups):
        save_json(out/'download_status.json',{'complete':False,'phase':'batch_complete','completed_ranges':len(done),
                  'expected_ranges':len(groups),'downloaded_bytes':sum(b-a+1 for a,b in groups if f'{a}-{b}' in done),
                  'expected_bytes':sum(b-a+1 for a,b in groups),'source_url':SOURCE,'resume_supported':True})
        print('ORFD batch saved. Resume to fetch remaining ranges; partial extraction is available.',flush=True)
        return
    extracted=0
    with zipfile.ZipFile(archive) as z:
        for i,row in zip(infos,files):
            target=out/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
            # Reading each member validates its CRC, including on resumed runs.
            data=z.read(i);temporary=target.with_suffix('.part');temporary.write_bytes(data);temporary.replace(target);extracted+=1
            if extracted%1000==0:print(f'Extracted/CRC checked {extracted}/{len(files)} files',flush=True)
    save_json(out/'download_status.json',{'complete':True,'phase':'extracted','files':extracted,'expected_files':len(files),'source_url':SOURCE,'mirror_file_id':FILE_ID,'crc_checks_passed':True,'published_image_count':12198,'published_count_complete':False,'mirror_count_complete':True,'available_image_pairs':sum('/image_data/' in x['path'] for x in files)})
    print('ORFD RGB/mask acquisition complete',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--out',type=Path,default=ROOT/'data/raw/orfd');options,_=parser.parse_known_args()
        out=options.out;p=out/'download_status.json'
        report=json.loads(p.read_text()) if p.exists() else {}
        report.update(complete=False,phase='download_failed',error=str(exc),resume_supported=True)
        save_json(p,report)
        raise SystemExit(f'ORFD acquisition stopped: {exc}. Completed ranges are retained for resume.')
