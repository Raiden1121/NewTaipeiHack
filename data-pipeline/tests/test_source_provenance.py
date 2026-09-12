import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors.contracts import CollectedPayload  # noqa: E402
from run_pipeline import _raw_and_transform_payload  # noqa: E402
from source_registry import SourceRegistry  # noqa: E402
from transform.provenance import enrich_curated_records  # noqa: E402


class TestSourceProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SourceRegistry.from_json(CONFIG_DIR / "sources.json")

    def test_generic_collector_gets_source_fields_from_dataset_default(self):
        raw_payload, records, artifacts = _raw_and_transform_payload(
            "population",
            [{"value": "1"}],
            period="11507",
            fetched_at="2026-09-12T02:00:00+00:00",
            source_registry=self.registry,
        )

        self.assertEqual(raw_payload["source"], "moi_household_registration")
        self.assertEqual(raw_payload["source_url"], "https://www.ris.gov.tw/rs-opendata/")
        self.assertEqual(raw_payload["source_url_type"], "dataset")
        self.assertEqual(records, [{"value": "1"}])
        self.assertEqual(artifacts, ())

    def test_collected_payload_metadata_source_url_overrides_registry(self):
        raw_payload, _, _ = _raw_and_transform_payload(
            "population",
            CollectedPayload(
                records=[{"value": "1"}],
                metadata={
                    "source": "moi_household_registration",
                    "source_url": "https://example.gov.tw/resource.json",
                    "source_url_type": "resource",
                },
            ),
            period="11507",
            fetched_at="2026-09-12T02:00:00+00:00",
            source_registry=self.registry,
        )

        self.assertEqual(raw_payload["source"], "moi_household_registration")
        self.assertEqual(raw_payload["source_url"], "https://example.gov.tw/resource.json")
        self.assertEqual(raw_payload["source_url_type"], "resource")

    def test_wage_metadata_source_url_is_promoted_to_raw_envelope(self):
        raw_payload, _, _ = _raw_and_transform_payload(
            "wages",
            {
                "records": [{"資料年度": "114年"}],
                "metadata": {
                    "source_url": "https://example.gov.tw/table6.xlsx",
                },
            },
            period="114",
            fetched_at="2026-09-12T02:00:00+00:00",
            source_registry=self.registry,
        )

        self.assertEqual(raw_payload["source"], "dgbas_table_6")
        self.assertEqual(
            raw_payload["source_url"], "https://example.gov.tw/table6.xlsx"
        )
        self.assertEqual(
            raw_payload["metadata"]["source_url"], raw_payload["source_url"]
        )

    def test_curated_record_source_wins_and_conflict_is_reported(self):
        records, report = enrich_curated_records(
            [{"source": "tdx", "value": 1}],
            dataset="population",
            raw_payload={
                "source": "moi_household_registration",
                "source_url": "https://example.gov.tw/population",
            },
            registry=self.registry,
        )

        self.assertEqual(records[0]["source"], "tdx")
        self.assertEqual(records[0]["source_url"], "https://example.gov.tw/population")
        self.assertIn("source_conflict", report["warnings"])
        self.assertEqual(report["resolved_sources"], ["tdx"])

    def test_legacy_record_uses_raw_or_dataset_default_without_mutating_input(self):
        raw_payload = {
            "dataset": "population",
            "period": "11507",
            "records": [{"value": 1}],
        }
        original = json.loads(json.dumps(raw_payload))

        records, report = enrich_curated_records(
            raw_payload["records"],
            dataset="population",
            raw_payload=raw_payload,
            registry=self.registry,
        )

        self.assertEqual(raw_payload, original)
        self.assertEqual(records[0]["source"], "moi_household_registration")
        self.assertEqual(records[0]["source_url"], "https://www.ris.gov.tw/rs-opendata/")
        self.assertEqual(report["unresolved_count"], 0)

    def test_unknown_source_keeps_id_and_returns_quality_warning(self):
        records, report = enrich_curated_records(
            [{"source": "not_in_registry", "value": 1}],
            dataset="population",
            raw_payload={},
            registry=self.registry,
        )

        self.assertEqual(records[0]["source"], "not_in_registry")
        self.assertIsNone(records[0]["source_url"])
        self.assertIn("unknown_source_id", report["warnings"])
        self.assertEqual(report["unresolved_count"], 1)


if __name__ == "__main__":
    unittest.main()
