import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_DIR = PROJECT_DIR / "data-pipeline" / "config"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.published_snapshot import publish_homepage_snapshot  # noqa: E402
from collectors.contracts import CollectedPayload  # noqa: E402
from publish.dynamo_projection import project_snapshot_items  # noqa: E402
from run_pipeline import _raw_and_transform_payload  # noqa: E402
from source_registry import SourceRegistry  # noqa: E402
from transform.io import write_raw  # noqa: E402
from transform.provenance import enrich_curated_records  # noqa: E402


class TestSourceProvenanceEndToEnd(unittest.TestCase):
    def test_legacy_new_published_and_dynamo_contracts_share_source_metadata(self):
        registry = SourceRegistry.from_json(CONFIG_DIR / "sources.json")
        legacy_record = {"value": 100}

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            legacy_raw = write_raw(
                {
                    "dataset": "population",
                    "period": "11507",
                    "fetched_at": "2026-09-12T02:00:00+00:00",
                    "records": [legacy_record],
                },
                dataset="population",
                snapshot="legacy",
                output_dir=root / "data",
            )
            legacy_hash = hashlib.sha256(legacy_raw.read_bytes()).hexdigest()

            new_raw, _, _ = _raw_and_transform_payload(
                "population",
                CollectedPayload(records=[legacy_record], metadata={}),
                period="11507",
                fetched_at="2026-09-12T02:00:00+00:00",
                source_registry=registry,
            )
            enriched, resolution = enrich_curated_records(
                [legacy_record],
                dataset="population",
                raw_payload={"dataset": "population", "records": [legacy_record]},
                registry=registry,
            )
            self.assertEqual(new_raw["source"], "moi_household_registration")
            self.assertEqual(new_raw["source_url_type"], "dataset")
            self.assertEqual(enriched[0]["source"], "moi_household_registration")
            self.assertEqual(resolution["unresolved_count"], 0)

            published = publish_homepage_snapshot(
                {
                    "metric_id": "homepage",
                    "generated_at": "2026-09-12T02:00:00+00:00",
                    "districts": [
                        {
                            "district_id": "65000010",
                            "district_name": "板橋區",
                            "population": 100,
                        }
                    ],
                },
                output_dir=root / "data",
                snapshot_id="e2e-source",
                source_catalog=registry.public_catalog(),
                source_refs_by_dataset={
                    "homepage": ["moi_household_registration"]
                },
            )
            manifest = json.loads(published.manifest_path.read_text(encoding="utf-8"))
            items = project_snapshot_items(published.snapshot_dir, manifest)

            district_item = next(
                item
                for item in items
                if item["resource"] == "district_details"
            )
            metric = district_item["metrics"]["population"]
            self.assertEqual(metric["source"], "moi_household_registration")
            self.assertEqual(metric["sourceName"], "內政部戶政司")
            self.assertEqual(metric["sourceUrl"], "https://www.ris.gov.tw/rs-opendata/")
            self.assertEqual(
                hashlib.sha256(legacy_raw.read_bytes()).hexdigest(), legacy_hash
            )

            for path in (root / "data" / "analytics" / "published" / "e2e-source").rglob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotIn("raw_records", json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
