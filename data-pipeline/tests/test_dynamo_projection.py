import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from publish.dynamo_projection import (  # noqa: E402
    project_metric_source,
    project_snapshot_items,
)


SOURCE_CATALOG = [
    {
        "source": "moi_household_registration",
        "sourceName": "內政部戶政司",
        "sourceUrl": "https://example.gov.tw/population",
        "urlType": "dataset",
    },
    {
        "source": "taiwanjobs",
        "sourceName": "台灣就業通",
        "sourceUrl": "https://example.gov.tw/jobs",
        "urlType": "api",
    },
]


class TestDynamoProjection(unittest.TestCase):
    def test_projects_direct_metric_source_fields_without_changing_value(self):
        metric = {
            "value": 100,
            "source": "moi_household_registration",
        }

        projected = project_metric_source(metric, SOURCE_CATALOG)

        self.assertEqual(projected["value"], 100)
        self.assertEqual(projected["source"], "moi_household_registration")
        self.assertEqual(projected["sourceName"], "內政部戶政司")
        self.assertEqual(projected["sourceUrl"], "https://example.gov.tw/population")
        self.assertEqual(projected["sourceRefs"], [])

    def test_projects_multi_source_metric_without_selecting_one_url(self):
        projected = project_metric_source(
            {"value": 42, "sourceRefs": ["taiwanjobs", "moi_household_registration"]},
            SOURCE_CATALOG,
        )

        self.assertIsNone(projected["source"])
        self.assertIsNone(projected["sourceName"])
        self.assertIsNone(projected["sourceUrl"])
        self.assertEqual(
            projected["sourceRefs"], ["moi_household_registration", "taiwanjobs"]
        )

    def test_projects_district_details_with_existing_snapshot_keys(self):
        with tempfile.TemporaryDirectory() as tempdir:
            snapshot_dir = Path(tempdir) / "fixture"
            snapshot_dir.mkdir()
            (snapshot_dir / "district_details.json").write_text(
                json.dumps(
                    {
                        "districts": [
                            {
                                "district_id": "65000010",
                                "district_name": "板橋區",
                                "metrics": {
                                    "population": {
                                        "value": 100,
                                        "source": "moi_household_registration",
                                    }
                                },
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest = {
                "snapshot_id": "fixture",
                "artifacts": {
                    "dashboard_overview": "dashboard_overview.json",
                    "district_details": "district_details.json",
                    "analyses": {},
                },
                "sources": SOURCE_CATALOG,
                "datasets": [
                    {
                        "dataset": "district_details",
                        "sources": ["moi_household_registration"],
                    }
                ],
            }

            items = project_snapshot_items(snapshot_dir, manifest)

            self.assertEqual(len(items), 1)
            self.assertEqual(
                items[0]["PK"],
                "SNAPSHOT#fixture#RESOURCE#district_details",
            )
            self.assertEqual(items[0]["SK"], "DISTRICT#65000010")
            metric = items[0]["metrics"]["population"]
            self.assertEqual(metric["source"], "moi_household_registration")
            self.assertEqual(metric["sourceName"], "內政部戶政司")
            self.assertEqual(metric["sourceUrl"], "https://example.gov.tw/population")


if __name__ == "__main__":
    unittest.main()
