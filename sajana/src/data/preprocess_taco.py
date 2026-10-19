"""Convert TACO COCO polygons to one-class YOLO segmentation labels.

Only Python's standard library is required. Source annotations are never edited;
resizing and augmentation belong to training. Multipart objects remain one object
by joining contours with a zero-area, doubled bridge between nearest vertices.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANNOTATIONS = COMPONENT_ROOT / "data/interim/taco/annotations_official_binary_litter.json"
DEFAULT_OUT = COMPONENT_ROOT / "data/processed/taco_litter_seg"
TRAIN_BATCHES = {"batch_1", "batch_2", "batch_5", "batch_6", "batch_7", "batch_8", "batch_9", "batch_10", "batch_12", "batch_13"}
VAL_BATCHES = {"batch_3", "batch_4", "batch_11"}
TEST_BATCHES = {"batch_14", "batch_15"}
SPLITS = ("train", "val", "test")
SPLIT_POLICIES = ("official_batches", "train_only")
MANIFEST_FIELDS = (
    "image_id", "batch", "source_file_name", "flat_file_name", "width", "height",
    "object_count", "scene_ids", "scene_names", "natural_focus", "flickr_url",
    "flickr_640_url", "license", "annotation_ids", "original_category_ids",
    "source_annotation_indices", "date_captured", "coco_url",
)
# A few official TACO polygons contain -1 at an image edge. Account for this
# known one-pixel annotation overshoot explicitly; do not hide larger errors.
BOUNDARY_TOLERANCE_PIXELS = 1.0
Point = tuple[float, float]


def choose_split(file_name: str, split_policy: str = "official_batches") -> str:
    if split_policy not in SPLIT_POLICIES:
        raise ValueError(f"Unknown split policy: {split_policy!r}; expected one of {SPLIT_POLICIES}")
    if split_policy == "train_only":
        return "train"
    batch = file_name.split("/")[0]
    if batch in TRAIN_BATCHES:
        return "train"
    if batch in VAL_BATCHES:
        return "val"
    if batch in TEST_BATCHES:
        return "test"
    raise ValueError(f"Unexpected TACO batch: {batch}")


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}; got {value!r}")
    return value


def _records(coco: dict[str, Any], key: str, *, required: bool = True) -> list[dict[str, Any]]:
    value = coco.get(key, None if required else [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{key} must be a list of objects")
    return value


def _indexed(records: list[dict[str, Any]], label: str) -> dict[int, dict[str, Any]]:
    result = {}
    for record in records:
        record_id = _integer(record.get("id"), f"{label} id")
        if record_id in result:
            raise ValueError(f"Duplicate {label} id: {record_id}")
        result[record_id] = record
    return result


def _signed_area(points: list[Point]) -> float:
    return sum(x * by - y * bx for (x, y), (bx, by) in zip(points, points[1:] + points[:1])) / 2


def merge_polygons(polygons: list[list[Point]]) -> list[Point]:
    """Join contours without filling the gap between them.

    Both endpoints of each bridge are repeated, so a rasterizer traverses the
    bridge in both directions. This is the usual YOLO multipart approximation;
    the original COCO contours remain available in the immutable source JSON.
    """
    merged = list(polygons[0])
    winding = _signed_area(merged)
    for contour in polygons[1:]:
        contour = list(contour)
        if _signed_area(contour) * winding < 0:
            contour.reverse()
        _, left, right = min(
            ((x - bx) ** 2 + (y - by) ** 2, i, j)
            for i, (x, y) in enumerate(merged)
            for j, (bx, by) in enumerate(contour)
        )
        rotated = contour[right:] + contour[:right]
        merged = merged[:left + 1] + rotated + [rotated[0], merged[left]] + merged[left + 1:]
    return merged


def _polygon(raw: Any, width: int, height: int, label: str) -> tuple[list[Point], int]:
    if not isinstance(raw, list) or len(raw) < 6 or len(raw) % 2:
        raise ValueError(f"{label}: polygon must have at least three x/y coordinate pairs")
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in raw):
        raise ValueError(f"{label}: polygon coordinates must be finite numbers")
    points: list[Point] = []
    clipped = 0
    for x, y in zip(raw[::2], raw[1::2]):
        if not (-BOUNDARY_TOLERANCE_PIXELS <= x <= width and
                -BOUNDARY_TOLERANCE_PIXELS <= y <= height):
            raise ValueError(f"{label}: point {(x, y)} is outside image {width}x{height} (1px tolerance)")
        point = (min(max(float(x), 0.0), width - 1), min(max(float(y), 0.0), height - 1))
        clipped += int(point != (x, y))
        points.append(point)
    if len(set(points)) < 3 or abs(_signed_area(points)) < 1e-9:
        raise ValueError(f"{label}: polygon has fewer than three distinct points or zero area")
    return points, clipped


def _csv_text(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=MANIFEST_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _fail_on_stale_files(out: Path, expected: dict[str, set[str]]) -> None:
    """Never silently keep old labels/images after changing source or splits."""
    for kind in ("labels", "images"):
        directory = out / kind
        if not directory.exists():
            continue
        stale = []
        for path in directory.rglob("*"):
            if not path.is_file() or path.name.startswith(".") or path.suffix == ".cache":
                continue
            relative = path.relative_to(directory)
            if len(relative.parts) != 2:
                stale.append(str(path))
                continue
            split, name = relative.parts
            permitted = expected.get(split, set())
            image_name = f"{Path(name).stem}.jpg" if kind == "labels" else name
            if (kind == "labels" and path.suffix != ".txt") or image_name not in permitted:
                stale.append(str(path))
        if stale:
            raise ValueError(
                f"Output contains {len(stale)} stale {kind} file(s), for example {stale[0]}. "
                "Use a fresh --out directory or review and move stale files before regenerating."
            )


def preprocess(annotations: Path, out: Path, split_policy: str = "official_batches") -> dict[str, Any]:
    """Validate the entire source before writing labels, manifests and report.

    Existing images are preserved. A mismatch with old output filenames fails
    before writing; matching output labels/manifests can be regenerated safely.
    This step needs annotations only and does not claim images are available.
    The optional train_only policy keeps supplemental sources out of the official
    validation/test benchmark; callers must use a separate output directory.
    """
    if split_policy not in SPLIT_POLICIES:
        raise ValueError(f"Unknown split policy: {split_policy!r}; expected one of {SPLIT_POLICIES}")
    annotations, out = Path(annotations).resolve(), Path(out).resolve()
    source_bytes = annotations.read_bytes()
    try:
        coco = json.loads(source_bytes)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid annotation JSON: {annotations}: {exc}") from exc
    if not isinstance(coco, dict):
        raise ValueError("COCO source must be a JSON object")
    images = _indexed(_records(coco, "images"), "image")
    categories = _indexed(_records(coco, "categories"), "category")
    annotation_records = _records(coco, "annotations")
    if not images or not categories:
        raise ValueError("COCO source must contain at least one image and category")
    for category in categories.values():
        if not isinstance(category.get("name"), str) or not category["name"].strip():
            raise ValueError(f"Category {category['id']} must have a nonempty name")
    scene_categories = _indexed(_records(coco, "scene_categories", required=False), "scene category")
    scenes: dict[int, set[int]] = defaultdict(set)
    unknown_scene_id_counts: Counter[int] = Counter()
    for scene in _records(coco, "scene_annotations", required=False):
        image_id = _integer(scene.get("image_id"), "Scene image_id")
        if image_id not in images:
            raise ValueError(f"Scene references unknown image_id {image_id}")
        background_ids = scene.get("background_ids")
        if not isinstance(background_ids, list):
            raise ValueError(f"Scene for image {image_id}: background_ids must be a list")
        for scene_id in background_ids:
            _integer(scene_id, "Scene background id")
            if scene_id not in scene_categories:
                unknown_scene_id_counts[scene_id] += 1
            scenes[image_id].add(scene_id)

    image_meta = {}
    expected: dict[str, set[str]] = {split: set() for split in SPLITS}
    flat_names: set[str] = set()
    source_names: set[str] = set()
    for image_id, im in images.items():
        width = _integer(im.get("width"), f"Image {image_id} width", 1)
        height = _integer(im.get("height"), f"Image {image_id} height", 1)
        file_name = im.get("file_name")
        if not isinstance(file_name, str) or "\\" in file_name:
            raise ValueError(f"Image {image_id}: invalid file_name {file_name!r}")
        source = PurePosixPath(file_name)
        if source.is_absolute() or len(source.parts) != 2 or any(p in (".", "..") for p in source.parts):
            expected_name = "batch_N/filename" if split_policy == "official_batches" else "source_folder/filename"
            raise ValueError(f"Image {image_id}: expected {expected_name}, got {file_name!r}")
        if file_name in source_names:
            raise ValueError(f"Duplicate source file_name: {file_name}")
        source_names.add(file_name)
        split = choose_split(file_name, split_policy)
        batch = source.parts[0]
        flat_name = f"{batch}__{source.stem}.jpg"
        if flat_name.casefold() in flat_names:
            raise ValueError(f"Flattened filename collision: {flat_name}")
        flat_names.add(flat_name.casefold())
        expected[split].add(flat_name)
        image_meta[image_id] = (split, batch, flat_name, width, height)

    by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)
    original_counts: Counter[int] = Counter()
    clipped_vertices = 0
    clipped_annotations = 0
    multipart_annotations = 0
    annotation_id_locations: dict[int, list[dict[str, int]]] = defaultdict(list)
    for source_index, ann in enumerate(annotation_records):
        ann_id = _integer(ann.get("id"), f"Annotation at index {source_index} id")
        image_id = _integer(ann.get("image_id"), f"Annotation {ann_id} image_id")
        category_id = _integer(ann.get("category_id"), f"Annotation {ann_id} category_id")
        if image_id not in images:
            raise ValueError(f"Annotation {ann_id} references unknown image_id {image_id}")
        if category_id not in categories:
            raise ValueError(f"Annotation {ann_id} references unknown category_id {category_id}")
        annotation_id_locations[ann_id].append({"source_index": source_index, "image_id": image_id})
        original_id = _integer(ann.get("original_category_id", category_id), f"Annotation {ann_id} original_category_id")
        if ann.get("iscrowd", 0) not in (0, False):
            raise ValueError(f"Annotation {ann_id}: crowd/RLE masks are unsupported; provide polygon annotations")
        segmentation = ann.get("segmentation")
        if not isinstance(segmentation, list) or not segmentation:
            raise ValueError(f"Annotation {ann_id}: segmentation must be a nonempty list of polygons (RLE unsupported)")
        _, _, _, width, height = image_meta[image_id]
        polygons = []
        annotation_clipped = 0
        for i, raw in enumerate(segmentation):
            polygon, clipped = _polygon(raw, width, height, f"Annotation {ann_id}, polygon {i}")
            polygons.append(polygon)
            annotation_clipped += clipped
        multipart_annotations += int(len(polygons) > 1)
        clipped_vertices += annotation_clipped
        clipped_annotations += int(annotation_clipped > 0)
        points = merge_polygons(polygons)
        coords = [coordinate for x, y in points for coordinate in (x / width, y / height)]
        row = "0 " + " ".join(f"{value:.8f}" for value in coords)
        by_image[image_id].append({"id": ann_id, "source_index": source_index, "original_id": original_id, "row": row})
        original_counts[original_id] += 1

    # Every source record has now been validated. Do not create output on errors.
    _fail_on_stale_files(out, expected)
    manifests: dict[str, list[dict[str, Any]]] = {split: [] for split in SPLITS}
    for image_id, im in images.items():
        split, batch, flat_name, width, height = image_meta[image_id]
        objects = by_image[image_id]
        scene_ids = sorted(scenes[image_id])
        manifests[split].append({
            "image_id": image_id, "batch": batch, "source_file_name": im["file_name"],
            "flat_file_name": flat_name, "width": width, "height": height,
            "object_count": len(objects), "scene_ids": "|".join(map(str, scene_ids)),
            "scene_names": "|".join(str(scene_categories.get(s, {}).get("name", f"unknown_{s}")) for s in scene_ids),
            "natural_focus": bool(set(scene_ids) & {3, 5}),
            "flickr_url": im.get("flickr_url") or "", "flickr_640_url": im.get("flickr_640_url") or "",
            "license": im.get("license") if im.get("license") is not None else "",
            "annotation_ids": "|".join(str(obj["id"]) for obj in objects),
            "original_category_ids": "|".join(str(obj["original_id"]) for obj in objects),
            "source_annotation_indices": "|".join(str(obj["source_index"]) for obj in objects),
            "date_captured": im.get("date_captured") or "", "coco_url": im.get("coco_url") or "",
        })

    source_warnings = []
    if any(len(locations) > 1 for locations in annotation_id_locations.values()):
        source_warnings.append("Source annotation IDs repeat; every source record is retained and indexed by its zero-based source position.")
    if unknown_scene_id_counts:
        source_warnings.append("Undeclared scene background IDs are preserved as unknown_ID; no missing scene name is invented.")
    summary = {
        "source": str(annotations), "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_info": coco.get("info", {}), "source_licenses": coco.get("licenses", []),
        "source_categories": list(categories.values()), "source_scene_categories": list(scene_categories.values()),
        "class_mapping": {str(category_id): 0 for category_id in categories}, "target_names": {"0": "litter"},
        "original_category_instance_counts": {str(k): v for k, v in sorted(original_counts.items())},
        "images_total": len(images), "annotations_total": len(annotation_records),
        "duplicate_source_annotation_ids": {str(k): locations for k, locations in annotation_id_locations.items() if len(locations) > 1},
        "source_warnings": source_warnings,
        "unknown_scene_id_counts": {str(k): v for k, v in sorted(unknown_scene_id_counts.items())},
        "multi_polygon_annotations": multipart_annotations, "invalid_annotations": 0,
        "boundary_tolerance_pixels": BOUNDARY_TOLERANCE_PIXELS,
        "clipped_vertices": clipped_vertices, "annotations_with_clipped_vertices": clipped_annotations,
        "multipart_strategy": "nearest contour vertices joined by duplicated bridge endpoints",
        "normalization": "clip <=1px boundary overshoot to pixel bounds [0,width-1]x[0,height-1]; x / width; y / height",
        "split_policy": split_policy,
        "split_strategy": "batch holdout" if split_policy == "official_batches" else "train_only",
        "dataset_role": "official benchmark" if split_policy == "official_batches" else "optional train-only pool",
        "train_batches": sorted(TRAIN_BATCHES) if split_policy == "official_batches" else sorted({meta[1] for meta in image_meta.values()}),
        "val_batches": sorted(VAL_BATCHES) if split_policy == "official_batches" else [],
        "test_batches": sorted(TEST_BATCHES) if split_policy == "official_batches" else [],
        "splits": {
            split: {"images": len(rows), "objects": sum(row["object_count"] for row in rows),
                    "natural_focus_images": sum(row["natural_focus"] for row in rows)}
            for split, rows in manifests.items()
        },
        "images_verified": False,
        "scope": "Litter instance segmentation only; TACO contains no trail-damage masks.",
    }
    for split in SPLITS:
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
    for image_id, (split, _, flat_name, _, _) in image_meta.items():
        text = "\n".join(obj["row"] for obj in by_image[image_id])
        (out / "labels" / split / f"{Path(flat_name).stem}.txt").write_text(text + ("\n" if text else ""), encoding="utf-8")
    (out / "manifests").mkdir(parents=True, exist_ok=True)
    for split, rows in manifests.items():
        (out / "manifests" / f"{split}.csv").write_text(_csv_text(rows), encoding="utf-8")
    # JSON-quoted absolute paths are also valid YAML strings, including spaces.
    yaml = "# Generated by src.data.preprocess_taco; absolute paths support any working directory.\n"
    yaml += "".join(f"{split}: {json.dumps(str(out / 'images' / split))}\n" for split in SPLITS)
    yaml += "names:\n  0: litter\n"
    (out / "data.yaml").write_text(yaml, encoding="utf-8")
    (out / "conversion_report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--split-policy", choices=SPLIT_POLICIES, default="official_batches",
                        help="Official fixed batch holdouts, or a separate supplemental train-only pool.")
    args = parser.parse_args()
    try:
        summary = preprocess(args.annotations, args.out, split_policy=args.split_policy)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Preprocessing failed: {exc}\n")
    print(f"Converted {summary['annotations_total']} litter instances across {summary['images_total']} images.")
    print(f"Labels/manifests/config: {args.out.resolve()}")
    print("Image files must be imported/downloaded and verified separately before training.")


if __name__ == "__main__":
    main()
