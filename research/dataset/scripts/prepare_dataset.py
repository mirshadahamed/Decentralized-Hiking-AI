"""Audit the real files, generate provenance/report/manifests; never fabricate joins/labels."""
from common import *
from collections import Counter
import math,xml.etree.ElementTree as ET
init();quality={'trails':{},'weather':{},'elevation':{},'connectivity':{},'warnings':[]};processing=[]
allids=[]
for p in sorted((ROOT/'processed/trails').glob('*candidate_paths.geojson')):
 d=json.loads(p.read_text());fs=d['features'];ids=[f['id'] for f in fs];allids.extend(ids);invalid=0;zero=0;missing=Counter();types=Counter()
 for f in fs:
  typ=f['geometry']['type'];types[typ]+=1
  parts=[f['geometry']['coordinates']] if typ=='LineString' else f['geometry']['coordinates']
  for part in parts:
   invalid+=int(len(part)<2 or any(not(-180<=x<=180 and -90<=y<=90) or not(math.isfinite(x) and math.isfinite(y)) for x,y in part))
  zero+=f['properties'].get('length_km',0)<=0
  for key in ['name','sac_scale','surface','smoothness','incline','trail_visibility','access','foot']:missing[key]+=not bool(f['properties'].get(key))
 quality['trails'][p.name]=dict(features=len(fs),duplicate_ids=len(ids)-len(set(ids)),invalid_coordinate_parts=invalid,zero_length=zero,geometry_types=dict(types),missing_tags=dict(missing),crs='GeoJSON WGS84 lon/lat',verified_hiking_count=0)
 processing.append(dict(output=str(p.relative_to(ROOT)),inputs='raw/trails/sri-lanka-261012.osm.pbf',script='scripts/extract_osm.py',method='any vertex inside provisional bbox; full ways; all tags; geodesic length'))
quality['cross_region_repeated_trail_ids']=len(allids)-len(set(allids))
quality['unique_candidate_trail_ids']=len(set(allids))
for p in sorted((ROOT/'processed/weather').glob('*.csv')):
 rows=list(csv.DictReader(p.open()));keys=[(r['point_id'],r['timestamp']) for r in rows];missing={k:sum(r[k]=='' for r in rows) for k in rows[0]};badtime=0;nonhourly=0;prev=None;bounds=Counter()
 for r in rows:
  try:
   t=datetime.fromisoformat(r['timestamp'].replace('Z','+00:00'));badtime+=int(t.utcoffset().total_seconds()!=0)
   if prev:nonhourly+=int((t-prev).total_seconds()!=3600)
   prev=t
  except ValueError:badtime+=1
  for v,lo,hi in [('relative_humidity_2m',0,100),('cloud_cover',0,100),('precipitation',0,1000),('rain',0,1000),('wind_speed_10m',0,500),('wind_gusts_10m',0,500)]:
   if r[v] and not lo<=float(r[v])<=hi:bounds[v]+=1
 quality['weather'][p.name]=dict(rows=len(rows),expected_rows=43824,duplicate_keys=len(keys)-len(set(keys)),missing_values=missing,invalid_time=badtime,nonhourly_steps=nonhourly,range_flags=dict(bounds),start=rows[0]['timestamp'],end=rows[-1]['timestamp'],grid_latitude=rows[0]['grid_latitude'],grid_longitude=rows[0]['grid_longitude'])
 raw=ROOT/'raw/weather'/p.name.replace('_hourly.csv','_2021_2025.json')
 d=json.loads(raw.read_text())
 quality['weather'][p.name]['raw_units']=d['hourly_units']
 quality['weather'][p.name]['invalid_coordinates']=sum(not(-90<=float(r['requested_latitude'])<=90 and -180<=float(r['requested_longitude'])<=180 and -90<=float(r['grid_latitude'])<=90 and -180<=float(r['grid_longitude'])<=180) for r in rows)
 quality['weather'][p.name]['utc_offset_seconds']=d['utc_offset_seconds']
 processing.append(dict(output=str(p.relative_to(ROOT)),inputs='raw/weather/'+p.name.replace('_hourly.csv','_2021_2025.json'),script='scripts/download_weather.py',method='hourly JSON arrays to CSV; attach requested/returned coordinates; UTC offset made explicit; no imputation'))
