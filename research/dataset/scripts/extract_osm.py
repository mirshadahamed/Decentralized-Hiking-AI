"""Fallback extraction from Geofabrik PBF; requires osmium and pyproj.
Full ways are retained if any vertex lies inside an AOI; not clipped.
Relations retain membership/roles; member-way geometry stored separately.
"""
from common import *
import osmium
from pyproj import Geod
geod=Geod(ellps='WGS84');init()
class Extract(osmium.SimpleHandler):
 def __init__(self):
  super().__init__();self.paths={r:[] for r in REGIONS};self.facilities={r:[] for r in REGIONS};self.relations=[];self.errors=0;self.hiking_ways=set()
 def regions(self,coords):
  return [r for r,(s,w,n,e) in REGIONS.items() if any(w<=x<=e and s<=y<=n for x,y in coords)]
 def relation(self,o):
  tags=dict(o.tags)
  if tags.get('route')=='hiking':
   members=[dict(type=m.type,ref=m.ref,role=m.role) for m in o.members]
   self.relations.append(dict(osm_id=o.id,tags=tags,members=members))
   self.hiking_ways.update(m.ref for m in o.members if m.type=='w')
 def node(self,o):
  tags=dict(o.tags)
  if not self.is_facility(tags):return
  coords=[o.location.lon,o.location.lat]
  for r in self.regions([coords]):self.facilities[r].append(self.feature('node',o.id,tags,'Point',coords))
 @staticmethod
 def is_facility(t):return t.get('amenity') in ['hospital','clinic','doctors','drinking_water','shelter','police','ranger_station'] or 'emergency' in t or t.get('natural')=='spring'
 @staticmethod
 def feature(kind,oid,tags,gt,coords):return dict(type='Feature',id=f'{kind}/{oid}',properties=dict(osm_type=kind,osm_id=oid,tags=tags,**tags),geometry=dict(type=gt,coordinates=coords))
 def way(self,o):
  tags=dict(o.tags);candidate=tags.get('highway') in ['path','footway','track','steps','bridleway'] or o.id in self.hiking_ways
  if not candidate and not self.is_facility(tags):return
  try:coords=[[p.lon,p.lat] for p in o.nodes]
  except osmium.InvalidLocationError:self.errors+=1;return
  if len(coords)<2:return
  for r in self.regions(coords):
   f=self.feature('way',o.id,tags,'LineString',coords)
   if candidate:
    f['properties'].update(verified_hiking_trail=False,length_km=geod.line_length(*zip(*coords))/1000,hiking_relation_ids=[rel['osm_id'] for rel in self.relations if any(m['type']=='w' and m['ref']==o.id for m in rel['members'])]);self.paths[r].append(f)
   if self.is_facility(tags):self.facilities[r].append(self.feature('way',o.id,tags,'LineString',coords))
p=ROOT/'raw/trails/sri-lanka-261012.osm.pbf'
e=Extract()
# First pass relations, second nodes/ways. Prevent duplicate relation parsing.
class R(osmium.SimpleHandler):
 def relation(self,o):e.relation(o)
R().apply_file(str(p))
e.relation=lambda o:None
e.apply_file(str(p),locations=True,idx='flex_mem')
for r in REGIONS:
 for folder,features in [('trails',e.paths[r]),('emergency',e.facilities[r])]:
  filename=f'processed/trails/{r}_candidate_paths.geojson' if folder=='trails' else f'raw/emergency/{r}_facilities.geojson'
  (ROOT/filename).write_text(json.dumps(dict(type='FeatureCollection',features=features)))
 # Region-specific extracts, while country PBF remains unmodified.
 (ROOT/f'raw/trails/{r}_pbf_extract.geojson').write_text(json.dumps(dict(type='FeatureCollection',features=e.paths[r])))
 ids={f['properties']['osm_id'] for f in e.paths[r]}
 rel=[x for x in e.relations if any(m['type']=='w' and m['ref'] in ids for m in x['members'])]
 (ROOT/f'raw/trails/{r}_hiking_relations.json').write_text(json.dumps(rel))
 print(r,len(e.paths[r]),len(e.facilities[r]),len(rel),flush=True)
(ROOT/'metadata/osm_extraction_quality.json').write_text(json.dumps(dict(invalid_locations=e.errors,method='any vertex inside bbox; full ways retained; relations not assembled; facility ways retained as lines, not polygons')))
