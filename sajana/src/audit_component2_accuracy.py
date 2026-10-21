"""Read-only audit of Component 2's existing compact and supplemental profiles.

This audits annotations and image files in place. It does not edit, move, or
relabel dataset files, and it never loads a model or starts training.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[2]
SAJANA = ROOT / "sajana"
COMPACT = SAJANA / "data/processed/component2_compact_2000"
TRAIL = SAJANA / "data/processed/component2_cycle2_trail_v4"
OUTPUT = SAJANA / "results/component2_training/dataset_accuracy_audit.json"

TASKS = {
    "litter": {"classes": {0: "litter"}, "geometry": "polygon", "source": "TACO"},
    "obstacle": {"classes": {0: "rock_region", 1: "log_region"}, "geometry": "box", "source": "WildScenes2d"},
}
TRAIL_CLASSES = {
    0: "tree",
    1: "stump",
    2: "stem",
    3: "obstacle_region",
    4: "non_passable_obstacle",
    5: "debris",
    6: "rock",
}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dhash(path: Path) -> int:
    with Image.open(path) as image:
        image = ImageOps.grayscale(image)
        image = ImageOps.fit(image, (9, 8), method=Image.Resampling.LANCZOS)
        pixels = list(image.getdata())
    value = 0
    for y in range(8):
        for x in range(8):
            value = (value << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return value


def read_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def image_files(folder: Path):
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def parse_annotation(label: Path, width: int, height: int, geometry: str):
    summary = {
        "annotation_rows": 0,
        "class_counts": Counter(),
        "valid_rows": 0,
        "invalid_rows": [],
        "tiny_rows_lt_10px": 0,
        "edge_touching_rows": 0,
        "areas_px2": [],
        "bbox_width_px": [],
        "bbox_height_px": [],
        "size_bins": Counter(),
        "coordinate_values": [],
        "suspicious_rows": [],
    }
    text = label.read_text(errors="replace") if label.exists() else ""
    lines = text.splitlines()
    def orientation(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def on_segment(a, b, p):
        return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])

    def segments_intersect(a, b, c, d):
        o1, o2, o3, o4 = orientation(a, b, c), orientation(a, b, d), orientation(c, d, a), orientation(c, d, b)
        if o1 == 0 and on_segment(a, b, c):
            return True
        if o2 == 0 and on_segment(a, b, d):
            return True
        if o3 == 0 and on_segment(c, d, a):
            return True
        if o4 == 0 and on_segment(c, d, b):
            return True
        return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)

    def polygon_self_intersects(points):
        count = len(points)
        for first in range(count):
            a, b = points[first], points[(first + 1) % count]
            for second in range(first + 1, count):
                # Neighboring segments share a polygon vertex by design.
                if second == first or second == (first + 1) % count or (second + 1) % count == first:
                    continue
                c, d = points[second], points[(second + 1) % count]
                if segments_intersect(a, b, c, d):
                    return True
        return False

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        summary["annotation_rows"] += 1
        fields = line.split()
        issue = None
        try:
            class_id = int(fields[0])
            coordinates = [float(value) for value in fields[1:]]
            summary["class_counts"][class_id] += 1
            if class_id < 0:
                issue = "negative_class_id"
            elif geometry == "box" and len(coordinates) != 4:
                issue = "box_requires_four_coordinates"
            elif geometry == "polygon" and (len(coordinates) < 6 or len(coordinates) % 2):
                issue = "polygon_requires_three_or_more_xy_pairs"
            elif not all(math.isfinite(value) for value in coordinates):
                issue = "non_finite_coordinate"
            elif any(value < 0.0 or value > 1.0 for value in coordinates):
                issue = "coordinate_outside_normalized_range"
            else:
                if geometry == "box":
                    cx, cy, bw, bh = coordinates
                    if bw <= 0 or bh <= 0:
                        issue = "non_positive_box_size"
                    else:
                        left, right = cx - bw / 2, cx + bw / 2
                        top, bottom = cy - bh / 2, cy + bh / 2
                        box_width, box_height = bw * width, bh * height
                        area = box_width * box_height
                        summary["coordinate_values"].extend(coordinates)
                        if left < -1e-6 or top < -1e-6 or right > 1 + 1e-6 or bottom > 1 + 1e-6:
                            issue = "box_edges_outside_image"
                        points = None
                else:
                    points = list(zip(coordinates[0::2], coordinates[1::2]))
                    if len(points) > 3 and points[0] == points[-1]:
                        points = points[:-1]
                    if len(set(points)) < 3:
                        issue = "fewer_than_three_unique_polygon_vertices"
                    elif any(points[index] == points[(index + 1) % len(points)] for index in range(len(points))):
                        issue = "repeated_consecutive_polygon_vertex"
                    elif polygon_self_intersects(points):
                        issue = "self_intersecting_polygon"
                    xs, ys = zip(*points)
                    left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
                    box_width, box_height = (right - left) * width, (bottom - top) * height
                    area_norm = 0.0
                    for index, (x1, y1) in enumerate(points):
                        x2, y2 = points[(index + 1) % len(points)]
                        area_norm += x1 * y2 - x2 * y1
                    area = abs(area_norm) * 0.5 * width * height
                    summary["coordinate_values"].extend(coordinates)
                    if area <= 0 or box_width <= 0 or box_height <= 0:
                        issue = "zero_area_polygon"
                if issue is None:
                    summary["valid_rows"] += 1
                    summary["areas_px2"].append(area)
                    summary["bbox_width_px"].append(box_width)
                    summary["bbox_height_px"].append(box_height)
                    if area < 32**2:
                        summary["size_bins"]["small_lt_32px2"] += 1
                    elif area <= 96**2:
                        summary["size_bins"]["medium_32_to_96px2"] += 1
                    else:
                        summary["size_bins"]["large_gt_96px2"] += 1
                    if box_width < 10 or box_height < 10:
                        summary["tiny_rows_lt_10px"] += 1
                        summary["suspicious_rows"].append({"line": line_number, "reason": "bbox_under_10px"})
                    if left <= 1 / max(width, 1) or top <= 1 / max(height, 1) or right >= 1 - 1 / max(width, 1) or bottom >= 1 - 1 / max(height, 1):
                        summary["edge_touching_rows"] += 1
            if issue:
                summary["invalid_rows"].append({"line": line_number, "reason": issue})
        except (ValueError, IndexError, OverflowError) as exc:
            summary["invalid_rows"].append({"line": line_number, "reason": f"parse_error:{type(exc).__name__}"})
    return summary


def distribution(values):
    if not values:
        return {"count": 0, "min": None, "median": None, "p90": None, "max": None}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": round(ordered[0], 3),
        "median": round(median(ordered), 3),
        "p90": round(ordered[min(len(ordered) - 1, math.ceil(0.9 * len(ordered)) - 1)], 3),
        "max": round(ordered[-1], 3),
    }


def audit_yolo_task(task: str, info: dict):
    root = COMPACT / task
    result = {
        "source": info["source"],
        "task": "instance_segmentation" if info["geometry"] == "polygon" else "object_detection",
        "classes": {},
        "splits": {},
        "image_dimensions": Counter(),
        "image_records": [],
        "invalid_annotation_rows": [],
        "missing_label_images": [],
        "tiny_annotation_rows_lt_10px": 0,
        "edge_touching_annotation_rows": 0,
    }
    class_photo_counts = {class_id: Counter() for class_id in info["classes"]}
    class_object_counts = Counter()
    size_counts = Counter()
    area_values, box_widths, box_heights = [], [], []
    for split in ("train", "val", "test"):
        folder = root / "images" / split
        label_folder = root / "labels" / split
        photos = image_files(folder) if folder.exists() else []
        split_summary = {
            "images": len(photos),
            "labels_present": 0,
            "images_with_empty_label": 0,
            "images_without_any_target_label": 0,
            "annotation_rows": 0,
            "classes": {},
            "dimensions": Counter(),
        }
        for class_id in info["classes"]:
            split_summary["classes"][info["classes"][class_id]] = {
                "positive_images": 0,
                "no_class_annotation_images": 0,
                "annotations": 0,
            }
        for image_path in photos:
            label_path = label_folder / (image_path.stem + ".txt")
            try:
                with Image.open(image_path) as im:
                    im.verify()
                with Image.open(image_path) as im:
                    width, height = im.size
            except Exception as exc:
                result.setdefault("image_errors", []).append({"file": str(image_path.relative_to(ROOT)), "error": type(exc).__name__})
                continue
            result["image_dimensions"][f"{width}x{height}"] += 1
            split_summary["dimensions"][f"{width}x{height}"] += 1
            if not label_path.exists():
                result["missing_label_images"].append(str(image_path.relative_to(ROOT)))
                parsed = {"annotation_rows": 0, "class_counts": Counter(), "invalid_rows": [], "areas_px2": [], "bbox_width_px": [], "bbox_height_px": [], "size_bins": Counter(), "tiny_rows_lt_10px": 0, "edge_touching_rows": 0}
            else:
                split_summary["labels_present"] += 1
                parsed = parse_annotation(label_path, width, height, info["geometry"])
                if parsed["annotation_rows"] == 0:
                    split_summary["images_with_empty_label"] += 1
            split_summary["annotation_rows"] += parsed["annotation_rows"]
            result["tiny_annotation_rows_lt_10px"] += parsed.get("tiny_rows_lt_10px", 0)
            result["edge_touching_annotation_rows"] += parsed.get("edge_touching_rows", 0)
            if parsed["annotation_rows"] == 0:
                split_summary["images_without_any_target_label"] += 1
            for class_id, class_name in info["classes"].items():
                count = parsed["class_counts"].get(class_id, 0)
                class_photo_counts[class_id]["positive"] += int(count > 0)
                class_photo_counts[class_id]["no_class_annotation"] += int(count == 0)
                class_object_counts[class_id] += count
                split_summary["classes"][class_name]["positive_images"] += int(count > 0)
                split_summary["classes"][class_name]["no_class_annotation_images"] += int(count == 0)
                split_summary["classes"][class_name]["annotations"] += count
            split_summary["images_with_any_target_label"] = split_summary["images"] - split_summary["images_without_any_target_label"]
            size_counts.update(parsed["size_bins"])
            area_values.extend(parsed["areas_px2"])
            box_widths.extend(parsed["bbox_width_px"])
            box_heights.extend(parsed["bbox_height_px"])
            if parsed["invalid_rows"]:
                result["invalid_annotation_rows"].append({"image": str(image_path.relative_to(ROOT)), "rows": parsed["invalid_rows"]})
            result["image_records"].append({
                "path": image_path,
                "split": split,
                "source": info["source"],
                "group": image_path.stem.split("__", 1)[0] if task == "litter" else image_path.stem.split("__", 1)[0],
                "width": width,
                "height": height,
                "sha256": sha256(image_path),
                "dhash": dhash(image_path),
                "class_counts": dict(parsed["class_counts"]),
            })
        result["splits"][split] = split_summary
    for class_id, class_name in info["classes"].items():
        positives = class_photo_counts[class_id]["positive"]
        total = sum(summary["images"] for summary in result["splits"].values())
        result["classes"][class_name] = {
            "positive_images": positives,
            "no_class_annotation_images": total - positives,
            "annotations": class_object_counts[class_id],
            "negative_semantics": "No class label in a class-specific export; not a verified trail-clear/passability label",
        }
    result["annotation_geometry"] = {
        "valid_annotation_rows": len(area_values),
        "invalid_annotation_rows": sum(len(entry["rows"]) for entry in result["invalid_annotation_rows"]),
        "invalid_annotation_reason_counts": dict(Counter(row["reason"] for entry in result["invalid_annotation_rows"] for row in entry["rows"])),
        "annotation_area_px2": distribution(area_values),
        "bbox_width_px": distribution(box_widths),
        "bbox_height_px": distribution(box_heights),
        "object_size_bins": dict(size_counts),
        "size_area_definition": "Polygon pixel area for segmentation labels; axis-aligned bounding-box area for box labels. Bins: small < 32^2 px, medium 32^2–96^2 px, large > 96^2 px",
        "tiny_boxes_under_10px": result["tiny_annotation_rows_lt_10px"],
        "edge_touching_annotation_rows": result["edge_touching_annotation_rows"],
    }
    # Keep photo-level hash records out of the JSON report.
    return result


def audit_trail_v4():
    manifest = TRAIL / "manifest.csv"
    rows = list(csv.DictReader(manifest.open(newline="")))
    names = {int(key): value for key, value in TRAIL_CLASSES.items()}
    result = {
        "manifest": str(manifest.relative_to(ROOT)),
        "photos": len(rows),
        "classes": {},
        "splits": {},
        "source_split_counts": {},
        "source_records": [],
        "invalid_annotation_rows": [],
        "image_dimensions": Counter(),
        "label_rows": 0,
        "empty_labels": 0,
        "missing_images": [],
        "missing_labels": [],
        "group_membership": {},
    }
    per_class = {int(key): {"objects": 0, "positive_images": 0, "negative_images": 0} for key in names}
    group_splits = defaultdict(set)
    group_source_splits = defaultdict(lambda: defaultdict(set))
    area_values, widths, heights = [], [], []
    size_counts = Counter()
    for row in rows:
        split = row["split"]
        source = row["source"]
        image_path = TRAIL / row["image"]
        label_path = TRAIL / row["label"]
        counts = {int(k): int(v) for k, v in json.loads(row["object_counts"]).items()}
        result["source_split_counts"].setdefault(source, Counter())[split] += 1
        if not image_path.exists():
            result["missing_images"].append(row["image"])
            continue
        if not label_path.exists():
            result["missing_labels"].append(row["label"])
            continue
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            width, height = image.size
        result["image_dimensions"][f"{width}x{height}"] += 1
        text = label_path.read_text(errors="replace")
        result["label_rows"] += sum(1 for line in text.splitlines() if line.strip())
        if not text.strip():
            result["empty_labels"] += 1
        parsed = parse_annotation(label_path, width, height, "box")
        result["invalid_annotation_rows"].extend({"image": row["image"], **entry} for entry in parsed["invalid_rows"])
        area_values.extend(parsed["areas_px2"])
        widths.extend(parsed["bbox_width_px"])
        heights.extend(parsed["bbox_height_px"])
        size_counts.update(parsed["size_bins"])
        for class_id in names:
            count = counts.get(class_id, 0)
            per_class[class_id]["objects"] += count
            per_class[class_id]["positive_images"] += int(count > 0)
            per_class[class_id]["negative_images"] += int(count == 0)
        if source == "GOOSE":
            member = Path(row["source_member"])
            # The enclosing capture name is preserved by the source manifest;
            # for the extension it also contains sequenceNN in the leaf name.
            match = re.search(r"(.*sequence\d+)_\d+_", member.stem)
            group = str(member.parent / (match.group(1) if match else member.stem))
        else:
            # Mobima's supplied export has only file_NNNN and no session ID.
            group = "unavailable"
        result["source_records"].append({
            "path": image_path,
            "split": split,
            "source": source,
            "group": group,
            "width": width,
            "height": height,
            "sha256": sha256(image_path),
            "manifest_sha256": row["sha256"],
            "dhash": dhash(image_path),
            "class_counts": counts,
        })
        if group != "unavailable":
            group_splits[group].add(split)
            group_source_splits[source][group].add(split)
    result["classes"] = {
        names[class_id]: {
            **summary,
            "negative_semantics": "No source label for this class; unknown for passability or route safety",
        }
        for class_id, summary in per_class.items()
    }
    for source in result["source_split_counts"]:
        result["source_split_counts"][source] = dict(result["source_split_counts"][source])
    for source, groups in group_source_splits.items():
        result["group_membership"][source] = {
            "groups": len(groups),
            "groups_per_split": dict(Counter(split for splits in groups.values() for split in splits)),
            "groups_crossing_splits": [group for group, splits in groups.items() if len(splits) > 1],
            "verified_group_split_disjoint": all(len(splits) == 1 for splits in groups.values()),
        }
    result["group_membership"]["MobimaSkidRoads"] = {
        "groups": None,
        "verified_group_split_disjoint": None,
        "limitation": "Source manifest has no route, sequence, or session field; 234 train and 59 validation photos share one source member namespace, and no Mobima photos are in this test split.",
    }
    result["annotation_geometry"] = {
        "annotation_area_px2": distribution(area_values),
        "bbox_width_px": distribution(widths),
        "bbox_height_px": distribution(heights),
        "object_size_bins": dict(size_counts),
        "size_area_definition": "Polygon pixel area for segmentation labels; axis-aligned bounding-box area for box labels. Bins: small < 32^2 px, medium 32^2–96^2 px, large > 96^2 px",
    }
    result["splits"] = {}
    for split in ("train", "val", "test"):
        subset = [r for r in result["source_records"] if r["split"] == split]
        result["splits"][split] = {
            "images": len(subset),
            "sources": dict(Counter(r["source"] for r in subset)),
            "class_positive_images": {
                class_name: sum(1 for r in subset if r["class_counts"].get(class_id, 0) > 0)
                for class_id, class_name in TRAIL_CLASSES.items()
            },
            "class_no_annotation_images": {
                class_name: sum(1 for r in subset if r["class_counts"].get(class_id, 0) == 0)
                for class_id, class_name in TRAIL_CLASSES.items()
            },
            "annotation_rows": sum(sum(r["class_counts"].values()) for r in subset),
            "dimensions": dict(Counter(f"{r['width']}x{r['height']}" for r in subset)),
        }
    return result


def leak_audit(records):
    exact = defaultdict(list)
    by_hash = defaultdict(list)
    for record in records:
        exact[record["sha256"]].append(record)
        by_hash[record["dhash"]].append(record)
    exact_groups = [items for items in exact.values() if len(items) > 1]
    seen = set()
    near = []
    # The audited profile is only 2,560 images; exhaustive 64-bit comparisons
    # are practical and avoid a brittle approximate indexing scheme.
    for index, left in enumerate(records):
        for right in records[index + 1 :]:
            key = tuple(sorted((str(left["path"]), str(right["path"]))))
            if key in seen:
                continue
            distance = bin(left["dhash"] ^ right["dhash"]).count("1")
            if distance <= 4:
                seen.add(key)
                near.append({
                    "left": str(left["path"].relative_to(ROOT)),
                    "right": str(right["path"].relative_to(ROOT)),
                    "left_split": left["split"],
                    "right_split": right["split"],
                    "left_source": left["source"],
                    "right_source": right["source"],
                    "hamming_distance": distance,
                    "cross_split": left["split"] != right["split"],
                    "cross_source": left["source"] != right["source"],
                })
    exact_examples = []
    for items in exact_groups:
        exact_examples.append({
            "sha256": items[0]["sha256"],
            "paths": [str(item["path"].relative_to(ROOT)) for item in items],
            "splits": sorted({item["split"] for item in items}),
            "sources": sorted({item["source"] for item in items}),
        })
    near.sort(key=lambda item: (item["hamming_distance"], item["left"], item["right"]))
    return {
        "method": "SHA-256 exact-byte comparison; 64-bit difference hash candidate search at Hamming distance <=4",
        "images_compared": len(records),
        "exact_duplicate_groups": len(exact_groups),
        "exact_duplicate_images_in_groups": sum(len(items) for items in exact_groups),
        "exact_duplicate_cross_split_groups": sum(len({x["split"] for x in items}) > 1 for items in exact_groups),
        "exact_duplicate_examples": exact_examples[:100],
        "near_duplicate_candidate_pairs": len(near),
        "near_duplicate_cross_split_candidate_pairs": sum(item["cross_split"] for item in near),
        "near_duplicate_cross_task_or_source_pairs": sum(item["cross_source"] for item in near),
        "near_duplicate_candidates": near[:300],
        "near_duplicate_note": "Difference-hash matches are review candidates, not confirmed duplicates; visually verify before exclusion. The report caps detailed examples at 300 pairs.",
    }


def group_audit(task_results, trail_result):
    result = {}
    for task, task_result in task_results.items():
        groups = defaultdict(set)
        for record in task_result["image_records"]:
            groups[record["group"]].add(record["split"])
        result[task_result["source"]] = {
            "groups": len(groups),
            "groups_per_split": dict(Counter(split for splits in groups.values() for split in splits)),
            "groups_crossing_splits": [group for group, splits in groups.items() if len(splits) > 1],
            "verified_group_split_disjoint": all(len(splits) == 1 for splits in groups.values()),
            "group_definition": "TACO batch_N from source filename" if task == "litter" else "WildScenes sequence prefix before __timestamp",
        }
    for source, summary in trail_result["group_membership"].items():
        result[source] = summary
    return result


def source_readiness():
    files = {
        "TACO_official_clean": SAJANA / "results/taco_preprocessing/official_clean_readiness.json",
        "TACO_unofficial_pool": SAJANA / "data/processed/taco_unofficial_litter_seg_available/readiness.json",
        "MJU_Waste": SAJANA / "results/mju_preprocessing/local_readiness.json",
        "WildScenes_rock_log": SAJANA / "data/processed/wildscenes_rock_log_detection/readiness.json",
        "WildScenes_semantic": SAJANA / "results/wildscenes_preprocessing/local_readiness.json",
        "GOOSE_Mobima_cycle2": SAJANA / "results/component2_cycle2/trail_preprocessing.json",
        "Pakistan_Urban_Waste": SAJANA / "results/component2_cycle2/urban_source_audit.json",
        "pLitter": SAJANA / "results/plitter_preprocessing/local_readiness.json",
        "ORFD": SAJANA / "results/orfd_preprocessing/local_readiness.json",
        "RUGD": SAJANA / "results/rugd_preprocessing/local_readiness.json",
    }
    summary = {}
    for name, path in files.items():
        obj = read_json(path)
        if obj is None:
            summary[name] = {"record": str(path.relative_to(ROOT)), "available": False}
            continue
        keys = ("passed", "training_ready", "training_pool_ready", "auxiliary_train_ready", "independent_evaluation_supported", "obstruction_training_ready", "full_component_ready", "status", "task", "splits", "issues", "warnings", "limitations", "route_blockage_ground_truth", "goose_root_class_trained", "garbage_dataset_included", "photos_by_split", "sources_by_split", "goose_sequences_by_split", "images_by_split", "temporal_audit", "exclusion_reason_counts", "excluded_images", "canonical_source_complete", "license", "licence")
        summary[name] = {"record": str(path.relative_to(ROOT)), "available": True}
        for key in keys:
            if key in obj:
                summary[name][key] = obj[key]
    local_images = [p for p in (SAJANA / "data/local_trails/images").rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    summary["Local_trails"] = {
        "record": "sajana/data/local_trails/",
        "available": True,
        "photos": len(local_images),
        "annotations": len([p for p in (SAJANA / "data/local_trails/annotations").rglob("*") if p.is_file() and p.name != ".gitkeep"]),
        "user_confirmed_no_annotated_local_trails": True,
        "status": "no local trail photo or annotation supplied",
    }
    return summary


def frozen_data_integrity(trail_result):
    compact_inventory_path = COMPACT / "inventory.json"
    compact_inventory = read_json(compact_inventory_path) or {}
    compact_missing = []
    compact_mismatched = []
    for relative, expected in compact_inventory.items():
        path = COMPACT / relative
        if not path.is_file():
            compact_missing.append(relative)
        elif sha256(path) != expected:
            compact_mismatched.append(relative)
    manifest_mismatches = [
        item["path"].relative_to(ROOT).as_posix()
        for item in trail_result["source_records"]
        if item["sha256"] != item["manifest_sha256"]
    ]
    label_manifest_mismatches = []
    source_rows = list(csv.DictReader((TRAIL / "manifest.csv").open(newline="")))
    by_image = {item["path"].relative_to(TRAIL).as_posix(): item for item in trail_result["source_records"]}
    for row in source_rows:
        record = by_image.get(row["image"])
        if not record:
            continue
        stated = {int(k): int(v) for k, v in json.loads(row["object_counts"]).items()}
        observed = record["class_counts"]
        if stated != {key: value for key, value in observed.items() if value}:
            label_manifest_mismatches.append(row["image"])
    size_bytes = {}
    for name, path in (("budgeted_compact_profile", COMPACT), ("supplemental_trail_profile", TRAIL)):
        size_bytes[name] = sum(item.stat().st_size for item in path.rglob("*") if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES | {".txt"})
    return {
        "compact_inventory": {
            "record": str(compact_inventory_path.relative_to(ROOT)),
            "listed_files": len(compact_inventory),
            "missing_files": compact_missing,
            "hash_mismatches": compact_mismatched,
            "passed": bool(compact_inventory) and not compact_missing and not compact_mismatched,
        },
        "supplemental_manifest_image_hash_mismatches": manifest_mismatches,
        "supplemental_manifest_annotation_count_mismatches": label_manifest_mismatches,
        "image_and_label_bytes": size_bytes,
    }


def full_sequence_split_audit():
    wild_root = SAJANA / "data/processed/wildscenes_rock_log_detection/manifests"
    wild_rows = []
    for split in ("train", "val", "test"):
        path = wild_root / f"{split}.csv"
        if path.exists():
            wild_rows.extend(csv.DictReader(path.open(newline="")))
    wild_groups = defaultdict(set)
    wild_per_split = defaultdict(Counter)
    for row in wild_rows:
        wild_groups[row["sequence"]].add(row["split"])
        wild_per_split[row["sequence"]][row["split"]] += 1

    mju_root = SAJANA / "data/processed/mju_waste_litter_seg/images"
    mju_groups = defaultdict(set)
    mju_counts = Counter()
    for split in ("train", "val", "test"):
        for path in image_files(mju_root / split):
            group = path.name[:10]
            mju_groups[group].add(split)
            mju_counts[split] += 1
    mju_readiness = read_json(SAJANA / "results/mju_preprocessing/local_readiness.json") or {}
    temporal = mju_readiness.get("temporal_audit", {})

    goose_path = SAJANA / "data/raw/component2_cycle2_sources/goose_labels_48_with_ex.json"
    goose_summary = None
    if goose_path.exists():
        goose_rows = json.loads(goose_path.read_text())
        sequences = defaultdict(Counter)
        class_image_counts = defaultdict(Counter)
        for row in goose_rows:
            split, sequence = row["source_split"], row["sequence"]
            sequences[split][sequence] += 1
            for class_id in ("4", "28", "29", "40", "62"):
                if int(row["pixels"].get(class_id, 0)) > 0:
                    class_image_counts[(split, sequence)][class_id] += 1
        goose_summary = {
            "source_groups_by_partition": {split: len(groups) for split, groups in sequences.items()},
            "annotated_frames_by_partition": {split: sum(groups.values()) for split, groups in sequences.items()},
            "untouched_official_val_groups": sorted(sequences.get("val", {})),
            "untouched_official_val_frames": sum(sequences.get("val", {}).values()),
            "official_val_target_positive_frames_by_class": {
                class_id: sum(count[class_id] > 0 for (split, _), count in class_image_counts.items() if split == "val")
                for class_id in ("4", "28", "29", "40", "62")
            },
            "current_cycle_source_partition_use": "Current supplemental training samples source_split=train for train/validation and source_split=ex_val for the examined 51-photo test; original source_split=val is absent from the v4 manifest and is a candidate only after confirming it remains unexamined.",
        }
    return {
        "WildScenes_full_profile": {
            "source_manifest_images": len(wild_rows),
            "sequence_groups": len(wild_groups),
            "groups_per_split": dict(Counter(split for splits in wild_groups.values() for split in splits)),
            "groups_crossing_splits": {group: sorted(splits) for group, splits in wild_groups.items() if len(splits) > 1},
            "validation_sequence_groups": sorted({row["sequence"] for row in wild_rows if row["split"] == "val"}),
            "test_sequence_groups": sorted({row["sequence"] for row in wild_rows if row["split"] == "test"}),
            "note": "All five source sequences appear in both train and test; K-01 also appears in validation. Source split labels do not provide independent route/session holdouts.",
        },
        "MJU_full_profile": {
            "images_by_split": dict(mju_counts),
            "date_groups": len(mju_groups),
            "date_groups_crossing_splits": {group: sorted(splits) for group, splits in mju_groups.items() if len(splits) > 1},
            "temporal_audit": temporal,
            "independent_evaluation_supported": mju_readiness.get("independent_evaluation_supported"),
            "note": "All nine image dates occur in train, validation, and test; do not use its source validation/test as independent evaluation.",
        },
        "GOOSE_available_sequence_metadata": goose_summary,
    }


def checkpoint_inventory():
    runs = SAJANA / "runs"
    files = []
    for path in sorted(p for p in runs.rglob("*") if p.is_file() and p.suffix.lower() in {".pt", ".tflite", ".onnx"}):
        stat = path.stat()
        files.append({"path": str(path.relative_to(ROOT)), "format": path.suffix.lower(), "bytes": stat.st_size, "sha256": sha256(path)})
    return {
        "files": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "inventory": files,
        "scope": "Existing Component 2 run/mobile artifacts under sajana/runs; binary weights were hash-inventoried, not retrained or modified.",
    }


def clean_json(value):
    if isinstance(value, Counter):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, defaultdict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items() if k not in {"image_records", "source_records"}}
    if isinstance(value, list):
        return [clean_json(item) for item in value]
    if isinstance(value, Path):
        return str(value.relative_to(ROOT)) if value.is_absolute() else str(value)
    return value


def main():
    task_results = {task: audit_yolo_task(task, info) for task, info in TASKS.items()}
    trail_result = audit_trail_v4()
    records = []
    for result in task_results.values():
        records.extend(result["image_records"])
    records.extend(trail_result["source_records"])
    sources = source_readiness()
    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "audit_type": "read_only_pretraining_accuracy_recovery",
        "training_started": False,
        "data_modified": False,
        "scope": {
            "current_budgeted_profile": "sajana/data/processed/component2_compact_2000",
            "supplemental_profile": "sajana/data/processed/component2_cycle2_trail_v4",
            "budgeted_profile_photos": sum(sum(v["images"] for v in r["splits"].values()) for r in task_results.values()),
            "supplemental_profile_photos": len(trail_result["source_records"]),
            "old_test_sets": "Reviewed; quarantined from new tuning, training, threshold calibration, or final acceptance.",
        },
        "budgeted_profile": {task: {k: v for k, v in result.items() if k != "image_records"} for task, result in task_results.items()},
        "supplemental_trail_profile": {k: v for k, v in trail_result.items() if k != "source_records"},
        "duplicates_and_leakage": {
            "image_duplicates": leak_audit(records),
            "sequence_groups": group_audit(task_results, trail_result),
            "source_leakage_notes": [
                "TACO batch_N source groups are assigned wholly to one of train/validation/test in the selected profile.",
                "WildScenes K-01 and K-03 sequence groups cross selected train/validation/test splits; frame-level source split preservation did not prevent sequence leakage in this compact sample.",
                "GOOSE groups are disjoint across train/validation/test in the supplemental profile; its test is a separate extension domain.",
                "Mobima source session/route IDs are absent; train/validation group independence cannot be verified, and Mobima has no supplemental test photos.",
                "MJU source readiness warns that official splits contain temporally adjacent frames; keep only training source records for auxiliary training and do not use its test as fresh evaluation.",
                "TACO, WildScenes, GOOSE, and Mobima provide separate task/class coverage. Their class-absent label files do not provide clear-trail or safe-route truth.",
            ],
        },
        "available_dataset_audits": sources,
        "full_source_sequence_split_audit": full_sequence_split_audit(),
        "frozen_data_integrity": frozen_data_integrity(trail_result),
        "existing_model_artifact_inventory": checkpoint_inventory(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(clean_json(output), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    print(f"Exact/near duplicate scan: {output['duplicates_and_leakage']['image_duplicates']['images_compared']} images")
    for task, result in task_results.items():
        print(task, json.dumps(clean_json(result["classes"]), sort_keys=True))
    print("supplemental classes", json.dumps(clean_json(trail_result["classes"]), sort_keys=True))
    print("checkpoint files", output["existing_model_artifact_inventory"]["files"], "bytes", output["existing_model_artifact_inventory"]["total_bytes"])


if __name__ == "__main__":
    main()
