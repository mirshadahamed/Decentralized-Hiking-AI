# Local trail annotation workspace

No local trail photographs or annotations have been supplied. The CSVs contain headers only; empty directories are intentional. Follow [the component dataset plan](../../docs/COMPONENT2_DATASET_PLAN.md) before adding real records.

- `images/`: genuine original trail photographs; preserve source files and SHA256.
- `annotations/`: original, versioned annotation-tool exports with native image geometry.
- `review/`: separate reviewer exports and adjudication/uncertainty records.
- `image_manifest.csv`: one row per real image, immutable IDs, provenance, capture/group metadata and review status.
- `class_coverage.csv`: one row per image/class review; missing means unknown, not absent.
- `passability_review.csv`: independently reviewed visible passability judgments; no automatic labels from freespace.

Set split membership to `unassigned` until complete site/route/session/sequence/duplicate groups can be assigned together. Actual final local training, validation and test sets do not exist yet. These templates must not be passed directly to model training.

Large images, masks and annotation payloads should remain local; commit only intentionally shareable non-sensitive metadata under project policy. Keep consent/permission records outside public data manifests and reference them by an opaque ID.
