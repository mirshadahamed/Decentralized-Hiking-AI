# pLitterStreet detection and Mawanella mapping preparation

pLitter adds street litter detection data and a separate geospatial observation sample. It does not supply trail-damage labels. Its bounding rectangles must not be used as object masks in the TACO/MJU segmentation dataset.

The primary sources are the [official pLitter project](https://github.com/gicait/pLitter) and its [Zenodo release 8288500](https://zenodo.org/records/8288500). Public release metadata, including the CC-BY-4.0 license, is preserved in `data/interim/plitter/zenodo_release_8288500.json`. Original downloaded and supplied files remain unchanged.

## Data order

1. Validate and preserve the supplied Mawanella CSV for mapping.
2. Download the official annotation and image ZIPs and verify their published MD5 checksums.
3. Safely extract JSON and RGB files without executing archive contents.
4. Convert the official four-class bounding boxes into YOLO detection labels and preserve source IDs, dimensions, category IDs, paths and metadata in manifests.
5. Import the exact matching RGB images and verify every source/label relationship, decoded image, image geometry, orientation and decoded-pixel split overlap.

The generated `data/processed/plitter_street_det/data.yaml` is created only after full checks pass. `labels_ready: true` alone does not certify missing photographs or training readiness. The remote image download can be resumed; an incomplete archive is never treated as extracted training data.

## Official detection source

| Split | Original images / boxes | Retained images / boxes |
| --- | ---: | ---: |
| Train | 12,111 / 70,426 | 12,086 / 70,133 |
| Validation | 1,514 / 8,852 | 1,511 / 8,809 |
| Test | 1,513 / 8,782 | 1,508 / 8,719 |
| Total | 15,138 / 88,060 | 15,105 / 87,661 |

The release also supplies an alternative ten-class annotation version covering 13,064 images. Both original annotation versions are preserved, but they describe overlapping source photographs and must not be appended to one another as separate training examples. The four-class version is the canonical prepared detection dataset because it covers more images and preserves bins as a distinct target.

Target classes are `0=plastic_litter`, `1=litter_pile`, `2=face_mask`, and `3=trash_bin`. The conversion excludes 33 whole images containing 64 invalid bounding boxes and 399 total object records. Invalid records include zero-area boxes and coordinates far outside the declared image. Whole-image quarantine avoids turning their surviving unlabeled objects into false background. See `results/plitter_preprocessing/quarantine.json` for every exclusion. Boxes are not broadly clipped or invented.

Official split memberships are preserved. The same source video/city groups occur in multiple splits (173 shared source path groups), so these splits do not establish independent hiking-location or video-sequence evaluation. Keep this data auxiliary and keep the TACO benchmark separate. Full verification also checks exact decoded-pixel duplication across the official pLitter splits and blocks readiness if any is found.

## Mapping sample

`Mawanella_January_2022_Sample.csv` contains 31,489 valid longitude/latitude and plastic/bin count observations at 31,230 coordinates. All source observations are retained with original CSV line numbers; 217 repeated exact observations are flagged. The coordinate aggregate exposes both observation sums and maxima so repeated observations are visible.

The plastic observation sum is 85,484 and the bin observation sum is 58. These are sums of observations, not verified counts of unique physical objects. The CSV has no image/frame identifiers, so it cannot be paired automatically with release photographs or turned into image labels. Longitude/latitude values are retained unchanged; the CSV does not explicitly declare a CRS.

## Commands from the repository root

Use the existing environment with Pillow and requests installed. Do not run two pLitter download processes concurrently against the same directory.

```bash
sajana/.venv/bin/python -B -m sajana.src.data.preprocess_plitter_mawanella

# Resumes the existing contiguous prefix/chunks, then imports and audits images.
sajana/.venv/bin/python -B -m sajana.src.data.download_plitter \
  --workers 12 --preprocess-after-download

# Run after the downloaded images have been extracted successfully.
sajana/.venv/bin/python -B -m sajana.src.data.preprocess_plitter \
  --prepare-images --verify

# Label audit before images arrive. This never sets training_ready=true.
sajana/.venv/bin/python -B -m sajana.src.data.preprocess_plitter \
  --verify --labels-only

sajana/.venv/bin/python -B -m unittest sajana.tests.test_plitter_preprocessing -v
```

The public release archive checksums and sizes are:

| Archive | Bytes | Published MD5 |
| --- | ---: | --- |
| annotations.zip | 8,764,662 | `2484e076b1e9d66036b0a15e9928692f` |
| images.zip | 13,728,630,001 | `02382a3b9620ae7b086ff4c7fd11891d` |

The image archive is large and the source server may be slow. Valid byte-range response headers are required before appending data. Range checkpoints and the original partial prefix remain under `data/raw/plitter/` until a fully assembled archive matches the release checksum. Downloads default to four workers and permit at most twelve, with bounded retries and backoff when the server returns HTTP 429. An OS file lock prevents two range downloaders from writing the same checkpoint directory. Raw archives and photographs remain local under the repository's raw-data ignore rules.

To pause, press Ctrl+C once or create `data/raw/plitter/plitter_pause_requested`. Active workers preserve their partial chunks and stop after their current bounded network read. Remove that pause file before resuming. `--max-chunks N` limits a run to N newly acquired chunks without discarding previous downloads; an intentional incomplete pause exits with status 75. `data/raw/plitter/plitter_download_progress.json` records live byte counts. These pause/resume controls do not certify an incomplete archive or dataset as ready.

## Reports

- `results/plitter_preprocessing/mawanella_audit.json`: observation validity, source hash and mapping limitations.
- `results/plitter_preprocessing/labels_readiness.json`: source hashes, detection conversion, counts and exclusions.
- `results/plitter_preprocessing/quarantine.json`: all invalid source records and whole-image exclusions.
- `results/plitter_preprocessing/image_import_report.json`: photo pairing, geometry and orientation import issues, after import runs.
- `results/plitter_preprocessing/local_readiness.json`: complete label and image audit; consult `training_ready` and `missing_images`.
- `data/raw/plitter/download_status.json`: archive checksums, extraction state and download errors. During an active download, `.part` and `.ranges` files hold the current progress.

Inspect actual bounding-box overlays once photographs become available before training a detector. Native boxes may support detector pretraining; they do not replace local hiking photographs with litter masks, damage masks or measured passability.
