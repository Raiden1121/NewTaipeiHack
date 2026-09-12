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
    def test_projects_participation_budget_allocation_to_api_department_shape(self):
        with tempfile.TemporaryDirectory() as tempdir:
            snapshot_dir = Path(tempdir) / "fixture"
            (snapshot_dir / "analyses").mkdir(parents=True)
            (snapshot_dir / "analyses" / "participation.json").write_text(
                json.dumps(
                    {
                        "budget_allocation": {
                            "budget_year_roc": 116,
                            "document_status": "proposed_budget",
                            "total_amount": 159521000,
                            "unit": "TWD",
                            "items": [
                                {
                                    "code": "01",
                                    "name": "綜合規劃業務",
                                    "amount": 38960000,
                                    "share_percent": 24.42,
                                },
                                {
                                    "code": "04",
                                    "name": "青年業務設施",
                                    "amount": 11852000,
                                    "share_percent": 7.43,
                                },
                            ],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest = {
                "snapshot_id": "fixture",
                "artifacts": {
                    "analyses": {"participation": "analyses/participation.json"}
                },
                "sources": [],
                "datasets": [],
            }

            items = project_snapshot_items(snapshot_dir, manifest)

            self.assertEqual(
                items,
                [
                    {
                        "PK": "SNAPSHOT#fixture#ANALYSIS#politics-resource-io",
                        "SK": "DATA",
                        "snapshot_id": "fixture",
                        "analysis_id": "politics-resource-io",
                        "budget_by_department": [
                            {
                                "label": "綜合規劃業務",
                                "amount_thousand": 38960,
                                "share_percent": 24.42,
                            },
                            {
                                "label": "青年業務設施",
                                "amount_thousand": 11852,
                                "share_percent": 7.43,
                            },
                        ],
                        "budget_year_roc": 116,
                        "document_status": "proposed_budget",
                        "sourceRefs": [],
                    }
                ],
            )

    def test_projects_missing_budget_allocation_as_empty_department_list(self):
        with tempfile.TemporaryDirectory() as tempdir:
            snapshot_dir = Path(tempdir) / "fixture"
            (snapshot_dir / "analyses").mkdir(parents=True)
            (snapshot_dir / "analyses" / "participation.json").write_text(
                json.dumps({"budget": {"status": "observed"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            manifest = {
                "snapshot_id": "fixture",
                "artifacts": {
                    "analyses": {"participation": "analyses/participation.json"}
                },
                "sources": [],
                "datasets": [],
            }

            items = project_snapshot_items(snapshot_dir, manifest)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["analysis_id"], "politics-resource-io")
            self.assertEqual(items[0]["budget_by_department"], [])

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
