import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.published_snapshot import publish_homepage_snapshot  # noqa: E402
from source_registry import SourceRegistry  # noqa: E402


class TestPublishedSourceCatalog(unittest.TestCase):
    def test_manifest_contains_source_catalog_and_dataset_source_refs(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "sources.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "sources": {
                            "source_a": {
                                "name_zh": "來源 A",
                                "source_url": "https://example.gov.tw/a",
                                "url_type": "dataset",
                            },
                            "source_b": {
                                "name_zh": "來源 B",
                                "source_url": "https://example.gov.tw/b",
                                "url_type": "api",
                            },
                        },
                        "dataset_defaults": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            registry = SourceRegistry.from_json(config_path)
            homepage = {
                "metric_id": "homepage",
                "generated_at": "2026-09-12T02:00:00+00:00",
                "districts": [],
            }
            analysis = {
                "metric_id": "derived",
                "generated_at": "2026-09-12T02:00:00+00:00",
                "districts": [],
            }

            result = publish_homepage_snapshot(
                homepage,
                output_dir=tempdir,
                snapshot_id="source-catalog",
                analyses={"derived": analysis},
                source_catalog=registry.public_catalog(),
                source_refs_by_dataset={
                    "homepage": ["source_a"],
                    "derived": ["source_a", "source_b"],
                },
            )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["sources"][0]["source"], "source_a")
            self.assertEqual(manifest["sources"][0]["sourceName"], "來源 A")
            self.assertEqual(manifest["sources"][0]["sourceUrl"], "https://example.gov.tw/a")
            homepage_entry = next(
                item for item in manifest["datasets"] if item["dataset"] == "homepage"
            )
            derived_entry = next(
                item for item in manifest["datasets"] if item["dataset"] == "derived"
            )
            self.assertEqual(homepage_entry["sources"], ["source_a"])
            self.assertEqual(derived_entry["sources"], ["source_a", "source_b"])

    def test_published_snapshot_keeps_current_pointer_atomic_with_source_catalog(self):
        with tempfile.TemporaryDirectory() as tempdir:
            homepage = {
                "metric_id": "homepage",
                "generated_at": "2026-09-12T02:00:00+00:00",
                "districts": [],
            }
            publish_homepage_snapshot(
                homepage,
                output_dir=tempdir,
                snapshot_id="current-release",
                source_catalog=[],
            )
            candidate = publish_homepage_snapshot(
                homepage,
                output_dir=tempdir,
                snapshot_id="candidate-release",
                source_catalog=[],
                update_current=False,
            )

            current = json.loads(
                (Path(tempdir) / "analytics" / "published" / "current.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(current, {"snapshot_id": "current-release"})
            self.assertTrue(candidate.manifest_path.is_file())


if __name__ == "__main__":
    unittest.main()
