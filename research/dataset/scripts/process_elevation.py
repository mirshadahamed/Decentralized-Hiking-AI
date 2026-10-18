from common import *
import math,numpy as np,rasterio
from pyproj import Geod
from rasterio.windows import Window
init();g=Geod(ellps='WGS84')
tiles=[rasterio.open(p) for p in (ROOT/'raw/elevation').glob('*.tif')]
def sample(x,y):
 for d in tiles:
  if d.bounds.left<=x<d.bounds.right and d.bounds.bottom<y<=d.bounds.top:
   row,col=d.index(x,y)
   if not(0<=row<d.height and 0<=col<d.width):return None,None
   center=d.read(1,window=Window(col,row,1,1),masked=True)
   if np.ma.getmaskarray(center).any() or not np.isfinite(center).all():return None,None
   height=float(center[0,0])
   if not(1<=row<d.height-1 and 1<=col<d.width-1):return height,None
   z=d.read(1,window=Window(col-1,row-1,3,3),masked=True)
   if np.ma.getmaskarray(z).any() or not np.isfinite(z).all():return height,None
   dx=abs(g.inv(x,y,x+d.res[0],y)[2]);dy=abs(g.inv(x,y,x,y+d.res[1])[2])
   sx=(float(z[1,2])-float(z[1,0]))/(2*dx);sy=(float(z[2,1])-float(z[0,1]))/(2*dy)
   return float(z[1,1]),math.degrees(math.atan(math.hypot(sx,sy)))
 return None,None
inventory=[]
for d in tiles:
 inventory.append(dict(filename=Path(d.name).name,crs=str(d.crs),width=d.width,height=d.height,bounds=str(d.bounds),pixel_degrees=str(d.res),nodata=d.nodata,vertical_datum='EGM2008',unit='m'))
if inventory:write_csv('metadata/elevation_inventory.csv',inventory)
for p in (ROOT/'processed/trails').glob('*_candidate_paths.geojson'):
 region=p.name.removesuffix('_candidate_paths.geojson');points=[];stats=[]
 for f in json.loads(p.read_text())['features']:
  if f['properties']['osm_type']!='way':continue
  c=f['geometry']['coordinates'];dense=[c[0]]
  for a,b in zip(c,c[1:]):
   length=g.inv(*a,*b)[2];n=max(0,math.ceil(length/60)-1)
   dense.extend(g.npts(*a,*b,n) if n else []);dense.append(b)
  chain=0;zs=[]
  for i,(x,y) in enumerate(dense):
   if i:chain+=g.inv(*dense[i-1],x,y)[2]
   z,s=sample(x,y);zs.append(z)
   points.append(dict(region=region,trail_id=f['id'],point_index=i,latitude=y,longitude=x,chainage_m=chain,elevation_m=z,slope_deg=s))
  valid=[z for z in zs if z is not None];complete=len(valid)==len(zs)
  stats.append(dict(trail_id=f['id'],minimum_elevation_m=min(valid) if valid else None,maximum_elevation_m=max(valid) if valid else None,elevation_gain_m=sum(max(b-a,0) for a,b in zip(zs,zs[1:])) if complete else None,elevation_loss_m=sum(max(a-b,0) for a,b in zip(zs,zs[1:])) if complete else None,profile_complete=complete,sample_spacing_max_m=60,direction='OSM way node order'))
 if points:write_csv(f'processed/elevation/{region}_trail_points.csv',points)
 if stats:write_csv(f'processed/elevation/{region}_trail_summary.csv',stats)
 print(region,len(points),len(stats),flush=True)
for d in tiles:d.close()
