"""Prepare the supplied TACO sources without downloading or editing originals.

The official batch benchmark is kept separate from an optional unofficial
train-only pool. Invalid unofficial images are quarantined as whole images so
their surviving objects cannot become incomplete training targets.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .preprocess_taco import SPLITS, _indexed, _integer, _polygon, _records, choose_split, preprocess
from .verify_taco_ready import verify

ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _read_source(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"COCO source must be an object: {path}")
    images = _indexed(_records(value, "images"), "image")
    categories = _indexed(_records(value, "categories"), "category")
    if not images or not categories:
        raise ValueError(f"Source must contain images and categories: {path}")
    for index, ann in enumerate(_records(value, "annotations")):
        _integer(ann.get("id"), f"Annotation {index} id")
        image_id = _integer(ann.get("image_id"), f"Annotation {index} image_id")
        category_id = _integer(ann.get("category_id"), f"Annotation {index} category_id")
        if image_id not in images or category_id not in categories:
            raise ValueError(f"Annotation {index} references an unknown image or category")
    return value, hashlib.sha256(raw).hexdigest()


def _baseline_images(dataset: Path, source: dict) -> dict[int, tuple[str, Path]]:
    images = {image["id"]: image for image in source["images"]}
    paths = {}
    for split in SPLITS:
        with (dataset / "manifests" / f"{split}.csv").open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                image_id = int(row["image_id"])
                image = images.get(image_id)
                name = row["flat_file_name"]
                if image is None or image_id in paths:
                    raise ValueError(f"Baseline manifest contains unknown/duplicate image {image_id}")
                expected = f"{Path(image['file_name']).parts[0]}__{Path(image['file_name']).stem}.jpg"
                if (name != expected or row["source_file_name"] != image["file_name"]
                        or choose_split(image["file_name"]) != split):
                    raise ValueError(f"Baseline manifest differs from source for image {image_id}")
                path = dataset / "images" / split / name
                if not path.is_file():
                    raise FileNotFoundError(f"Required supplied official image is missing: {path}")
                paths[image_id] = (split, path)
    if set(paths) != set(images):
        raise ValueError("Baseline manifests do not cover every source image")
    return paths


def _derived_source(source: dict, source_path: Path, source_sha256: str,
                    removed: set[int], operation: str) -> dict:
    derived = copy.deepcopy(source)
    derived["images"] = [dict(image, raw_source_image_index=index)
                         for index, image in enumerate(source["images"]) if image["id"] not in removed]
    derived["annotations"] = [dict(ann, raw_source_annotation_index=index)
                              for index, ann in enumerate(source["annotations"]) if ann["image_id"] not in removed]
    if "scene_annotations" in source:
        derived["scene_annotations"] = [scene for scene in derived["scene_annotations"]
                                         if scene["image_id"] not in removed]
    derived["preprocessing_provenance"] = {
        "raw_source": str(source_path.resolve()), "raw_source_sha256": source_sha256,
        "operation": operation, "excluded_image_ids": sorted(removed),
        "annotation_index_field": "raw_source_annotation_index",
        "image_index_field": "raw_source_image_index",
        "source_unchanged": True,
    }
    return derived


def _clean_official(source: dict, source_path: Path, source_hash: str,
                    paths: dict[int, tuple[str, Path]]) -> tuple[dict, dict]:
    objects = Counter(ann["image_id"] for ann in source["annotations"])
    groups: dict[str, list[int]] = defaultdict(list)
    for image in source["images"]:
        groups[_sha256(paths[image["id"]][1])].append(image["id"])
    removed, exclusions = set(), []
    for digest, ids in groups.items():
        if len(ids) < 2:
            continue
        if len({paths[image_id][0] for image_id in ids}) > 1:
            raise ValueError(f"Identical image bytes occur across official splits: {sorted(ids)}; review source before preparing")
        kept_id = min(ids, key=lambda image_id: (-objects[image_id], image_id))
        for image_id in sorted(set(ids) - {kept_id}):
            removed.add(image_id)
            excluded_anns = [{"annotation_id": ann["id"], "raw_source_annotation_index": index}
                             for index, ann in enumerate(source["annotations"]) if ann["image_id"] == image_id]
            exclusions.append({"image_id": image_id, "kept_image_id": kept_id,
                               "source_file": str(paths[image_id][1]), "kept_file": str(paths[kept_id][1]),
                               "split": paths[image_id][0], "image_sha256": digest,
                               "removed_annotations": excluded_anns,
                               "reason": "Identical image bytes within one split; retained the image record with most annotations, then lowest ID."})
    derived = _derived_source(source, source_path, source_hash, removed, "within-split exact-byte image deduplication")
    report = {"source": str(source_path), "source_sha256": source_hash,
              "source_images": len(source["images"]), "source_annotations": len(source["annotations"]),
              "excluded_image_ids": sorted(removed), "excluded_images": len(removed),
              "excluded_annotations": sum(objects[image_id] for image_id in removed),
              "retained_images": len(derived["images"]), "retained_annotations": len(derived["annotations"]),
              "exclusions": exclusions, "originals_preserved": True}
    return derived, report


def _quarantine_unofficial(source: dict, source_path: Path, source_hash: str) -> tuple[dict, dict]:
    images = {image["id"]: image for image in source["images"]}
    invalid: dict[int, list[dict]] = defaultdict(list)
    for index, ann in enumerate(source["annotations"]):
        image = images[ann["image_id"]]
        width = _integer(image.get("width"), f"Image {image['id']} width", 1)
        height = _integer(image.get("height"), f"Image {image['id']} height", 1)
        reasons = []
        segments = ann.get("segmentation")
        if ann.get("iscrowd", 0) not in (0, False):
            reasons.append("Crowd/RLE masks are unsupported; polygon annotations required")
        if not isinstance(segments, list) or not segments:
            reasons.append("segmentation must be a nonempty list of polygons (RLE unsupported)")
        else:
            for polygon_index, raw in enumerate(segments):
                try:
                    _polygon(raw, width, height, f"Annotation {ann['id']}, polygon {polygon_index}")
                except ValueError as exc:
                    reasons.append(str(exc))
        if reasons:
            invalid[image["id"]].append({"annotation_id": ann["id"], "raw_source_annotation_index": index,
                                          "reasons": reasons})
    removed = set(invalid)
    derived = _derived_source(source, source_path, source_hash, removed, "whole-image quarantine for invalid polygon annotations")
    quarantines = []
    for image_id in sorted(removed):
        excluded_anns = [{"annotation_id": ann["id"], "raw_source_annotation_index": index}
                         for index, ann in enumerate(source["annotations"]) if ann["image_id"] == image_id]
        quarantines.append({"image_id": image_id, "source_file_name": images[image_id]["file_name"],
                            "invalid_annotations": invalid[image_id], "excluded_annotations": excluded_anns,
                            "reason": "Whole image excluded to avoid incomplete segmentation targets; source needs annotation review."})
    report = {"source": str(source_path), "source_sha256": source_hash,
              "source_images": len(source["images"]), "source_annotations": len(source["annotations"]),
              "quarantined_image_ids": sorted(removed), "quarantined_images": len(removed),
              "invalid_annotations": sum(map(len, invalid.values())),
              "quarantined_annotations": sum(len(row["excluded_annotations"]) for row in quarantines),
              "retained_images": len(derived["images"]), "retained_annotations": len(derived["annotations"]),
              "policy": "Whole image quarantined if any annotation fails existing strict polygon validation; no broad clipping.",
              "quarantines": quarantines, "originals_preserved": True}
    return derived, report


def _populate_official_images(cleaned: dict, paths: dict[int, tuple[str, Path]], out: Path) -> dict:
    counts = Counter()
    for image in cleaned["images"]:
        split, source = paths[image["id"]]
        target = out / "images" / split / source.name
        if target.exists():
            if _sha256(target) != _sha256(source):
                raise ValueError(f"Existing prepared image differs from supplied baseline: {target}")
            counts["existing"] += 1
            continue
        try:
            os.link(source, target)
            counts["hardlinked"] += 1
        except OSError:
            shutil.copy2(source, target)
            counts["copied"] += 1
    return dict(counts)


def prepare(component_root: Path = ROOT, verify_images: bool = True) -> dict:
    """Prepare both supplied sources; full official image verification is default."""
    root = Path(component_root).resolve()
    interim = root / "data/interim/taco"
    official_path = interim / "annotations_official_binary_litter.json"
    unofficial_path = interim / "annotations_unofficial_binary_litter.json"
    official, official_hash = _read_source(official_path)
    unofficial, unofficial_hash = _read_source(unofficial_path)
    paths = _baseline_images(root / "data/processed/taco_litter_seg", official)
    official_cleaned, exclusions = _clean_official(official, official_path, official_hash, paths)
    unofficial_validated, quarantine = _quarantine_unofficial(unofficial, unofficial_path, unofficial_hash)
    official_derived_path = interim / "annotations_official_cleaned.json"
    unofficial_derived_path = interim / "annotations_unofficial_validated.json"
    official_out = root / "data/processed/taco_litter_seg_clean"
    unofficial_out = root / "data/processed/taco_unofficial_litter_seg"
    results = root / "results/taco_preprocessing"
    _write_json(official_derived_path, official_cleaned)
    _write_json(unofficial_derived_path, unofficial_validated)
    _write_json(results / "official_exclusions.json", exclusions)
    _write_json(results / "unofficial_quarantine.json", quarantine)
    official_conversion = preprocess(official_derived_path, official_out)
    image_import = _populate_official_images(official_cleaned, paths, official_out)
    unofficial_conversion = preprocess(unofficial_derived_path, unofficial_out, split_policy="train_only")
    official_audit = verify(official_out, labels_only=not verify_images, annotations=official_derived_path)
    unofficial_audit = verify(unofficial_out, labels_only=True, annotations=unofficial_derived_path, split_policy="train_only")
    _write_json(results / "official_clean_readiness.json", official_audit)
    _write_json(results / "unofficial_labels_audit.json", unofficial_audit)
    # Protect immutable inputs even when another process edits them mid-run.
    if _sha256(official_path) != official_hash or _sha256(unofficial_path) != unofficial_hash:
        raise ValueError("Source annotation files changed during preparation; review and rerun")
    passed = official_audit["passed"] and unofficial_audit["passed"]
    all_images_present = all(split["missing_images"] == 0
                             for audit in (official_audit, unofficial_audit) for split in audit["splits"].values())
    status = {
        "passed": passed, "preprocessing_complete": passed,
        "all_prepared_images_present": all_images_present,
        "official": {"dataset": str(official_out), "source": str(official_derived_path),
                     "images": official_conversion["images_total"], "annotations": official_conversion["annotations_total"],
                     "training_ready": official_audit["training_ready"], "verification": official_audit,
                     "excluded_images": exclusions["excluded_images"], "excluded_annotations": exclusions["excluded_annotations"],
                     "image_import": image_import},
        "unofficial": {"dataset": str(unofficial_out), "source": str(unofficial_derived_path),
                       "images": unofficial_conversion["images_total"], "annotations": unofficial_conversion["annotations_total"],
                       "training_ready": unofficial_audit["training_ready"], "training_pool_ready": unofficial_audit.get("training_pool_ready", False),
                       "labels_only": True,
                       "verification": unofficial_audit, "role": "optional train-only pool; never an evaluation benchmark",
                       "quarantined_images": quarantine["quarantined_images"], "quarantined_annotations": quarantine["quarantined_annotations"]},
        "raw_sources": {str(official_path): official_hash, str(unofficial_path): unofficial_hash},
        "originals_preserved": True, "network_used": False,
        "component_scope": "Litter instance segmentation only. Trail-damage/path masks and local paired annotations are still required for the full component.",
    }
    _write_json(results / "supplied_preprocessing_status.json", status)
    register = io.StringIO(newline="")
    writer = csv.DictWriter(register, fieldnames=("dataset", "role", "raw_source", "raw_source_sha256", "split_policy",
                                                "class_mapping", "images", "annotations", "label_files", "present_images",
                                                "missing_images", "training_ready", "training_pool_ready", "path"))
    writer.writeheader()
    for key, role in (("official", "official batch benchmark, exact within-split duplicates removed"),
                      ("unofficial", "optional train-only pool, invalid images quarantined")):
        entry = status[key]
        raw_source = official_path if key == "official" else unofficial_path
        splits = entry["verification"]["splits"].values()
        writer.writerow({"dataset": key, "role": role, "raw_source": str(raw_source),
                         "raw_source_sha256": official_hash if key == "official" else unofficial_hash,
                         "split_policy": "official_batches" if key == "official" else "train_only",
                         "class_mapping": "all original categories -> litter", "images": entry["images"], "annotations": entry["annotations"],
                         "label_files": sum(split["present_labels"] for split in splits),
                         "present_images": sum(split["present_images"] for split in splits),
                         "missing_images": sum(split["missing_images"] for split in splits),
                         "training_ready": entry["training_ready"], "training_pool_ready": entry.get("training_pool_ready", False), "path": entry["dataset"]})
    (results / "supplied_dataset_register.csv").write_text(register.getvalue(), encoding="utf-8")
    mju_report = root / "results/mju_preprocessing/local_readiness.json"
    if mju_report.is_file():
        from .preprocess_mju_waste import refresh_component_status
        status = refresh_component_status(json.loads(mju_report.read_text()), root) or status
    orfd_report = root / "results/orfd_preprocessing/local_readiness.json"
    if orfd_report.is_file():
        status["orfd"] = json.loads(orfd_report.read_text())
        from .preprocess_orfd_rgb import refresh_component_status as refresh_orfd_status
        refresh_orfd_status(status["orfd"], root)
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component-root", type=Path, default=ROOT)
    parser.add_argument("--labels-only", action="store_true", help="Skip official image decoding; does not certify training readiness")
    args = parser.parse_args()
    try:
        status = prepare(args.component_root, verify_images=not args.labels_only)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Supplied TACO preprocessing failed: {exc}\n")
    print(json.dumps({key: {field: status[key][field] for field in ("images", "annotations", "training_ready")}
                      for key in ("official", "unofficial")}, indent=2))
    if not status["passed"]:
        parser.exit(1, "One or more dataset audits failed; inspect supplied_preprocessing_status.json.\n")


if __name__ == "__main__":
    main()