for p in sorted((ROOT/'processed/elevation').glob('*points.csv')):
 rows=list(csv.DictReader(p.open()));keys=[(r['trail_id'],r['point_index']) for r in rows]
 quality['elevation'][p.name]=dict(rows=len(rows),duplicate_keys=len(keys)-len(set(keys)),missing_elevation=sum(r['elevation_m']=='' for r in rows),missing_slope=sum(r['slope_deg']=='' for r in rows),invalid_slope=sum(bool(r['slope_deg']) and not 0<=float(r['slope_deg'])<=90 for r in rows))
 processing.append(dict(output=str(p.relative_to(ROOT)),inputs='processed/trails/'+p.name.replace('_trail_points.csv','_candidate_paths.geojson')+'; raw/elevation/*.tif',script='scripts/process_elevation.py',method='geodesic densification <=60m; nearest DSM pixel; local slope 3x3 central difference; no gap filling or smoothing'))
for p in (ROOT/'raw/connectivity').glob('*.geojson'):
 fs=json.loads(p.read_text())['features'];quality['connectivity'][p.name]=dict(structures=len(fs),coverage_observations=0,limitation='Only explicitly tagged OSM nodes inside bbox; no buffer, no ways/relations, no measured coverage')
 processing.append(dict(output=str(p.relative_to(ROOT)),inputs='raw/trails/sri-lanka-261012.osm.pbf',script='scripts/extract_connectivity_proxy.py',method='Filter communication mast/tower nodes, preserve tags; no signal inference'))
rss=ROOT/'raw/hazards/meteo_cap_rss.xml'
if rss.exists():quality['warning_rss']=dict(items=len(ET.fromstring(rss.read_bytes()).findall('./channel/item')),copyright=ET.fromstring(rss.read_bytes()).findtext('./channel/copyright'),meaning='Snapshot only; empty feed is not evidence of historical no hazard')
quality['raw_overpass']={}
for p in (ROOT/'raw/trails').glob('*_overpass.json'):
 try:
  d=json.loads(p.read_text());quality['raw_overpass'][p.name]=dict(elements=len(d.get('elements',[])),remark=d.get('remark'),osm_base=d.get('osm3s',{}).get('timestamp_osm_base'),usable_without_truncation_warning=not bool(d.get('remark')))
 except Exception as ex:quality['raw_overpass'][p.name]=dict(unusable=str(ex))
quality['support_facilities']={}
for p in (ROOT/'raw/emergency').glob('*_facilities.geojson'):
 fs=json.loads(p.read_text())['features'];ids=[f['id'] for f in fs]
 quality['support_facilities'][p.name]=dict(features=len(fs),duplicate_ids=len(ids)-len(set(ids)),geometry_types=dict(Counter(f['geometry']['type'] for f in fs)),independently_verified=False)
