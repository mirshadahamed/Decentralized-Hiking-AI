# RUGD natural-scene semantic context preparation

RUGD provides source terrain/object semantic segmentation, useful for learning natural trail context. Its classes do not establish erosion, exposed-root damage, a blocked route or hiking safety. Keep it separate from the litter instance dataset and from the final local joint annotations.

## Official sources and exact label preservation

The [official RUGD site](http://rugd.vision/) links the RGB frames and RGB annotation ZIP archives. The converter preserves the annotation archive's original IDs, names and colors: **0 is void; 1–24 are the 24 semantic classes**. Prepared masks are lossless single-channel PNGs containing those integer IDs, not display RGB colors or intensities 0/255. Unknown colors are rejected, never matched to a nearest color. Photos remain at native source resolution and masks are never resized during preprocessing.

`configs/rugd_semantic.yaml` lists the source classes. `data/processed/rugd_semantic/source_colormap.json` preserves every source color. Treat void 0 as an ignored class during training; use nearest-neighbor interpolation for any later mask resizing. Dirt is not mapped to erosion, log is not mapped to obstruction, and container/generic-object is not automatically litter.

## Sequence holdouts and release discrepancy

Sequence membership follows **Table I, page 5** of the [official IROS 2019 paper](http://rugd.vision/pdfs/RUGD_IROS2019.pdf), which was inspected visually:

| Split | Whole source sequences | Current official archive pairs | Paper Table I total |
| --- | --- | ---: | ---: |
| Train | park-2, trail, trail-3, trail-4, trail-6, trail-9, trail-10, trail-11, trail-12, trail-14, trail-15, village | 4,779 | 4,759 |
| Validation | park-8, trail-5 | 733 | 733 |
| Test | creek, park-1, trail-7, trail-13 | 1,924 | 1,964 |
| Total | 18 sequences | 7,436 | 7,456 |

The current official annotation archive contains 7,436 files. Its counts do not match the totals printed in Table I even when the listed sequence membership is preserved. The preparation reports both sets of counts and does not invent frames, omit genuine files or move sequences to conceal the discrepancy. `available_source_complete` refers to the current available release, while `published_count_complete` compares against the printed table. The official source context task can be ready while this publication discrepancy remains documented. It does not certify independent Sri Lankan hiking performance.

## Acquisition and verification

Official downloads can be resumed through exact byte ranges from the same public S3 bucket. Every range must have the correct `Content-Range`, length and source ETag. Completed chunks and SHA256 hashes are cached. Extraction permits photos, masks and label metadata only; it rejects unsafe paths/symlinks and checks every extracted member's ZIP CRC.

The official multi-gigabyte photo transfer was slow during this preparation. `--mirror-frames` offers the [public WilliamBonilla62/RUGD mirror](https://huggingface.co/datasets/WilliamBonilla62/RUGD) as a transport fallback. It pins the mirror commit and requires **every photo's original relative filename, byte length and CRC to match the official ZIP central directory**. The official annotations and colormap remain the source of mask truth. Each acquired file also receives a SHA256 in the source inventory. The mirror is recorded as a mirror; a sparse ZIP index/cache is not described as a downloaded full image archive.

The source trees under `data/raw/rugd/extracted/` remain read-only inputs. Prepared photos use hardlinks where possible; augment copies/in-memory data during training, not these source files. Conversion writes independent semantic masks and source-aware manifests. Full verification rechecks archive inventory hashes, image decoding/geometry/orientation, all source-to-output label pixels, catalog identity, manifest counts/hashes, exact-pixel cross-split duplicates and sequence membership.

Read `results/rugd_preprocessing/local_readiness.json` and `data/processed/rugd_semantic/readiness.json` for the actual current completion state. `data/raw/rugd/download_status.json` and `mirror_progress.json` report acquisition separately; an interrupted transfer is not training readiness.

## Commands from the repository root

```bash
sajana/.venv/bin/python -m pip install -r sajana/requirements_rugd.txt
sajana/.venv/bin/python -B -m sajana.src.data.download_rugd --mirror-frames --workers 24
sajana/.venv/bin/python -B -m sajana.src.data.preprocess_rugd
```

Omit `--mirror-frames` to download the entire official photo ZIP. Repeat the same command to resume matching completed files/ranges. The downloader retries each range/file at most three times and retains matching completed data when other files fail. No account, model training or external application is required.

For a fresh verification only:

```bash
sajana/.venv/bin/python -B -m sajana.src.data.preprocess_rugd --verify-only
```

Inspect `{train,val,test}_overlays.jpg` in `results/rugd_preprocessing/`. The left image is the source RGB; the right blends the source class colors over the photo.

## Source terms

The inspected official page and paper did not state a dataset reuse licence. The homepage's **CC BY 3.0 comment applies to the Colorlib website template**, not the RUGD data. Do not label this dataset CC BY 3.0/4.0 based on the footer or a third-party mirror. Record `license_status: unspecified_in_reviewed_primary_dataset_material`, retain the paper citation, and resolve the data's actual redistribution/commercial terms before a later release.
