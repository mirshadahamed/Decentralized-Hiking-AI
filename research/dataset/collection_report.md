# Collection report — 2026-10-14

Partial release. No model trained, no random labels, no missing-value fabrication.

## Successfully acquired
* Dated Geofabrik/OpenStreetMap Sri Lanka PBF (2026-10-12), original bytes and matching provider MD5; regional full-way candidate geometry and hiking-relation metadata for all ten AOIs. Region counts: {"adams_peak_candidate_paths.geojson": 253, "ella_candidate_paths.geojson": 582, "haputale_candidate_paths.geojson": 1013, "horton_plains_candidate_paths.geojson": 204, "knuckles_candidate_paths.geojson": 559, "meemure_candidate_paths.geojson": 28, "namunukula_candidate_paths.geojson": 339, "riverston_candidate_paths.geojson": 19, "sigiriya_pidurangala_candidate_paths.geojson": 181, "sinharaja_candidate_paths.geojson": 658}. These counts include overlap and unverified paths, tracks, steps and footways.
* Open-Meteo / ECMWF-Copernicus: 14 original hourly JSON responses, 2021–2025, 613,536 hourly CSV rows. Five points across the provisional Knuckles extent; remaining areas one each. Reanalysis, not field stations. No visibility.
* Copernicus GLO-30: four original regional GeoTIFF tiles via documented AWS mirror, 2021 release, ~30m DSM; 86,058 derived trail-profile rows. DSM slope/gain is approximate.
* OSM support facilities in ten regional extracts and sourced national contacts: 1990 ambulance, 119 police, 117 DMC plus EOC numbers.
* OSM explicitly tagged communication structure nodes: 44 region-assigned features (overlap possible), raw tags retained. This is inventory context, NOT a mobile coverage or signal-strength dataset.
* Department of Meteorology public CAP RSS snapshot: 0 alerts. Feed declares Public Domain. No historical warning archive collected; new service marked provisional.
* Official safety/source link catalogues, resource target structure, label validation methodology, proposed feature origins, reproducible scripts and audit files. No copyrighted safety manuals copied.

## Quality checks
3545 unique candidate OSM IDs; 291 repeated assignments across overlapping area files. No within-file duplicate trail IDs or invalid trail coordinates were found in the current release. All candidate way geometries are LineStrings. Weather files have 43,824 rows each; time continuity, UTC offsets, returned units, range flags and missingness are audited. Terrain has 12 missing heights and 169 missing slopes, preserved as blank. Knuckles difficulty/navigation tags are sparse: {"name": 532, "sac_scale": 558, "surface": 514, "smoothness": 552, "incline": 555, "trail_visibility": 559, "access": 551, "foot": 545}. Missing sac_scale does not mean easy. Checks do not independently verify field accuracy.

## Not acquired / manual actions
Measured mobile coverage and signal strength remain missing. Obtain OpenCelliD token/country export, licensed dated Dialog/Mobitel/regulator layers, or consented field measurements. Tower distance alone cannot prove upcoming loss of connectivity. NBRO/DMC spatial hazard layers require access/licence clarification; PDF references are linked and not numeric training data. Park/ranger contacts, verified potable water/shelters, wildlife guidance and clinically reviewed licensed offline content remain incomplete. Existing user trail file was not attached. Exact official pages and actions are in metadata/manual_acquisition.md.

## Restrictions and limitations
OSM ODbL 1.0, weather CC BY 4.0 (free service non-commercial), Copernicus-specific licence/attribution; no blanket licence. Future OpenCelliD CC BY-SA 4.0 obligations remain separate. Operator and government PDF availability does not establish redistribution permission. Current 2026 OSM is temporally mismatched with 2021–2025 weather; use for explicit retrospective scenario design rather than claiming historical route/coverage observations. AOIs/points provisional; volunteered features may be incomplete, inaccurate, inaccessible or stale. Weather grid dependence and mountain microclimates limit resolution. Gain/loss may be canopy/noise-sensitive. Read metadata/quality_report.json for numeric missingness/duplicates and warnings.

## Next preprocessing and readiness
Review original Knuckles trails, route access, continuity and safe support points with local experts. Deduplicate IDs across Knuckles/Riverston/Meemure. Refine weather samples by validated route/elevation strata without claiming independent nearby weather cells. Assemble hiking route relations and validate DSM-derived ascent. Collect forecast issue times and dated connectivity measurements/layers. Obtain licensed hazard GIS and independent blinded expert resource labels; leave all unavailable fields NULL. Validate connectivity transitions on route segments with operator/technology and freshness recorded.

Sufficient to BEGIN a Knuckles data pipeline and exploratory terrain/weather prototype. NOT sufficient for training or independently evaluating the full context-aware, connectivity-driven recommender. Important data is still missing.
