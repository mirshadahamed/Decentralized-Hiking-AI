from common import *
import zipfile
target=ROOT.parent/'decentralized_hiking_ai_dataset.zip'
with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
 for p in sorted(ROOT.rglob('*')):
  if '__pycache__' in p.parts:continue
  z.write(p,arcname=str(p.relative_to(ROOT.parent)))
with zipfile.ZipFile(target) as z:
 bad=z.testzip()
 if bad:raise RuntimeError('Corrupt ZIP member: '+bad)
 print(dict(zip=str(target),bytes=target.stat().st_size,members=len(z.infolist()),crc_check='pass'))
