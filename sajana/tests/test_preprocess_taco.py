"""Meaningful conversion/validation checks, using only the Python standard library."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sajana.src.data.preprocess_taco import MANIFEST_FIELDS, choose_split, merge_polygons, preprocess


def fixture() -> dict:
    return {
        "info": {"description": "test source"}, "licenses": [{"id": 1, "name": "CC BY"}],
        "categories": [{"id": 4, "name": "bottle"}],
        "images": [{"id": 1, "file_name": "batch_1/example.jpg", "width": 100, "height": 200, "license": 1}],
        "annotations": [{"id": 8, "image_id": 1, "category_id": 4, "original_category_id": 17,
                         "segmentation": [[0, 0, 100, 0, 100, 200, 0, 200]]}],
    }


class PreprocessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.json"
        self.out = self.root / "output with spaces"

    def run_conversion(self, coco=None, *, split_policy="official_batches"):
        self.source.write_text(json.dumps(coco if coco is not None else fixture()), encoding="utf-8")
        return preprocess(self.source, self.out, split_policy=split_policy)

    def test_normalization_mapping_and_provenance(self):
        summary = self.run_conversion()
        label = (self.out / "labels/train/batch_1__example.txt").read_text().split()
        self.assertEqual(label[0], "0")
        self.assertEqual(list(map(float, label[1:])), [0, 0, .99, 0, .99, .995, 0, .995])
        self.assertEqual(summary["class_mapping"], {"4": 0})
        self.assertEqual(summary["original_category_instance_counts"], {"17": 1})
        self.assertEqual(summary["source_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(json.loads(self.source.read_text()), fixture())
        with (self.out / "manifests/train.csv").open(newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row["license"], "1")
        self.assertEqual(row["annotation_ids"], "8")
        self.assertEqual(row["original_category_ids"], "17")
        self.assertIn(json.dumps(str(self.out.resolve() / "images/train")), (self.out / "data.yaml").read_text())
        self.assertFalse(summary["images_verified"])
        self.assertEqual(summary["split_policy"], "official_batches")
        self.assertEqual(summary["split_strategy"], "batch holdout")

    def test_multipart_bridges_preserve_area_and_one_object(self):
        polygons = [[(0, 0), (10, 0), (10, 10), (0, 10)],
                    [(20, 0), (20, 10), (30, 10), (30, 0)]]
        merged = merge_polygons(polygons)
        area = abs(sum(x * by - y * bx for (x, y), (bx, by) in zip(merged, merged[1:] + merged[:1])) / 2)
        self.assertEqual(area, 200)
        self.assertEqual(len(merged), 10)
        self.assertGreaterEqual(merged.count((10, 0)), 2)
        self.assertGreaterEqual(merged.count((20, 0)), 2)
        coco = fixture()
        coco["annotations"][0]["segmentation"] = [[value for point in polygon for value in point] for polygon in polygons]
        summary = self.run_conversion(coco)
        self.assertEqual(summary["multi_polygon_annotations"], 1)
        self.assertEqual(summary["annotations_total"], 1)
        self.assertEqual(len((self.out / "labels/train/batch_1__example.txt").read_text().splitlines()), 1)

    def test_known_one_pixel_boundary_overshoot_is_counted(self):
        coco = fixture()
        coco["annotations"][0]["segmentation"] = [[-1, 0, 99, 0, 99, 199, 0, 199]]
        summary = self.run_conversion(coco)
        self.assertEqual(summary["clipped_vertices"], 1)
        self.assertEqual(summary["annotations_with_clipped_vertices"], 1)

    def test_invalid_sources_fail_before_writing(self):
        changes = {
            "missing image": lambda c: c["annotations"][0].update(image_id=99),
            "missing category": lambda c: c["annotations"][0].update(category_id=99),
            "negative id": lambda c: c["annotations"][0].update(id=-1),
            "duplicate image": lambda c: c["images"].append(copy.deepcopy(c["images"][0])),
            "invalid dimension": lambda c: c["images"][0].update(width=0),
            "fractional dimension": lambda c: c["images"][0].update(width=10.5),
            "nonfinite point": lambda c: c["annotations"][0].update(segmentation=[[0, 0, float("nan"), 0, 1, 1]]),
            "empty polygons": lambda c: c["annotations"][0].update(segmentation=[]),
            "bad polygon": lambda c: c["annotations"][0].update(segmentation=[[0, 0, 1, 0, 2, 0]]),
            "outside image": lambda c: c["annotations"][0].update(segmentation=[[-2, 0, 1, 0, 1, 1]]),
            "outside upper pixel bound": lambda c: c["annotations"][0].update(segmentation=[[101, 0, 1, 0, 1, 1]]),
            "RLE": lambda c: c["annotations"][0].update(segmentation={"counts": "mask", "size": [100, 200]}),
            "unknown batch": lambda c: c["images"][0].update(file_name="batch_99/example.jpg"),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                coco = fixture()
                change(coco)
                with self.assertRaises(ValueError):
                    self.run_conversion(coco)
                self.assertFalse(self.out.exists(), "Invalid input must not create output directories")

    def test_duplicate_source_annotation_ids_retain_every_object(self):
        coco = fixture()
        coco["images"].append({"id": 2, "file_name": "batch_3/other.jpg", "width": 100, "height": 200})
        ann = copy.deepcopy(coco["annotations"][0])
        ann["image_id"] = 2
        coco["annotations"].append(ann)
        summary = self.run_conversion(coco)
        self.assertEqual(summary["annotations_total"], 2)
        self.assertEqual(summary["duplicate_source_annotation_ids"], {"8": [{"source_index": 0, "image_id": 1}, {"source_index": 1, "image_id": 2}]})
        self.assertEqual(summary["splits"]["train"]["objects"], 1)
        self.assertEqual(summary["splits"]["val"]["objects"], 1)

    def test_single_polygon_preserves_closure_and_duplicate_vertices(self):
        coco = fixture()
        coco["annotations"][0]["segmentation"] = [[0, 0, 50, 0, 50, 0, 50, 100, 0, 0]]
        self.run_conversion(coco)
        label = (self.out / "labels/train/batch_1__example.txt").read_text().split()
        self.assertEqual(list(map(float, label[1:])), [0, 0, .5, 0, .5, 0, .5, .5, 0, 0])

    def test_unknown_scene_category_is_preserved_with_warning(self):
        coco = fixture()
        coco["scene_categories"] = [{"id": 3, "name": "Sand, Dirt, Pebbles"}]
        coco["scene_annotations"] = [{"image_id": 1, "background_ids": [3, 7, 7]}]
        summary = self.run_conversion(coco)
        self.assertEqual(summary["unknown_scene_id_counts"], {"7": 2})
        self.assertTrue(summary["source_warnings"])
        with (self.out / "manifests/train.csv").open(newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row["scene_names"], "Sand, Dirt, Pebbles|unknown_7")

    def test_filename_collisions_fail_before_writing(self):
        for name in ("batch_1/example.png", "batch_1/EXAMPLE.jpg"):
            with self.subTest(name=name):
                coco = fixture()
                coco["images"].append({"id": 2, "file_name": name, "width": 100, "height": 200})
                with self.assertRaisesRegex(ValueError, "collision"):
                    self.run_conversion(coco)
                self.assertFalse(self.out.exists())

    def test_regeneration_preserves_images_and_refuses_stale_outputs(self):
        self.run_conversion()
        image = self.out / "images/train/batch_1__example.jpg"
        image.write_bytes(b"existing image")
        self.run_conversion()
        self.assertEqual(image.read_bytes(), b"existing image")
        stale = self.out / "labels/train/stale.txt"
        stale.write_text("unrelated label")
        before = (self.out / "conversion_report.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "stale labels"):
            self.run_conversion()
        self.assertEqual(stale.read_text(), "unrelated label")
        self.assertEqual((self.out / "conversion_report.json").read_bytes(), before)

    def test_fixed_batch_holdout(self):
        self.assertEqual(choose_split("batch_1/x.jpg"), "train")
        self.assertEqual(choose_split("batch_11/x.jpg"), "val")
        self.assertEqual(choose_split("batch_15/x.jpg"), "test")

    def test_train_only_pool_preserves_source_and_empty_holdouts(self):
        coco = fixture()
        coco["images"][0]["file_name"] = "unofficial/000000.jpg"
        coco["images"].append({"id": 2, "file_name": "batch_11/example.jpg", "width": 100, "height": 200})
        annotation = copy.deepcopy(coco["annotations"][0])
        annotation.update(id=9, image_id=2)
        coco["annotations"].append(annotation)
        summary = self.run_conversion(coco, split_policy="train_only")
        self.assertEqual(summary["split_policy"], "train_only")
        self.assertEqual(summary["split_strategy"], "train_only")
        self.assertEqual(summary["dataset_role"], "optional train-only pool")
        self.assertEqual(summary["splits"]["train"]["images"], 2)
        self.assertEqual(summary["splits"]["train"]["objects"], 2)
        self.assertEqual(summary["train_batches"], ["batch_11", "unofficial"])
        self.assertEqual(summary["val_batches"], [])
        self.assertEqual(summary["test_batches"], [])
        self.assertEqual(json.loads(self.source.read_text()), coco)
        self.assertEqual(summary["source_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())
        with (self.out / "manifests/train.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["source_file_name"] for row in rows], ["unofficial/000000.jpg", "batch_11/example.jpg"])
        self.assertEqual([row["source_annotation_indices"] for row in rows], ["0", "1"])
        self.assertTrue((self.out / "labels/train/unofficial__000000.txt").is_file())
        for split in ("val", "test"):
            self.assertEqual(summary["splits"][split], {"images": 0, "objects": 0, "natural_focus_images": 0})
            with (self.out / "manifests" / f"{split}.csv").open(newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, list(MANIFEST_FIELDS))
                self.assertEqual(list(reader), [])
            self.assertEqual(list((self.out / "labels" / split).iterdir()), [])

    def test_unofficial_folder_requires_explicit_train_only_policy(self):
        coco = fixture()
        coco["images"][0]["file_name"] = "unofficial/000000.jpg"
        with self.assertRaisesRegex(ValueError, "Unexpected TACO batch"):
            self.run_conversion(coco)
        self.assertFalse(self.out.exists())
        self.assertEqual(choose_split("unofficial/000000.jpg", "train_only"), "train")
        self.assertEqual(choose_split("batch_15/x.jpg", "train_only"), "train")

    def test_train_only_keeps_polygon_validation_and_clipping(self):
        coco = fixture()
        coco["images"][0]["file_name"] = "unofficial/000000.jpg"
        coco["annotations"][0]["segmentation"] = [[-2, 0, 99, 0, 99, 199, 0, 199]]
        with self.assertRaisesRegex(ValueError, "outside image"):
            self.run_conversion(coco, split_policy="train_only")
        self.assertFalse(self.out.exists())
        coco["annotations"][0]["segmentation"][0][0] = -1
        summary = self.run_conversion(coco, split_policy="train_only")
        self.assertEqual(summary["clipped_vertices"], 1)
        self.assertEqual(summary["annotations_with_clipped_vertices"], 1)

    def test_unknown_split_policy_fails_before_writing(self):
        with self.assertRaisesRegex(ValueError, "Unknown split policy"):
            self.run_conversion(split_policy="random")
        self.assertFalse(self.out.exists())
        with self.assertRaisesRegex(ValueError, "Unknown split policy"):
            choose_split("batch_1/x.jpg", "random")

    def test_train_only_refuses_output_with_official_holdout_labels(self):
        coco = fixture()
        coco["images"][0]["file_name"] = "batch_11/example.jpg"
        self.run_conversion(coco)
        before = (self.out / "conversion_report.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "stale labels"):
            self.run_conversion(coco, split_policy="train_only")
        self.assertEqual((self.out / "conversion_report.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
