from common import *
from math import radians,sin,cos,atan2,sqrt
init()
def distance(a,b):
 lat1,lat2=radians(a[1]),radians(b[1]);dl=radians(b[0]-a[0]);dp=lat2-lat1
 h=sin(dp/2)**2+cos(lat1)*cos(lat2)*sin(dl/2)**2
 return 6371008.8*2*atan2(sqrt(h),sqrt(max(0,1-h)))
def convert(d):
 features=[]
 for el in d['elements']:
  tags=el.get('tags',{});props=dict(osm_type=el['type'],osm_id=el['id'],tags=tags,verified_hiking_trail=False,**tags)
  if el['type']=='way':parts=[[[p['lon'],p['lat']] for p in el.get('geometry',[])]]
  elif el['type']=='relation':parts=[[[p['lon'],p['lat']] for p in m.get('geometry',[])] for m in el.get('members',[]) if m['type']=='way']
  else:continue
  parts=[p for p in parts if len(p)>1]
  if not parts:continue
  props['length_km']=sum(distance(a,b) for part in parts for a,b in zip(part,part[1:]))/1000
  features.append(dict(type='Feature',id=f"{el['type']}/{el['id']}",properties=props,geometry=dict(type='LineString' if el['type']=='way' else 'MultiLineString',coordinates=parts[0] if el['type']=='way' else parts)))
 return dict(type='FeatureCollection',features=features)
for region,bbox in REGIONS.items():
 box=','.join(map(str,bbox));q=f'[out:json][timeout:60];(way[highway~"^(path|footway|track|steps|bridleway)$"]({box});relation[route=hiking]({box}););out body geom;'
 (ROOT/f'raw/trails/{region}.overpassql').write_text(q)
 p=fetch('https://maps.mail.ru/osm/tools/overpass/api/interpreter?'+urllib.parse.urlencode({'data':q}),f'raw/trails/{region}_overpass.json','trails','OpenStreetMap contributors','ODbL 1.0',str(bbox),'OSM snapshot at API osm3s timestamp')
 if p:
  try:
   d=json.loads(p.read_text())
   if d.get('remark'):print('INCOMPLETE OVERPASS RESPONSE',d['remark']);continue
   geo=convert(d);(ROOT/f'raw/trails/{region}_overpass_paths.geojson').write_text(json.dumps(geo));print(region,len(geo['features']),flush=True)
  except Exception as ex:print('UNUSABLE',ex,flush=True)
 # Separate facilities query; retains all tags and actual geometry (nodes are points).
 q=f'[out:json][timeout:60];(nwr[amenity~"^(hospital|clinic|doctors|drinking_water|shelter|police|ranger_station)$"]({box});nwr[emergency]({box});nwr[natural=spring]({box}););out body geom;'
 fetch('https://maps.mail.ru/osm/tools/overpass/api/interpreter?'+urllib.parse.urlencode({'data':q}),f'raw/emergency/{region}_facilities_osm.json','emergency','OpenStreetMap contributors','ODbL 1.0',str(bbox),'OSM snapshot at API osm3s timestamp')
