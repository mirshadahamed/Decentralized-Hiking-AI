from common import *
init()
# Four one-degree regional tiles cover all provisional AOIs.
for lat,lon in [(6,80),(6,81),(7,80),(7,81)]:
 name=f'Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM'
 fetch(f'https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif',f'raw/elevation/{name}.tif','elevation','Copernicus Programme; Airbus; AWS/Sinergise mirror','Copernicus DEM GLO-30 licence (not CC BY)',f'{lat}–{lat+1} N; {lon}–{lon+1} E','2021 release; source acquisition generally 2011–2015')
