import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from source_registry import SourceRegistry, SourceRegistryError  # noqa: E402


def write_registry(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class TestSourceRegistry(unittest.TestCase):
    def test_resolves_dataset_default_to_public_source_fields(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "sources.json"
            write_registry(
                path,
                {
                    "schema_version": 1,
                    "sources": {
                        "moi_household_registration": {
                            "name_zh": "內政部戶政司",
                            "source_url": "https://example.gov.tw/population",
                            "url_type": "dataset",
                        }
                    },
                    "dataset_defaults": {
                        "population": "moi_household_registration"
                    },
                },
            )

            registry = SourceRegistry.from_json(path)
            context = registry.resolve(dataset="population")

            self.assertEqual(context.source, "moi_household_registration")
            self.assertEqual(context.source_name, "內政部戶政司")
            self.assertEqual(context.source_url, "https://example.gov.tw/population")
            self.assertEqual(context.warnings, ())

    def test_explicit_source_url_overrides_registry_url(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "sources.json"
            write_registry(
                path,
                {
                    "schema_version": 1,
                    "sources": {
                        "source_a": {
                            "name_zh": "來源 A",
                            "source_url": "https://example.gov.tw/catalog",
                            "url_type": "dataset",
                        }
                    },
                    "dataset_defaults": {"example": "source_a"},
                },
            )

            context = SourceRegistry.from_json(path).resolve(
                dataset="example",
                source_url="https://example.gov.tw/resource.json",
            )

            self.assertEqual(context.source_url, "https://example.gov.tw/resource.json")

    def test_unknown_source_is_preserved_and_warned(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "sources.json"
            write_registry(
                path,
                {
                    "schema_version": 1,
                    "sources": {},
                    "dataset_defaults": {},
                },
            )

            context = SourceRegistry.from_json(path).resolve(
                dataset="example", source="unknown_source"
            )

            self.assertEqual(context.source, "unknown_source")
            self.assertIsNone(context.source_name)
            self.assertIsNone(context.source_url)
            self.assertIn("unknown_source_id", context.warnings)

    def test_loader_rejects_invalid_url_and_unknown_dataset_default(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "sources.json"
            write_registry(
                path,
                {
                    "schema_version": 1,
                    "sources": {
                        "source_a": {
                            "name_zh": "來源 A",
                            "source_url": "ftp://example.gov.tw/data",
                            "url_type": "dataset",
                        }
                    },
                    "dataset_defaults": {"example": "missing_source"},
                },
            )

            with self.assertRaises(SourceRegistryError):
                SourceRegistry.from_json(path)

    def test_loader_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "duplicate.json"
            path.write_text(
                '{"schema_version":1,"sources":{"source_a":{"name_zh":"A",'
                '"source_url":"https://example.gov.tw/a"},"source_a":{'
                '"name_zh":"B","source_url":"https://example.gov.tw/b"}},'
                '"dataset_defaults":{}}',
                encoding="utf-8",
            )

            with self.assertRaises(SourceRegistryError):
                SourceRegistry.from_json(path)

    def test_public_catalog_is_deterministically_sorted(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "sources.json"
            write_registry(
                path,
                {
                    "schema_version": 1,
                    "sources": {
                        "z_source": {
                            "name_zh": "Z",
                            "source_url": "https://example.gov.tw/z",
                            "url_type": "api",
                        },
                        "a_source": {
                            "name_zh": "A",
                            "source_url": "https://example.gov.tw/a",
                            "url_type": "dataset",
                        },
                    },
                    "dataset_defaults": {},
                },
            )

            catalog = SourceRegistry.from_json(path).public_catalog()

            self.assertEqual([item["source"] for item in catalog], ["a_source", "z_source"])
            self.assertEqual(catalog[0]["sourceName"], "A")
            self.assertEqual(catalog[0]["sourceUrl"], "https://example.gov.tw/a")


if __name__ == "__main__":
    unittest.main()
