from common import *
init()
VARIABLES=['temperature_2m','apparent_temperature','relative_humidity_2m','precipitation','rain','weather_code','cloud_cover','wind_speed_10m','wind_gusts_10m','surface_pressure']
points=[]
for region,(s,w,n,e) in REGIONS.items():
 coords=[(7.45,80.80),(7.30,80.70),(7.30,80.90),(7.55,80.70),(7.55,80.90)] if region=='knuckles' else [((s+n)/2,(w+e)/2)]
 for i,(lat,lon) in enumerate(coords):points.append(dict(point_id=f'{region}_{i}',region=region,latitude=lat,longitude=lon,selection='provisional AOI sampling; not field observation'))
write_csv('metadata/weather_sampling_points.csv',points)
for point in points:
 params=dict(latitude=point['latitude'],longitude=point['longitude'],start_date='2021-01-01',end_date='2025-12-31',hourly=','.join(VARIABLES),models='era5_seamless',timezone='GMT',temperature_unit='celsius',wind_speed_unit='kmh',precipitation_unit='mm')
 url='https://archive-api.open-meteo.com/v1/archive?'+urllib.parse.urlencode(params)
 p=fetch(url,f"raw/weather/{point['point_id']}_2021_2025.json",'weather','Open-Meteo; ECMWF/Copernicus ERA5 + ERA5-Land','CC BY 4.0; free API non-commercial',point['region'],'2021-01-01/2025-12-31')
 if not p:continue
 try:
  d=json.loads(p.read_text());h=d['hourly'];rows=[]
  for j,t in enumerate(h['time']):rows.append(dict(point_id=point['point_id'],region=point['region'],requested_latitude=point['latitude'],requested_longitude=point['longitude'],grid_latitude=d['latitude'],grid_longitude=d['longitude'],api_elevation_m=d['elevation'],timestamp=t+':00Z',**{v:h[v][j] for v in VARIABLES}))
  write_csv(f"processed/weather/{point['point_id']}_hourly.csv",rows)
 except Exception as ex:print('UNUSABLE',p,ex,flush=True)
