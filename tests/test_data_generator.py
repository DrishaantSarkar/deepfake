"""Tests for the multimodal synthetic test dataset generator and manifest integrity."""

import json
from pathlib import Path
import unittest

from tests.fixtures.multimodal.generate_fixtures import (
    FIXTURE_DIR,
    MANIFEST_PATH,
    compute_sha256,
    generate_all_fixtures,
    verify_fixtures,
)


class TestDataGenerator(unittest.TestCase):
    def setUp(self):
        self.manifest_path = MANIFEST_PATH
        self.fixtures_dir = FIXTURE_DIR

    def test_manifest_file_exists(self):
        self.assertTrue(self.manifest_path.exists(), "Multimodal fixture manifest.json must exist")

    def test_manifest_entries_and_schema(self):
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        manifest = manifest_data.get("samples", manifest_data)
        self.assertIsInstance(manifest, list)
        self.assertEqual(len(manifest), 16, "Must contain exactly 16 documented multimodal fixtures")

        sample_ids = set()
        required_keys = {
            "sample_id",
            "modality",
            "ground_truth",
            "provenance",
            "generation_method",
            "transformations",
            "sha256",
            "expected_test_behavior",
        }

        modalities = {"image": 0, "video": 0, "audio": 0}
        ground_truths = {"real": 0, "synthetic": 0}

        for entry in manifest:
            # Schema integrity
            for key in required_keys:
                self.assertIn(key, entry, f"Missing key '{key}' in manifest entry {entry.get('sample_id')}")

            # No duplicate sample IDs
            sid = entry["sample_id"]
            self.assertNotIn(sid, sample_ids, f"Duplicate sample ID found: {sid}")
            sample_ids.add(sid)

            # Modality validation
            mod = entry["modality"]
            self.assertIn(mod, modalities)
            modalities[mod] += 1

            # Ground truth validation
            gt = entry["ground_truth"]
            self.assertIn(gt, ground_truths)
            ground_truths[gt] += 1

            # File existence and checksum match
            rel_path = entry.get("relative_path")
            self.assertIsNotNone(rel_path)
            full_path = self.manifest_path.parent / rel_path
            self.assertTrue(full_path.exists(), f"Fixture file {full_path} must exist on disk")

            actual_hash = compute_sha256(full_path)
            expected_hash = entry.get("sha256") or entry.get("file_hash")
            self.assertEqual(
                actual_hash,
                expected_hash,
                f"Hash mismatch for {sid}: expected {expected_hash}, got {actual_hash}",
            )

        # Balanced collection
        self.assertEqual(modalities["image"], 8)
        self.assertEqual(modalities["video"], 4)
        self.assertEqual(modalities["audio"], 4)
        self.assertEqual(ground_truths["real"], 8)
        self.assertEqual(ground_truths["synthetic"], 8)

    def test_verify_fixtures_function_passes(self):
        all_passed, mismatches = verify_fixtures(self.manifest_path)
        self.assertTrue(all_passed, f"verify_fixtures failed with mismatches: {mismatches}")
        self.assertEqual(len(mismatches), 0)

    def test_reproducibility_with_fixed_seed(self):
        # Verify that generating again with seed 42 produces identical hashes
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_manifest = generate_all_fixtures(output_dir=tmp_path, seed=42)

            with open(self.manifest_path, "r", encoding="utf-8") as f:
                original_manifest = json.load(f)

            orig_entries = original_manifest.get("samples", original_manifest)
            new_entries = tmp_manifest.get("samples", tmp_manifest)

            orig_hashes = {e["sample_id"]: (e.get("sha256") or e.get("file_hash")) for e in orig_entries}
            new_hashes = {e["sample_id"]: (e.get("sha256") or e.get("file_hash")) for e in new_entries}

            self.assertEqual(
                orig_hashes,
                new_hashes,
                "Regenerating fixtures with seed=42 must produce identical SHA-256 hashes",
            )

    def test_detection_of_corrupted_fixture(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            manifest = generate_all_fixtures(output_dir=tmp_path, seed=42)
            manifest_file = tmp_path / "manifest.json"

            # Corrupt one file
            entries = manifest.get("samples", manifest)
            first_entry = entries[0]
            corrupt_target = tmp_path / first_entry["relative_path"]
            with open(corrupt_target, "ab") as f:
                f.write(b"CORRUPTION_BYTES")

            all_passed, mismatches = verify_fixtures(manifest_file)
            self.assertFalse(all_passed, "Corrupted fixture must fail verification")
            self.assertEqual(len(mismatches), 1)
            self.assertEqual(mismatches[0]["sample_id"], first_entry["sample_id"])



if __name__ == "__main__":
    unittest.main()