quality['warnings']=['Overlapping AOIs duplicate OSM IDs across files; deduplicate before splitting','Missing tags are unknown, not easy/safe/access permitted','No validated recommendation labels','No licensed spatial landslide/flood training layer','OSM structure absence is not no coverage','Visibility unavailable','Historical realised weather must not leak into pre-trip forecast evaluation','Existing user Knuckles trail file not supplied','PBF facilities and regional extracts are derived despite raw folder location','Unsmooth DSM profiles may inflate ascent/descent; validate against survey/GNSS','Relation-based facilities not assembled in PBF extraction; raw Overpass may include them']
(ROOT/'metadata/quality_report.json').write_text(json.dumps(quality,indent=2))
write_csv('metadata/processing_manifest.csv',processing)
counts={r:x['features'] for r,x in quality['trails'].items()};weather=sum(x['rows'] for x in quality['weather'].values());terrain=sum(x['rows'] for x in quality['elevation'].values());comm=sum(x['structures'] for x in quality['connectivity'].values())
report=f'''# Collection report — 2026-10-14

Partial release. No model trained, no random labels, no missing-value fabrication.

## Successfully acquired
* Dated Geofabrik/OpenStreetMap Sri Lanka PBF (2026-10-12), original bytes and matching provider MD5; regional full-way candidate geometry and hiking-relation metadata for all ten AOIs. Region counts: {json.dumps(counts)}. These counts include overlap and unverified paths, tracks, steps and footways.
* Open-Meteo / ECMWF-Copernicus: 14 original hourly JSON responses, 2021–2025, {weather:,} hourly CSV rows. Five points across the provisional Knuckles extent; remaining areas one each. Reanalysis, not field stations. No visibility.
* Copernicus GLO-30: four original regional GeoTIFF tiles via documented AWS mirror, 2021 release, ~30m DSM; {terrain:,} derived trail-profile rows. DSM slope/gain is approximate.
* OSM support facilities in ten regional extracts and sourced national contacts: 1990 ambulance, 119 police, 117 DMC plus EOC numbers.
* OSM explicitly tagged communication structure nodes: {comm} region-assigned features (overlap possible), raw tags retained. This is inventory context, NOT a mobile coverage or signal-strength dataset.
* Department of Meteorology public CAP RSS snapshot: {quality.get('warning_rss',{}).get('items','unknown')} alerts. Feed declares Public Domain. No historical warning archive collected; new service marked provisional.
* Official safety/source link catalogues, resource target structure, label validation methodology, proposed feature origins, reproducible scripts and audit files. No copyrighted safety manuals copied.

## Quality checks
{quality['unique_candidate_trail_ids']} unique candidate OSM IDs; {quality['cross_region_repeated_trail_ids']} repeated assignments across overlapping area files. No within-file duplicate trail IDs or invalid trail coordinates were found in the current release. All candidate way geometries are LineStrings. Weather files have 43,824 rows each; time continuity, UTC offsets, returned units, range flags and missingness are audited. Terrain has {sum(x['missing_elevation'] for x in quality['elevation'].values())} missing heights and {sum(x['missing_slope'] for x in quality['elevation'].values())} missing slopes, preserved as blank. Knuckles difficulty/navigation tags are sparse: {json.dumps(quality['trails'].get('knuckles_candidate_paths.geojson',{}).get('missing_tags',{}))}. Missing sac_scale does not mean easy. Checks do not independently verify field accuracy.

## Not acquired / manual actions
Measured mobile coverage and signal strength remain missing. Obtain OpenCelliD token/country export, licensed dated Dialog/Mobitel/regulator layers, or consented field measurements. Tower distance alone cannot prove upcoming loss of connectivity. NBRO/DMC spatial hazard layers require access/licence clarification; PDF references are linked and not numeric training data. Park/ranger contacts, verified potable water/shelters, wildlife guidance and clinically reviewed licensed offline content remain incomplete. Existing user trail file was not attached. Exact official pages and actions are in metadata/manual_acquisition.md.

## Restrictions and limitations
OSM ODbL 1.0, weather CC BY 4.0 (free service non-commercial), Copernicus-specific licence/attribution; no blanket licence. Future OpenCelliD CC BY-SA 4.0 obligations remain separate. Operator and government PDF availability does not establish redistribution permission. Current 2026 OSM is temporally mismatched with 2021–2025 weather; use for explicit retrospective scenario design rather than claiming historical route/coverage observations. AOIs/points provisional; volunteered features may be incomplete, inaccurate, inaccessible or stale. Weather grid dependence and mountain microclimates limit resolution. Gain/loss may be canopy/noise-sensitive. Read metadata/quality_report.json for numeric missingness/duplicates and warnings.

## Next preprocessing and readiness
Review original Knuckles trails, route access, continuity and safe support points with local experts. Deduplicate IDs across Knuckles/Riverston/Meemure. Refine weather samples by validated route/elevation strata without claiming independent nearby weather cells. Assemble hiking route relations and validate DSM-derived ascent. Collect forecast issue times and dated connectivity measurements/layers. Obtain licensed hazard GIS and independent blinded expert resource labels; leave all unavailable fields NULL. Validate connectivity transitions on route segments with operator/technology and freshness recorded.

Sufficient to BEGIN a Knuckles data pipeline and exploratory terrain/weather prototype. NOT sufficient for training or independently evaluating the full context-aware, connectivity-driven recommender. Important data is still missing.
'''
(ROOT/'collection_report.md').write_text(report)
manifest=[]
for p in sorted(ROOT.rglob('*')):
 if p.is_file() and p.name!='file_manifest.csv' and '__pycache__' not in str(p):manifest.append(dict(path=str(p.relative_to(ROOT)),size_bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
write_csv('metadata/file_manifest.csv',manifest)
print(json.dumps(dict(trails=counts,weather_rows=weather,terrain_rows=terrain,communication_structures=comm,files=len(manifest)),indent=2))
