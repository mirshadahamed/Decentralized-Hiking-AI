# Rock/log object-context data card

This is a separate YOLOv8-compatible detection export. Litter training continues in its frozen L1 run.

| Split | Images | Rock-region boxes | Log-region boxes | Known context-background images |
| --- | ---: | ---: | ---: | ---: |
| train | 6,051 | 569 | 8,933 | 3,311 |
| val | 283 | 3 | 316 | 179 |
| test | 2,133 | 138 | 4,226 | 1,004 |

All 8,467 source image/mask pairs passed current file/pixel hash and exported box checks. Native YOLO train/validation loader counts match the exporter, with no lost boxes. Test files were audited for data integrity; no model test evaluation was performed.

Source: author WildScenes opt2d splits, source IDs 14 rock and 15 log; CC BY-NC-SA 4.0 as recorded in the source certificate. Native connected-region boxes are derived context supervision, not physical object-instance counts or hiking blockage labels.

The 88-image review queue uses training photos only and contains no invented corridor/obstruction judgments. Author validation has just three rock images; independent local obstruction/clear-trail evaluation remains necessary.

The same source photos also appear in the native semantic export. Do not count them twice or merge their unknown litter labels into the garbage head. Raw images, caches, generated overlays and local machine configs remain ignored.

Obstruction training, visible bypasses and app navigation are not ready. See `sajana/docs/OBSTACLES_AND_ROUTE_ADVISORY.md`.
