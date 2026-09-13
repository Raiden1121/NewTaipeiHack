"""Read-side routing and reshaping in modules/api/lambda/handler.py.

DynamoDB is replaced by an in-memory table, so this runs without AWS:

    python -m unittest discover infrastructure/modules/api/tests

Lives outside lambda/ so it is not zipped into the deployed function.
"""

import json
import os
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path

LAMBDA_DIR = Path(__file__).resolve().parents[1] / "lambda"
TABLE_NAME = "test-analytics"


class FakeDynamoDB:
    def __init__(self):
        self.items = {}

    def put(self, pk, sk, **fields):
        self.items[(pk, sk)] = {"pk": pk, "sk": sk, **fields}

    def batch_get_item(self, RequestItems):
        keys = RequestItems[TABLE_NAME]["Keys"]
        found = [self.items[(k["pk"], k["sk"])] for k in keys if (k["pk"], k["sk"]) in self.items]
        return {"Responses": {TABLE_NAME: found}}


FAKE_DYNAMODB = FakeDynamoDB()
os.environ["ANALYTICS_TABLE_NAME"] = TABLE_NAME
fake_boto3 = types.ModuleType("boto3")
fake_boto3.resource = lambda _service: FAKE_DYNAMODB
sys.modules["boto3"] = fake_boto3
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))

import handler  # noqa: E402


def get(path):
    response = handler.handler(
        {"requestContext": {"http": {"method": "GET"}}, "rawPath": path},
        types.SimpleNamespace(aws_request_id="test-request"),
    )
    return response["statusCode"], json.loads(response["body"])


class TestApiHandler(unittest.TestCase):
    def setUp(self):
        FAKE_DYNAMODB.items.clear()
        FAKE_DYNAMODB.put("META", "MANIFEST", snapshot_id="test-snapshot", generated_at="2026-09-13T00:00:00Z")
        FAKE_DYNAMODB.put(
            "DASHBOARD",
            "POLICY",
            currentBudget=Decimal("196153"),
            budgetTrend=[],
            executionRate=Decimal("93.2"),
            executionRateYearRoc=Decimal("114"),
            executionFailure=None,
        )

    def test_youth_topic_weight_alias_returns_the_canonical_keyword_item(self):
        FAKE_DYNAMODB.put(
            "ANALYSIS#youth-keyword-frequency",
            "DATA",
            analysis_id="youth-keyword-frequency",
            period_scope="all_available",
            keywords=[{"term": "就業", "weight": Decimal("5")}],
        )

        alias_status, alias_body = get("/api/v1/analyses/youth-topic-weight")
        canonical_status, canonical_body = get("/api/v1/analyses/youth-keyword-frequency")

        self.assertEqual(alias_status, 200)
        self.assertEqual(canonical_status, 200)
        self.assertEqual(alias_body["data"], canonical_body["data"])
        self.assertEqual(alias_body["data"]["analysis_id"], "youth-keyword-frequency")
        self.assertNotIn("topics", alias_body["data"])
        self.assertNotIn("year_roc", alias_body["data"])

    def test_politics_resource_io_carries_the_execution_rate_year(self):
        FAKE_DYNAMODB.put(
            "ANALYSIS#politics-resource-io", "DATA", analysis_id="politics-resource-io", budget_by_department=[]
        )

        status, body = get("/api/v1/analyses/politics-resource-io")

        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["executionRate"], 93.2)
        self.assertEqual(body["data"]["executionRateYearRoc"], 114)

    def test_policy_outcomes_reads_the_pipeline_population_shape(self):
        FAKE_DYNAMODB.put("ANALYSIS#policy-outcomes", "DATA", analysis_id="policy-outcomes", wageTrend=[])
        FAKE_DYNAMODB.put(
            "DASHBOARD",
            "POPULATION_TREND",
            years=[
                {"year_roc": Decimal("113"), "city": {"youth_18_35_total": Decimal("862933"), "people_total": Decimal("4047001")}},
                {"year_roc": Decimal("114"), "city": {"youth_18_35_total": Decimal("845938"), "people_total": Decimal("4044831")}},
            ],
        )

        status, body = get("/api/v1/analyses/policy-outcomes")

        self.assertEqual(status, 200)
        self.assertEqual(
            body["data"]["populationTrend"],
            [
                {"year_roc": 113, "population": 862933, "yoy": None},
                {"year_roc": 114, "population": 845938, "yoy": -1.97},
            ],
        )

    def test_policy_outcomes_still_accepts_the_seed_data_shape_and_missing_values(self):
        FAKE_DYNAMODB.put("ANALYSIS#policy-outcomes", "DATA", analysis_id="policy-outcomes")
        FAKE_DYNAMODB.put(
            "DASHBOARD",
            "POPULATION_TREND",
            years=[
                {"year_roc": Decimal("112"), "city": {"youth_population": Decimal("100")}},
                {"year_roc": Decimal("113"), "city": {"youth_18_35_total": None}},
                {"year_roc": Decimal("114"), "city": {"youth_population": Decimal("110")}},
            ],
        )

        status, body = get("/api/v1/analyses/policy-outcomes")

        self.assertEqual(status, 200)
        self.assertEqual(
            [row["yoy"] for row in body["data"]["populationTrend"]],
            [None, None, None],
        )
        self.assertEqual(body["data"]["populationTrend"][0]["population"], 100)

    def test_unknown_analysis_is_still_404(self):
        status, body = get("/api/v1/analyses/not-a-real-analysis")

        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "ANALYSIS_NOT_FOUND")

    def test_dashboard_overview_returns_the_projected_kpis_unchanged(self):
        FAKE_DYNAMODB.put(
            "DASHBOARD",
            "KPIS",
            kpis={"nationalYouthPopulation": Decimal("4979852"), "nationalYouthPopulationQuality": "observed"},
            availability={},
        )

        status, body = get("/api/v1/dashboard/overview")

        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["kpis"]["nationalYouthPopulation"], 4979852)
        self.assertEqual(body["data"]["kpis"]["nationalYouthPopulationQuality"], "observed")
        self.assertEqual(body["data"]["policy"]["executionRateYearRoc"], 114)


if __name__ == "__main__":
    unittest.main()
