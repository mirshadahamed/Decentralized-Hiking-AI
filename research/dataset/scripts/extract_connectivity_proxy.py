"""OSM explicitly tagged communication structures; presence is not mobile coverage."""
from common import *
import osmium
init()
features={r:[] for r in REGIONS}
class H(osmium.SimpleHandler):
 def node(self,o):
  t=dict(o.tags)
  if t.get('man_made') not in ['mast','tower','communications_tower']:return
  if not(t.get('tower:type')=='communication' or t.get('man_made')=='communications_tower' or t.get('communication:mobile_phone')=='yes'):return
  x,y=o.location.lon,o.location.lat
  for r,(s,w,n,e) in REGIONS.items():
   if w<=x<=e and s<=y<=n:features[r].append(dict(type='Feature',id=f'node/{o.id}',properties=dict(osm_id=o.id,osm_type='node',tags=t,source='OSM via Geofabrik 2026-10-12',osm_mobile_phone_tag_present=t.get('communication:mobile_phone')=='yes',coverage_known=False),geometry=dict(type='Point',coordinates=[x,y])))
H().apply_file(str(ROOT/'raw/trails/sri-lanka-261012.osm.pbf'))
for r,f in features.items():
 (ROOT/f'raw/connectivity/{r}_osm_communication_structures.geojson').write_text(json.dumps(dict(type='FeatureCollection',features=f)))
 print(r,len(f),flush=True)
