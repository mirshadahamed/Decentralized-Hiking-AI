# Collection report

Standalone collection completed 2026-10-18. No existing project folder was accessed during this collection. No Git commands were used.

- Accepted authoritative sources: 17
- Downloaded original files: 11
- URL-only sources: 6

## Coverage

Counts overlap because one canonical document can cover several categories. URL-only sources are excluded from the downloaded column.

| Category | Accepted | Downloaded |
|---|---:|---:|
| general_first_aid | 3 | 2 |
| hypothermia | 4 | 2 |
| heat_illness | 4 | 2 |
| heavy_rain | 2 | 2 |
| strong_wind | 2 | 2 |
| water_safety | 4 | 3 |
| remote_emergency | 4 | 3 |

## Organizations

- IFRC
- CDC, including NIOSH and the Yellow Book
- NOAA National Weather Service
- US National Park Service
- Disaster Management Centre Sri Lanka (URL-only)
- St John Ambulance (URL-only)
- NHS (England)
- US Environmental Protection Agency

## URL-only entries

- SRC_002 - Preventing Hypothermia: URL-only: could not verify robots policy: HTTP 403
- SRC_003 - Heat-related Illnesses: URL-only: could not verify robots policy: HTTP 403
- SRC_004 - About Water Treatment Options When Hiking, Camping, or Traveling: URL-only: could not verify robots policy: HTTP 403
- SRC_011 - National Emergency Operational Centre (EOC): URL-only: could not verify robots policy: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1010)>
- SRC_012 - How to Do the Primary Survey (DR ABCDE): URL-only: copyrighted advice; reuse permission not established.
- SRC_013 - Heat and Cold Illness in Travelers: URL-only: could not verify robots policy: HTTP 403

## Rejected candidates and reasons

- DMC training-material index: https://www.dmc.gov.lk/index.php?Itemid=217&id=52&lang=en&option=com_content&view=article - navigation/index rather than a retrieved safety document; cyclone/flood labels did not expose direct document links in the inspected page.
- NBRO historical landslide warning: https://www.nbro.gov.lk/images/Amber210520180800.pdf - expired incident bulletin; unsuitable as timeless offline guidance.
- DMC/NBRO warning issued 2026-02-16: https://www.dmc.gov.lk/images/dmcreports/Landslide_EW_Report_at_0900hrs_on_2026__1771215166.pdf - expired warning, despite containing general awareness text.
- DMC National Disaster Management Plan draft: https://www.dmc.gov.lk/images/pdfs/NDMP_DRAFT_VERSION_17-03-2022.pdf - draft strategic policy, limited direct hiking-safety value.
- CDC 2017 heat poster: https://www.cdc.gov/extreme-heat/media/pdf/Heat_Related_Illness.pdf - older and substantively overlapping current selected heat guidance; no redundant download.
- NHS first-aid index: https://www.nhs.uk/conditions/first-aid/ - redirects to St John advice index; no duplicate catalog record.
- Search results from Reddit, Wikipedia, Scribd, commercial news/blogs and unverified sites were excluded as source material. They were not downloaded.

## Validation and duplicate checks

- All 11 local source files reopened successfully; nonzero sizes, original response SHA-256 hashes and media-type checks recorded in SOURCES.md.
- The single PDF has a valid PDF signature, 594 parseable pages and extractable text. Page 2 was rendered and visually checked. No HTML error page was renamed as PDF.
- All HTML pages parsed, contain substantial text, and have the expected document heading; no access-denied/error response was retained.
- Every downloaded document has exactly one catalog record and an existing relative local_path. All accepted entries have an official HTTPS URL and identified organization.
- SHA-256 exact duplicate count: 0. Normalized eight-word shingle comparisons found no pair at or above 0.85 Jaccard similarity. Highest pair: (0.261, 'SRC_006', 'SRC_008'). This automated screen complements title/scope review; it is not proof of semantic uniqueness.
- Flood/lightning and before/during wind pages were reviewed as complementary. IFRC is stored once despite five category assignments.
- All seven category directories exist, and every category has useful downloaded authoritative coverage via catalog cross-references. Hypothermia/heat/water folders contain their specialized originals; IFRC remains in general_first_aid.
- ZIP integrity and its members are verified after packaging.

## Weak coverage and missing information

- Strong wind has two official general safety pages, but lacks a specialized exposed-ridge/mountain wind source.
- Heavy rain has two downloaded NWS pages, but no accepted evergreen Sri Lankan landslide safety leaflet.
- Sri Lankan emergency context is URL-only because TLS certificate verification failed. No TLS checks or access restrictions were bypassed. Local rescue procedures and current contact details still need confirmation.
- CDC guidance is verified online but absent offline because the collection agent could not verify its robots policy (HTTP 403). Its links are retained without fabricated files.
- NHS hypothermia has an overdue clinical review date; the more recent IFRC reference is also present.
- Publication dates are unavailable for some sources; no inferred date has been invented. HTML metadata creation/modification is distinguished from clinical review.
- No Sinhala/Tamil source document was accepted. This collection is English only.
- Source selection and file integrity do not constitute clinical validation or permission for all future distribution. IFRC permits noncommercial attributed copying; NHS has OGL conditions; St John needs permission.
- This package contains no chunks, embeddings, SQLite database, model/LLM implementation, Flutter files or generated safety advice.

## Complete created package file list

- SOURCES.md
- collection_report.md
- source_catalog.csv
- source_documents/general_first_aid/ifrc_first_aid_guidelines_2025.pdf
- source_documents/general_first_aid/nhs_cuts_grazes.html
- source_documents/heat_illness/nhs_heat_exhaustion_heatstroke.html
- source_documents/heavy_rain/nws_during_a_flood.html
- source_documents/heavy_rain/nws_lightning_safety.html
- source_documents/hypothermia/nhs_hypothermia.html
- source_documents/remote_emergency/nps_outdoor_emergency_plan.html
- source_documents/remote_emergency/nps_ten_essentials.html
- source_documents/strong_wind/nws_before_high_wind.html
- source_documents/strong_wind/nws_during_high_wind.html
- source_documents/water_safety/epa_emergency_water_disinfection.html

Category directories created:
- source_documents/general_first_aid/
- source_documents/hypothermia/
- source_documents/heat_illness/
- source_documents/heavy_rain/
- source_documents/strong_wind/
- source_documents/water_safety/
- source_documents/remote_emergency/

Archive created alongside the folder: offline_rag_authoritative_sources.zip. Collection scripts and render previews remain outside the ZIP in work/.
