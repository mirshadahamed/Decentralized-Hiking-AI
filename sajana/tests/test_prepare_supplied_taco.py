"""Supplied-data pipeline checks with tiny sources and no network or real data writes."""
from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sajana.src.data.prepare_supplied_taco import prepare
from sajana.src.data.preprocess_taco import preprocess


def image(image_id, name):
    return {"id": image_id, "file_name": name, "width": 100, "height": 100}


def annotation(annotation_id, image_id):
    return {"id": annotation_id, "image_id": image_id, "category_id": 0, "original_category_id": 7,
            "segmentation": [[0, 0, 50, 0, 50, 50, 0, 50]], "iscrowd": 0}


def sources():
    official = {"images": [image(0, "batch_1/first.jpg"), image(1, "batch_2/more_objects.jpg"),
                           image(2, "batch_3/validation.jpg"), image(3, "batch_14/test.jpg")],
                "annotations": [annotation(10, 0), annotation(11, 1), annotation(12, 1),
                                annotation(13, 2), annotation(14, 3)],
                "categories": [{"id": 0, "name": "litter"}],
                "scene_categories": [{"id": 5, "name": "Vegetation"}],
                "scene_annotations": [{"image_id": i, "background_ids": [5]} for i in range(4)]}
    unofficial = {"images": [image(i, f"unofficial/{i:06d}.jpg") for i in range(10, 14)],
                  "annotations": [annotation(20, 10), annotation(21, 11), annotation(22, 11),
                                  annotation(23, 12), annotation(24, 13)],
                  "categories": [{"id": 0, "name": "litter"}],
                  "scene_categories": [{"id": 5, "name": "Vegetation"}],
                  "scene_annotations": [{"image_id": i, "background_ids": [5]} for i in range(10, 14)]}
    unofficial["annotations"][1]["segmentation"][0][0] = -2
    unofficial["annotations"][1]["bbox"] = [float("inf"), 0, 50, 50]
    unofficial["annotations"][3]["segmentation"] = []
    return official, unofficial


class PrepareSuppliedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.interim = self.root / "data/interim/taco"
        self.interim.mkdir(parents=True)
        self.official_path = self.interim / "annotations_official_binary_litter.json"
        self.unofficial_path = self.interim / "annotations_unofficial_binary_litter.json"
        self.baseline = self.root / "data/processed/taco_litter_seg"
        self.official, self.unofficial = sources()
        self.write_sources()
        preprocess(self.official_path, self.baseline)
        self.image_paths = {}
        for split in ("train", "val", "test"):
            with (self.baseline / "manifests" / f"{split}.csv").open(newline="") as handle:
                for row in csv.DictReader(handle):
                    image_id = int(row["image_id"])
                    path = self.baseline / "images" / split / row["flat_file_name"]
                    path.write_bytes(b"same supplied image" if image_id in (0, 1) else f"distinct image {image_id}".encode())
                    self.image_paths[image_id] = path

    def write_sources(self):
        self.official_path.write_text(json.dumps(self.official), encoding="utf-8")
        self.unofficial_path.write_text(json.dumps(self.unofficial), encoding="utf-8")

    def report(self, name):
        return json.loads((self.root / "results/taco_preprocessing" / name).read_text())

    def test_prepares_clean_benchmark_and_separate_optional_pool(self):
        original_bytes = (self.official_path.read_bytes(), self.unofficial_path.read_bytes())
        status = prepare(self.root, verify_images=False)
        self.assertTrue(status["passed"])
        self.assertTrue(status["preprocessing_complete"])
        self.assertFalse(status["all_prepared_images_present"])
        self.assertEqual((status["official"]["images"], status["official"]["annotations"]), (3, 4))
        self.assertEqual((status["unofficial"]["images"], status["unofficial"]["annotations"]), (2, 2))
        self.assertFalse(status["official"]["training_ready"])
        self.assertFalse(status["unofficial"]["training_ready"])
        self.assertFalse(status["unofficial"]["training_pool_ready"])
        self.assertEqual((self.official_path.read_bytes(), self.unofficial_path.read_bytes()), original_bytes)
        self.assertEqual(status["raw_sources"][str(self.official_path.resolve())], hashlib.sha256(original_bytes[0]).hexdigest())
        cleaned = json.loads((self.interim / "annotations_official_cleaned.json").read_text())
        self.assertEqual([record["id"] for record in cleaned["images"]], [1, 2, 3])
        self.assertEqual([record["raw_source_annotation_index"] for record in cleaned["annotations"]], [1, 2, 3, 4])
        self.assertEqual([record["image_id"] for record in cleaned["scene_annotations"]], [1, 2, 3])
        optional = json.loads((self.interim / "annotations_unofficial_validated.json").read_text())
        self.assertEqual([record["id"] for record in optional["images"]], [10, 13])
        self.assertEqual([record["raw_source_annotation_index"] for record in optional["annotations"]], [0, 4])
        optional_root = Path(status["unofficial"]["dataset"])
        self.assertEqual(json.loads((optional_root / "conversion_report.json").read_text())["split_strategy"], "train_only")
        self.assertEqual(list((optional_root / "images/train").iterdir()), [])
        for split in ("val", "test"):
            with (optional_root / "manifests" / f"{split}.csv").open(newline="") as handle:
                self.assertEqual(list(csv.DictReader(handle)), [])
        self.assertFalse(status["network_used"])

    def test_exclusion_proofs_and_whole_image_quarantine(self):
        prepare(self.root, verify_images=False)
        exclusion = self.report("official_exclusions.json")
        self.assertEqual(exclusion["excluded_image_ids"], [0])
        proof = exclusion["exclusions"][0]
        self.assertEqual(proof["kept_image_id"], 1)
        self.assertEqual(proof["image_sha256"], hashlib.sha256(self.image_paths[0].read_bytes()).hexdigest())
        self.assertEqual(proof["removed_annotations"], [{"annotation_id": 10, "raw_source_annotation_index": 0}])
        quarantine = self.report("unofficial_quarantine.json")
        self.assertEqual(quarantine["quarantined_image_ids"], [11, 12])
        self.assertEqual(quarantine["invalid_annotations"], 2)
        self.assertEqual(quarantine["quarantined_annotations"], 3)
        self.assertEqual([a["annotation_id"] for a in quarantine["quarantines"][0]["excluded_annotations"]], [21, 22])
        self.assertEqual(quarantine["quarantines"][0]["invalid_annotations"][0]["raw_source_annotation_index"], 1)
        # Invalid bbox data stays in the immutable raw source, not the report.
        raw_report = (self.root / "results/taco_preprocessing/unofficial_quarantine.json").read_text()
        json.loads(raw_report, parse_constant=lambda value: self.fail(f"Nonfinite report value {value}"))

    def test_equal_object_counts_keep_lowest_image_id(self):
        self.official["annotations"] = [ann for ann in self.official["annotations"] if ann["id"] != 12]
        self.write_sources()
        status = prepare(self.root, verify_images=False)
        self.assertTrue(status["passed"])
        self.assertEqual(self.report("official_exclusions.json")["excluded_image_ids"], [1])

    def test_cross_split_duplicate_fails_before_deriving_data(self):
        self.image_paths[2].write_bytes(self.image_paths[0].read_bytes())
        before = self.official_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "across official splits"):
            prepare(self.root, verify_images=False)
        self.assertFalse((self.interim / "annotations_official_cleaned.json").exists())
        self.assertEqual(self.official_path.read_bytes(), before)

    def test_missing_source_or_image_is_explicit(self):
        with self.assertRaises(FileNotFoundError):
            prepare(self.root / "missing root", verify_images=False)
        self.image_paths[3].unlink()
        with self.assertRaisesRegex(FileNotFoundError, "supplied official image is missing"):
            prepare(self.root, verify_images=False)
        self.assertFalse((self.interim / "annotations_official_cleaned.json").exists())

    def test_image_copy_fallback_and_idempotent_regeneration(self):
        before = {image_id: path.read_bytes() for image_id, path in self.image_paths.items()}
        with patch("sajana.src.data.prepare_supplied_taco.os.link", side_effect=OSError("Cross-device link")):
            first = prepare(self.root, verify_images=False)
        self.assertEqual(first["official"]["image_import"], {"copied": 3})
        second = prepare(self.root, verify_images=False)
        self.assertEqual(second["official"]["image_import"], {"existing": 3})
        self.assertEqual({image_id: path.read_bytes() for image_id, path in self.image_paths.items()}, before)
        self.assertEqual(self.report("official_exclusions.json")["retained_images"], 3)

    def test_bad_structural_references_fail_without_silent_quarantine(self):
        self.unofficial["annotations"][0]["image_id"] = 999
        self.write_sources()
        with self.assertRaisesRegex(ValueError, "unknown image or category"):
            prepare(self.root, verify_images=False)
        self.assertFalse((self.interim / "annotations_unofficial_validated.json").exists())


if __name__ == "__main__":
    unittest.main()
