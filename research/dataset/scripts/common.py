import csv, json, urllib.request, urllib.parse, hashlib
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
REGIONS={
 'knuckles':(7.25,80.65,7.60,80.95), 'horton_plains':(6.75,80.75,6.88,80.88),
 'adams_peak':(6.75,80.45,6.90,80.58), 'ella':(6.82,81.00,6.93,81.10),
 'riverston':(7.48,80.70,7.58,80.80), 'meemure':(7.38,80.80,7.49,80.90),
 'sinharaja':(6.32,80.35,6.50,80.65), 'sigiriya_pidurangala':(7.93,80.70,8.00,80.80),
 'namunukula':(6.85,81.05,6.96,81.17), 'haputale':(6.72,80.88,6.83,81.02)}
def write_csv(path,rows,fields=None):
 path=ROOT/path;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def fetch(url,relative,category,source,license,coverage,temporal,processing='none'):
 path=ROOT/relative;path.parent.mkdir(parents=True,exist_ok=True)
 rec=dict(access_time_utc=datetime.now(timezone.utc).isoformat(),url=url,path=relative,category=category,source=source,license=license,coverage=coverage,temporal=temporal,processing=processing)
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'UniversityHikingResearch/1.0'}),timeout=90) as r:
   b=r.read();rec.update(status='downloaded',http_status=r.status,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),content_type=r.headers.get('Content-Type'));path.write_bytes(b)
 except Exception as e:rec.update(status='failed',error=str(e))
 with (ROOT/'metadata/download_log.jsonl').open('a') as f:f.write(json.dumps(rec)+'\n')
 print(relative,rec['status'],rec.get('bytes',rec.get('error')),flush=True)
 return path if rec['status']=='downloaded' else None
def init():
 for folder in ['raw/trails','raw/weather','raw/elevation','raw/hazards','raw/connectivity','raw/safety_sources','raw/emergency','processed/trails','processed/weather','processed/elevation','processed/hazards','processed/connectivity','metadata','labels']:(ROOT/folder).mkdir(parents=True,exist_ok=True)
