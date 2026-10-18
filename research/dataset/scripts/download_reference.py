from common import *
init()
fetch('https://was.meteo.gov.lk/cap/en/rss.xml','raw/hazards/meteo_cap_rss.xml','hazards','Department of Meteorology Sri Lanka','Public Domain as declared by downloaded RSS copyright field','Sri Lanka','Current warning snapshot only; not historical absence evidence')
fetch('https://copernicus-dem-30m.s3.amazonaws.com/readme.html','metadata/copernicus_aws_readme.html','elevation documentation','Sinergise / Copernicus','Documentation reference; Copernicus DEM separate licence','Global documentation','2021 release')
fetch('https://download.geofabrik.de/asia/sri-lanka-261012.osm.pbf.md5','raw/trails/sri-lanka-261012.osm.pbf.md5','trails checksum','Geofabrik','ODbL 1.0','Sri Lanka','2026-10-12')
