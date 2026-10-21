# WildScenes 2D preprocessing

WildScenes provides auxiliary terrain and object semantic segmentation for natural outdoor scenes. Dirt, mud, water, gravel, rocks and logs can support scene context for Component 2. The original annotations describe object and terrain classes; hiking passability and trail damage still require the component's own labelled examples.

The official CSIRO release has **9,306 RGB images**. The authors' `opt2d` split CSVs select **8,467 pairs**: 6,051 training, 283 validation and 2,133 testing. The remaining **839 images are unassigned by those CSVs**, rather than missing downloads. The complete selected RGB/index-label download is **44,887,369,710 bytes (41.8 GiB)**. The source inventory records those exclusions explicitly.

The acquisition uses the public CSIRO S3 connection endpoint. CSIRO issues temporary read credentials without an account for this public collection. The script keeps credentials in process memory and excludes them from reports. Previously inspected temporary connection metadata remains under the ignored raw-data directory. The acquisition selects RGB PNGs and indexed semantic masks; it does not fetch point clouds or colour-only annotation visualizations.

Official source links:

- [WildScenes dataset](https://data.csiro.au/collection/csiro:61541)
- [Author repository and download instructions](https://github.com/csiro-robotics/WildScenes)
- [Pinned source revision used for split definitions and classes](https://github.com/csiro-robotics/WildScenes/tree/9eb4e10b4483a634159e2b371be0437e465fe218)

The dataset licence is **CC BY-NC-SA 4.0**. Preserve attribution and the source licence when reusing its data.

## Run from the repository root

```bash
# Small metadata request: show the exact source inventory and download size.
sajana/.venv/bin/python -B -m sajana.src.data.download_wildscenes --inventory-only

# Resume verified RGB/mask acquisition with at most six parallel objects.
sajana/.venv/bin/python -B -u -m sajana.src.data.download_wildscenes --workers 6

# Convert and then fully verify all official selected pairs.
sajana/.venv/bin/python -B -u -m sajana.src.data.preprocess_wildscenes --workers 4 --preview

# Recheck existing preprocessed files against retained source files.
sajana/.venv/bin/python -B -u -m sajana.src.data.preprocess_wildscenes --verify-only
```

Use `--max-files 100` for a bounded download batch. An incomplete batch exits with a nonzero status and keeps a truthful incomplete report. Rerunning the acquisition verifies and reuses complete objects and resumes `.part` files by HTTP byte range. MD5 ETags verify the public S3 objects. If credentials expire, resume the command to request fresh public credentials. An interrupted or incomplete download cannot become a training-ready dataset.

## Data preparation

Raw source files stay at `sajana/data/raw/wildscenes/source/WildScenes2d`. Official CSVs and class definitions are retained in `official_metadata`. Generated data is under `sajana/data/processed/wildscenes_terrain_semantic`:

- `images/{train,val,test}` preserves RGB pixels using local hardlinks when available.
- `masks/{train,val,test}` contains single-channel PNGs with original semantic IDs **0–18**. Class **0** is unlabelled and must be ignored by the loss function.
- `manifests/{train,val,test}.csv` retains author IDs, sequences, source paths, dimensions and file/pixel checksums.
- `class_mapping.json` retains the source palette and semantic ID names.
- `conversion_report.json` records conversion evidence and source metadata hashes.

The conversion retains all native classes. It does not apply the authors' optional benchmark class merges. Indexed PNG pixels are read as class IDs; converting their colours to grayscale would change their meaning. There is no resizing, interpolation, crop, random resplit or augmentation in these prepared files. Training-time augmentation must apply the same geometry to images and masks and use nearest-neighbour interpolation for masks.

`results/wildscenes_preprocessing/local_readiness.json` certifies the exact official split coverage only after complete image decoding, source-to-mask pixel comparison, source checksum validation, manifest checks and an exact RGB duplicate check across splits. `overlays.jpg` shows representative RGB images and label overlays after verification. The generated `data.yaml` and checked-in `configs/wildscenes_terrain.yaml` describe a semantic segmentation dataset for a semantic mask trainer.
