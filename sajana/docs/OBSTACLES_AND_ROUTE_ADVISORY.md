# Garbage, obstacle objects and alternative paths

The active L1 YOLOv8n-seg run learns garbage/litter. A separate WildScenes-derived detection export supplies rock/log **region boxes** for an object-context experiment. Neither source supplies reviewed hiking blockage, a clear walking corridor or a usable bypass.

## Data now available

Run the context exporter with the YOLO environment, which includes OpenCV:

```bash
sajana/.venv-yolov8/bin/python -B -m sajana.src.data.prepare_obstacle_context
```

The output is `data/processed/wildscenes_rock_log_detection/`, with source-preserving image links, normalized YOLO detection labels, split manifests, a training-only review queue and a readiness report. The run summary is copied to `results/obstacle_context/readiness.json`. Use its generated absolute `data.yaml` for a later detector run; [obstacle_objects.yaml](../configs/obstacle_objects.yaml) documents the portable mapping.

Native WildScenes rock ID 14 maps to detector class 0 `rock_region`; log ID 15 maps to detector class 1 `log_region`. Connected semantic pixels can join multiple physical objects or split one occluded object. The derived boxes are context supervision, not physical-instance or trail-obstruction ground truth. All components, including tiny positives, are retained. Identical same-class boxes are deduplicated. A source image containing unlabelled/void pixels is rejected rather than turning unknown pixels into YOLO negatives.

The exporter checks current photo file hashes and native mask pixel hashes against the verified source manifests, validates author split identities, checks cross-split exact duplicates, and rereads saved box geometry. Author train/validation/test membership stays unchanged. The original validation set has only three rock images and no water/fence examples; do not claim strong rock/blockage evaluation from it. No held-out test model evaluation occurs during export.

Keep this task separate from garbage training: detector class 0 means `rock_region`, while litter-segmentation class 0 means `litter`. WildScenes images have no exhaustive litter review. Do not naively merge them into a single multiclass YOLO folder. Its [official source](https://github.com/csiro-robotics/WildScenes) describes semantic scene labels; the local source report records CC BY-NC-SA 4.0 for this data.

## Ground truth still needed

Use `review_queue.csv` to inspect source training photos for draft corridor/blockage annotations. Selection uses object-class presence and source sequence; even a sample with no rock/log labels is **unreviewed**, not a clear trail. Review all intended classes before producing joint labels. Public source photos do not replace independent local hiking evaluation.

The local templates remain header-only until real reviews exist:

- `obstruction_review.csv`: reference the actual object and corridor polygons, then review `on_trail`, `beside_trail` or `unknown`, plus clear/restricted/blocked/uncertain evidence.
- `visible_bypass_review.csv`: reference actual candidate polygons and review whether they remain on and rejoin the marked trail; retain uncertain surface/clearance judgments. Image pixel gaps do not establish physical walking clearance.

Roots, erosion, major branches and rubble remain separate reviewed annotation targets. A natural log or rock appearing beside the trail is not automatically an obstruction. Garbage may occur with a clear trail or together with a blockage.

## Marked-trail alternative prototype

[route_advisory.py](../src/route_advisory.py) is a tested planning function and CLI. It consumes a supplied map graph and reviewed, located blockage observations. It does not run a vision model, match GPS to an edge, acquire a real map or issue turn-by-turn navigation.

```bash
sajana/.venv/bin/python -B -m sajana.src.route_advisory \
  --input sajana/configs/templates/route_advisory_request.json
```

The empty template returns `insufficient_route_context`. To obtain a candidate, supply:

1. A versioned `graph_id` and `source_reference`; string node IDs with finite `lat`/`lon`; edges with string IDs, `from`, `to`, positive `length_m`, explicit `permitted: true`, `geometry_reviewed: true`, actual `geometry` coordinate lists oriented from source node to destination node, and optional `bidirectional: true`. Missing/mismatched geometry is excluded. Returned polylines preserve the supplied trail curves instead of drawing straight shortcuts between junctions.
2. Current map-matched start/destination node IDs and an ordered, connected `current_route` edge list.
3. Current observations with `observation_id`, stable `hazard_id`, reviewed `edge_id` match, `review_state: reviewed`, `reviewer_id`, timezone-qualified `reviewed_at` and `expires_at`, `route_relation: on_trail` and `blockage: blocked`.

The planner excludes confirmed blocked edges and edges with unresolved observations, respects directions/access permissions, and finds a connected minimum-distance marked route. A newer reviewed clear judgment replaces an older blocked judgment for the same hazard; it does not clear other hazards. A garbage prediction alone, an object beside the trail, expired evidence, missing location or disconnected graph never establishes a detour. No mapped route produces `no_mapped_alternative`; missing evidence produces a review/missing-context state. The result is a **candidate** requiring a check of current conditions, with source, edge IDs and evidence references retained.

Visible left/right bypass suggestions require a reviewed corridor, surfaces and clearance data; the prototype returns this feature as pending. It never draws an invented path through vegetation or private/unmapped terrain. A verified local graph, live location/matching, obstruction model and app integration remain required.

## Work and commit order

Commit tested dataset preparation, verified data records and route logic as separate meaningful milestones. Keep raw photos, source downloads, model weights, derived overlays, caches and live progress logs ignored. Do not interrupt or change the frozen running litter experiment to add new classes. Train object context as a separate recorded experiment after its full export passes; deploy blockage/routing only after the missing local review and evaluation are completed.
